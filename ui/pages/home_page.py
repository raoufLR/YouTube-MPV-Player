import contextlib
import threading

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.events import EVENT_THUMBNAIL_LOADED
from ui.components.home_section import HomeSection
from ui.components.video_card import VideoCard
from ui.event_dispatcher import QtEventDispatcher
from ui.i18n import tr
from ui.thumbnail_pixmaps import cached_pixmap, pixmap_loader, request_pixmap

MAX_CONCURRENT_LOADS = 3
_load_semaphore = threading.BoundedSemaphore(MAX_CONCURRENT_LOADS)

SECTION_DEFS = [
    ("continue_watching", "Continue Watching"),
    ("recommended", "Recommended For You"),
    ("trending", "Trending"),
    ("history_based", "Based On Your History"),
    ("recently_played", "Recently Played"),
    ("watch_later_preview", "Watch Later"),
    ("liked_preview", "Liked Videos"),
]

SECTION_LOADERS = {
    "continue_watching": "get_continue_watching",
    "recommended": "get_recommended",
    "trending": "get_trending",
    "history_based": "get_history_based",
    "recently_played": "get_recently_played",
    "watch_later_preview": "get_watch_later_preview",
    "liked_preview": "get_liked_preview",
}

SECTION_KWARGS = {
    "continue_watching": ["history_service", "max_count"],
    "recommended": ["history_service", "likes_service", "playlist_service", "max_count"],
    "trending": ["max_count"],
    "history_based": ["history_service", "max_count"],
    "recently_played": ["history_service", "max_count"],
    "watch_later_preview": ["playlist_service", "max_count"],
    "liked_preview": ["likes_service", "max_count"],
}

SKELETON_COUNT = 6


class _SectionBridge(QObject):
    section_loaded = pyqtSignal(str, list, int)


class HomePage(QWidget):
    play_video_requested = pyqtSignal(str, str, object)
    like_toggled = pyqtSignal(object)
    watch_later_toggled = pyqtSignal(object)

    def __init__(self, history_service, likes_service, playlist_service,
                 user_manager_service, recommendation_service=None,
                 thumbnail_service=None, event_bus=None, parent=None):
        super().__init__(parent)
        self._history_service = history_service
        self._likes_service = likes_service
        self._playlist_service = playlist_service
        self._user_manager = user_manager_service
        self._recommendation_service = recommendation_service
        self._thumbnail_service = thumbnail_service
        self._event_bus = event_bus
        self._subscriptions = []

        self._bridge = _SectionBridge()
        self._bridge.section_loaded.connect(self._on_section_loaded)

        self._sections: dict = {}
        self._loaded: set = set()
        self._inflight: dict = {}
        self._load_generation = 0
        self._pending_refresh = False

        self._setup_ui()
        self._subscribe()
        self._load_all()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(24, 20, 24, 24)
        self._content_layout.setSpacing(28)

        for section_key, section_title in SECTION_DEFS:
            section = HomeSection(tr(section_title))
            section.show_skeleton(SKELETON_COUNT)
            section.play_requested.connect(self._on_play_requested)
            section.like_toggled.connect(self._on_like_toggled)
            section.watch_later_toggled.connect(self._on_watch_later_toggled)
            self._sections[section_key] = section
            self._content_layout.addWidget(section)

        self._content_layout.addStretch()
        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll, 1)
        self.setLayout(layout)

    def _load_all(self):
        self._start_loads(self._load_generation)

    def _start_loads(self, generation: int):
        for section_key in SECTION_LOADERS:
            if section_key in self._inflight:
                continue
            self._inflight[section_key] = generation
            self._load_section_async(section_key, generation)

    def _load_section_async(self, section_key: str, generation: int):
        loader_name = SECTION_LOADERS[section_key]
        kwargs_keys = SECTION_KWARGS[section_key]

        thread = threading.Thread(
            target=self._load_section_task,
            args=(section_key, loader_name, kwargs_keys, generation),
            daemon=True,
            name=f"home-{section_key}",
        )
        thread.start()

    def _load_section_task(self, section_key: str, loader_name: str,
                           kwargs_keys: list, generation: int):
        with _load_semaphore:
            self._do_load_section(section_key, loader_name, kwargs_keys, generation)

    def _do_load_section(self, section_key: str, loader_name: str,
                         kwargs_keys: list, generation: int = 0):
        service = self._recommendation_service
        if not service:
            self._bridge.section_loaded.emit(section_key, [], generation)
            return

        loader = getattr(service, loader_name, None)
        if not loader:
            self._bridge.section_loaded.emit(section_key, [], generation)
            return

        kwargs = {}
        for k in kwargs_keys:
            if k == "history_service":
                kwargs["history_service"] = self._history_service
            elif k == "likes_service":
                kwargs["likes_service"] = self._likes_service
            elif k == "playlist_service":
                kwargs["playlist_service"] = self._playlist_service
            elif k == "max_count":
                kwargs["max_count"] = 10

        try:
            videos = loader(**kwargs)
        except Exception:
            videos = []

        self._bridge.section_loaded.emit(section_key, videos, generation)

    def _on_section_loaded(self, section_key: str, videos: list,
                           generation: int = None):
        if generation is None:
            generation = self._load_generation
        self._inflight.pop(section_key, None)

        if generation == self._load_generation:
            section = self._sections.get(section_key)
            if section:
                self._loaded.add(section_key)
                section.set_videos(
                    videos,
                    thumbnail_service=self._thumbnail_service,
                    likes_service=self._likes_service,
                    playlist_service=self._playlist_service,
                )

        # A refresh requested while loads were running is coalesced into a
        # single re-run once the last stale section finishes.
        if not self._inflight and self._pending_refresh:
            self._pending_refresh = False
            self._start_loads(self._load_generation)

    def refresh(self):
        self._load_generation += 1
        self._loaded.clear()
        for section in self._sections.values():
            section.show_skeleton(SKELETON_COUNT)

        if self._inflight:
            # Previous loads are now stale; rerun everything when they finish
            # instead of piling another seven threads on top.
            self._pending_refresh = True
            return
        self._load_all()

    def _on_play_requested(self, video_id, quality, video_data):
        self.play_video_requested.emit(video_id, quality, video_data)

    def _on_like_toggled(self, video_data):
        self.like_toggled.emit(video_data)

    def _on_watch_later_toggled(self, video_data):
        self.watch_later_toggled.emit(video_data)

    # ------------------------------------------------------------------
    # Thumbnails
    # ------------------------------------------------------------------

    def _subscribe(self):
        if not self._event_bus:
            return
        self._subscriptions = [
            self._event_bus.subscribe(
                EVENT_THUMBNAIL_LOADED,
                QtEventDispatcher(self._on_thumbnail_loaded),
                weak=False,
            )
        ]
        pixmap_loader().pixmap_ready.connect(self._on_pixmap_ready)

    def _on_thumbnail_loaded(self, event):
        """Apply a background-downloaded thumbnail to every matching card.

        The cache returns ``None`` on a cold miss and later publishes the
        bytes; without this handler cards that were built before the image
        arrived kept the placeholder forever.
        """
        url = getattr(event, "item", "")
        data = getattr(event, "icon", None)
        if not url or not data:
            return
        pixmap = request_pixmap(
            url, data, VideoCard.THUMBNAIL_WIDTH, VideoCard.THUMBNAIL_HEIGHT
        )
        if pixmap is None:
            return
        for section in self._sections.values():
            section.apply_thumbnail(url, pixmap)

    def _on_pixmap_ready(self, url: str, width: int, height: int):
        if (width, height) != (VideoCard.THUMBNAIL_WIDTH, VideoCard.THUMBNAIL_HEIGHT):
            return
        pixmap = cached_pixmap(url, width, height)
        if pixmap is None:
            return
        for section in self._sections.values():
            section.apply_thumbnail(url, pixmap)

    def cleanup(self):
        for subscription in getattr(self, "_subscriptions", []):
            with contextlib.suppress(Exception):
                self._event_bus.unsubscribe(subscription)
        self._subscriptions = []
        with contextlib.suppress(TypeError, RuntimeError):
            pixmap_loader().pixmap_ready.disconnect(self._on_pixmap_ready)
