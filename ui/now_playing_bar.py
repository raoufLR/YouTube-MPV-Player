import contextlib

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QStyle,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from core.events import (
    EVENT_PLAYBACK_ERROR,
    EVENT_VIDEO_PAUSED,
    EVENT_VIDEO_STARTED,
    EVENT_VIDEO_STOPPED,
)
from ui import icons
from ui.event_dispatcher import QtEventDispatcher
from ui.i18n import tr
from ui.thumbnail_pixmaps import cached_pixmap, pixmap_loader, request_pixmap

_PROGRESS_INTERVAL_MS = 500
_BAR_HEIGHT = 64
_THUMBNAIL_SIZE = 48


def format_time(seconds) -> str:
    """Format a number of seconds as ``m:ss`` or ``h:mm:ss``."""
    try:
        total = int(max(0.0, float(seconds)))
    except (TypeError, ValueError):
        return "0:00"
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


class SeekSlider(QSlider):
    """Seek slider that previews the target time while hovering."""

    def mouseMoveEvent(self, event):
        if self.isEnabled() and self.maximum() > 0:
            value = QStyle.sliderValueFromPosition(
                self.minimum(),
                self.maximum(),
                int(event.position().x()),
                max(1, self.width()),
            )
            QToolTip.showText(
                event.globalPosition().toPoint(), format_time(value), self
            )
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)


class NowPlayingBar(QWidget):
    open_in_mpv = pyqtSignal()
    show_video_requested = pyqtSignal()
    fullscreen_requested = pyqtSignal()

    def __init__(
        self,
        event_bus,
        player_service,
        thumbnail_service,
        parent=None,
        playback_service=None,
    ):
        super().__init__(parent)
        self._event_bus = event_bus
        self._player_service = player_service
        self._thumbnail_service = thumbnail_service
        self._playback_service = playback_service

        self._current_title = ""
        self._current_channel = ""
        self._current_thumbnail = ""
        self._is_playing = False
        self._is_paused = False
        self._duration = 0.0
        self._seeking = False
        self._muted_volume = 80
        self._subscriptions = []

        self.setObjectName("nowPlayingBar")
        self.setFixedHeight(_BAR_HEIGHT)
        self.hide()

        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(_PROGRESS_INTERVAL_MS)
        self._progress_timer.timeout.connect(self._refresh_progress)

        self._setup_ui()
        self._connect_events()
        pixmap_loader().pixmap_ready.connect(self._on_pixmap_ready)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        self._thumbnail = QLabel()
        self._thumbnail.setObjectName("nowPlayingThumb")
        self._thumbnail.setFixedSize(48, 48)
        self._thumbnail.setScaledContents(True)
        self._thumbnail.setCursor(Qt.CursorShape.PointingHandCursor)
        self._thumbnail.setToolTip(tr("Show video in player"))
        self._thumbnail.setAccessibleName(tr("Show video in player"))
        self._thumbnail.mousePressEvent = lambda e: self.show_video_requested.emit()
        layout.addWidget(self._thumbnail)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(0)

        self._title_label = QLabel(tr("No video playing"))
        self._title_label.setObjectName("nowPlayingTitle")
        self._title_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._title_label.setToolTip(tr("Show video in player"))
        self._title_label.mousePressEvent = lambda e: self.show_video_requested.emit()
        text_layout.addWidget(self._title_label)

        self._channel_label = QLabel("")
        self._channel_label.setObjectName("nowPlayingChannel")
        text_layout.addWidget(self._channel_label)

        layout.addLayout(text_layout, 1)

        self._play_btn = QPushButton()
        self._play_btn.setIcon(icons.play(22))
        self._play_btn.setObjectName("nowPlayingBtn")
        self._play_btn.setToolTip(tr("Play"))
        self._play_btn.setAccessibleName(tr("Play"))
        self._play_btn.setFixedSize(36, 36)
        self._play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._play_btn.clicked.connect(self._toggle_play)
        layout.addWidget(self._play_btn)

        self._stop_btn = QPushButton()
        self._stop_btn.setIcon(icons.stop(18))
        self._stop_btn.setObjectName("nowPlayingBtn")
        self._stop_btn.setToolTip(tr("Stop"))
        self._stop_btn.setAccessibleName(tr("Stop"))
        self._stop_btn.setFixedSize(32, 32)
        self._stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_btn.clicked.connect(self._stop_playback)
        layout.addWidget(self._stop_btn)

        self._volume_btn = QPushButton()
        self._volume_btn.setIcon(icons.volume(18))
        self._volume_btn.setObjectName("nowPlayingBtn")
        self._volume_btn.setToolTip(tr("Mute"))
        self._volume_btn.setAccessibleName(tr("Mute"))
        self._volume_btn.setFixedSize(32, 32)
        self._volume_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._volume_btn.clicked.connect(self._toggle_mute)
        layout.addWidget(self._volume_btn)

        self._volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setFixedWidth(80)
        self._volume_slider.setToolTip(tr("Volume"))
        self._volume_slider.setAccessibleName(tr("Volume"))
        self._volume_slider.valueChanged.connect(self._on_volume)
        layout.addWidget(self._volume_slider)
        self._sync_volume_controls()

        # Seek slider for embedded MPV
        seek_layout = QHBoxLayout()
        seek_layout.setSpacing(4)
        self._time_label = QLabel("0:00")
        self._time_label.setObjectName("nowPlayingTime")
        self._time_label.setFixedWidth(45)
        seek_layout.addWidget(self._time_label)

        self._seek_slider = SeekSlider(Qt.Orientation.Horizontal)
        self._seek_slider.setRange(0, 0)
        self._seek_slider.setSingleStep(5)
        self._seek_slider.setPageStep(30)
        self._seek_slider.setFixedHeight(14)
        self._seek_slider.setEnabled(False)
        self._seek_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self._seek_slider.setAccessibleName(tr("Seek"))
        self._seek_slider.sliderPressed.connect(self._seek_pressed)
        self._seek_slider.sliderMoved.connect(self._seek_moved)
        self._seek_slider.sliderReleased.connect(self._seek_released)
        seek_layout.addWidget(self._seek_slider, 1)

        self._duration_label = QLabel("0:00")
        self._duration_label.setObjectName("nowPlayingTime")
        self._duration_label.setFixedWidth(45)
        seek_layout.addWidget(self._duration_label)
        layout.addLayout(seek_layout)

        self._open_btn = QPushButton(tr("Restart"))
        self._open_btn.setObjectName("primaryButton")
        self._open_btn.setFixedHeight(32)
        self._open_btn.setToolTip(tr("Re-resolve and restart the current video"))
        self._open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_btn.clicked.connect(self.open_in_mpv.emit)
        layout.addWidget(self._open_btn)

        self._view_btn = QPushButton()
        self._view_btn.setIcon(icons.expand(18))
        self._view_btn.setObjectName("nowPlayingBtn")
        self._view_btn.setToolTip(tr("View video in player"))
        self._view_btn.setAccessibleName(tr("View video in player"))
        self._view_btn.setFixedSize(32, 32)
        self._view_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._view_btn.clicked.connect(self.show_video_requested.emit)
        layout.addWidget(self._view_btn)

        self._fullscreen_btn = QPushButton()
        self._fullscreen_btn.setIcon(icons.fullscreen(18))
        self._fullscreen_btn.setObjectName("nowPlayingBtn")
        self._fullscreen_btn.setToolTip(tr("Toggle Fullscreen (F11 / F)"))
        self._fullscreen_btn.setAccessibleName(tr("Toggle Fullscreen"))
        self._fullscreen_btn.setFixedSize(32, 32)
        self._fullscreen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fullscreen_btn.clicked.connect(self.fullscreen_requested.emit)
        layout.addWidget(self._fullscreen_btn)

        self.setLayout(layout)

    def _connect_events(self):
        if not self._event_bus:
            return
        self._subscriptions = [
            (EVENT_VIDEO_STARTED, QtEventDispatcher(self._on_video_started)),
            (EVENT_VIDEO_PAUSED, QtEventDispatcher(self._on_video_paused)),
            (EVENT_VIDEO_STOPPED, QtEventDispatcher(self._on_video_stopped)),
            (EVENT_PLAYBACK_ERROR, QtEventDispatcher(self._on_playback_error)),
        ]
        for event_type, callback in self._subscriptions:
            self._event_bus.subscribe(event_type, callback, weak=False)

    def cleanup(self):
        for event_type, callback in self._subscriptions:
            self._event_bus.unsubscribe(event_type, callback)
        self._subscriptions = []
        self._progress_timer.stop()
        with contextlib.suppress(TypeError, RuntimeError):
            pixmap_loader().pixmap_ready.disconnect(self._on_pixmap_ready)

    # ------------------------------------------------------------------
    # State updates
    # ------------------------------------------------------------------

    def _on_video_started(self, event):
        self._current_title = event.title or tr("Unknown")
        self._current_channel = event.channel or ""
        self._current_thumbnail = event.thumbnail or ""
        self._is_playing = True
        self._is_paused = False
        self._duration = 0.0
        self._seeking = False

        self._title_label.setText(self._current_title)
        self._channel_label.setText(self._current_channel)
        self._time_label.setText("0:00")
        self._duration_label.setText("0:00")
        self._seek_slider.setRange(0, 0)
        self._seek_slider.setValue(0)
        self._seek_slider.setEnabled(False)
        self._update_play_button()
        self._sync_volume_controls()
        self._load_thumbnail()
        self.show()
        self._progress_timer.start()

    def _on_video_paused(self, event):
        self._is_paused = bool(getattr(event, "is_paused", True))
        self._update_play_button()

    def _on_video_stopped(self, event=None):
        self.clear()

    def _on_playback_error(self, event=None):
        # Keep the current track visible: a failed *next* request does not
        # interrupt whatever is still playing.  Errors are surfaced by the
        # status bar.
        pass

    def _update_play_button(self):
        if self._is_paused:
            self._play_btn.setIcon(icons.play(22))
            self._play_btn.setToolTip(tr("Resume"))
            self._play_btn.setAccessibleName(tr("Resume"))
        else:
            self._play_btn.setIcon(icons.pause(22))
            self._play_btn.setToolTip(tr("Pause"))
            self._play_btn.setAccessibleName(tr("Pause"))

    def _load_thumbnail(self):
        if not self._current_thumbnail or self._thumbnail_service is None:
            return
        try:
            data = self._thumbnail_service.load_thumbnail_data(self._current_thumbnail)
        except Exception:
            return
        if not data:
            return
        pixmap = request_pixmap(
            self._current_thumbnail, data, _THUMBNAIL_SIZE, _THUMBNAIL_SIZE
        )
        if pixmap is not None:
            self._thumbnail.setPixmap(pixmap)

    def _on_pixmap_ready(self, url: str, width: int, height: int):
        if (
            url != self._current_thumbnail
            or (width, height) != (_THUMBNAIL_SIZE, _THUMBNAIL_SIZE)
        ):
            return
        pixmap = cached_pixmap(url, width, height)
        if pixmap is not None:
            self._thumbnail.setPixmap(pixmap)

    # ------------------------------------------------------------------
    # Progress / seeking
    # ------------------------------------------------------------------

    def _refresh_progress(self):
        service = self._player_service
        if service is None:
            return
        has_media = getattr(service, "has_media", False)
        if not has_media:
            self._progress_timer.stop()
            return

        duration = float(getattr(service, "get_duration", lambda: 0.0)() or 0.0)
        position = float(getattr(service, "get_position", lambda: 0.0)() or 0.0)
        if duration > 0:
            self._duration = duration
            maximum = int(duration)
            if self._seek_slider.maximum() != maximum:
                self._seek_slider.setRange(0, maximum)
            self._seek_slider.setEnabled(True)
        if not self._seeking and self._seek_slider.isEnabled():
            self._seek_slider.setValue(int(position))
            self._time_label.setText(format_time(position))
        if self._duration > 0:
            self._duration_label.setText(format_time(self._duration))

    def _seek_pressed(self):
        self._seeking = True

    def _seek_moved(self, value):
        self._seeking = True
        self._time_label.setText(format_time(value))

    def _seek_released(self):
        self._seeking = False
        value = float(self._seek_slider.value())
        service = self._player_service
        if service is None:
            return
        with contextlib.suppress(Exception):
            service.seek_absolute(value)
        self._time_label.setText(format_time(value))

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    def _toggle_play(self):
        service = self._player_service
        if service is None:
            return
        with contextlib.suppress(Exception):
            service.pause_resume()

    def _stop_playback(self):
        try:
            if self._playback_service is not None:
                self._playback_service.stop()
            elif self._player_service is not None:
                self._player_service.stop()
        except Exception:
            pass

    def _on_volume(self, value):
        if self._player_service is None:
            return
        with contextlib.suppress(Exception):
            self._player_service.set_volume(int(value))
        if value > 0:
            self._muted_volume = int(value)
        self._sync_volume_controls()

    def _toggle_mute(self):
        if self._player_service is None:
            return
        current = int(getattr(self._player_service, "get_volume", lambda: 0)() or 0)
        target = self._muted_volume if current == 0 else 0
        if target == 0:
            self._muted_volume = current
        self._volume_slider.setValue(int(target))

    def _sync_volume_controls(self):
        if self._player_service is None:
            return
        try:
            volume = int(self._player_service.get_volume())
        except Exception:
            return
        self._volume_slider.blockSignals(True)
        self._volume_slider.setValue(max(0, min(100, volume)))
        self._volume_slider.blockSignals(False)
        if volume == 0:
            self._volume_btn.setIcon(icons.mute(18))
            self._volume_btn.setToolTip(tr("Unmute"))
            self._volume_btn.setAccessibleName(tr("Unmute"))
        else:
            self._volume_btn.setIcon(icons.volume(18))
            self._volume_btn.setToolTip(tr("Mute"))
            self._volume_btn.setAccessibleName(tr("Mute"))
            self._muted_volume = volume

    def clear(self):
        self._progress_timer.stop()
        self.hide()
        self._is_playing = False
        self._is_paused = False
        self._seeking = False
        self._duration = 0.0
        self._current_title = ""
        self._current_channel = ""
        self._current_thumbnail = ""
        self._title_label.setText(tr("No video playing"))
        self._channel_label.setText("")
        self._time_label.setText("0:00")
        self._duration_label.setText("0:00")
        self._seek_slider.setRange(0, 0)
        self._seek_slider.setValue(0)
        self._seek_slider.setEnabled(False)
        self._thumbnail.clear()
