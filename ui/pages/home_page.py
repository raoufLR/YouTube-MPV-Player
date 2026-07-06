import threading

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea,
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject

from ui.components.home_section import HomeSection


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
    section_loaded = pyqtSignal(str, list)


class HomePage(QWidget):
    play_video_requested = pyqtSignal(str, str, object)
    like_toggled = pyqtSignal(object)
    watch_later_toggled = pyqtSignal(object)

    def __init__(self, history_service, likes_service, playlist_service,
                 user_manager_service, recommendation_service=None,
                 thumbnail_service=None, parent=None):
        super().__init__(parent)
        self._history_service = history_service
        self._likes_service = likes_service
        self._playlist_service = playlist_service
        self._user_manager = user_manager_service
        self._recommendation_service = recommendation_service
        self._thumbnail_service = thumbnail_service

        self._bridge = _SectionBridge()
        self._bridge.section_loaded.connect(self._on_section_loaded)

        self._sections: dict = {}
        self._loaded: set = set()

        self._setup_ui()
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
            section = HomeSection(section_title)
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
        for section_key in SECTION_LOADERS:
            self._load_section_async(section_key)

    def _load_section_async(self, section_key: str):
        loader_name = SECTION_LOADERS[section_key]
        kwargs_keys = SECTION_KWARGS[section_key]

        thread = threading.Thread(
            target=self._load_section_task,
            args=(section_key, loader_name, kwargs_keys),
            daemon=True,
            name=f"home-{section_key}",
        )
        thread.start()

    def _load_section_task(self, section_key: str, loader_name: str,
                           kwargs_keys: list):
        with _load_semaphore:
            self._do_load_section(section_key, loader_name, kwargs_keys)

    def _do_load_section(self, section_key: str, loader_name: str,
                         kwargs_keys: list):
        service = self._recommendation_service
        if not service:
            self._bridge.section_loaded.emit(section_key, [])
            return

        loader = getattr(service, loader_name, None)
        if not loader:
            self._bridge.section_loaded.emit(section_key, [])
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

        self._bridge.section_loaded.emit(section_key, videos)

    def _on_section_loaded(self, section_key: str, videos: list):
        section = self._sections.get(section_key)
        if not section:
            return
        self._loaded.add(section_key)
        section.set_videos(videos, thumbnail_service=self._thumbnail_service)

    def refresh(self):
        self._loaded.clear()
        for section_key, section in self._sections.items():
            section.show_skeleton(SKELETON_COUNT)
        self._load_all()

    def _on_play_requested(self, video_id, quality, video_data):
        self.play_video_requested.emit(video_id, quality, video_data)

    def _on_like_toggled(self, video_data):
        self.like_toggled.emit(video_data)

    def _on_watch_later_toggled(self, video_data):
        self.watch_later_toggled.emit(video_data)
