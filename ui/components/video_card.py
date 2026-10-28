from typing import TYPE_CHECKING

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui import icons
from ui.i18n import tr

if TYPE_CHECKING:
    from PyQt6.QtGui import QPixmap


def extract_video_id(video_data) -> str:
    """Return the video id used by every video container in the app.

    Search results use ``videoId`` while likes, history and playlist entries
    use ``video_id``.  Both must be accepted or sourced videos silently fail
    to play or resolve their state.
    """
    if not isinstance(video_data, dict):
        return ""
    for key in ("videoId", "video_id", "id"):
        value = video_data.get(key)
        if value:
            return str(value)
    return ""


class VideoCard(QWidget):
    play_requested = pyqtSignal(str, str, object)
    like_toggled = pyqtSignal(object)
    watch_later_toggled = pyqtSignal(object)

    THUMBNAIL_WIDTH = 260
    THUMBNAIL_HEIGHT = 146
    CARD_WIDTH = 260

    def __init__(self, video_data: dict, parent=None):
        super().__init__(parent)
        self._video_data = video_data if isinstance(video_data, dict) else {}
        self._video_id = extract_video_id(self._video_data)
        self._title = self._video_data.get("title", tr("Unknown"))
        self._channel = self._video_data.get("channel", "")
        self._thumbnail_url = self._video_data.get("thumbnail", "")
        self._duration = self._video_data.get("duration", "")
        self._views = self._video_data.get("views", "")
        self._upload_date = self._video_data.get(
            "uploadDate", self._video_data.get("upload_date", "")
        )
        self._is_liked = False
        self._is_watch_later = False
        self._is_resolving = False
        self._is_playing = False

        self._pixmap: QPixmap = None
        # The drop shadow is created on first hover: a graphics effect forces
        # Qt to render the widget through an offscreen buffer, so attaching
        # one to every card makes scrolling more expensive for no benefit
        # while the pointer is elsewhere.
        self._shadow = None
        self._anim = None

        self.setObjectName("videoCard")
        self.setFixedWidth(self.CARD_WIDTH)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        thumb_container = QWidget()
        thumb_container.setFixedSize(self.THUMBNAIL_WIDTH, self.THUMBNAIL_HEIGHT)
        thumb_layout = QVBoxLayout(thumb_container)
        thumb_layout.setContentsMargins(0, 0, 0, 0)

        self._thumbnail_label = QLabel()
        self._thumbnail_label.setObjectName("videoCardThumb")
        self._thumbnail_label.setFixedSize(self.THUMBNAIL_WIDTH, self.THUMBNAIL_HEIGHT)
        self._thumbnail_label.setScaledContents(True)
        thumb_layout.addWidget(self._thumbnail_label)

        if self._duration:
            dur_label = QLabel(self._duration)
            dur_label.setObjectName("duration")
            dur_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
            dur_label.setFixedHeight(20)
            thumb_layout.addWidget(dur_label, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

        layout.addWidget(thumb_container)

        # Overlay badge shown while a stream is resolving or the video plays.
        self._status_label = QLabel(thumb_container)
        self._status_label.setObjectName("cardStatus")
        self._status_label.move(8, 8)
        self._status_label.hide()

        self._info_container = QWidget()
        info_layout = QVBoxLayout(self._info_container)
        info_layout.setContentsMargins(4, 8, 4, 2)
        info_layout.setSpacing(2)

        title_label = QLabel(self._title)
        title_label.setObjectName("videoCardTitle")
        title_label.setWordWrap(False)
        title_label.setMaximumHeight(38)
        title_label.setToolTip(self._title)
        info_layout.addWidget(title_label)

        subtitle_parts = []
        if self._channel:
            subtitle_parts.append(self._channel)
        if self._views:
            subtitle_parts.append(self._views)
        if self._upload_date:
            subtitle_parts.append(self._upload_date)

        if subtitle_parts:
            sub = QLabel(" \u2022 ".join(subtitle_parts))
            sub.setObjectName("videoCardMeta")
            sub.setToolTip(self._title)
            info_layout.addWidget(sub)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 4, 0, 0)
        btn_row.setSpacing(2)

        self._play_btn = QPushButton()
        self._play_btn.setIcon(icons.play(20))
        self._play_btn.setObjectName("nowPlayingBtn")
        self._play_btn.setToolTip(tr("Play video"))
        self._play_btn.setAccessibleName(tr("Play video"))
        self._play_btn.setFixedSize(36, 36)
        self._play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._play_btn.clicked.connect(self._on_play)
        btn_row.addWidget(self._play_btn)

        self._like_btn = QPushButton()
        self._like_btn.setIcon(icons.like(20))
        self._like_btn.setObjectName("nowPlayingBtn")
        self._like_btn.setToolTip(tr("Like"))
        self._like_btn.setAccessibleName(tr("Like"))
        self._like_btn.setFixedSize(36, 36)
        self._like_btn.setCheckable(True)
        self._like_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._like_btn.clicked.connect(self._on_like)
        btn_row.addWidget(self._like_btn)

        self._wl_btn = QPushButton()
        self._wl_btn.setIcon(icons.watch_later_add(20))
        self._wl_btn.setObjectName("nowPlayingBtn")
        self._wl_btn.setToolTip(tr("Watch Later"))
        self._wl_btn.setAccessibleName(tr("Watch Later"))
        self._wl_btn.setFixedSize(36, 36)
        self._wl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._wl_btn.clicked.connect(self._on_watch_later)
        btn_row.addWidget(self._wl_btn)

        self._more_btn = QPushButton()
        self._more_btn.setIcon(icons.more_vert(20))
        self._more_btn.setObjectName("nowPlayingBtn")
        self._more_btn.setToolTip(tr("More options"))
        self._more_btn.setAccessibleName(tr("More options"))
        self._more_btn.setFixedSize(36, 36)
        self._more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._more_btn.clicked.connect(self._on_context_menu)
        btn_row.addWidget(self._more_btn)

        btn_row.addStretch()
        info_layout.addLayout(btn_row)

        layout.addWidget(self._info_container)
        self.setLayout(layout)

    def _setup_hover_effect(self):
        """Create the hover shadow on first use.

        Kept as a method (not inline in ``enterEvent``) so tests and future
        callers can force the effect to exist.
        """
        if self._shadow is not None:
            return
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(0)
        shadow.setOffset(0, 0)
        shadow.setColor(Qt.GlobalColor.transparent)
        self.setGraphicsEffect(shadow)

        anim = QPropertyAnimation(shadow, b"blurRadius", self)
        anim.setDuration(200)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(self._on_hover_animation_finished)

        self._shadow = shadow
        self._anim = anim

    def _on_hover_animation_finished(self):
        # Let the event loop settle before tearing the effect down: deleting
        # the effect from inside its animation's ``finished`` signal would
        # destroy the sender mid-emit.
        if self._shadow is not None and self._shadow.blurRadius() <= 0.0:
            QTimer.singleShot(0, self._release_hover_effect)

    def _release_hover_effect(self):
        """Detach the shadow when idle so the card paints directly again."""
        if self._shadow is None or self.underMouse():
            return
        try:
            if self._shadow.blurRadius() > 0.0:
                return
        except RuntimeError:
            self._shadow = None
            self._anim = None
            return
        anim = self._anim
        self._anim = None
        self._shadow = None
        try:
            if anim is not None:
                anim.stop()
                anim.deleteLater()
            self.setGraphicsEffect(None)
        except RuntimeError:
            # The card was destroyed while the deferred release was queued.
            pass

    def enterEvent(self, event):
        self._setup_hover_effect()
        self._anim.stop()
        self._anim.setStartValue(self._shadow.blurRadius())
        self._anim.setEndValue(16)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._shadow is not None and self._anim is not None:
            self._anim.stop()
            self._anim.setStartValue(self._shadow.blurRadius())
            self._anim.setEndValue(0)
            self._anim.start()
        super().leaveEvent(event)

    def set_thumbnail(self, pixmap: QPixmap):
        if pixmap and not pixmap.isNull():
            if (pixmap.width(), pixmap.height()) != (self.THUMBNAIL_WIDTH, self.THUMBNAIL_HEIGHT):
                pixmap = pixmap.scaled(
                    self.THUMBNAIL_WIDTH, self.THUMBNAIL_HEIGHT,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                )
            self._pixmap = pixmap
            self._thumbnail_label.setPixmap(pixmap)

    def set_liked(self, liked: bool):
        liked = bool(liked)
        if liked == self._is_liked:
            return
        self._is_liked = liked
        self._like_btn.setChecked(self._is_liked)
        self._like_btn.setIcon(icons.liked(20) if self._is_liked else icons.like(20))
        self._like_btn.setToolTip(tr("Unlike") if self._is_liked else tr("Like"))
        self._like_btn.setAccessibleName(
            tr("Unlike") if self._is_liked else tr("Like")
        )

    def set_watch_later(self, enabled: bool):
        enabled = bool(enabled)
        if enabled == self._is_watch_later:
            return
        self._is_watch_later = enabled
        self._wl_btn.setIcon(
            icons.watch_later(20) if self._is_watch_later
            else icons.watch_later_add(20)
        )
        self._wl_btn.setToolTip(
            tr("Remove from Watch Later") if self._is_watch_later else tr("Watch Later")
        )
        self._wl_btn.setAccessibleName(
            tr("Remove from Watch Later") if self._is_watch_later else tr("Watch Later")
        )

    def set_playback_state(self, resolving: bool = False, playing: bool = False):
        """Show a small badge while resolving or playing this video."""
        self._is_resolving = bool(resolving)
        self._is_playing = bool(playing)
        if self._is_playing:
            self._status_label.setText("\u25B6 " + tr("Playing"))
        elif self._is_resolving:
            self._status_label.setText(tr("Resolving..."))
        else:
            self._status_label.hide()
            return
        self._status_label.adjustSize()
        self._status_label.show()
        self._status_label.raise_()

    def video_id(self) -> str:
        return self._video_id

    def video_data(self) -> dict:
        return self._video_data

    def is_liked(self) -> bool:
        return self._is_liked

    def is_watch_later(self) -> bool:
        return self._is_watch_later

    def _on_play(self):
        self.play_requested.emit(self._video_id, "", self._video_data)

    def _on_like(self):
        self.set_liked(not self._is_liked)
        self.like_toggled.emit(self._video_data)

    def _on_watch_later(self):
        self.set_watch_later(not self._is_watch_later)
        self.watch_later_toggled.emit(self._video_data)

    def _on_context_menu(self):
        menu = QMenu(self)
        play_action = menu.addAction(icons.play(18), tr("Play"))
        menu.addSeparator()
        like_action = menu.addAction(tr("Unlike") if self._is_liked else tr("Like"))
        wl_action = menu.addAction(
            tr("Remove from Watch Later") if self._is_watch_later else tr("Watch Later")
        )
        action = menu.exec(self._more_btn.mapToGlobal(self._more_btn.rect().bottomLeft()))
        if action is None:
            return
        if action == play_action:
            self._on_play()
        elif action == like_action:
            self._on_like()
        elif action == wl_action:
            self._on_watch_later()
