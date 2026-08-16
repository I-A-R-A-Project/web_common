import os

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)


def _format_time(ms):
    if ms < 0:
        ms = 0
    total_seconds = ms // 1000
    h, rem = divmod(total_seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


class VideoTab(QWidget):
    def __init__(self, path, main_window=None):
        super().__init__()
        self.main_window = main_window
        self._path = os.path.abspath(path)
        self._qurl = QUrl.fromLocalFile(self._path)
        self._duration = 0
        self._seeking = False

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)

        self.video_widget = QVideoWidget(self)
        self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.video_widget.setStyleSheet("background-color: black;")
        self.player.setVideoOutput(self.video_widget)

        self.player.errorOccurred.connect(self._on_error)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)

        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedWidth(36)
        self.play_btn.setToolTip("Reproducir / Pausar (espacio)")
        self.play_btn.clicked.connect(self._toggle_play)

        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setStyleSheet("color:#bdc1c6; font-size:12px;")

        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.sliderPressed.connect(self._on_seek_start)
        self.seek_slider.sliderReleased.connect(self._on_seek_end)
        self.seek_slider.sliderMoved.connect(self._on_seek_move)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setFixedWidth(90)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.audio_output.setVolume(0.8)
        self.volume_slider.valueChanged.connect(lambda v: self.audio_output.setVolume(v / 100))

        controls = QHBoxLayout()
        controls.setContentsMargins(8, 4, 8, 6)
        controls.addWidget(self.play_btn)
        controls.addWidget(self.seek_slider, 1)
        controls.addWidget(self.time_label)
        controls.addSpacing(10)
        controls.addWidget(QLabel("Vol"))
        controls.addWidget(self.volume_slider)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.video_widget, 1)
        layout.addLayout(controls)
        self.setStyleSheet("background-color:#202124;")

        self.player.setSource(self._qurl)
        self.player.play()

    def url(self):
        return self._qurl

    def title(self):
        return os.path.basename(self._path)

    def setUrl(self, qurl):
        pass

    def back(self):
        pass

    def forward(self):
        pass

    def reload(self):
        self.player.setSource(self._qurl)
        self.player.play()

    def zoomFactor(self):
        return 1.0

    def setZoomFactor(self, factor):
        pass

    def stop(self):
        self.player.stop()

    def _toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _on_playback_state_changed(self, state):
        self.play_btn.setText("Pause" if state == QMediaPlayer.PlaybackState.PlayingState else "Play")

    def _on_duration_changed(self, duration):
        self._duration = duration
        self.seek_slider.setRange(0, duration)
        self._update_time_label(self.player.position())

    def _on_position_changed(self, position):
        if not self._seeking:
            self.seek_slider.setValue(position)
        self._update_time_label(position)

    def _update_time_label(self, position):
        self.time_label.setText(f"{_format_time(position)} / {_format_time(self._duration)}")

    def _on_seek_start(self):
        self._seeking = True

    def _on_seek_end(self):
        self._seeking = False
        self.player.setPosition(self.seek_slider.value())

    def _on_seek_move(self, value):
        self._update_time_label(value)

    def _on_error(self, error, error_string):
        if error == QMediaPlayer.Error.NoError or not self.main_window:
            return
        self.main_window.statusBar().showMessage(
            f"Error al reproducir video: {error_string}", 8000
        )

