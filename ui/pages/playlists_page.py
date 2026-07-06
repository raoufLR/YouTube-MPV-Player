from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QInputDialog, QMessageBox,
    QSplitter, QScrollArea, QMenu, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QPixmap, QIcon, QFont

from core.events import (
    EVENT_PLAYLIST_CREATED, EVENT_PLAYLIST_UPDATED, EVENT_PLAYLIST_DELETED,
    PlaylistCreatedEvent, PlaylistUpdatedEvent, PlaylistDeletedEvent,
)
from ui.event_dispatcher import QtEventDispatcher
from ui import icons
from ui.components import VideoCard


class PlaylistsPage(QWidget):
    play_video_requested = pyqtSignal(str, str, object)

    def __init__(self, player_service, thumbnail_service, playlist_service,
                 event_bus, parent=None):
        super().__init__(parent)
        self._player_service = player_service
        self._thumbnail_service = thumbnail_service
        self._playlist_service = playlist_service
        self._event_bus = event_bus

        self._current_playlist_id = None
        self._subscriptions = []

        self._setup_ui()
        self._connect_signals()
        self._load_playlists()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(24, 20, 24, 8)

        title = QLabel("Playlists")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(12, 0, 8, 12)
        left_layout.setSpacing(8)

        left_header = QHBoxLayout()
        left_label = QLabel("Your Playlists")
        left_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #AAAAAA; padding: 8px 4px 0 4px;")
        left_header.addWidget(left_label)
        left_header.addStretch()

        self._create_btn = QPushButton(icons.add_playlist(18), "")
        self._create_btn.setObjectName("iconButton")
        self._create_btn.setToolTip("Create Playlist")
        self._create_btn.setFixedSize(36, 36)
        self._create_btn.clicked.connect(self._on_create)
        left_header.addWidget(self._create_btn)
        left_layout.addLayout(left_header)

        self._playlist_list = QListWidget()
        self._playlist_list.setIconSize(QSize(160, 90))
        self._playlist_list.setSpacing(4)
        self._playlist_list.setUniformItemSizes(True)
        self._playlist_list.currentItemChanged.connect(self._on_playlist_selected)
        self._playlist_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._playlist_list.customContextMenuRequested.connect(self._on_playlist_context)
        left_layout.addWidget(self._playlist_list, 1)
        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 0, 16, 12)
        right_layout.setSpacing(8)

        self._playlist_title = QLabel("Select a playlist")
        self._playlist_title.setStyleSheet("font-size: 18px; font-weight: 700; color: #FFFFFF;")
        right_layout.addWidget(self._playlist_title)

        self._playlist_info = QLabel("")
        self._playlist_info.setStyleSheet("font-size: 12px; color: #AAAAAA;")
        right_layout.addWidget(self._playlist_info)

        self._video_list = QListWidget()
        self._video_list.setIconSize(QSize(120, 68))
        self._video_list.setSpacing(4)
        self._video_list.setUniformItemSizes(True)
        self._video_list.setWordWrap(True)
        self._video_list.itemDoubleClicked.connect(self._on_video_double_clicked)
        self._video_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._video_list.customContextMenuRequested.connect(self._on_video_context)
        right_layout.addWidget(self._video_list, 1)

        self._empty_video_label = QLabel("This playlist is empty.\nAdd videos from the search results.")
        self._empty_video_label.setObjectName("emptyState")
        self._empty_video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_video_label.hide()
        right_layout.addWidget(self._empty_video_label)

        splitter.addWidget(right_panel)
        splitter.setSizes([250, 450])
        layout.addWidget(splitter, 1)
        self.setLayout(layout)

    def _connect_signals(self):
        if self._event_bus:
            self._subscriptions = [
                (EVENT_PLAYLIST_CREATED, QtEventDispatcher(self._on_playlist_event)),
                (EVENT_PLAYLIST_UPDATED, QtEventDispatcher(self._on_playlist_event)),
                (EVENT_PLAYLIST_DELETED, QtEventDispatcher(self._on_playlist_event)),
            ]
            for event_type, cb in self._subscriptions:
                self._event_bus.subscribe(event_type, cb, weak=False)

    def cleanup(self):
        for event_type, cb in getattr(self, '_subscriptions', []):
            self._event_bus.unsubscribe(event_type, cb)
        self._subscriptions = []

    def _load_playlists(self):
        self._playlist_list.clear()
        playlists = self._playlist_service.get_all_playlists()
        for pl in sorted(playlists, key=lambda x: (x.id != "watch-later", x.name)):
            text = f"{pl.name}"
            if pl.id == "watch-later":
                text = "\u23F0 " + text
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, pl.id)
            count = len(pl.videos)
            item.setToolTip(f"{count} videos")
            self._playlist_list.addItem(item)

    def _on_playlist_selected(self, current, previous):
        if not current:
            return
        pl_id = current.data(Qt.ItemDataRole.UserRole)
        self._current_playlist_id = pl_id
        self._load_videos(pl_id)

    def _load_videos(self, playlist_id):
        self._video_list.clear()
        self._empty_video_label.hide()

        pl = self._playlist_service.get_playlist(playlist_id)
        if not pl:
            self._playlist_title.setText("Unknown Playlist")
            self._playlist_info.setText("")
            return

        self._playlist_title.setText(pl.name)
        count = len(pl.videos)
        self._playlist_info.setText(f"{count} video{'s' if count != 1 else ''}")

        if not pl.videos:
            self._video_list.hide()
            self._empty_video_label.show()
            return

        self._video_list.show()
        self._empty_video_label.hide()

        for v in pl.videos:
            display = f"{v.title}\n{v.channel}"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, v.to_dict())
            self._video_list.addItem(item)

    def _on_video_double_clicked(self, item):
        vdata = item.data(Qt.ItemDataRole.UserRole)
        if not vdata:
            return
        video_id = vdata.get("videoId", vdata.get("id", ""))
        if video_id:
            self.play_video_requested.emit(video_id, "", vdata)

    def _on_create(self):
        name, ok = QInputDialog.getText(self, "New Playlist", "Playlist name:")
        if ok and name.strip():
            self._playlist_service.create_playlist(name.strip())

    def _on_playlist_event(self, event):
        self._load_playlists()
        if self._current_playlist_id:
            self._load_videos(self._current_playlist_id)

    def _on_playlist_context(self, pos):
        item = self._playlist_list.itemAt(pos)
        if not item:
            return
        pl_id = item.data(Qt.ItemDataRole.UserRole)
        if pl_id == "watch-later":
            return

        menu = QMenu(self)
        rename_action = menu.addAction(icons.edit(18), "Rename")
        delete_action = menu.addAction(icons.delete(18), "Delete")
        action = menu.exec(self._playlist_list.mapToGlobal(pos))
        if action == rename_action:
            new_name, ok = QInputDialog.getText(self, "Rename Playlist", "New name:")
            if ok and new_name.strip():
                self._playlist_service.rename_playlist(pl_id, new_name.strip())
        elif action == delete_action:
            reply = QMessageBox.question(
                self, "Delete Playlist", "Delete this playlist?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._playlist_service.delete_playlist(pl_id)

    def _on_video_context(self, pos):
        item = self._video_list.itemAt(pos)
        if not item:
            return
        vdata = item.data(Qt.ItemDataRole.UserRole)
        if not vdata:
            return
        video_id = vdata.get("videoId", vdata.get("id", ""))
        if not video_id or not self._current_playlist_id:
            return

        menu = QMenu(self)
        play_action = menu.addAction(icons.play(18), "Play")
        remove_action = menu.addAction(icons.delete(18), "Remove from Playlist")
        action = menu.exec(self._video_list.mapToGlobal(pos))
        if action == play_action:
            self._on_video_double_clicked(item)
        elif action == remove_action:
            self._playlist_service.remove_video(self._current_playlist_id, video_id)
