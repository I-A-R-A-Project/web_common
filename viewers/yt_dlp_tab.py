"""Pestaña de reproducción y descarga para URLs reconocidas por yt-dlp."""

import os
import re
import threading
from pathlib import Path

from PyQt6.QtCore import QThread, QTimer, QUrl, QStandardPaths, pyqtSignal
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
)

from .video_tab import VideoTab
from .yt_dlp_cache import (
    get_cache_path_for_download,
    get_cached_video_path,
)
from .yt_dlp_ffmpeg import (
    FfmpegStream,
    find_ffmpeg,
    get_best_audio_input,
    get_media_inputs,
    is_audio_only_format,
)


_ACTIVE_WORKERS = set()
_EXTRACTOR_CLASSES = None
_EXTRACTOR_LOCK = threading.Lock()


def _extractor_classes():
    global _EXTRACTOR_CLASSES
    if _EXTRACTOR_CLASSES is None:
        with _EXTRACTOR_LOCK:
            if _EXTRACTOR_CLASSES is None:
                from yt_dlp.extractor import gen_extractor_classes

                _EXTRACTOR_CLASSES = tuple(gen_extractor_classes())
    return _EXTRACTOR_CLASSES


def is_supported_video_url(url):
    """Return true if a site-specific yt-dlp extractor matches an HTTP URL."""
    value = url.toString() if hasattr(url, "toString") else str(url or "")
    if not value.lower().startswith(("http://", "https://")):
        return False
    try:
        return any(
            extractor.suitable(value)
            and str(getattr(extractor, "IE_NAME", "") or "").lower() != "generic"
            for extractor in _extractor_classes()
        )
    except ImportError:
        return False


def _safe_filename(title, extension):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(title or "")).strip(" .")
    extension = re.sub(r"[^A-Za-z0-9]", "", str(extension or "mp4"))
    return f"{name or 'video'}.{extension or 'mp4'}"


class _YtDlpWorker(QThread):
    result_ready = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(object)

    def __init__(self, url, *, output_template=None, ffmpeg_location=None, cache_enabled=True):
        super().__init__()
        self.url = url
        self.output_template = output_template
        self.ffmpeg_location = ffmpeg_location
        self.cache_enabled = cache_enabled

    def run(self):
        try:
            from yt_dlp import YoutubeDL

            cache_path = None
            if not self.output_template and self.cache_enabled:
                cache_path = get_cached_video_path(self.url)
                if cache_path:
                    info = {"url": str(cache_path), "_cached": True}
                    self.result_ready.emit(info)
                    return

            if not self.output_template and self.cache_enabled:
                cache_path = get_cache_path_for_download(self.url)

            options = self._options(cache_path)
            try:
                info = self._extract(YoutubeDL, options, cache_download=bool(cache_path))
            except Exception as exc:
                if "requested format is not available" not in str(exc).lower():
                    raise
                fallback_options = dict(options, format="best")
                info = self._extract(YoutubeDL, fallback_options, cache_download=bool(cache_path))
            if not self.output_template:
                info = self._ensure_audio(YoutubeDL, info)
            self.result_ready.emit(info)
        except Exception as exc:
            message = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", str(exc))
            self.failed.emit(message or exc.__class__.__name__)

    def _options(self, cache_path=None):
        options = {
            "quiet": True,
            "no_warnings": True,
            "no_color": True,
            "noplaylist": True,
            "format": "bestvideo+bestaudio/best",
        }
        if self.output_template:
            options["outtmpl"] = self.output_template
            options["progress_hooks"] = [self._on_progress]
            options["ffmpeg_location"] = self.ffmpeg_location
            options["merge_output_format"] = "mkv"
            options["postprocessors"] = [
                {
                    "key": "FFmpegVideoRemuxer",
                    "preferedformat": "mkv",
                }
            ]
        elif cache_path is not None:
            options["outtmpl"] = str(cache_path.parent / cache_path.stem)
            options["progress_hooks"] = [self._on_progress]
            options["ffmpeg_location"] = self.ffmpeg_location
            options["merge_output_format"] = "mkv"
            options["postprocessors"] = [
                {
                    "key": "FFmpegVideoRemuxer",
                    "preferedformat": "mkv",
                }
            ]
            options["continue_dl"] = True
        return options

    def _ensure_audio(self, downloader_class, info):
        media_inputs = get_media_inputs(info, require_audio=False)
        if any(is_audio_only_format(media_format) for media_format in media_inputs):
            return info

        audio_options = self._options()
        audio_options["format"] = "bestaudio"
        audio_info = self._extract(downloader_class, audio_options)
        audio = get_best_audio_input(audio_info)
        if audio is None:
            raise ValueError(
                "yt-dlp no devolvió una pista de audio al solicitar bestaudio."
            )

        result = dict(info)
        result["requested_formats"] = media_inputs + [audio]
        result["formats"] = []
        return result

    def _extract(self, downloader_class, options, cache_download=False):
        with downloader_class(options) as ydl:
            info = ydl.extract_info(
                self.url,
                download=bool(self.output_template or cache_download),
            )
        if not isinstance(info, dict):
            raise ValueError("yt-dlp no devolvió información del video.")
        return info

    def _on_progress(self, data):
        if self.isInterruptionRequested():
            from yt_dlp.utils import DownloadError

            raise DownloadError("Download cancelled because video tab closed.")
        if data.get("status") == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            self.progress.emit((int(data.get("downloaded_bytes") or 0), int(total)))


class YtDlpVideoTab(VideoTab):
    """Reproduce y descargar un video resuelto por yt-dlp."""

    title_changed = pyqtSignal(str)

    def __init__(self, url, main_window=None):
        super().__init__(None, main_window, autoplay=False)
        self.source_url = url
        self._media_formats = None
        self._video_title = "Video"
        self._ffmpeg_location = find_ffmpeg()
        self._worker = None
        self._ffmpeg_stream = None
        self._download_in_progress = False
        self._stream_check_timer = QTimer(self)
        self._stream_check_timer.setInterval(1000)
        self._stream_check_timer.timeout.connect(self._check_ffmpeg_stream)

        self.download_button = QPushButton("Descargar video")
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self._choose_download_path)
        self.status_label = QLabel("Buscando formatos compatibles...")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.hide()

        controls = QHBoxLayout()
        controls.addWidget(self.download_button)
        controls.addWidget(self.status_label, 1)
        controls.addWidget(self.progress_bar)
        self.layout().insertLayout(1, controls)

        self._started = False

    def start(self):
        if self._started:
            return
        self._started = True
        self._start_worker(_YtDlpWorker(self.source_url))

    def title(self):
        return self._video_title

    def url(self):
        return QUrl(self.source_url)

    def _start_worker(self, worker):
        self._worker = worker
        _ACTIVE_WORKERS.add(worker)
        worker.finished.connect(lambda current=worker: _ACTIVE_WORKERS.discard(current))
        worker.result_ready.connect(self._on_result)
        worker.failed.connect(self._on_failure)
        worker.progress.connect(self._on_progress)
        worker.start()

    def _on_result(self, info):
        self._video_title = str(info.get("title") or "Video")
        self.title_changed.emit(self._video_title)
        
        if self._worker and self._worker.output_template:
            self._download_in_progress = False
            self.progress_bar.hide()
            self.download_button.setEnabled(True)
            self.status_label.setText("Descarga completada.")
            self._show_status("Descarga de video MKV completada.")
            return
        
        if info.get("_cached"):
            cached_path = info.get("url")
            self._download_in_progress = False
            self.progress_bar.hide()
            self.status_label.setText("Reproduciendo desde caché...")
            self.set_stream_url(cached_path)
            self.download_button.setEnabled(True)
            return

        try:
            self._media_formats = get_media_inputs(info)
        except ValueError as exc:
            self._on_failure(str(exc))
            return

        if not any(
            media_format.get("vcodec") not in (None, "none")
            for media_format in self._media_formats
        ):
            self._on_failure("yt-dlp no encontró una pista de video reproducible.")
            return

        self.download_button.setEnabled(self._ffmpeg_location is not None)
        if self._ffmpeg_location is None:
            self._on_failure(
                "No se encontró FFmpeg. Instala FFmpeg y agrégalo al PATH, o "
                "define FFMPEG_LOCATION con la ruta a ffmpeg.exe."
            )
            return
        try:
            self._ffmpeg_stream = FfmpegStream(
                self._ffmpeg_location,
                self._media_formats,
            )
            stream_url = self._ffmpeg_stream.start()
        except (OSError, ValueError) as exc:
            self._on_failure(f"No se pudo iniciar FFmpeg: {exc}")
            return
        self.status_label.setText("Reproduciendo stream en MKV...")
        self.set_stream_url(stream_url)
        self._stream_check_timer.start()

    def _on_failure(self, message):
        self._download_in_progress = False
        self.status_label.setText("No se pudo reproducir o descargar el video.")
        self.download_button.setEnabled(
            self._ffmpeg_location is not None
            and self._media_formats is not None
            and not self._download_in_progress
        )
        self.progress_bar.hide()
        self._show_status(message)
        QMessageBox.warning(
            self,
            "yt-dlp",
            f"No se pudo obtener, reproducir o descargar este video:\n{message}",
        )

    def _choose_download_path(self):
        if self._media_formats is None:
            return
        if self._ffmpeg_location is None:
            QMessageBox.warning(
                self,
                "FFmpeg requerido",
                "Instala FFmpeg y agrégalo al PATH, o define FFMPEG_LOCATION "
                "con la ruta a ffmpeg.exe para descargar videos en MKV.",
            )
            return
        default_name = _safe_filename(self._video_title, "mkv")
        download_dir = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DownloadLocation
        )
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar video",
            str(Path(download_dir or Path.home()) / default_name),
            "Video Matroska (*.mkv);;Todos los archivos (*.*)",
        )
        if not destination:
            return

        selected = Path(destination)
        parent = str(selected.parent).replace("%", "%%")
        stem = selected.stem.replace("%", "%%")
        template = os.path.join(parent, f"{stem}.%(ext)s")
        self.download_button.setEnabled(False)
        self._download_in_progress = True
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.status_label.setText("Descargando...")
        self._start_worker(
            _YtDlpWorker(
                self.source_url,
                output_template=template,
                ffmpeg_location=self._ffmpeg_location,
            )
        )

    def _check_ffmpeg_stream(self):
        if self._ffmpeg_stream is None or self._ffmpeg_stream.is_running():
            return
        self._stream_check_timer.stop()
        message = self._ffmpeg_stream.error_message()
        return_code = self._ffmpeg_stream.return_code()
        self._ffmpeg_stream.stop()
        self._ffmpeg_stream = None
        if self.player.error() != QMediaPlayer.Error.NoError:
            return
        if return_code == 0:
            self.status_label.setText("Reproducción finalizada.")
            return
        self.status_label.setText(f"FFmpeg cerró el stream: {message}")
        self._show_status(f"FFmpeg cerró el stream: {message}")

    def _on_progress(self, progress):
        downloaded, total = progress
        if total > 0:
            self.progress_bar.setValue(min(100, int(downloaded * 100 / total)))
            self.status_label.setText(
                f"Descargando... {downloaded * 100 // total}%"
            )
        else:
            self.status_label.setText(f"Descargados {downloaded} bytes...")

    def _show_status(self, message):
        status_bar = getattr(self.main_window, "statusBar", None)
        if callable(status_bar):
            status_bar().showMessage(message, 10000)

    def stop(self):
        self._stream_check_timer.stop()
        if self._ffmpeg_stream is not None:
            self._ffmpeg_stream.stop()
            self._ffmpeg_stream = None
        if self._worker is not None and self._worker.isRunning():
            self._worker.requestInterruption()
        super().stop()

    def _on_error(self, error, error_string):
        if error != QMediaPlayer.Error.NoError:
            self._stream_check_timer.stop()
            if self._ffmpeg_stream is not None:
                self._ffmpeg_stream.stop()
                self._ffmpeg_stream = None
            self.status_label.setText(
                f"Formato no compatible con Qt Multimedia: {error_string}"
            )
        super()._on_error(error, error_string)


def open_yt_dlp_tab(tabs, url, main_window, plus_widget=None):
    """Open dedicated yt-dlp tab before optional trailing plus tab."""
    tab = YtDlpVideoTab(url, main_window)
    insert_at = tabs.indexOf(plus_widget) if plus_widget is not None else tabs.count()
    if insert_at < 0:
        insert_at = tabs.count()
    index = tabs.insertTab(insert_at, tab, "yt-dlp")
    tabs.setCurrentIndex(index)
    tab.title_changed.connect(
        lambda title, video_tab=tab: tabs.setTabText(
            tabs.indexOf(video_tab), title[:30]
        )
        if tabs.indexOf(video_tab) >= 0
        else None
    )
    tab.start()
    return tab
