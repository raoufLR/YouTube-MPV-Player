import re

from PyQt6.QtWidgets import (
    QMainWindow, QMessageBox, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QShortcut, QKeySequence

from core.events import (
    EVENT_PLAYBACK_ERROR,
)
from .event_dispatcher import QtEventDispatcher
from .themes import ThemeManager
from .sidebar_widget import SidebarWidget
from .header_widget import HeaderWidget
from .status_bar_widget import StatusBarWidget
from .now_playing_bar import NowPlayingBar
from .pages.search_page import SearchPage
from .pages.history_page import HistoryPage
from .pages.playlists_page import PlaylistsPage
from .pages.settings_page import SettingsPage
from .pages.profile_page import ProfilePage
from .pages.home_page import HomePage
from .pages.profile_manager import ProfileManagerDialog

PAGE_IDS = {
    "home": 0,
    "search": 1,
    "history": 2,
    "playlists": 3,
    "liked": 4,
    "settings": 5,
    "profile": 6,
}


class MainWindow(QMainWindow):

    def __init__(self, application):
        super().__init__()
        self._application = application
        self._event_bus = application.event_bus
        services = application.services

        self.setWindowTitle("YouTube MPV Player")
        self.setGeometry(100, 100, 1280, 800)
        self.setMinimumSize(900, 600)

        self._central = QWidget()
        self._central.setObjectName("centralWidget")
        root_layout = QHBoxLayout(self._central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = SidebarWidget()
        root_layout.addWidget(self.sidebar)

        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.header = HeaderWidget()
        right_layout.addWidget(self.header)

        self.stack = QStackedWidget()
        self._create_pages(services)
        right_layout.addWidget(self.stack, 1)

        self.now_playing = NowPlayingBar(
            self._event_bus,
            services.player_service,
            services.thumbnail_service,
        )
        right_layout.addWidget(self.now_playing)

        self.status_bar = StatusBarWidget()
        right_layout.addWidget(self.status_bar)

        root_layout.addWidget(right_container, 1)
        self.setCentralWidget(self._central)

        self._theme_manager = ThemeManager(services.settings_service)
        self._theme_manager.theme_changed.connect(self._on_theme_changed)
        self._theme_manager.initialize(services.settings_service)

        self._connect_internal()
        self._setup_shortcuts()
        self._update_header_avatar()

    def _on_theme_changed(self, theme_name: str):
        self.setStyleSheet(self._theme_manager.stylesheet())

    def _create_pages(self, services):
        self.home_page = HomePage(
            services.history_service,
            services.likes_service,
            services.playlist_service,
            services.user_manager_service,
            recommendation_service=services.recommendation_service,
            thumbnail_service=services.thumbnail_service,
        )
        self.stack.addWidget(self.home_page)

        self.search_page = SearchPage(
            services.search_service,
            services.thumbnail_service,
            self._event_bus,
        )
        self.stack.addWidget(self.search_page)

        self.history_page = None
        self.playlists_page = None
        self.liked_page = None
        self.settings_page = None
        self.profile_page = None

    def _connect_internal(self):
        self.sidebar.page_changed.connect(self._on_page_changed)
        self.sidebar.profile_clicked.connect(self._on_profile_clicked)
        self.header.search_requested.connect(self._on_search_requested)
        self.now_playing.open_in_mpv.connect(self._on_open_in_mpv)

        self.home_page.play_video_requested.connect(self._on_play_video_requested)
        self.search_page.play_video_requested.connect(self._on_play_video_requested)

        self.home_page.like_toggled.connect(self._on_like_toggled)
        self.home_page.watch_later_toggled.connect(self._on_watch_later_toggled)
        self.search_page.like_toggled.connect(self._on_like_toggled)
        self.search_page.watch_later_toggled.connect(self._on_watch_later_toggled)

        self._event_bus.subscribe(EVENT_PLAYBACK_ERROR, QtEventDispatcher(self._on_playback_error_event), weak=False)

    def _setup_shortcuts(self):
        pages = ["home", "search", "history", "playlists", "settings"]
        keys = ["Ctrl+1", "Ctrl+2", "Ctrl+3", "Ctrl+4", "Ctrl+5"]
        for key, page in zip(keys, pages):
            sc = QShortcut(QKeySequence(key), self)
            sc.activated.connect(lambda checked=False, p=page: self._navigate_to(p))

        next_sc = QShortcut(QKeySequence("Ctrl+Tab"), self)
        next_sc.activated.connect(self._next_page)

        prev_sc = QShortcut(QKeySequence("Ctrl+Shift+Tab"), self)
        prev_sc.activated.connect(self._prev_page)

    def _navigate_to(self, page_key):
        self._ensure_page(page_key)
        idx = PAGE_IDS.get(page_key, 0)
        self.stack.setCurrentIndex(idx)
        if page_key == "profile" and self.profile_page:
            self.profile_page._load_profile()
        self.sidebar.set_active(page_key)

    def _ensure_page(self, page_key):
        if page_key == "history" and self.history_page is None:
            self.history_page = HistoryPage(
                self._application.services.history_service,
                self._application.services.player_service,
                self._application.services.thumbnail_service,
                self._event_bus,
            )
            self.stack.insertWidget(PAGE_IDS[page_key], self.history_page)
            self.history_page.play_video_requested.connect(self._on_play_video_requested)

        elif page_key == "playlists" and self.playlists_page is None:
            self.playlists_page = PlaylistsPage(
                self._application.services.player_service,
                self._application.services.thumbnail_service,
                self._application.services.playlist_service,
                self._event_bus,
            )
            self.stack.insertWidget(PAGE_IDS[page_key], self.playlists_page)
            self.playlists_page.play_video_requested.connect(self._on_play_video_requested)

        elif page_key == "liked" and self.liked_page is None:
            self.liked_page = QWidget()
            self.liked_page.setObjectName("likedPage")
            from PyQt6.QtWidgets import QLabel, QVBoxLayout
            liked_layout = QVBoxLayout(self.liked_page)
            liked_label = QLabel("Liked Videos")
            liked_label.setStyleSheet("font-size: 22px; font-weight: 700; color: #FFFFFF; padding: 24px;")
            liked_layout.addWidget(liked_label)
            liked_layout.addStretch()
            self.stack.insertWidget(PAGE_IDS[page_key], self.liked_page)

        elif page_key == "settings" and self.settings_page is None:
            self.settings_page = SettingsPage(
                self._application.services.settings_service,
                self._event_bus,
                self._theme_manager,
            )
            self.stack.insertWidget(PAGE_IDS[page_key], self.settings_page)

        elif page_key == "profile" and self.profile_page is None:
            self.profile_page = ProfilePage(
                self._application.services.user_manager_service,
                self._application.services.history_service,
                self._application.services.likes_service,
                self._application.services.playlist_service,
            )
            self.stack.insertWidget(PAGE_IDS[page_key], self.profile_page)
            self.profile_page._load_profile()

    def _next_page(self):
        current = self.stack.currentIndex()
        next_idx = (current + 1) % self.stack.count()
        self.stack.setCurrentIndex(next_idx)
        for key, idx in PAGE_IDS.items():
            if idx == next_idx:
                self.sidebar.set_active(key)
                break

    def _prev_page(self):
        current = self.stack.currentIndex()
        prev = (current - 1) % self.stack.count()
        self.stack.setCurrentIndex(prev)
        for key, idx in PAGE_IDS.items():
            if idx == prev:
                self.sidebar.set_active(key)
                break

    @staticmethod
    def _extract_video_id(url: str) -> str:
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})',
        ]
        for pattern in patterns:
            m = re.search(pattern, url)
            if m:
                return m.group(1)
        return ""

    def _on_page_changed(self, page_key):
        self._ensure_page(page_key)
        page_id = PAGE_IDS.get(page_key, 0)
        self.stack.setCurrentIndex(page_id)
        if page_key == "home":
            self.home_page.refresh()
        elif page_key == "profile" and self.profile_page:
            self.profile_page._load_profile()

    def _on_profile_clicked(self):
        um = self._application.services.user_manager_service
        name, accepted = ProfileManagerDialog.open_manager(um, self)
        if accepted and name:
            current = um.current_profile_name()
            if name != current:
                self._switch_profile(name)

    def _switch_profile(self, profile_name: str):
        self.status_bar.show_message(f"Switching to profile '{profile_name}'...")
        self._application.switch_profile(profile_name)
        services = self._application.services

        old_pages = [
            self.home_page, self.search_page,
            self.history_page, self.playlists_page,
            self.liked_page, self.settings_page, self.profile_page,
        ]
        for p in old_pages:
            if p is not None:
                self.stack.removeWidget(p)
                if hasattr(p, 'cleanup'):
                    p.cleanup()
                p.deleteLater()

        self._create_pages(services)
        self._connect_page_signals()
        self.status_bar.show_ready()

    def _update_header_avatar(self):
        um = self._application.services.user_manager_service
        profile = um.current_profile()
        if profile:
            self.header.set_profile_avatar(profile.name, profile.avatar or "")

    def _connect_page_signals(self):
        try:
            self.header.search_requested.disconnect()
        except TypeError:
            pass
        self._update_header_avatar()
        self.header.search_requested.connect(self._on_search_requested)
        self.home_page.play_video_requested.connect(self._on_play_video_requested)
        self.search_page.play_video_requested.connect(self._on_play_video_requested)
        self.home_page.like_toggled.connect(self._on_like_toggled)
        self.home_page.watch_later_toggled.connect(self._on_watch_later_toggled)
        self.search_page.like_toggled.connect(self._on_like_toggled)
        self.search_page.watch_later_toggled.connect(self._on_watch_later_toggled)

    def _on_search_requested(self, query):
        video_id = self._extract_video_id(query)
        if video_id:
            self._start_playback(video_id, self.header.current_quality(), None)
            return
        self.status_bar.show_searching()
        self.stack.setCurrentIndex(PAGE_IDS["search"])
        self.sidebar.set_active("search")
        self.search_page.search(query)

    def _on_play_video_requested(self, video_id, quality, video_data):
        if not video_id:
            return
        if not quality:
            quality = self.header.current_quality()
        self._start_playback(video_id, quality, video_data)

    def _start_playback(self, video_id: str, quality: str, video_data):
        self.status_bar.show_resolving()
        try:
            resolver = self._application.services.stream_resolver_service
            youtube_url = resolver.resolve_stream(video_id, quality)
            self._application.services.player_service.play_video(
                youtube_url, quality, video_data
            )
            self.status_bar.show_playing()
        except FileNotFoundError as e:
            self.status_bar.show_error(str(e))
            QMessageBox.critical(self, "Playback Error", str(e))
        except ValueError as e:
            self.status_bar.show_error(str(e))
            QMessageBox.warning(self, "Playback Error", str(e))
        except Exception as e:
            self.status_bar.show_error(f"Playback failed: {e}")
            QMessageBox.warning(self, "Playback Error", str(e))

    def _on_open_in_mpv(self):
        try:
            srv = self._application.services.player_service
            if srv.current_url:
                srv.play_video(srv.current_url, "best", None)
        except Exception:
            pass

    def _on_like_toggled(self, video_data):
        service = self._application.services.likes_service
        service.toggle_like(video_data)

    def _on_watch_later_toggled(self, video_data):
        service = self._application.services.playlist_service
        service.toggle_watch_later(video_data)

    def _on_playback_error_event(self, event):
        self.status_bar.show_error(f"Playback error: {event.error}")

    def closeEvent(self, event):
        self._application.shutdown()
        event.accept()
