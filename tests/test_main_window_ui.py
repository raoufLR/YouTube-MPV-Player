"""Main window integration: theming, geometry, shortcuts, profile switches."""

from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import QWidget

from core.event_bus import EventBus
from services.likes_service import LikesService
from services.player_service import PlayerService
from services.playlist_service import PlaylistService
from services.settings_service import SettingsService
from services.user_manager_service import UserManagerService
from tests.fakes import FakeMpvPlayer
from ui.pages.liked_page import LikedPage
from ui.window_state import clamp_geometry

pytestmark = pytest.mark.qt


def _page(label: str) -> QWidget:
    widget = QWidget()
    widget.setObjectName(label)
    return widget


def _make_window(monkeypatch, qapp, temp_dir, switch_result=None):
    import ui.main_window as main_window

    builders = {}
    for method, attribute in {
        "_build_home_page": "home_page",
        "_build_search_page": "search_page",
        "_build_history_page": "history_page",
        "_build_playlists_page": "playlists_page",
        "_build_liked_page": "liked_page",
        "_build_settings_page": "settings_page",
        "_build_profile_page": "profile_page",
        "_build_analytics_page": "analytics_page",
    }.items():
        builders[method] = getattr(main_window.MainWindow, method)

        def builder(self, attr=attribute, key=method):
            page = _page(key)
            setattr(self, attr, page)
            return page

        monkeypatch.setattr(main_window.MainWindow, method, builder)

    event_bus = EventBus()
    services = SimpleNamespace(
        settings_service=SettingsService(data_dir=temp_dir),
        player_service=PlayerService(FakeMpvPlayer(), event_bus),
        thumbnail_service=SimpleNamespace(),
        user_manager_service=UserManagerService(base_dir=temp_dir),
        history_service=SimpleNamespace(),
        likes_service=SimpleNamespace(),
        playlist_service=SimpleNamespace(),
        recommendation_service=SimpleNamespace(),
        search_service=SimpleNamespace(),
        stream_resolver_service=SimpleNamespace(),
    )

    class FakeApplication:
        def __init__(self):
            self.event_bus = event_bus
            self.services = services
            self.shut_down = False

        def switch_profile(self, name):
            return switch_result

        def shutdown(self):
            self.shut_down = True
            services.settings_service.shutdown()

    application = FakeApplication()
    window = main_window.MainWindow(application)
    return window, application, services, builders


def test_theme_is_applied_application_wide(monkeypatch, qapp, temp_dir):
    window, _, _, _ = _make_window(monkeypatch, qapp, temp_dir)
    try:
        stylesheet = qapp.styleSheet()
        assert stylesheet
        assert "QDialog" in stylesheet
        assert "QMenu" in stylesheet
        assert stylesheet == window._theme_manager.stylesheet()
    finally:
        window.close()
        qapp.setStyleSheet("")


def test_playback_shortcut_filter_lifecycle(monkeypatch, qapp, temp_dir):
    window, _, _, _ = _make_window(monkeypatch, qapp, temp_dir)
    assert window._shortcut_filter is not None
    window.close()
    assert window._shortcut_filter is None


def test_geometry_is_saved_on_close(monkeypatch, qapp, temp_dir):
    window, _, services, _ = _make_window(monkeypatch, qapp, temp_dir)
    window.resize(1000, 700)
    window.move(30, 40)
    expected_width = window.width()
    expected_height = window.height()

    window.close()

    settings = services.settings_service
    assert settings.get("window_width") == expected_width
    assert settings.get("window_height") == expected_height
    assert settings.get("window_x") == 30
    assert settings.get("window_y") == 40
    assert settings.get("window_maximized") is False


def test_geometry_is_restored_and_clamped(monkeypatch, qapp, temp_dir):
    services_settings = SettingsService(data_dir=temp_dir)
    services_settings.set("window_width", 1000)
    services_settings.set("window_height", 700)
    services_settings.set("window_x", 25)
    services_settings.set("window_y", 35)
    services_settings.shutdown()

    import ui.main_window as main_window

    for method, attribute in {
        "_build_home_page": "home_page",
        "_build_search_page": "search_page",
        "_build_history_page": "history_page",
        "_build_playlists_page": "playlists_page",
        "_build_liked_page": "liked_page",
        "_build_settings_page": "settings_page",
        "_build_profile_page": "profile_page",
        "_build_analytics_page": "analytics_page",
    }.items():
        def builder(self, attr=attribute, key=method):
            page = _page(key)
            setattr(self, attr, page)
            return page

        monkeypatch.setattr(main_window.MainWindow, method, builder)

    event_bus = EventBus()
    services = SimpleNamespace(
        settings_service=services_settings,
        player_service=PlayerService(FakeMpvPlayer(), event_bus),
        thumbnail_service=SimpleNamespace(),
        user_manager_service=UserManagerService(base_dir=temp_dir),
        history_service=SimpleNamespace(),
        likes_service=SimpleNamespace(),
        playlist_service=SimpleNamespace(),
        recommendation_service=SimpleNamespace(),
        search_service=SimpleNamespace(),
        stream_resolver_service=SimpleNamespace(),
    )

    class FakeApplication:
        def __init__(self):
            self.event_bus = event_bus
            self.services = services

        def switch_profile(self, name):
            return None

        def shutdown(self):
            pass

    window = main_window.MainWindow(FakeApplication())
    try:
        screen = qapp.primaryScreen().availableGeometry()
        expected = clamp_geometry(
            QRect(25, 35, 1000, 700),
            [screen],
            min_width=window.minimumWidth(),
            min_height=window.minimumHeight(),
        )
        assert window.width() == expected.width()
        assert window.height() == expected.height()
    finally:
        window.close()
        qapp.setStyleSheet("")


def test_failed_profile_switch_keeps_pages(monkeypatch, qapp, temp_dir):
    window, _, _, _ = _make_window(
        monkeypatch, qapp, temp_dir, switch_result=False
    )
    try:
        window._navigate_to("settings")
        page_count = window.stack.count()

        assert window._switch_profile("Missing") is False
        assert window.stack.count() == page_count
        assert "Could not switch" in window.status_bar.current_message()
    finally:
        window.close()
        qapp.setStyleSheet("")


def test_successful_profile_switch_rebuilds_pages(monkeypatch, qapp, temp_dir):
    window, _, _, _ = _make_window(monkeypatch, qapp, temp_dir, switch_result=None)
    try:
        window._navigate_to("settings")
        assert window._switch_profile("Default") is True
        assert window.stack.count() == 2  # home + search are eager
        assert "Default" in window.windowTitle()
        assert window.sidebar._buttons["home"].isChecked()
    finally:
        window.close()
        qapp.setStyleSheet("")


def test_build_liked_page_returns_real_page(monkeypatch, qapp, temp_dir):
    window, _, _, builders = _make_window(monkeypatch, qapp, temp_dir)
    try:
        event_bus = window._event_bus
        window._application.services.likes_service = LikesService(
            event_bus=event_bus, data_dir=temp_dir
        )
        window._application.services.playlist_service = PlaylistService(
            event_bus=event_bus, data_dir=temp_dir
        )
        page = builders["_build_liked_page"](window)
        assert isinstance(page, LikedPage)
        page.cleanup()
    finally:
        window.close()
        qapp.setStyleSheet("")


def test_fullscreen_toggle(monkeypatch, qapp, temp_dir):
    window, _, _, _ = _make_window(monkeypatch, qapp, temp_dir)
    try:
        assert not window.isFullScreen()
        assert not window.sidebar.isHidden()
        assert not window.header.isHidden()

        window.toggle_fullscreen()
        assert window.isFullScreen()
        assert window.sidebar.isHidden()
        assert window.header.isHidden()

        window.toggle_fullscreen()
        assert not window.isFullScreen()
        assert not window.sidebar.isHidden()
        assert not window.header.isHidden()
    finally:
        window.close()
        qapp.setStyleSheet("")


def test_show_video_player_and_navigation(monkeypatch, qapp, temp_dir):
    window, _, _, _ = _make_window(monkeypatch, qapp, temp_dir)
    try:
        # Simulate video started
        from core.events import VideoStartedEvent
        window._on_video_started(
            VideoStartedEvent(
                url="http://example.com",
                quality="720p",
                video_id="vid123",
                title="Sample",
                channel="Chan",
            )
        )
        assert not window.video_container.isHidden()
        assert window.stack.isHidden()

        # Navigate away to search page
        window._navigate_to("search")
        assert window.video_container.isHidden()
        assert not window.stack.isHidden()

        # Request returning to video player
        window.show_video_player()
        assert not window.video_container.isHidden()
        assert window.stack.isHidden()
    finally:
        window.close()
        qapp.setStyleSheet("")
