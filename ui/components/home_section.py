from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QPushButton,
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QPixmap

from ui.components.video_card import VideoCard
from ui.components.skeleton import SkeletonWidget


class HomeSection(QWidget):
    play_requested = pyqtSignal(str, str, object)
    like_toggled = pyqtSignal(object)
    watch_later_toggled = pyqtSignal(object)

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._title = title
        self.setObjectName("homeSection")

        self._layout = QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(10)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)

        title_label = QLabel(title)
        title_label.setObjectName("homeSectionTitle")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        self._show_all_btn = QPushButton("Show all")
        self._show_all_btn.setObjectName("sectionTab")
        self._show_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._show_all_btn.setVisible(False)
        header_layout.addWidget(self._show_all_btn)

        self._layout.addWidget(header)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(False)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setFixedHeight(280)
        self._scroll_area.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:horizontal { height: 6px; background: transparent; }"
            "QScrollBar::handle:horizontal { background: #5A5A5A; border-radius: 3px; min-width: 30px; }"
            "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }"
        )

        self._scroll_content = QWidget()
        self._scroll_content.setStyleSheet("background: transparent;")
        self._scroll_layout = QHBoxLayout(self._scroll_content)
        self._scroll_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_layout.setSpacing(12)
        self._scroll_layout.addStretch()

        self._scroll_area.setWidget(self._scroll_content)
        self._layout.addWidget(self._scroll_area)
        self.setLayout(self._layout)

    def set_videos(self, videos: list, thumbnail_service=None):
        self._clear_content()
        if not videos:
            self.show_skeleton(4)
            return
        for v in videos:
            card = VideoCard(v)
            card.play_requested.connect(self.play_requested.emit)
            card.like_toggled.connect(self.like_toggled.emit)
            card.watch_later_toggled.connect(self.watch_later_toggled.emit)
            self._scroll_layout.insertWidget(self._scroll_layout.count() - 1, card)

            thumb_url = v.get("thumbnail", "")
            if thumb_url and thumbnail_service:
                data = thumbnail_service.load_thumbnail_data(thumb_url)
                if data is not None:
                    pixmap = QPixmap()
                    pixmap.loadFromData(data)
                    if not pixmap.isNull():
                        card.set_thumbnail(pixmap)

        self._show_all_btn.setVisible(len(videos) > 0)
        self._sync_content_size()

    def show_skeleton(self, count: int = 6):
        self._clear_content()
        for _ in range(count):
            skeleton = SkeletonWidget(VideoCard.CARD_WIDTH, 270)
            self._scroll_layout.insertWidget(self._scroll_layout.count() - 1, skeleton)
        self._sync_content_size()

    def _sync_content_size(self):
        hint = self._scroll_layout.sizeHint()
        self._scroll_content.resize(hint)
        self._scroll_content.updateGeometry()

    def _clear_content(self):
        for i in reversed(range(self._scroll_layout.count() - 1)):
            item = self._scroll_layout.itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()
