from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMenu,
    QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPixmap

from ui import icons


class VideoCard(QWidget):
    play_requested = pyqtSignal(str, str, object)
    like_toggled = pyqtSignal(object)
    watch_later_toggled = pyqtSignal(object)

    THUMBNAIL_WIDTH = 260
    THUMBNAIL_HEIGHT = 146
    CARD_WIDTH = 260

    def __init__(self, video_data: dict, parent=None):
        super().__init__(parent)
        self._video_data = video_data
        self._video_id = str(video_data.get("videoId", video_data.get("id", "")))
        self._title = video_data.get("title", "Unknown")
        self._channel = video_data.get("channel", "")
        self._thumbnail_url = video_data.get("thumbnail", "")
        self._duration = video_data.get("duration", "")
        self._views = video_data.get("views", "")
        self._upload_date = video_data.get("uploadDate", video_data.get("upload_date", ""))
        self._is_liked = False
        self._is_watch_later = False

        self._pixmap: QPixmap = None

        self.setObjectName("videoCard")
        self.setFixedWidth(self.CARD_WIDTH)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._setup_ui()
        self._setup_hover_effect()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        thumb_container = QWidget()
        thumb_container.setFixedSize(self.THUMBNAIL_WIDTH, self.THUMBNAIL_HEIGHT)
        thumb_layout = QVBoxLayout(thumb_container)
        thumb_layout.setContentsMargins(0, 0, 0, 0)

        self._thumbnail_label = QLabel()
        self._thumbnail_label.setFixedSize(self.THUMBNAIL_WIDTH, self.THUMBNAIL_HEIGHT)
        self._thumbnail_label.setScaledContents(True)
        self._thumbnail_label.setStyleSheet("""
            QLabel {
                background-color: #303134;
                border-radius: 10px;
            }
        """)
        thumb_layout.addWidget(self._thumbnail_label)

        if self._duration:
            dur_label = QLabel(self._duration)
            dur_label.setObjectName("duration")
            dur_label.setStyleSheet("""
                color: #FFFFFF; font-size: 12px; font-weight: 600;
                background-color: rgba(0,0,0,0.8); border-radius: 4px;
                padding: 2px 6px;
            """)
            dur_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
            dur_label.setFixedHeight(20)
            thumb_layout.addWidget(dur_label, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

        layout.addWidget(thumb_container)

        self._info_container = QWidget()
        info_layout = QVBoxLayout(self._info_container)
        info_layout.setContentsMargins(4, 8, 4, 2)
        info_layout.setSpacing(2)

        title_label = QLabel(self._title)
        title_label.setWordWrap(False)
        title_label.setMaximumHeight(38)
        title_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #FFFFFF; line-height: 1.3;")
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
            sub.setStyleSheet("font-size: 11px; color: #AAAAAA;")
            sub.setToolTip(self._title)
            info_layout.addWidget(sub)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 4, 0, 0)
        btn_row.setSpacing(2)

        self._play_btn = QPushButton()
        self._play_btn.setIcon(icons.play(20))
        self._play_btn.setObjectName("nowPlayingBtn")
        self._play_btn.setToolTip("Play video")
        self._play_btn.setFixedSize(36, 36)
        self._play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._play_btn.clicked.connect(self._on_play)
        btn_row.addWidget(self._play_btn)

        self._like_btn = QPushButton()
        self._like_btn.setIcon(icons.like(20))
        self._like_btn.setObjectName("nowPlayingBtn")
        self._like_btn.setToolTip("Like")
        self._like_btn.setFixedSize(36, 36)
        self._like_btn.setCheckable(True)
        self._like_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._like_btn.clicked.connect(self._on_like)
        btn_row.addWidget(self._like_btn)

        self._wl_btn = QPushButton()
        self._wl_btn.setIcon(icons.watch_later_add(20))
        self._wl_btn.setObjectName("nowPlayingBtn")
        self._wl_btn.setToolTip("Watch Later")
        self._wl_btn.setFixedSize(36, 36)
        self._wl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._wl_btn.clicked.connect(self._on_watch_later)
        btn_row.addWidget(self._wl_btn)

        self._more_btn = QPushButton()
        self._more_btn.setIcon(icons.more_vert(20))
        self._more_btn.setObjectName("nowPlayingBtn")
        self._more_btn.setToolTip("More options")
        self._more_btn.setFixedSize(36, 36)
        self._more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._more_btn.clicked.connect(self._on_context_menu)
        btn_row.addWidget(self._more_btn)

        btn_row.addStretch()
        info_layout.addLayout(btn_row)

        layout.addWidget(self._info_container)
        self.setLayout(layout)

    def _setup_hover_effect(self):
        self._shadow = QGraphicsDropShadowEffect()
        self._shadow.setBlurRadius(0)
        self._shadow.setOffset(0, 0)
        self._shadow.setColor(Qt.GlobalColor.transparent)
        self.setGraphicsEffect(self._shadow)

        self._anim = QPropertyAnimation(self._shadow, b"blurRadius")
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def enterEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(self._shadow.blurRadius())
        self._anim.setEndValue(16)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
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
            self._thumbnail_label.setPixmap(pixmap)

            fade = QPropertyAnimation(self._thumbnail_label, b"opacity")
            fade.setDuration(300)
            fade.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._thumbnail_label.setGraphicsEffect(None)
            fade.setStartValue(0.0)
            fade.setEndValue(1.0)
            fade.start()

    def set_liked(self, liked: bool):
        self._is_liked = liked
        self._like_btn.setChecked(liked)
        if liked:
            self._like_btn.setIcon(icons.liked(20))
        else:
            self._like_btn.setIcon(icons.like(20))

    def video_id(self) -> str:
        return self._video_id

    def video_data(self) -> dict:
        return self._video_data

    def _on_play(self):
        self.play_requested.emit(self._video_id, "", self._video_data)

    def _on_like(self):
        self._is_liked = not self._is_liked
        self.set_liked(self._is_liked)
        self.like_toggled.emit(self._video_data)

    def _on_watch_later(self):
        self._is_watch_later = not self._is_watch_later
        self.watch_later_toggled.emit(self._video_data)

    def _on_context_menu(self):
        menu = QMenu(self)
        play_action = menu.addAction(icons.play(18), "Play")
        menu.addSeparator()
        like_text = "Unlike" if self._is_liked else "Like"
        menu.addAction(like_text)
        wl_text = "Remove Watch Later" if self._is_watch_later else "Watch Later"
        menu.addAction(wl_text)
        action = menu.exec(self._more_btn.mapToGlobal(self._more_btn.rect().bottomLeft()))
        if action == play_action:
            self._on_play()
