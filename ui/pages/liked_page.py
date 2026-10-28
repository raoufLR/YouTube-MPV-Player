"""Liked Videos page.

Lists every video the user has liked, updating live as likes are added or
removed elsewhere in the application.  The service stores ``video_id`` keys,
so this page accepts both that and the search-result ``videoId`` spelling when
building playback requests.
"""

from __future__ import annotations

import contextlib
import time

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.events import (
    EVENT_LIKE_CHANGED,
    EVENT_THUMBNAIL_LOADED,
    EVENT_WATCH_LATER_TOGGLED,
    LikeChangedEvent,
    ThumbnailLoadedEvent,
    WatchLaterToggledEvent,
)
from ui import icons
from ui.event_dispatcher import QtEventDispatcher
from ui.i18n import tr, trn
from ui.thumbnail_pixmaps import cached_pixmap, pixmap_loader, request_pixmap


class LikedPage(QWidget):
    play_video_requested = pyqtSignal(str, str, object)
    like_toggled = pyqtSignal(object)
    watch_later_toggled = pyqtSignal(object)

    THUMBNAIL_SIZE = (120, 68)

    def __init__(self, likes_service, playlist_service, thumbnail_service,
                 event_bus, parent=None):
        super().__init__(parent)
        self._likes_service = likes_service
        self._playlist_service = playlist_service
        self._thumbnail_service = thumbnail_service
        self._event_bus = event_bus

        self._items = {}
        self._items_by_thumbnail = {}
        self._subscriptions = []

        self._setup_ui()
        self._connect_signals()
        self.refresh()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(24, 20, 24, 8)

        title = QLabel(tr("Liked Videos"))
        title.setObjectName("pageTitle")
        header.addWidget(title)

        self._count_label = QLabel("")
        self._count_label.setObjectName("historyCount")
        header.addWidget(self._count_label)
        header.addStretch()

        self._refresh_btn = QPushButton(icons.refresh(18), " " + tr("Refresh"))
        self._refresh_btn.setObjectName("iconButton")
        self._refresh_btn.setToolTip(tr("Reload liked videos"))
        self._refresh_btn.setAccessibleName(tr("Reload liked videos"))
        self._refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self._refresh_btn)

        header_widget = QWidget()
        header_widget.setLayout(header)
        layout.addWidget(header_widget)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self._scroll_content = QWidget()
        content_layout = QVBoxLayout(self._scroll_content)
        content_layout.setContentsMargins(24, 0, 24, 16)
        content_layout.setSpacing(4)

        self._list_widget = QListWidget()
        self._list_widget.setIconSize(QSize(*self.THUMBNAIL_SIZE))
        self._list_widget.setSpacing(4)
        self._list_widget.setWordWrap(True)
        self._list_widget.setUniformItemSizes(True)
        self._list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list_widget.customContextMenuRequested.connect(self._on_context_menu)
        content_layout.addWidget(self._list_widget, 1)

        self._empty_label = QLabel(
            tr("No liked videos yet.\nUse the like button on any video to save it here.")
        )
        self._empty_label.setObjectName("emptyState")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        self._empty_label.hide()
        content_layout.addWidget(self._empty_label, 1)

        self._scroll_area.setWidget(self._scroll_content)
        layout.addWidget(self._scroll_area, 1)

        self.setLayout(layout)

    def _connect_signals(self):
        pixmap_loader().pixmap_ready.connect(self._on_pixmap_ready)
        if self._event_bus:
            self._subscriptions = [
                (EVENT_LIKE_CHANGED, QtEventDispatcher(self._on_like_changed)),
                (
                    EVENT_WATCH_LATER_TOGGLED,
                    QtEventDispatcher(self._on_watch_later_toggled),
                ),
                (
                    EVENT_THUMBNAIL_LOADED,
                    QtEventDispatcher(self._on_thumbnail_loaded),
                ),
            ]
            for event_type, callback in self._subscriptions:
                self._event_bus.subscribe(event_type, callback, weak=False)

    def cleanup(self):
        for event_type, callback in getattr(self, "_subscriptions", []):
            self._event_bus.unsubscribe(event_type, callback)
        self._subscriptions = []
        with contextlib.suppress(TypeError, RuntimeError):
            pixmap_loader().pixmap_ready.disconnect(self._on_pixmap_ready)

    # ------------------------------------------------------------------
    # Population
    # ------------------------------------------------------------------

    def refresh(self):
        selected_id = ""
        current = self._list_widget.currentItem()
        if current is not None:
            selected_id = str(current.data(Qt.ItemDataRole.UserRole + 1) or "")

        entries = self._likes_service.get_liked_videos() if self._likes_service else []
        self._list_widget.clear()
        self._items.clear()
        self._items_by_thumbnail.clear()

        self._count_label.setText(
            trn("{count} video", "{count} videos", len(entries)).format(
                count=len(entries)
            )
        )

        if not entries:
            self._list_widget.hide()
            self._empty_label.show()
            return

        self._list_widget.show()
        self._empty_label.hide()

        for entry in entries:
            item = self._make_item(entry)
            self._list_widget.addItem(item)
            if selected_id and item.data(Qt.ItemDataRole.UserRole + 1) == selected_id:
                self._list_widget.setCurrentItem(item)

    def _make_item(self, entry: dict) -> QListWidgetItem:
        video_id = str(entry.get("video_id", entry.get("videoId", "")) or "")
        title = entry.get("title") or tr("Unknown")
        channel = entry.get("channel") or tr("Unknown")
        liked_at = entry.get("liked_at") or 0

        when = ""
        if liked_at:
            try:
                when = time.strftime("%Y-%m-%d %H:%M", time.localtime(liked_at))
            except (OSError, ValueError):
                when = ""

        parts = [channel]
        if when:
            parts.append(tr("Liked {when}").format(when=when))
        item = QListWidgetItem(f"{title}\n{'  \u2022  '.join(parts)}")
        item.setData(Qt.ItemDataRole.UserRole, entry)
        item.setData(Qt.ItemDataRole.UserRole + 1, video_id)
        item.setToolTip(title)
        item.setSizeHint(QSize(0, 76))

        if video_id:
            self._items[video_id] = item

        thumb_url = entry.get("thumbnail", "")
        if thumb_url:
            self._items_by_thumbnail[thumb_url] = item
            self._defer_thumbnail(thumb_url, item)
        return item

    def _defer_thumbnail(self, url: str, item: QListWidgetItem):
        pixmap = cached_pixmap(url, *self.THUMBNAIL_SIZE)
        if pixmap is not None:
            item.setIcon(QIcon(pixmap))
            return
        if self._thumbnail_service is None:
            return
        try:
            data = self._thumbnail_service.load_thumbnail_data(url)
        except Exception:
            data = None
        if data is not None:
            self._apply_thumbnail((data, url), item)

    def _on_thumbnail_loaded(self, event: ThumbnailLoadedEvent):
        item = self._items_by_thumbnail.get(event.item)
        if item is not None and event.icon:
            self._apply_thumbnail((event.icon, event.item), item)

    def _apply_thumbnail(self, payload, item):
        data, url = payload
        pixmap = request_pixmap(url, data, *self.THUMBNAIL_SIZE)
        if pixmap is not None:
            item.setIcon(QIcon(pixmap))

    def _on_pixmap_ready(self, url: str, width: int, height: int):
        if (width, height) != self.THUMBNAIL_SIZE:
            return
        item = self._items_by_thumbnail.get(url)
        if item is None:
            return
        pixmap = cached_pixmap(url, width, height)
        if pixmap is not None:
            item.setIcon(QIcon(pixmap))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _selected_entry(self, item):
        if item is None:
            return None
        entry = item.data(Qt.ItemDataRole.UserRole)
        return entry if isinstance(entry, dict) else None

    def _play(self, entry):
        video_id = str(
            entry.get("video_id", entry.get("videoId", entry.get("id", ""))) or ""
        )
        if video_id:
            self.play_video_requested.emit(video_id, "", entry)

    def _on_item_double_clicked(self, item):
        entry = self._selected_entry(item)
        if entry:
            self._play(entry)

    def _on_context_menu(self, pos):
        item = self._list_widget.itemAt(pos)
        entry = self._selected_entry(item)
        if entry is None:
            return

        video_id = str(
            entry.get("video_id", entry.get("videoId", entry.get("id", ""))) or ""
        )
        if not video_id:
            return

        in_watch_later = False
        if self._playlist_service is not None:
            try:
                in_watch_later = self._playlist_service.is_in_watch_later(video_id)
            except Exception:
                in_watch_later = False

        menu = QMenu(self)
        play_action = menu.addAction(icons.play(18), tr("Play"))
        menu.addSeparator()
        unlike_action = menu.addAction(icons.liked(18), tr("Unlike"))
        wl_action = menu.addAction(
            tr("Remove from Watch Later") if in_watch_later else tr("Watch Later")
        )

        action = menu.exec(self._list_widget.mapToGlobal(pos))
        if action is None:
            return
        if action == play_action:
            self._play(entry)
        elif action == unlike_action:
            self.like_toggled.emit(entry)
        elif action == wl_action:
            self.watch_later_toggled.emit(entry)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _on_like_changed(self, event: LikeChangedEvent):
        if not event.is_liked:
            item = self._items.get(event.video_id)
            if item is not None:
                row = self._list_widget.row(item)
                self._list_widget.takeItem(row)
                self._items.pop(event.video_id, None)
        self.refresh()

    def _on_watch_later_toggled(self, event: WatchLaterToggledEvent):
        # Only the context-menu labels depend on this; no rebuild required.
        return
