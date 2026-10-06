"""FFmpeg helpers for yt-dlp playback and MKV downloads."""

import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def find_ffmpeg():
    """Find FFmpeg from configuration, PATH, or beside the running app."""
    configured = os.environ.get("FFMPEG_LOCATION", "").strip().strip('"')
    candidates = []
    if configured:
        configured_path = Path(configured).expanduser()
        if configured_path.is_dir():
            candidates.extend(
                (configured_path / "ffmpeg.exe", configured_path / "ffmpeg")
            )
        else:
            candidates.append(configured_path)

    for name in ("ffmpeg.exe", "ffmpeg"):
        located = shutil.which(name)
        if located:
            candidates.append(Path(located))

    roots = {
        Path(sys.executable).resolve().parent,
        Path(sys.argv[0]).resolve().parent,
        Path.cwd(),
    }
    for root in roots:
        candidates.extend((root / "ffmpeg.exe", root / "ffmpeg"))

    for candidate in candidates:
        try:
            if candidate.is_file():
                return str(candidate.resolve())
        except OSError:
            continue
    return None


def is_audio_only_format(media_format):
    if media_format.get("acodec") not in (None, "none"):
        return True
    return (
        media_format.get("vcodec") == "none"
        and "audio only" in str(media_format.get("format") or "").lower()
    )


def get_media_inputs(info, *, require_audio=True):
    """Return selected formats, adding best available audio when missing."""
    requested = info.get("requested_formats")
    formats = requested if isinstance(requested, list) and requested else (
        [info] if info.get("url") else info.get("formats", [])
    )
    playable = [
        media_format
        for media_format in formats
        if isinstance(media_format, dict) and media_format.get("url")
    ]
    if not playable:
        raise ValueError("yt-dlp no devolvió URLs de formatos de video.")
    playable = sorted(
        playable,
        key=lambda media_format: (
            0 if media_format.get("vcodec") not in (None, "none") else 1
        ),
    )
    has_audio = any(
        is_audio_only_format(media_format)
        for media_format in playable
    )
    if not has_audio:
        audio = get_best_audio_input(info)
        if audio is not None and audio not in playable:
            playable.append(audio)

    if require_audio and not any(
        is_audio_only_format(media_format)
        for media_format in playable
    ):
        raise ValueError(
            "yt-dlp encontró video, pero no encontró una pista de audio "
            "disponible para reproducir."
        )
    return playable


def get_best_audio_input(info):
    """Return highest-quality URL for an audio-only yt-dlp format."""
    requested = info.get("requested_formats")
    formats = requested if isinstance(requested, list) and requested else (
        ([info] if info.get("url") else []) + info.get("formats", [])
    )
    audio_formats = [
        media_format
        for media_format in formats
        if isinstance(media_format, dict)
        and media_format.get("url")
        and media_format.get("vcodec") in (None, "none")
        and is_audio_only_format(media_format)
    ]
    if not audio_formats:
        return None

    def quality(media_format):
        values = []
        for key in ("abr", "tbr", "filesize", "filesize_approx"):
            try:
                values.append(float(media_format.get(key) or 0))
            except (TypeError, ValueError):
                values.append(0)
        return tuple(values)

    return max(audio_formats, key=quality)


def _format_headers(headers):
    if not isinstance(headers, dict):
        return ""
    lines = []
    for name, value in headers.items():
        name = str(name).replace("\r", "").replace("\n", "")
        value = str(value).replace("\r", "").replace("\n", "")
        if name and value:
            lines.append(f"{name}: {value}")
    return "\r\n".join(lines) + ("\r\n" if lines else "")


def build_ffmpeg_command(executable, formats):
    """Build a low-latency H.264/AAC Matroska stream for Qt Multimedia."""
    formats = list(formats)
    if not formats:
        raise ValueError("No hay formatos seleccionados para reproducir.")
    if not any(
        is_audio_only_format(media_format)
        for media_format in formats
    ):
        raise ValueError("No hay una pista de audio para incluir en el stream.")
    command = [
        str(executable),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-fflags",
        "+genpts",
    ]
    for media_format in formats:
        headers = _format_headers(media_format.get("http_headers"))
        if headers:
            command.extend(("-headers", headers))
        command.extend(("-i", str(media_format["url"])))

    command.extend(("-map", "0:v:0?"))
    for index, media_format in enumerate(formats):
        if is_audio_only_format(media_format):
            command.extend(("-map", f"{index}:a:0?"))
    command.extend(
        (
            "-c",
            "libx264",
            "-preset",
            "ultrafast",
            "-tune",
            "zerolatency",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-flush_packets",
            "1",
            "-f",
            "matroska",
            "-live",
            "1",
            "-cluster_time_limit",
            "1000",
            "-cluster_size_limit",
            "1048576",
            "pipe:1",
        )
    )
    return command


class FfmpegStream:
    """Serve FFmpeg's live Matroska stdout over local chunked HTTP."""

    def __init__(self, executable, formats):
        self._process = None
        self._stderr = bytearray()
        self._stderr_lock = threading.Lock()
        self._server = None
        self._server_thread = None
        self._stderr_thread = None
        self._closed = False
        self._command = build_ffmpeg_command(executable, formats)

    def start(self):
        stream = self

        class StreamHandler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):
                if self.path != "/stream":
                    self.send_error(404)
                    return
                if stream._process is None or stream._process.poll() is not None:
                    self.send_error(503, stream.error_message())
                    return
                self.send_response(200)
                self.send_header("Content-Type", "video/x-matroska")
                self.send_header("Transfer-Encoding", "chunked")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                try:
                    while not stream._closed:
                        chunk = stream._process.stdout.read1(64 * 1024)
                        if not chunk:
                            break
                        self.wfile.write(f"{len(chunk):X}\r\n".encode("ascii"))
                        self.wfile.write(chunk)
                        self.wfile.write(b"\r\n")
                        self.wfile.flush()
                    self.wfile.write(b"0\r\n\r\n")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    stream.stop()

            def log_message(self, _format, *_args):
                return

        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._process = subprocess.Popen(
            self._command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
        self._stderr_thread = threading.Thread(
            target=self._read_stderr,
            name="yt-dlp-ffmpeg-stderr",
            daemon=True,
        )
        self._stderr_thread.start()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), StreamHandler)
        self._server.daemon_threads = True
        self._server_thread = threading.Thread(
            target=self._server.serve_forever,
            name="yt-dlp-ffmpeg-http",
            daemon=True,
        )
        self._server_thread.start()
        address, port = self._server.server_address
        return f"http://{address}:{port}/stream"

    def _read_stderr(self):
        while self._process is not None and self._process.stderr is not None:
            chunk = self._process.stderr.read(4096)
            if not chunk:
                return
            with self._stderr_lock:
                self._stderr.extend(chunk)
                if len(self._stderr) > 16_384:
                    del self._stderr[:-16_384]

    def error_message(self):
        if (
            self._process is not None
            and self._process.poll() is not None
            and self._stderr_thread is not None
        ):
            self._stderr_thread.join(timeout=0.2)
        with self._stderr_lock:
            output = self._stderr.decode("utf-8", errors="replace").strip()
        return output or "FFmpeg terminó el stream inesperadamente."

    def is_running(self):
        return self._process is not None and self._process.poll() is None

    def return_code(self):
        return self._process.poll() if self._process is not None else None

    def stop(self):
        if self._closed:
            return
        self._closed = True
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if process is not None:
            if self._stderr_thread is not None:
                self._stderr_thread.join(timeout=0.5)
            for pipe in (process.stdout, process.stderr):
                if pipe is not None:
                    pipe.close()
