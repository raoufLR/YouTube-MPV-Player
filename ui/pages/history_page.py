import time
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QMessageBox, QMenu, QScrollArea,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QPixmap, QIcon

from core.events import EVENT_HISTORY_UPDATED, HistoryUpdatedEvent
from core import EventBus
from ui import icons


class HistoryPage(QWidget):
    play_video_requested = pyqtSignal(str, str, object)
    _thumbnail_ready = pyqtSignal(object, object)

    PAGE_SIZE = 50

    def __init__(self, history_service, player_service, thumbnail_service,
                 event_bus, parent=None):
        super().__init__(parent)
        self._history_service = history_service
        self._player_service = player_service
        self._thumbnail_service = thumbnail_service
        self._event_bus = event_bus

        self._history_items = {}
        self._section_widgets = {}
        self._subscriptions = []

        self._setup_ui()
        self._connect_signals()
        self._load_history()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(24, 20, 24, 8)

        title = QLabel("History")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()

        self.clear_btn = QPushButton(icons.delete(18), " Clear All")
        self.clear_btn.setObjectName("dangerButton")
        self.clear_btn.clicked.connect(self._on_clear)
        header.addWidget(self.clear_btn)

        header_widget = QWidget()
        header_widget.setLayout(header)
        layout.addWidget(header_widget)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._scroll_content = QWidget()
        self._content_layout = QVBoxLayout(self._scroll_content)
        self._content_layout.setContentsMargins(24, 0, 24, 16)
        self._content_layout.setSpacing(4)

        self._list_widget = QListWidget()
        self._list_widget.setIconSize(QSize(120, 68))
        self._list_widget.setSpacing(4)
        self._list_widget.setWordWrap(True)
        self._list_widget.setUniformItemSizes(True)
        self._list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list_widget.customContextMenuRequested.connect(self._on_context_menu)
        self._content_layout.addWidget(self._list_widget)

        self._empty_label = QLabel("No watch history yet.\nPlay a video to get started.")
        self._empty_label.setObjectName("emptyState")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.hide()
        self._content_layout.addWidget(self._empty_label)

        self._content_layout.addStretch()
        self._scroll_area.setWidget(self._scroll_content)
        layout.addWidget(self._scroll_area, 1)

        self.setLayout(layout)

    def _connect_signals(self):
        self._thumbnail_ready.connect(self._apply_thumbnail_data)
        if self._event_bus:
            self._subscriptions = [(EVENT_HISTORY_UPDATED, self._on_history_updated)]
            for event_type, cb in self._subscriptions:
                self._event_bus.subscribe(event_type, cb, weak=False)

    def cleanup(self):
        for event_type, cb in getattr(self, '_subscriptions', []):
            self._event_bus.unsubscribe(event_type, cb)
        self._subscriptions = []

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
        self._list_widget.clear()
        self._history_items.clear()
        entries = self._history_service.get_all()
        if not entries:
            self._list_widget.hide()
            self._empty_label.show()
            return
        self._list_widget.show()
        self._empty_label.hide()

        for section_name, section_entries in self._group_entries(entries):
            self._add_section_header(section_name)
            for entry in section_entries:
                self._add_entry(entry)

    def _add_section_header(self, name: str):
        item = QListWidgetItem(name)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        f = item.font()
        f.setPointSize(13)
        f.setBold(True)
        item.setFont(f)
        item.setForeground(Qt.GlobalColor.white)
        item.setSizeHint(QSize(0, 36))
        self._list_widget.addItem(item)

    def _make_display_text(self, entry):
        title = entry.get("title", "Unknown")
        channel = entry.get("channel", "Unknown")
        ts = entry.get("watched_at", 0)
        time_str = ""
        if ts:
            try:
                time_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
            except (OSError, ValueError):
                pass
        return f"{title}\n{channel}  \u2022  {time_str}"

    def _add_entry(self, entry):
        display = self._make_display_text(entry)
        item = QListWidgetItem(display)
        item.setData(Qt.ItemDataRole.UserRole, entry)
        self._list_widget.addItem(item)

        thumb_url = entry.get("thumbnail", "")
        if thumb_url:
            self._history_items[thumb_url] = item
            self._defer_thumbnail(thumb_url, item)

    def _defer_thumbnail(self, thumb_url, item):
        data = self._thumbnail_service.load_thumbnail_data(thumb_url)
        if data is not None:
            QTimer.singleShot(0, lambda u=thumb_url, d=data, i=item: self._apply_thumbnail_cached(u, d, i))

    def _apply_thumbnail_cached(self, url, data, item):
        if self._history_items.get(url) is item:
            self._apply_thumbnail_data(data, item)

    def _on_item_double_clicked(self, item):
        if not item.flags() & Qt.ItemFlag.ItemIsSelectable:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        if not entry:
            return
        video_id = entry.get("id", entry.get("videoId", ""))
        if video_id:
            self.play_video_requested.emit(video_id, "", entry)

    def _on_clear(self):
        reply = QMessageBox.question(
            self, "Clear History",
            "Are you sure you want to clear all watch history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._history_service.clear()

    def _on_history_updated(self, event):
        if event.action == "added":
            entries = self._history_service.get_recent(limit=1)
            if not entries:
                return
            entry = entries[0]
            self._empty_label.hide()
            self._list_widget.show()
            display = self._make_display_text(entry)
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self._list_widget.insertItem(0, item)
            thumb_url = entry.get("thumbnail", "")
            if thumb_url:
                self._history_items[thumb_url] = item
                self._defer_thumbnail(thumb_url, item)
        elif event.action == "removed":
            for i in range(self._list_widget.count()):
                existing = self._list_widget.item(i)
                if existing:
                    edata = existing.data(Qt.ItemDataRole.UserRole)
                    vid = edata.get("id", edata.get("videoId", "")) if edata else ""
                    if vid == event.video_id:
                        self._list_widget.takeItem(i)
                        break
            if self._list_widget.count() == 0:
                self._list_widget.hide()
                self._empty_label.show()
        elif event.action == "cleared":
            self._list_widget.clear()
            self._history_items.clear()
            self._list_widget.hide()
            self._empty_label.show()

    def _on_context_menu(self, pos):
        item = self._list_widget.itemAt(pos)
        if not item:
            return
        if not item.flags() & Qt.ItemFlag.ItemIsSelectable:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        if not entry:
            return
        menu = QMenu(self)
        play_action = menu.addAction(icons.play(18), "Play")
        remove_action = menu.addAction(icons.delete(18), "Remove from History")
        action = menu.exec(self._list_widget.mapToGlobal(pos))
        if action == play_action:
            self._on_item_double_clicked(item)
        elif action == remove_action:
            video_id = entry.get("id", entry.get("videoId", ""))
            if video_id:
                self._history_service.remove(video_id)

    def _apply_thumbnail_data(self, data, item):
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        item.setIcon(QIcon(pixmap))
