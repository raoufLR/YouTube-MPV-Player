import logging
import re

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.events import (
    EVENT_PLAYBACK_ERROR,
)

from .event_dispatcher import QtEventDispatcher
from .header_widget import HeaderWidget
from .i18n import tr
from .now_playing_bar import NowPlayingBar
from .page_registry import PageRegistry
from .pages.analytics_page import AnalyticsPage
from .pages.history_page import HistoryPage
from .pages.home_page import HomePage
from .pages.liked_page import LikedPage
from .pages.playlists_page import PlaylistsPage
from .pages.profile_manager import ProfileManagerDialog
from .pages.profile_page import ProfilePage
from .pages.search_page import SearchPage
from .pages.settings_page import SettingsPage
from .shortcuts import PlaybackShortcutFilter
from .sidebar_widget import SidebarWidget
from .status_bar_widget import StatusBarWidget
from .themes import ThemeManager
from .window_state import restore_window_geometry, save_window_geometry

_logger = logging.getLogger(__name__)

PAGE_KEYS = (
    "home",
    "search",
    "history",
    "playlists",
    "liked",
    "settings",
    "profile",
    "analytics",
)

# Below this window width the sidebar switches to its icons-only rail; the
# pages need the horizontal space more than the navigation labels do.
SIDEBAR_COLLAPSE_WIDTH = 1100


class MainWindow(QMainWindow):

    def __init__(self, application):
        super().__init__()
        self._application = application
        self._event_bus = application.event_bus
        services = application.services
        self._subscriptions = []

        self.setWindowTitle(tr("YouTube MPV Player"))
        self.setGeometry(100, 100, 1280, 800)
        self.setMinimumSize(900, 600)
        self._settings_service = services.settings_service

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

        self.header = HeaderWidget(
            settings_service=services.settings_service,
            event_bus=self._event_bus,
        )
        right_layout.addWidget(self.header)

        # Embedded MPV container (no external window)
        self.video_container = QWidget()
        self.video_container.setObjectName("embeddedVideoContainer")
        self.video_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.video_container.mouseDoubleClickEvent = lambda event: self.toggle_fullscreen()
        self.video_container.hide()
        right_layout.addWidget(self.video_container, 1)

        self.stack = QStackedWidget()
        self.page_registry = PageRegistry(self.stack)
        self._create_pages(services)
        right_layout.addWidget(self.stack, 1)

        self.now_playing = NowPlayingBar(
            self._event_bus,
            services.player_service,
            services.thumbnail_service,
            playback_service=getattr(services, "playback_service", None),
        )
        right_layout.addWidget(self.now_playing)

        self.status_bar = StatusBarWidget()
        self.status_bar.error_retry_requested.connect(self._on_retry_playback)
        self.status_bar.open_in_browser_requested.connect(self._on_open_in_browser)
        right_layout.addWidget(self.status_bar)

        root_layout.addWidget(right_container, 1)
        self.setCentralWidget(self._central)

        self._theme_manager = ThemeManager(services.settings_service)
        self._theme_manager.theme_changed.connect(self._on_theme_changed)
        self._theme_manager.initialize(services.settings_service)

        self._shortcut_filter = None
        self._connect_internal()
        self._setup_shortcuts()
        self._install_shortcut_filter()
        self._update_header_avatar()
        self._update_window_title()

        # Restore last once every widget exists: ``showMaximized`` delivers a
        # resize event synchronously, and ``resizeEvent`` needs ``sidebar``.
        self._geometry_restored = restore_window_geometry(
            self, self._settings_service
        )

    def _on_theme_changed(self, theme_name: str):
        # Apply the theme to the whole application so dialogs, menus, message
        # boxes and tooltips are styled too, not just this window.
        stylesheet = self._theme_manager.stylesheet()
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(stylesheet)
        self.setStyleSheet(stylesheet)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.sidebar.set_collapsed(self.width() < SIDEBAR_COLLAPSE_WIDTH)

    # ------------------------------------------------------------------
    # Page registration / factories
    # ------------------------------------------------------------------

    def _reset_page_attributes(self):
        self.home_page = None
        self.search_page = None
        self.history_page = None
        self.playlists_page = None
        self.liked_page = None
        self.settings_page = None
        self.profile_page = None
        self.analytics_page = None

    def _create_pages(self, services=None):
        """Register every page and eagerly create the two startup pages."""
        self._reset_page_attributes()
        self.page_registry.register("home", self._build_home_page)
        self.page_registry.register("search", self._build_search_page)
        self.page_registry.register("history", self._build_history_page)
        self.page_registry.register("playlists", self._build_playlists_page)
        self.page_registry.register("liked", self._build_liked_page)
        self.page_registry.register("settings", self._build_settings_page)
        self.page_registry.register("profile", self._build_profile_page)
        self.page_registry.register("analytics", self._build_analytics_page)

        self.home_page = self.page_registry.ensure("home")
        self.search_page = self.page_registry.ensure("search")
        self.page_registry.show("home")

    def _build_home_page(self) -> HomePage:
        services = self._application.services
        page = HomePage(
            services.history_service,
            services.likes_service,
            services.playlist_service,
            services.user_manager_service,
            recommendation_service=services.recommendation_service,
            thumbnail_service=services.thumbnail_service,
            event_bus=self._event_bus,
        )
        page.play_video_requested.connect(self._on_play_video_requested)
        page.like_toggled.connect(self._on_like_toggled)
        page.watch_later_toggled.connect(self._on_watch_later_toggled)
        self.home_page = page
        return page

    def _build_search_page(self) -> SearchPage:
        services = self._application.services
        page = SearchPage(
            services.search_service,
            services.thumbnail_service,
            self._event_bus,
            likes_service=services.likes_service,
            playlist_service=services.playlist_service,
        )
        page.play_video_requested.connect(self._on_play_video_requested)
        page.like_toggled.connect(self._on_like_toggled)
        page.watch_later_toggled.connect(self._on_watch_later_toggled)
        page.search_finished.connect(self._on_search_finished)
        self.search_page = page
        return page

    def _build_history_page(self) -> HistoryPage:
        services = self._application.services
        page = HistoryPage(
            services.history_service,
            services.player_service,
            services.thumbnail_service,
            self._event_bus,
            likes_service=services.likes_service,
            playlist_service=services.playlist_service,
        )
        page.play_video_requested.connect(self._on_play_video_requested)
        page.like_toggled.connect(self._on_like_toggled)
        page.watch_later_toggled.connect(self._on_watch_later_toggled)
        self.history_page = page
        return page

    def _build_playlists_page(self) -> PlaylistsPage:
        services = self._application.services
        page = PlaylistsPage(
            services.player_service,
            services.thumbnail_service,
            services.playlist_service,
            self._event_bus,
            likes_service=services.likes_service,
        )
        page.play_video_requested.connect(self._on_play_video_requested)
        page.like_toggled.connect(self._on_like_toggled)
        page.watch_later_toggled.connect(self._on_watch_later_toggled)
        self.playlists_page = page
        return page

    def _build_liked_page(self) -> LikedPage:
        services = self._application.services
        page = LikedPage(
            services.likes_service,
            services.playlist_service,
            services.thumbnail_service,
            self._event_bus,
        )
        page.play_video_requested.connect(self._on_play_video_requested)
        page.like_toggled.connect(self._on_like_toggled)
        page.watch_later_toggled.connect(self._on_watch_later_toggled)
        self.liked_page = page
        return page

    def _build_settings_page(self) -> SettingsPage:
        services = self._application.services
        page = SettingsPage(
            services.settings_service,
            self._event_bus,
            self._theme_manager,
            update_service=getattr(services, "update_service", None),
            data_import_service=getattr(services, "data_import_service", None),
        )
        self.settings_page = page
        return page

    def _build_profile_page(self) -> ProfilePage:
        services = self._application.services
        page = ProfilePage(
            services.user_manager_service,
            services.history_service,
            services.likes_service,
            services.playlist_service,
        )
        self.profile_page = page
        return page

    def _build_analytics_page(self) -> AnalyticsPage:
        services = self._application.services
        page = AnalyticsPage(
            services.analytics_service,
            event_bus=self._event_bus,
        )
        self.analytics_page = page
        return page

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def _connect_internal(self):
        self.sidebar.page_changed.connect(self._on_page_changed)
        self.sidebar.profile_clicked.connect(self._on_profile_clicked)
        self.header.search_requested.connect(self._on_search_requested)
        self.now_playing.open_in_mpv.connect(self._on_restart_video)
        self.now_playing.show_video_requested.connect(self.show_video_player)
        self.now_playing.fullscreen_requested.connect(self.toggle_fullscreen)

        self._subscriptions.append(
            self._event_bus.subscribe(
                EVENT_PLAYBACK_ERROR,
                QtEventDispatcher(self._on_playback_error_event),
                weak=False,
            )
        )
        from core.events import EVENT_VIDEO_STARTED, EVENT_VIDEO_STOPPED

        self._subscriptions.append(
            self._event_bus.subscribe(
                EVENT_VIDEO_STARTED,
                QtEventDispatcher(self._on_video_started),
                weak=False,
            )
        )
        self._subscriptions.append(
            self._event_bus.subscribe(
                EVENT_VIDEO_STOPPED,
                QtEventDispatcher(self._on_video_stopped),
                weak=False,
            )
        )

    def _setup_shortcuts(self):
        pages = [
            "home",
            "search",
            "history",
            "playlists",
            "settings",
            "liked",
            "profile",
            "analytics",
        ]
        keys = [
            "Ctrl+1",
            "Ctrl+2",
            "Ctrl+3",
            "Ctrl+4",
            "Ctrl+5",
            "Ctrl+6",
            "Ctrl+7",
            "Ctrl+8",
        ]
        for key, page in zip(keys, pages):
            sc = QShortcut(QKeySequence(key), self)
            sc.activated.connect(lambda checked=False, p=page: self._navigate_to(p))

        next_sc = QShortcut(QKeySequence("Ctrl+Tab"), self)
        next_sc.activated.connect(self._next_page)

        prev_sc = QShortcut(QKeySequence("Ctrl+Shift+Tab"), self)
        prev_sc.activated.connect(self._prev_page)

    def _install_shortcut_filter(self):
        """Install the focus-aware playback key handler.

        Space/arrow/Escape are no longer ``QShortcut``s: a window shortcut
        fires even while the user types in the search box.  The event filter
        only claims keys when focus is not on a text, value, or item widget.
        """
        app = QApplication.instance()
        if app is None:
            return
        self._shortcut_filter = PlaybackShortcutFilter(self)
        self._shortcut_filter.play_pause_requested.connect(self._on_space_pressed)
        self._shortcut_filter.stop_requested.connect(self._on_esc_pressed)
        self._shortcut_filter.seek_requested.connect(self._seek_relative)
        self._shortcut_filter.volume_requested.connect(self._volume_relative)
        self._shortcut_filter.fullscreen_requested.connect(self.toggle_fullscreen)
        app.installEventFilter(self._shortcut_filter)

    def _remove_shortcut_filter(self):
        app = QApplication.instance()
        if app is not None and self._shortcut_filter is not None:
            app.removeEventFilter(self._shortcut_filter)
        self._shortcut_filter = None

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _navigate_to(self, page_key):
        try:
            self.page_registry.show(page_key)
        except KeyError:
            _logger.warning("Ignoring navigation to unknown page: %r", page_key)
            return None

        if self.video_container:
            self.video_container.hide()
        if self.stack:
            self.stack.show()

        if page_key == "home" and self.home_page:
            refresh = getattr(self.home_page, "refresh", None)
            if callable(refresh):
                refresh()
        elif page_key == "liked" and self.liked_page:
            refresh = getattr(self.liked_page, "refresh", None)
            if callable(refresh):
                refresh()
        elif page_key == "profile" and self.profile_page:
            load_profile = getattr(self.profile_page, "_load_profile", None)
            if callable(load_profile):
                load_profile()
        self.sidebar.set_active(page_key)
        return self.page_registry.get(page_key)

    def show_video_player(self):
        """Bring the embedded video player back into view at full size."""
        if self.stack:
            self.stack.hide()
        if self.video_container:
            self.video_container.show()
        self.sidebar.clear_selection()

    def toggle_fullscreen(self):
        """Toggle fullscreen mode for distraction-free video playback."""
        if self.isFullScreen():
            self.showNormal()
            self.sidebar.show()
            self.header.show()
            self.status_bar.show()
        else:
            self.sidebar.hide()
            self.header.hide()
            self.status_bar.hide()
            self.showFullScreen()

    def _ensure_page(self, page_key):
        return self.page_registry.ensure(page_key)

    def _next_page(self):
        key = self.page_registry.next_key(1)
        if key:
            self._navigate_to(key)

    def _prev_page(self):
        key = self.page_registry.next_key(-1)
        if key:
            self._navigate_to(key)

    def _on_page_changed(self, page_key):
        self._navigate_to(page_key)

    # ------------------------------------------------------------------
    # Application actions
    # ------------------------------------------------------------------

    def _on_space_pressed(self):
        srv = self._application.services.player_service if self._application else None
        if srv:
            srv.pause_resume()

    def _on_esc_pressed(self):
        if self.isFullScreen():
            self.toggle_fullscreen()
            return
        playback = (
            getattr(self._application.services, "playback_service", None)
            if self._application else None
        )
        if playback is not None:
            playback.stop()
            return
        srv = self._application.services.player_service if self._application else None
        if srv:
            srv.stop()

    def _seek_relative(self, seconds: int):
        srv = self._application.services.player_service if self._application else None
        if srv:
            srv.seek_relative(seconds)

    def _volume_relative(self, delta: int):
        srv = self._application.services.player_service if self._application else None
        if srv:
            current = srv.get_volume()
            srv.set_volume(max(0, min(100, current + delta)))

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

    def _on_profile_clicked(self):
        um = self._application.services.user_manager_service
        name, accepted = ProfileManagerDialog.open_manager(um, self)
        if accepted and name:
            current = um.current_profile_name()
            if name.casefold() != str(current or "").casefold():
                self._switch_profile(name)
        # Renaming the active profile does not switch profiles, so refresh the
        # header and title unconditionally after the dialog closes.
        self._update_header_avatar()
        self._update_window_title()

    def _switch_profile(self, profile_name: str) -> bool:
        self.status_bar.show_message(
            tr("Switching to profile '{name}'...").format(name=profile_name)
        )
        result = self._application.switch_profile(profile_name)
        if result is False:
            self.status_bar.show_error(
                tr("Could not switch to profile '{name}'.").format(name=profile_name)
            )
            return False

        services = self._application.services

        for page in self.page_registry.clear():
            cleanup = getattr(page, "cleanup", None)
            if callable(cleanup):
                try:
                    cleanup()
                except Exception:
                    _logger.exception("Page cleanup failed during profile switch")
            page.deleteLater()

        self._create_pages(services)
        self._update_header_avatar()
        self._update_window_title()
        self.sidebar.set_active("home")
        self.status_bar.show_ready()
        return True

    def _update_header_avatar(self):
        um = self._application.services.user_manager_service
        if um is None:
            return
        profile = um.current_profile()
        if profile:
            self.header.set_profile_avatar(profile.name, profile.avatar or "")

    def _update_window_title(self):
        um = getattr(self._application.services, "user_manager_service", None)
        name = ""
        if um is not None:
            try:
                name = um.current_profile_name() or ""
            except Exception:
                name = ""
        title = tr("YouTube MPV Player")
        if name:
            title = f"{title} \u2014 {name}"
        self.setWindowTitle(title)

    def _on_search_requested(self, query):
        video_id = self._extract_video_id(query)
        if video_id:
            # Metadata is fetched by PlaybackService in its worker so the UI
            # thread never blocks on yt-dlp for a pasted URL.
            self._start_playback(
                video_id,
                self.header.current_quality(),
                {"videoId": video_id},
            )
            return

        self.status_bar.show_searching()
        self._navigate_to("search")
        self.search_page.search(query)

    def _on_search_finished(self, success: bool, message: str):
        if success:
            self.status_bar.show_ready()
        else:
            self.status_bar.show_error(
                tr("Search failed: {message}").format(message=message)
                if message
                else tr("Search failed")
            )

    def _on_play_video_requested(self, video_id, quality, video_data):
        if not video_id:
            return
        if not quality:
            quality = self.header.current_quality()
        self._start_playback(video_id, quality, video_data)

    def _start_playback(self, video_id: str, quality: str, video_data):
        services = self._application.services if self._application else None
        playback = getattr(services, "playback_service", None) if services else None
        if playback is None:
            self.status_bar.show_error(tr("Playback service unavailable"))
            return

        if not quality:
            quality = self.header.current_quality()
        vdata = dict(video_data or {})
        vdata.setdefault("videoId", video_id)
        if self.video_container:
            self.video_container.show()
        if self.stack:
            self.stack.hide()
        self.sidebar.clear_selection()
        win_id = int(self.video_container.winId()) if self.video_container else None

        self.status_bar.show_resolving()
        try:
            playback.play(video_id, quality, vdata, win_id=win_id)
        except ValueError as exc:
            self.status_bar.show_error(str(exc), allow_actions=True)
        except RuntimeError as exc:
            self.status_bar.show_error(
                tr("Playback unavailable: {message}").format(message=exc),
                allow_actions=True,
            )
        except Exception as exc:
            self.status_bar.show_error(
                tr("Playback failed: {message}").format(message=exc),
                allow_actions=True,
            )

    def _on_restart_video(self):
        services = self._application.services if self._application else None
        playback = getattr(services, "playback_service", None) if services else None
        if playback is None:
            return
        try:
            playback.replay()
        except Exception:
            _logger.debug("Unable to replay current video", exc_info=True)

    def _on_like_toggled(self, video_data):
        service = self._application.services.likes_service
        service.toggle_like(video_data)

    def _on_watch_later_toggled(self, video_data):
        service = self._application.services.playlist_service
        service.toggle_watch_later(video_data)

    def _on_video_started(self, event):
        if self.video_container:
            self.video_container.show()
        if self.stack:
            self.stack.hide()
        self.sidebar.clear_selection()
        self.status_bar.show_playing()

    def _on_video_stopped(self, event):
        if self.isFullScreen():
            self.toggle_fullscreen()
        if self.video_container:
            self.video_container.hide()
        if self.stack:
            self.stack.show()
        self.status_bar.show_ready()

    def _on_playback_error_event(self, event):
        if self.isFullScreen():
            self.toggle_fullscreen()
        if self.video_container:
            self.video_container.hide()
        if self.stack:
            self.stack.show()
        self.status_bar.show_error(
            tr("Playback error: {message}").format(message=event.error),
            allow_actions=True,
        )

    def _on_retry_playback(self):
        services = self._application.services if self._application else None
        playback = getattr(services, "playback_service", None) if services else None
        if playback is not None:
            playback.replay()

    def _on_open_in_browser(self):
        services = self._application.services if self._application else None
        playback = getattr(services, "playback_service", None) if services else None
        if playback is not None:
            last = playback.last_request
            if last:
                video_id = last[0]
                if video_id:
                    url = f"https://www.youtube.com/watch?v={video_id}"
                    QDesktopServices.openUrl(QUrl(url))

    def closeEvent(self, event):
        try:
            save_window_geometry(self, self._settings_service)
        except Exception:
            _logger.exception("Failed to save window geometry")
        self._remove_shortcut_filter()
        self.header.cleanup()
        self._application.shutdown()
        event.accept()
