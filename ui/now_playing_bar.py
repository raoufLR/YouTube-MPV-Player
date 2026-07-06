from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QSlider,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap

from ui import icons
from core.events import (
    EVENT_VIDEO_STARTED, EVENT_PLAYBACK_ERROR,
    EVENT_THUMBNAIL_LOADED,
)
from ui.event_dispatcher import QtEventDispatcher


class NowPlayingBar(QWidget):
    open_in_mpv = pyqtSignal()

    def __init__(self, event_bus, player_service, thumbnail_service, parent=None):
        super().__init__(parent)
        self._event_bus = event_bus
        self._player_service = player_service
        self._thumbnail_service = thumbnail_service

        self._current_title = ""
        self._current_channel = ""
        self._current_thumbnail = ""
        self._is_playing = False

        self.setObjectName("nowPlayingBar")
        self.setFixedHeight(64)
        self.hide()

        self._setup_ui()
        self._connect_events()

    def _setup_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        self._thumbnail = QLabel()
        self._thumbnail.setFixedSize(48, 48)
        self._thumbnail.setScaledContents(True)
        self._thumbnail.setStyleSheet("background-color: #303134; border-radius: 6px;")
        layout.addWidget(self._thumbnail)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(0)

        self._title_label = QLabel("No video playing")
        self._title_label.setObjectName("nowPlayingTitle")
        text_layout.addWidget(self._title_label)

        self._channel_label = QLabel("")
        self._channel_label.setObjectName("nowPlayingChannel")
        text_layout.addWidget(self._channel_label)

        layout.addLayout(text_layout, 1)

        self._play_btn = QPushButton()
        self._play_btn.setIcon(icons.play(22))
        self._play_btn.setObjectName("nowPlayingBtn")
        self._play_btn.setToolTip("Play/Pause")
        self._play_btn.setFixedSize(40, 40)
        self._play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._play_btn.clicked.connect(self._toggle_play)
        layout.addWidget(self._play_btn)

        self._volume_btn = QPushButton()
        self._volume_btn.setIcon(icons.liked_videos(18))
        self._volume_btn.setObjectName("nowPlayingBtn")
        self._volume_btn.setToolTip("Volume")
        self._volume_btn.setFixedSize(32, 32)
        self._volume_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self._volume_btn)

        self._volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(80)
        self._volume_slider.setFixedWidth(80)
        self._volume_slider.setToolTip("Volume")
        self._volume_slider.valueChanged.connect(self._on_volume)
        layout.addWidget(self._volume_slider)

        self._open_btn = QPushButton("Open in MPV")
        self._open_btn.setObjectName("primaryButton")
        self._open_btn.setFixedHeight(32)
        self._open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_btn.clicked.connect(self.open_in_mpv.emit)
        layout.addWidget(self._open_btn)

        self.setLayout(layout)

    def _connect_events(self):
        if self._event_bus:
            self._event_bus.subscribe(EVENT_VIDEO_STARTED, QtEventDispatcher(self._on_video_started), weak=False)

    def _on_video_started(self, event):
        self._current_title = event.title or "Unknown"
        self._current_channel = event.channel or ""
        self._current_thumbnail = event.thumbnail or ""
        self._is_playing = True

        self._title_label.setText(self._current_title)
        self._channel_label.setText(self._current_channel)
        self._play_btn.setIcon(icons.play(22))

        if self._current_thumbnail:
            data = self._thumbnail_service.load_thumbnail_data(self._current_thumbnail)
            if data:
                pixmap = QPixmap()
                pixmap.loadFromData(data)
                if not pixmap.isNull():
                    self._thumbnail.setPixmap(pixmap.scaled(
                        48, 48, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation
                    ))

        self.show()

    def _toggle_play(self):
        try:
            self._player_service.pause_resume()
        except Exception:
            pass

    def _on_volume(self, val):
        try:
            self._player_service.set_volume(val)
        except Exception:
            pass

    def clear(self):
        self.hide()
        self._current_title = ""
        self._current_channel = ""
        self._current_thumbnail = ""
        self._thumbnail.clear()
