"""Watch-history page.

History entries are keyed by ``id``.  The page rebuilds its rows whenever the
history changes instead of blindly inserting new entries: replaying a video
moves its existing entry to the top, and inserting without removing the old
row produced duplicates.
"""

from __future__ import annotations

import contextlib
import time
from datetime import datetime

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.events import (
    EVENT_HISTORY_UPDATED,
    EVENT_LIKE_CHANGED,
    EVENT_THUMBNAIL_LOADED,
    EVENT_WATCH_LATER_TOGGLED,
    HistoryUpdatedEvent,
    LikeChangedEvent,
    ThumbnailLoadedEvent,
    WatchLaterToggledEvent,
)
from ui import icons
from ui.event_dispatcher import QtEventDispatcher
from ui.i18n import tr, trn
from ui.thumbnail_pixmaps import cached_pixmap, pixmap_loader, request_pixmap


def entry_video_id(entry) -> str:
    """Return the id used by a history entry."""
    if not isinstance(entry, dict):
        return ""
    for key in ("id", "video_id", "videoId"):
        value = entry.get(key)
        if value:
            return str(value)
    return ""


class HistoryPage(QWidget):
    play_video_requested = pyqtSignal(str, str, object)
    like_toggled = pyqtSignal(object)
    watch_later_toggled = pyqtSignal(object)

    PAGE_SIZE = 50
    LIKE_MARK = "\u2665  "
    WL_MARK = "\u23F1  "
    THUMBNAIL_SIZE = (120, 68)

    def __init__(self, history_service, player_service, thumbnail_service,
                 event_bus, likes_service=None, playlist_service=None,
                 parent=None):
        super().__init__(parent)
        self._history_service = history_service
        self._player_service = player_service
        self._thumbnail_service = thumbnail_service
        self._event_bus = event_bus
        self._likes_service = likes_service
        self._playlist_service = playlist_service

        self._items_by_id = {}
        self._items_by_thumbnail = {}
        self._subscriptions = []

        self._setup_ui()
        self._connect_signals()
        self._load_history()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(24, 20, 24, 8)

        title = QLabel(tr("History"))
        title.setObjectName("pageTitle")
        header.addWidget(title)

        self._count_label = QLabel("")
        self._count_label.setObjectName("historyCount")
        header.addWidget(self._count_label)
        header.addStretch()

        self.clear_btn = QPushButton(icons.delete(18), " " + tr("Clear All"))
        self.clear_btn.setObjectName("dangerButton")
        self.clear_btn.setAccessibleName(tr("Clear all watch history"))
        self.clear_btn.clicked.connect(self._on_clear)
        header.addWidget(self.clear_btn)

        header_widget = QWidget()
        header_widget.setLayout(header)
        layout.addWidget(header_widget)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self._scroll_content = QWidget()
        self._content_layout = QVBoxLayout(self._scroll_content)
        self._content_layout.setContentsMargins(24, 0, 24, 16)
        self._content_layout.setSpacing(4)

        self._list_widget = QListWidget()
        self._list_widget.setIconSize(QSize(*self.THUMBNAIL_SIZE))
        self._list_widget.setSpacing(4)
        self._list_widget.setWordWrap(True)
        self._list_widget.setUniformItemSizes(True)
        self._list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list_widget.customContextMenuRequested.connect(self._on_context_menu)
        # The list owns the remaining page height; without a stretch factor
        # the trailing stretch below stole that space and clipped the rows.
        self._content_layout.addWidget(self._list_widget, 1)

        self._empty_label = QLabel(
            tr("No watch history yet.\nPlay a video to get started.")
        )
        self._empty_label.setObjectName("emptyState")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        self._empty_label.hide()
        self._content_layout.addWidget(self._empty_label, 1)

        self._scroll_area.setWidget(self._scroll_content)
        layout.addWidget(self._scroll_area, 1)

        self.setLayout(layout)

    def _connect_signals(self):
        pixmap_loader().pixmap_ready.connect(self._on_pixmap_ready)
        if self._event_bus:
            self._subscriptions = [
                (EVENT_HISTORY_UPDATED, QtEventDispatcher(self._on_history_updated)),
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
    # Data loading
    # ------------------------------------------------------------------

    def _group_entries(self, entries):
        today = datetime.now().date()
        groups = {"Today": [], "Yesterday": [], "Last 7 Days": [], "Older": []}

        for entry in entries:
            ts = entry.get("watched_at", 0)
            if ts:
                try:
                    d = datetime.fromtimestamp(ts).date()
                    diff = (today - d).days
                    if diff == 0:
                        groups["Today"].append(entry)
                    elif diff == 1:
                        groups["Yesterday"].append(entry)
                    elif diff < 7:
                        groups["Last 7 Days"].append(entry)
                    else:
                        groups["Older"].append(entry)
                except (OSError, ValueError):
                    groups["Older"].append(entry)
            else:
                groups["Older"].append(entry)

        return [(k, v) for k, v in groups.items() if v]

    def _load_history(self):
        selected_id = ""
        current = self._list_widget.currentItem()
        if current is not None:
            entry = current.data(Qt.ItemDataRole.UserRole)
            selected_id = entry_video_id(entry)

        scroll_pos = self._scroll_area.verticalScrollBar().value()
        self._list_widget.clear()
        self._items_by_id.clear()
        self._items_by_thumbnail.clear()

        entries = self._history_service.get_all()
        self._count_label.setText(
            trn("{count} video", "{count} videos", len(entries)).format(
                count=len(entries)
            )
        )
        self.clear_btn.setEnabled(bool(entries))

        if not entries:
            self._list_widget.hide()
            self._empty_label.show()
            return

        self._list_widget.show()
        self._empty_label.hide()

        for section_name, section_entries in self._group_entries(entries):
            self._add_section_header(tr(section_name))
            for entry in section_entries:
                self._add_entry(entry, selected_id)

        self._scroll_area.verticalScrollBar().setValue(scroll_pos)

    def _add_section_header(self, name: str):
        item = QListWidgetItem(name)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        font = item.font()
        font.setPointSize(13)
        font.setBold(True)
        item.setFont(font)
        item.setForeground(Qt.GlobalColor.white)
        item.setSizeHint(QSize(0, 36))
        self._list_widget.addItem(item)

    def _make_display_text(self, entry):
        title = entry.get("title") or tr("Unknown")
        channel = entry.get("channel") or tr("Unknown")
        ts = entry.get("watched_at", 0)
        time_str = ""
        if ts:
            with contextlib.suppress(OSError, ValueError):
                time_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))

        markers = ""
        if self._is_liked(entry):
            markers += self.LIKE_MARK
        if self._in_watch_later(entry):
            markers += self.WL_MARK
        return f"{markers}{title}\n{channel}  \u2022  {time_str}"

    def _add_entry(self, entry, selected_id: str = ""):
        video_id = entry_video_id(entry)
        item = QListWidgetItem(self._make_display_text(entry))
        item.setData(Qt.ItemDataRole.UserRole, entry)
        item.setToolTip(entry.get("title") or "")
        self._list_widget.addItem(item)

        if video_id:
            self._items_by_id[video_id] = item
            if selected_id and video_id == selected_id:
                self._list_widget.setCurrentItem(item)

        thumb_url = entry.get("thumbnail", "")
        if thumb_url:
            self._items_by_thumbnail[thumb_url] = item
            self._defer_thumbnail(thumb_url, item)

    def _is_liked(self, entry) -> bool:
        video_id = entry_video_id(entry)
        if not video_id or self._likes_service is None:
            return False
        try:
            return bool(self._likes_service.is_liked(video_id))
        except Exception:
            return False

    def _in_watch_later(self, entry) -> bool:
        video_id = entry_video_id(entry)
        if not video_id or self._playlist_service is None:
            return False
        try:
            return bool(self._playlist_service.is_in_watch_later(video_id))
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Thumbnails
    # ------------------------------------------------------------------

    def _defer_thumbnail(self, thumb_url, item):
        data = self._thumbnail_service.load_thumbnail_data(thumb_url)
        if data is not None:
            QTimer.singleShot(
                0,
                lambda u=thumb_url, d=data, i=item: self._apply_thumbnail_cached(
                    u, d, i
                ),
            )

    def _apply_thumbnail_cached(self, url, data, item):
        if self._items_by_thumbnail.get(url) is not item:
            return
        pixmap = request_pixmap(url, data, *self.THUMBNAIL_SIZE)
        if pixmap is not None:
            item.setIcon(QIcon(pixmap))

    def _on_thumbnail_loaded(self, event: ThumbnailLoadedEvent):
        item = self._items_by_thumbnail.get(event.item)
        if item is not None and event.icon:
            pixmap = request_pixmap(event.item, event.icon, *self.THUMBNAIL_SIZE)
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

    def _play(self, entry):
        video_id = entry_video_id(entry)
        if video_id:
            self.play_video_requested.emit(video_id, "", entry)

    def _on_item_double_clicked(self, item):
        if item is None or not item.flags() & Qt.ItemFlag.ItemIsSelectable:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(entry, dict):
            self._play(entry)

    def _on_context_menu(self, pos):
        item = self._list_widget.itemAt(pos)
        if item is None or not item.flags() & Qt.ItemFlag.ItemIsSelectable:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(entry, dict):
            return
        video_id = entry_video_id(entry)
        if not video_id:
            return

        liked = self._is_liked(entry)
        in_wl = self._in_watch_later(entry)

        menu = QMenu(self)
        play_action = menu.addAction(icons.play(18), tr("Play"))
        menu.addSeparator()
        like_action = menu.addAction(tr("Unlike") if liked else tr("Like"))
        wl_action = menu.addAction(
            tr("Remove from Watch Later") if in_wl else tr("Add to Watch Later")
        )
        menu.addSeparator()
        remove_action = menu.addAction(icons.delete(18), tr("Remove from History"))

        action = menu.exec(self._list_widget.mapToGlobal(pos))
        if action is None:
            return
        if action == play_action:
            self._play(entry)
        elif action == like_action:
            self.like_toggled.emit(entry)
        elif action == wl_action:
            self.watch_later_toggled.emit(entry)
        elif action == remove_action:
            self._history_service.remove(video_id)

    def _on_clear(self):
        if self._history_service.count() == 0:
            return
        reply = QMessageBox.question(
            self,
            tr("Clear History"),
            tr("Are you sure you want to clear all watch history?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._history_service.clear()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _on_history_updated(self, event: HistoryUpdatedEvent):
        # Every mutation is reflected by rebuilding: replaying a video moves
        # its entry, so inserting blindly would duplicate rows.
        if event.action in ("added", "removed", "cleared", "import"):
            self._load_history()

    def _on_like_changed(self, event: LikeChangedEvent):
        entry = None
        item = self._items_by_id.get(event.video_id)
        if item is not None:
            entry = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(entry, dict):
            item.setText(self._make_display_text(entry))

    def _on_watch_later_toggled(self, event: WatchLaterToggledEvent):
        item = self._items_by_id.get(event.video_id)
        if item is None:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(entry, dict):
            item.setText(self._make_display_text(entry))
