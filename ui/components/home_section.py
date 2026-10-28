import contextlib
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.components.skeleton import SkeletonWidget
from ui.components.video_card import VideoCard, extract_video_id
from ui.i18n import tr
from ui.thumbnail_pixmaps import request_pixmap

if TYPE_CHECKING:
    from PyQt6.QtGui import QPixmap


class HomeSection(QWidget):
    play_requested = pyqtSignal(str, str, object)
    like_toggled = pyqtSignal(object)
    watch_later_toggled = pyqtSignal(object)

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._title = title
        self.setObjectName("homeSection")
        # Thumbnail URLs may appear in several cards of the same row; keep a
        # reverse index so an asynchronously loaded image reaches every card.
        self._cards_by_thumbnail: dict = {}
        # Last size applied to the scroll content; re-applying an identical
        # size would schedule another layout/geometry pass for no reason.
        self._last_content_size = None

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

        self._show_all_btn = QPushButton(tr("Show all"))
        self._show_all_btn.setObjectName("sectionTab")
        self._show_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._show_all_btn.setVisible(False)
        header_layout.addWidget(self._show_all_btn)

        self._layout.addWidget(header)

        self._scroll_area = QScrollArea()
        self._scroll_area.setObjectName("homeSectionScroll")
        self._scroll_area.setWidgetResizable(False)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setFixedHeight(280)

        self._scroll_content = QWidget()
        self._scroll_content.setStyleSheet("background: transparent;")
        self._scroll_layout = QHBoxLayout(self._scroll_content)
        self._scroll_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_layout.setSpacing(12)
        self._scroll_layout.addStretch()

        self._scroll_area.setWidget(self._scroll_content)
        self._layout.addWidget(self._scroll_area)
        self.setLayout(self._layout)

    def set_videos(self, videos: list, thumbnail_service=None,
                   likes_service=None, playlist_service=None):
        self._clear_content()
        if not videos:
            self.show_skeleton(4)
            return
        # Build the whole row before letting Qt repaint: each insertion into a
        # visible layout would otherwise schedule its own layout/paint pass.
        self._scroll_content.setUpdatesEnabled(False)
        try:
            for v in videos:
                card = VideoCard(v)
                card.play_requested.connect(self.play_requested.emit)
                card.like_toggled.connect(self.like_toggled.emit)
                card.watch_later_toggled.connect(self.watch_later_toggled.emit)
                card.set_liked(self._likes(likes_service, v))
                card.set_watch_later(self._in_watch_later(playlist_service, v))
                self._scroll_layout.insertWidget(self._scroll_layout.count() - 1, card)

                thumb_url = v.get("thumbnail", "")
                if thumb_url:
                    self._cards_by_thumbnail.setdefault(thumb_url, []).append(card)
                if thumb_url and thumbnail_service:
                    data = thumbnail_service.load_thumbnail_data(thumb_url)
                    if data is not None:
                        # Cached frames are applied immediately; misses are
                        # decoded on the worker pool and arrive by signal.
                        pixmap = request_pixmap(
                            thumb_url, data,
                            card.THUMBNAIL_WIDTH, card.THUMBNAIL_HEIGHT,
                        )
                        if pixmap is not None:
                            card.set_thumbnail(pixmap)
        finally:
            self._scroll_content.setUpdatesEnabled(True)

        self._show_all_btn.setVisible(len(videos) > 0)
        self._sync_content_size()
        # Deferred deletions and font/layout activation can adjust the hint
        # by one event-loop turn; re-sync after they settle.
        self._schedule_sync()

    def apply_thumbnail(self, url: str, pixmap: QPixmap) -> int:
        """Apply an asynchronously loaded *pixmap* to matching cards.

        Returns the number of cards updated so the caller can tell whether a
        section still needs the image.
        """
        if not url or pixmap is None or pixmap.isNull():
            return 0
        updated = 0
        for card in self._cards_by_thumbnail.get(url, ()):
            card.set_thumbnail(pixmap)
            updated += 1
        return updated

    @staticmethod
    def _likes(likes_service, video_data) -> bool:
        if likes_service is None:
            return False
        try:
            video_id = extract_video_id(video_data)
            return bool(video_id and likes_service.is_liked(video_id))
        except Exception:
            return False

    @staticmethod
    def _in_watch_later(playlist_service, video_data) -> bool:
        if playlist_service is None:
            return False
        try:
            video_id = extract_video_id(video_data)
            return bool(video_id and playlist_service.is_in_watch_later(video_id))
        except Exception:
            return False

    def show_skeleton(self, count: int = 6):
        self._clear_content()
        for _ in range(count):
            skeleton = SkeletonWidget(VideoCard.CARD_WIDTH, 270)
            self._scroll_layout.insertWidget(self._scroll_layout.count() - 1, skeleton)
        self._sync_content_size()
        self._schedule_sync()

    def _sync_content_size(self):
        # The layout must be activated before reading its size hint: right
        # after insertions the cached hint can still describe the previous
        # row (for example the six skeletons).  Sizing the content from that
        # stale hint makes QBoxLayout compress the fixed-width cards on top of
        # each other once the deferred deletions settle.
        self._scroll_layout.activate()
        hint = self._scroll_layout.sizeHint()
        if hint.width() > 0 and hint.height() > 0 and hint != self._last_content_size:
            self._last_content_size = hint
            self._scroll_content.resize(hint)
            self._scroll_content.updateGeometry()

    def _schedule_sync(self):
        """Recompute after Qt has activated the layout and deleted old cards."""
        QTimer.singleShot(0, self._safe_deferred_sync)

    def _safe_deferred_sync(self):
        # The page may have been destroyed (profile switch / shutdown) before
        # the deferred layout pass ran.
        with contextlib.suppress(RuntimeError):
            self._sync_content_size()

    def _clear_content(self):
        self._cards_by_thumbnail.clear()
        # Remove the items from the layout *and* delete them.  Calling
        # deleteLater() alone leaves the old widgets in the layout until the
        # event loop runs, so a size hint taken immediately afterwards
        # includes stale cards and the new row is laid out against the wrong
        # width.
        while self._scroll_layout.count() > 1:  # keep the trailing stretch
            item = self._scroll_layout.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
