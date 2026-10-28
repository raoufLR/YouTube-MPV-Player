"""Playlist browsing page.

Playlist entries are serialized from :class:`models.Playlist` and therefore
carry ``video_id`` rather than the search-result ``videoId``.  Both spellings
are accepted here; previously only ``videoId``/``id`` were checked, which made
every playlist video unplayable.
"""

from __future__ import annotations

import contextlib

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.events import (
    EVENT_LIKE_CHANGED,
    EVENT_PLAYLIST_CREATED,
    EVENT_PLAYLIST_DELETED,
    EVENT_PLAYLIST_UPDATED,
    EVENT_THUMBNAIL_LOADED,
    EVENT_WATCH_LATER_TOGGLED,
    LikeChangedEvent,
    PlaylistDeletedEvent,
    ThumbnailLoadedEvent,
    WatchLaterToggledEvent,
)
from services.playlist_service import WATCH_LATER_ID
from ui import icons
from ui.components.video_card import extract_video_id
from ui.event_dispatcher import QtEventDispatcher
from ui.i18n import tr, trn
from ui.thumbnail_pixmaps import cached_pixmap, pixmap_loader, request_pixmap


class PlaylistsPage(QWidget):
    play_video_requested = pyqtSignal(str, str, object)
    like_toggled = pyqtSignal(object)
    watch_later_toggled = pyqtSignal(object)

    LIKE_MARK = "\u2665  "
    WL_MARK = "\u23F1  "
    PLAYLIST_THUMBNAIL_SIZE = (160, 90)
    VIDEO_THUMBNAIL_SIZE = (120, 68)

    def __init__(self, player_service, thumbnail_service, playlist_service,
                 event_bus, likes_service=None, parent=None):
        super().__init__(parent)
        self._player_service = player_service
        self._thumbnail_service = thumbnail_service
        self._playlist_service = playlist_service
        self._event_bus = event_bus
        self._likes_service = likes_service

        self._current_playlist_id = None
        self._video_items = {}
        self._items_by_thumbnail = {}
        self._subscriptions = []

        self._setup_ui()
        self._connect_signals()
        self._load_playlists()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(24, 20, 24, 8)

        title = QLabel(tr("Playlists"))
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
        left_label = QLabel(tr("Your Playlists"))
        left_label.setObjectName("playlistPanelLabel")
        left_header.addWidget(left_label)
        left_header.addStretch()

        self._create_btn = QPushButton(icons.add_playlist(18), "")
        self._create_btn.setObjectName("iconButton")
        self._create_btn.setToolTip(tr("Create Playlist"))
        self._create_btn.setAccessibleName(tr("Create Playlist"))
        self._create_btn.setFixedSize(36, 36)
        self._create_btn.clicked.connect(self._on_create)
        left_header.addWidget(self._create_btn)
        left_layout.addLayout(left_header)

        self._playlist_list = QListWidget()
        self._playlist_list.setIconSize(QSize(*self.PLAYLIST_THUMBNAIL_SIZE))
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

        self._playlist_title = QLabel(tr("Select a playlist"))
        self._playlist_title.setObjectName("playlistTitle")
        right_layout.addWidget(self._playlist_title)

        self._playlist_info = QLabel("")
        self._playlist_info.setObjectName("playlistInfo")
        right_layout.addWidget(self._playlist_info)

        self._video_list = QListWidget()
        self._video_list.setIconSize(QSize(*self.VIDEO_THUMBNAIL_SIZE))
        self._video_list.setSpacing(4)
        self._video_list.setUniformItemSizes(True)
        self._video_list.setWordWrap(True)
        self._video_list.itemDoubleClicked.connect(self._on_video_double_clicked)
        self._video_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._video_list.customContextMenuRequested.connect(self._on_video_context)
        right_layout.addWidget(self._video_list, 1)

        self._empty_video_label = QLabel(
            tr("This playlist is empty.\nAdd videos from the search results.")
        )
        self._empty_video_label.setObjectName("emptyState")
        self._empty_video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_video_label.hide()
        right_layout.addWidget(self._empty_video_label)

        splitter.addWidget(right_panel)
        splitter.setSizes([250, 450])
        layout.addWidget(splitter, 1)
        self.setLayout(layout)

    def _connect_signals(self):
        pixmap_loader().pixmap_ready.connect(self._on_pixmap_ready)
        if not self._event_bus:
            return
        self._subscriptions = [
            (EVENT_PLAYLIST_CREATED, QtEventDispatcher(self._on_playlist_event)),
            (EVENT_PLAYLIST_UPDATED, QtEventDispatcher(self._on_playlist_event)),
            (EVENT_PLAYLIST_DELETED, QtEventDispatcher(self._on_playlist_event)),
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
    # Playlist list
    # ------------------------------------------------------------------

    def _load_playlists(self):
        selected_id = self._current_playlist_id
        self._playlist_list.blockSignals(True)
        self._playlist_list.clear()

        playlists = self._playlist_service.get_all_playlists()
        target_item = None
        for playlist in sorted(
            playlists, key=lambda pl: (pl.id != WATCH_LATER_ID, pl.name.casefold())
        ):
            text = playlist.name
            if playlist.id == WATCH_LATER_ID:
                text = "\u23F0 " + text
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, playlist.id)
            item.setToolTip(
                trn("{count} video", "{count} videos", len(playlist.videos)).format(
                    count=len(playlist.videos)
                )
            )
            self._playlist_list.addItem(item)
            if playlist.id == selected_id:
                target_item = item

        if target_item is not None:
            self._playlist_list.setCurrentItem(target_item)
        self._playlist_list.blockSignals(False)

        if target_item is not None:
            self._current_playlist_id = selected_id
            self._load_videos(selected_id)
        else:
            self._current_playlist_id = None

    def _on_playlist_selected(self, current, previous):
        if current is None:
            return
        playlist_id = current.data(Qt.ItemDataRole.UserRole)
        self._current_playlist_id = playlist_id
        self._load_videos(playlist_id)

    # ------------------------------------------------------------------
    # Video list
    # ------------------------------------------------------------------

    def _load_videos(self, playlist_id):
        selected_video_id = ""
        current = self._video_list.currentItem()
        if current is not None:
            selected_video_id = extract_video_id(
                current.data(Qt.ItemDataRole.UserRole)
            )

        self._video_list.clear()
        self._video_items.clear()
        self._items_by_thumbnail.clear()
        self._empty_video_label.hide()

        playlist = self._playlist_service.get_playlist(playlist_id)
        if playlist is None:
            self._playlist_title.setText(tr("Unknown Playlist"))
            self._playlist_info.setText("")
            self._video_list.hide()
            return

        self._playlist_title.setText(playlist.name)
        count = len(playlist.videos)
        self._playlist_info.setText(
            trn("{count} video", "{count} videos", count).format(count=count)
        )

        if not playlist.videos:
            self._video_list.hide()
            self._empty_video_label.show()
            return

        self._video_list.show()
        self._empty_video_label.hide()

        for video in playlist.videos:
            vdata = video.to_dict()
            video_id = extract_video_id(vdata)
            markers = ""
            if self._is_liked(video_id):
                markers += self.LIKE_MARK
            if self._is_in_watch_later(video_id):
                markers += self.WL_MARK
            display = f"{markers}{video.title}\n{video.channel}"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, vdata)
            item.setToolTip(video.title)
            self._video_list.addItem(item)

            if video_id:
                self._video_items[video_id] = item
                if selected_video_id and video_id == selected_video_id:
                    self._video_list.setCurrentItem(item)

            thumb_url = vdata.get("thumbnail", "")
            if thumb_url:
                self._items_by_thumbnail[thumb_url] = item
                self._defer_thumbnail(thumb_url, item)

    def _is_liked(self, video_id: str) -> bool:
        if not video_id or self._likes_service is None:
            return False
        try:
            return bool(self._likes_service.is_liked(video_id))
        except Exception:
            return False

    def _is_in_watch_later(self, video_id: str) -> bool:
        if not video_id:
            return False
        try:
            return bool(self._playlist_service.is_in_watch_later(video_id))
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Thumbnails
    # ------------------------------------------------------------------

    def _defer_thumbnail(self, url: str, item: QListWidgetItem):
        if self._thumbnail_service is None:
            return
        try:
            data = self._thumbnail_service.load_thumbnail_data(url)
        except Exception:
            data = None
        if data is not None:
            QTimer.singleShot(
                0, lambda d=data, i=item, u=url: self._apply_thumbnail_cached(u, d, i)
            )

    def _apply_thumbnail_cached(self, url: str, data: bytes, item: QListWidgetItem):
        if self._items_by_thumbnail.get(url) is not item:
            return
        pixmap = request_pixmap(url, data, *self.VIDEO_THUMBNAIL_SIZE)
        if pixmap is not None:
            item.setIcon(QIcon(pixmap))

    def _on_thumbnail_loaded(self, event: ThumbnailLoadedEvent):
        item = self._items_by_thumbnail.get(event.item)
        if item is not None and event.icon:
            pixmap = request_pixmap(
                event.item, event.icon, *self.VIDEO_THUMBNAIL_SIZE
            )
            if pixmap is not None:
                item.setIcon(QIcon(pixmap))

    def _on_pixmap_ready(self, url: str, width: int, height: int):
        if (width, height) != self.VIDEO_THUMBNAIL_SIZE:
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

    def _video_id_from_item(self, item) -> str:
        if item is None:
            return ""
        return extract_video_id(item.data(Qt.ItemDataRole.UserRole))

    def _play_video_data(self, vdata):
        video_id = extract_video_id(vdata)
        if video_id:
            self.play_video_requested.emit(video_id, "", vdata)

    def _on_video_double_clicked(self, item):
        vdata = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if isinstance(vdata, dict):
            self._play_video_data(vdata)

    def _on_create(self):
        name, ok = QInputDialog.getText(
            self, tr("New Playlist"), tr("Playlist name:")
        )
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        if self._playlist_service.create_playlist(name) is None:
            QMessageBox.warning(
                self,
                tr("Cannot Create Playlist"),
                tr(
                    "A playlist named '{name}' already exists or the name is invalid."
                ).format(name=name),
            )

    def _on_playlist_event(self, event):
        if (
            isinstance(event, PlaylistDeletedEvent)
            and event.playlist_id == self._current_playlist_id
        ):
            self._current_playlist_id = None
        self._load_playlists()

    def _on_playlist_context(self, pos):
        item = self._playlist_list.itemAt(pos)
        if item is None:
            return
        playlist_id = item.data(Qt.ItemDataRole.UserRole)
        if playlist_id == WATCH_LATER_ID:
            return

        menu = QMenu(self)
        rename_action = menu.addAction(icons.edit(18), tr("Rename"))
        delete_action = menu.addAction(icons.delete(18), tr("Delete"))
        action = menu.exec(self._playlist_list.mapToGlobal(pos))
        if action is None:
            return

        if action == rename_action:
            new_name, ok = QInputDialog.getText(
                self, tr("Rename Playlist"), tr("New name:"), text=item.text()
            )
            if not ok:
                return
            new_name = new_name.strip()
            if not new_name:
                return
            if not self._playlist_service.rename_playlist(playlist_id, new_name):
                QMessageBox.warning(
                    self,
                    tr("Cannot Rename Playlist"),
                    tr("'{name}' is already in use or the name is invalid.").format(
                        name=new_name
                    ),
                )
        elif action == delete_action:
            reply = QMessageBox.question(
                self,
                tr("Delete Playlist"),
                tr("Delete this playlist?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            if not self._playlist_service.delete_playlist(playlist_id):
                QMessageBox.warning(
                    self,
                    tr("Cannot Delete Playlist"),
                    tr("The playlist could not be deleted."),
                )

    def _on_video_context(self, pos):
        item = self._video_list.itemAt(pos)
        vdata = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if not isinstance(vdata, dict):
            return
        video_id = extract_video_id(vdata)
        if not video_id or not self._current_playlist_id:
            return

        liked = self._is_liked(video_id)
        in_wl = self._is_in_watch_later(video_id)

        menu = QMenu(self)
        play_action = menu.addAction(icons.play(18), tr("Play"))
        menu.addSeparator()
        like_action = menu.addAction(tr("Unlike") if liked else tr("Like"))
        wl_action = menu.addAction(
            tr("Remove from Watch Later") if in_wl else tr("Add to Watch Later")
        )
        menu.addSeparator()
        remove_action = menu.addAction(icons.delete(18), tr("Remove from Playlist"))

        action = menu.exec(self._video_list.mapToGlobal(pos))
        if action is None:
            return
        if action == play_action:
            self._play_video_data(vdata)
        elif action == like_action:
            self.like_toggled.emit(vdata)
        elif action == wl_action:
            self.watch_later_toggled.emit(vdata)
        elif action == remove_action and not self._playlist_service.remove_video(
            self._current_playlist_id, video_id
        ):
            QMessageBox.warning(
                self,
                tr("Cannot Remove Video"),
                tr("The video is no longer part of this playlist."),
            )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _on_like_changed(self, event: LikeChangedEvent):
        self._refresh_video_row(event.video_id)

    def _on_watch_later_toggled(self, event: WatchLaterToggledEvent):
        self._refresh_video_row(event.video_id)

    def _refresh_video_row(self, video_id: str):
        if not video_id:
            return
        # A Watch Later toggle can add/remove the current playlist's contents;
        # the PlaylistUpdatedEvent handles that case.  Here we only refresh the
        # markers of an existing row.
        item = self._video_items.get(video_id)
        if item is None:
            return
        if self._current_playlist_id == WATCH_LATER_ID:
            return
        vdata = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(vdata, dict):
            return
        markers = ""
        if self._is_liked(video_id):
            markers += self.LIKE_MARK
        if self._is_in_watch_later(video_id):
            markers += self.WL_MARK
        title = vdata.get("title", tr("Unknown"))
        channel = vdata.get("channel", "")
        item.setText(f"{markers}{title}\n{channel}")
