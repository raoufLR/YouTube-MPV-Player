import contextlib
import threading

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.events import (
    EVENT_LIKE_CHANGED,
    EVENT_PLAYBACK_ERROR,
    EVENT_STREAM_RESOLVED,
    EVENT_STREAM_RESOLVING,
    EVENT_THUMBNAIL_LOADED,
    EVENT_VIDEO_STARTED,
    EVENT_WATCH_LATER_TOGGLED,
    LikeChangedEvent,
    SearchCancelledEvent,
    WatchLaterToggledEvent,
)
from ui.components import SkeletonWidget, VideoCard
from ui.components.video_card import extract_video_id
from ui.event_dispatcher import QtEventDispatcher
from ui.i18n import tr
from ui.thumbnail_pixmaps import cached_pixmap, pixmap_loader, request_pixmap

LOADING_TEXT = "Loading more results..."


class SearchPage(QWidget):
    play_video_requested = pyqtSignal(str, str, object)
    like_toggled = pyqtSignal(object)
    watch_later_toggled = pyqtSignal(object)
    search_finished = pyqtSignal(bool, str)
    _search_results_ready = pyqtSignal(object, object)
    _search_failed = pyqtSignal(object, object)
    _thumbnail_ready = pyqtSignal(object, object)

    PAGE_SIZE = 30
    SCROLL_THRESHOLD = 300
    MAX_PAGES = 10
    CARDS_PER_ROW = 3

    def __init__(self, search_service, thumbnail_service, event_bus,
                 likes_service=None, playlist_service=None, parent=None):
        super().__init__(parent)
        self._search_service = search_service
        self._thumbnail_service = thumbnail_service
        self._event_bus = event_bus
        self._likes_service = likes_service
        self._playlist_service = playlist_service

        self._current_query = ""
        self._current_page = 0
        self._has_more = True
        self._is_loading = False

        self._request_counter = 0
        self._current_request_id = 0

        self._like_cache = {}
        self._wl_cache = {}
        self._resolving_ids = set()
        self._playing_id = ""

        self._card_by_id = {}
        self._skeletons = []
        self._subscriptions = []

        self._setup_ui()
        self._connect_signals()
        self._show_empty_message(tr("Search for videos to get started"))

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setObjectName("searchScroll")

        self._scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(self._scroll_content)
        self._scroll_layout.setContentsMargins(16, 8, 16, 16)
        self._scroll_layout.setSpacing(0)

        self._grid_widget = QWidget()
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(12)
        self._scroll_layout.addWidget(self._grid_widget)

        self._load_more_container = QWidget()
        self._load_more_layout = QVBoxLayout(self._load_more_container)
        self._load_more_layout.setContentsMargins(0, 12, 0, 12)
        self._load_more_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._load_more_label = QLabel(tr(LOADING_TEXT))
        self._load_more_label.setObjectName("loadMoreLabel")
        self._load_more_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._load_more_label.setVisible(False)
        self._load_more_layout.addWidget(self._load_more_label)
        self._scroll_layout.addWidget(self._load_more_container)

        self._empty_label = QLabel(tr("Search for videos to get started"))
        self._empty_label.setObjectName("emptyState")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setVisible(False)
        self._scroll_layout.addWidget(self._empty_label)

        self._scroll_layout.addStretch()
        self._scroll_area.setWidget(self._scroll_content)

        layout.addWidget(self._scroll_area)

        self._scroll_area.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self._scroll_area.verticalScrollBar().rangeChanged.connect(self._on_range_changed)

        self.setLayout(layout)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_grid_columns()

    def _update_grid_columns(self):
        width = self._scroll_area.viewport().width()
        if width < 500:
            self.CARDS_PER_ROW = 1
        elif width < 800:
            self.CARDS_PER_ROW = 2
        else:
            self.CARDS_PER_ROW = 3

    def _connect_signals(self):
        self._search_results_ready.connect(self._on_results)
        self._search_failed.connect(self._on_error)
        self._thumbnail_ready.connect(self._apply_thumbnail_bytes)
        self._subscriptions = [
            (EVENT_THUMBNAIL_LOADED, QtEventDispatcher(self._on_thumbnail_loaded_event)),
            (EVENT_LIKE_CHANGED, QtEventDispatcher(self._on_like_changed)),
            (EVENT_WATCH_LATER_TOGGLED, QtEventDispatcher(self._on_watch_later_toggled)),
            (EVENT_STREAM_RESOLVING, QtEventDispatcher(self._on_stream_resolving)),
            (EVENT_STREAM_RESOLVED, QtEventDispatcher(self._on_stream_resolved)),
            (EVENT_VIDEO_STARTED, QtEventDispatcher(self._on_video_started)),
            (EVENT_PLAYBACK_ERROR, QtEventDispatcher(self._on_playback_error)),
        ]
        for event_type, cb in self._subscriptions:
            self._event_bus.subscribe(event_type, cb, weak=False)

        pixmap_loader().pixmap_ready.connect(self._on_pixmap_ready)

    def cleanup(self):
        for event_type, cb in getattr(self, '_subscriptions', []):
            self._event_bus.unsubscribe(event_type, cb)
        self._subscriptions = []
        with contextlib.suppress(TypeError, RuntimeError):
            pixmap_loader().pixmap_ready.disconnect(self._on_pixmap_ready)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query):
        if hasattr(self, '_search_thread') and self._search_thread and self._search_thread.is_alive():
            self._search_cancel_event.set()
        self._search_cancel_event = threading.Event()

        if self._current_query:
            self._event_bus.publish(SearchCancelledEvent(query=self._current_query))

        self._request_counter += 1
        self._current_request_id = self._request_counter

        self._current_query = query
        self._current_page = 0
        self._has_more = True
        self._is_loading = False

        self._resolving_ids.clear()
        self._like_cache.clear()
        self._wl_cache.clear()
        self._playing_id = ""

        self._clear_cards()
        self._empty_label.setVisible(False)
        self._load_more_label.setVisible(False)

        self._show_skeletons(6)
        self._load_page(query, 0)

    def _clear_cards(self):
        for i in reversed(range(self._grid.count())):
            w = self._grid.itemAt(i).widget()
            if w:
                self._grid.removeWidget(w)
                w.deleteLater()
        self._card_by_id.clear()
        self._skeletons.clear()
        self._playing_id = ""
        self._resolving_ids.clear()

    def _show_skeletons(self, count: int):
        for s in self._skeletons:
            self._grid.removeWidget(s)
            s.stop()
            s.deleteLater()
        self._skeletons.clear()
        cols = self.CARDS_PER_ROW
        row = 0
        for i in range(count):
            s = SkeletonWidget()
            self._skeletons.append(s)
            self._grid.addWidget(s, row, i % cols)
            if (i + 1) % cols == 0:
                row += 1

    def _hide_skeletons(self):
        for s in self._skeletons:
            self._grid.removeWidget(s)
            s.stop()
            s.deleteLater()
        self._skeletons.clear()

    def _load_page(self, query, page):
        if self._is_loading:
            return
        self._is_loading = True
        self._load_more_label.setVisible(True)

        request_id = self._current_request_id
        cancel_event = self._search_cancel_event

        def run():
            if cancel_event.is_set():
                return
            try:
                videos, has_more = self._search_service.search_page(
                    query, page=page, page_size=self.PAGE_SIZE
                )
                if not cancel_event.is_set():
                    self._search_results_ready.emit((videos, has_more, request_id), None)
            except Exception as e:
                if not cancel_event.is_set():
                    self._search_failed.emit(str(e), request_id)

        self._search_thread = threading.Thread(
            target=run, daemon=True, name="search-page-loader"
        )
        self._search_thread.start()

    def _on_results(self, data, _unused):
        videos, has_more, request_id = data
        if request_id != self._current_request_id:
            return
        self._hide_skeletons()
        self._is_loading = False
        self._has_more = has_more
        self._load_more_label.setVisible(False)
        first_page = self._current_page == 0

        if not videos:
            if not self._card_by_id:
                self._show_empty_message(
                    tr("No results for \u201c{query}\u201d").format(
                        query=self._current_query
                    )
                    if self._current_query
                    else tr("Search for videos to get started")
                )
            if first_page:
                self.search_finished.emit(True, "")
            return

        self._empty_label.setVisible(False)
        self._update_grid_columns()
        cols = self.CARDS_PER_ROW
        start_row = len(self._card_by_id) // cols
        col = len(self._card_by_id) % cols

        self._grid_widget.setUpdatesEnabled(False)
        for vid in videos:
            video_id = extract_video_id(vid)
            card = VideoCard(vid)
            card.play_requested.connect(self._on_card_play)
            card.like_toggled.connect(self._on_card_like)
            card.watch_later_toggled.connect(self._on_card_watch_later)
            self._grid.addWidget(card, start_row, col)
            if video_id:
                self._card_by_id[video_id] = card

            self._apply_initial_like_state(video_id, card)
            self._apply_initial_wl_state(video_id, card)
            self._apply_playback_state(video_id, card)

            thumb_url = vid.get("thumbnail", "")
            if thumb_url:
                data = self._thumbnail_service.load_thumbnail_data(thumb_url)
                if data is not None:
                    self._apply_thumbnail_bytes((data, thumb_url), card)

            col += 1
            if col >= cols:
                col = 0
                start_row += 1

        self._grid_widget.setUpdatesEnabled(True)

        self._current_page += 1
        QTimer.singleShot(0, self._check_auto_load)
        if first_page:
            self.search_finished.emit(True, "")

    def _on_error(self, error, request_id):
        if request_id != self._current_request_id:
            return
        self._hide_skeletons()
        self._is_loading = False
        self._load_more_label.setVisible(False)
        message = str(error or tr("Search failed"))
        if not self._card_by_id:
            self._show_empty_message(
                tr("Search failed: {message}").format(message=message)
            )
        self.search_finished.emit(False, message)

    def _show_empty_message(self, text: str):
        self._empty_label.setText(text)
        self._empty_label.setVisible(True)

    # ------------------------------------------------------------------
    # Video card signal handlers
    # ------------------------------------------------------------------

    def _on_card_play(self, video_id, quality, video_data):
        self.play_video_requested.emit(video_id, quality, video_data)

    def _on_card_like(self, video_data):
        self.like_toggled.emit(video_data)

    def _on_card_watch_later(self, video_data):
        self.watch_later_toggled.emit(video_data)

    # ------------------------------------------------------------------
    # Scroll
    # ------------------------------------------------------------------

    def _on_scroll(self, value):
        if self._is_loading or not self._has_more or not self._current_query:
            return
        scrollbar = self._scroll_area.verticalScrollBar()
        if scrollbar.maximum() - value < self.SCROLL_THRESHOLD:
            self._load_next_page()

    def _on_range_changed(self, min_val, max_val):
        if self._is_loading or not self._has_more or not self._current_query:
            return
        if max_val == 0:
            QTimer.singleShot(0, self._check_auto_load)

    def _check_auto_load(self):
        if self._is_loading or not self._has_more or not self._current_query:
            return
        scrollbar = self._scroll_area.verticalScrollBar()
        if scrollbar.maximum() <= 0:
            self._load_next_page()

    def _load_next_page(self):
        if self._is_loading or not self._has_more:
            return
        if self._current_page >= self.MAX_PAGES:
            self._has_more = False
            return
        self._load_page(self._current_query, self._current_page)

    # ------------------------------------------------------------------
    # Thumbnails
    # ------------------------------------------------------------------

    def _on_thumbnail_loaded_event(self, event):
        url = event.item
        data = event.icon
        if not url or not data:
            return
        for card in self._card_by_id.values():
            if card._thumbnail_url == url:
                self._thumbnail_ready.emit((data, url), card)
                return

    def _apply_thumbnail_bytes(self, payload, card):
        data, url = payload
        # Cached frames apply inline; a cold decode completes on the worker
        # pool and reaches the card through ``_on_pixmap_ready``.
        pixmap = request_pixmap(
            url, data, card.THUMBNAIL_WIDTH, card.THUMBNAIL_HEIGHT
        )
        if pixmap is not None:
            card.set_thumbnail(pixmap)

    def _on_pixmap_ready(self, url: str, width: int, height: int):
        pixmap = cached_pixmap(url, width, height)
        if pixmap is None:
            return
        for card in self._card_by_id.values():
            if card._thumbnail_url == url:
                card.set_thumbnail(pixmap)

    # ------------------------------------------------------------------
    # Like / Watch Later initial state
    # ------------------------------------------------------------------

    def _apply_initial_like_state(self, video_id: str, card: VideoCard):
        if not video_id:
            return
        if video_id not in self._like_cache and self._likes_service is not None:
            try:
                self._like_cache[video_id] = bool(
                    self._likes_service.is_liked(video_id)
                )
            except Exception:
                self._like_cache[video_id] = False
        card.set_liked(self._like_cache.get(video_id, False))

    def _apply_initial_wl_state(self, video_id: str, card: VideoCard):
        if not video_id:
            return
        if video_id not in self._wl_cache and self._playlist_service is not None:
            try:
                self._wl_cache[video_id] = bool(
                    self._playlist_service.is_in_watch_later(video_id)
                )
            except Exception:
                self._wl_cache[video_id] = False
        card.set_watch_later(self._wl_cache.get(video_id, False))

    def _apply_playback_state(self, video_id: str, card: VideoCard):
        card.set_playback_state(
            resolving=video_id in self._resolving_ids,
            playing=bool(video_id) and video_id == self._playing_id,
        )

    # ------------------------------------------------------------------
    # EventBus subscribers
    # ------------------------------------------------------------------

    def _on_like_changed(self, event: LikeChangedEvent):
        self._like_cache[event.video_id] = event.is_liked
        card = self._card_by_id.get(event.video_id)
        if card:
            card.set_liked(event.is_liked)

    def _on_watch_later_toggled(self, event: WatchLaterToggledEvent):
        self._wl_cache[event.video_id] = event.is_watch_later
        card = self._card_by_id.get(event.video_id)
        if card:
            card.set_watch_later(event.is_watch_later)

    def _on_stream_resolving(self, event):
        self._resolving_ids.add(event.video_id)
        card = self._card_by_id.get(event.video_id)
        if card:
            self._apply_playback_state(event.video_id, card)

    def _on_stream_resolved(self, event):
        self._resolving_ids.discard(event.video_id)
        card = self._card_by_id.get(event.video_id)
        if card:
            self._apply_playback_state(event.video_id, card)

    def _on_video_started(self, event):
        previous = self._playing_id
        self._playing_id = event.video_id
        for video_id in {previous, self._playing_id}:
            card = self._card_by_id.get(video_id)
            if card:
                self._apply_playback_state(video_id, card)

    def _on_playback_error(self, event):
        self._resolving_ids.discard(event.video_id)
        if self._playing_id == event.video_id:
            self._playing_id = ""
        card = self._card_by_id.get(event.video_id)
        if card:
            self._apply_playback_state(event.video_id, card)

    # ------------------------------------------------------------------
    # Clear
    # ------------------------------------------------------------------

    def clear_search(self):
        if self._current_query:
            self._event_bus.publish(SearchCancelledEvent(query=self._current_query))
        self._request_counter += 1
        self._current_request_id = self._request_counter
        self._current_query = ""
        self._current_page = 0
        self._has_more = True
        self._is_loading = False
        self._resolving_ids.clear()
        self._like_cache.clear()
        self._wl_cache.clear()
        self._playing_id = ""
        self._clear_cards()
        self._show_empty_message(tr("Search for videos to get started"))
        self._load_more_label.setVisible(False)
