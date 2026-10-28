from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QLabel, QStackedWidget, QWidget

from core.event_bus import EventBus
from tests.fakes import FakeMpvPlayer
from ui.page_registry import PageRegistry

pytestmark = pytest.mark.qt


def _page(label: str) -> QWidget:
    widget = QWidget()
    widget.setObjectName(label)
    return widget


class TestPageRegistry:
    def test_pages_are_lazy_and_created_once(self, qapp):
        stack = QStackedWidget()
        registry = PageRegistry(stack)
        calls = []

        def factory():
            calls.append("home")
            return _page("home")

        registry.register("home", factory)
        assert registry.keys() == ["home"]
        assert not registry.is_created("home")
        assert calls == []

        page = registry.show("home")
        assert page is stack.currentWidget()
        assert registry.is_created("home")
        assert calls == ["home"]

        assert registry.show("home") is page
        assert calls == ["home"]
        assert stack.count() == 1

    def test_registered_order_drives_next_and_previous(self, qapp):
        stack = QStackedWidget()
        registry = PageRegistry(stack)
        for key in ("home", "history", "settings"):
            registry.register(key, lambda k=key: _page(k))

        registry.show("home")
        assert registry.current_key() == "home"
        assert registry.next_key() == "history"
        assert registry.next_key(-1) == "settings"

        registry.show("settings")
        assert registry.next_key() == "home"
        assert registry.previous_key() == "history"

    def test_unknown_key_raises(self, qapp):
        registry = PageRegistry(QStackedWidget())

        with pytest.raises(KeyError):
            registry.show("missing")
        assert registry.get("missing") is None

    def test_factory_must_return_widget(self, qapp):
        registry = PageRegistry(QStackedWidget())
        registry.register("broken", lambda: QLabel())

        page = registry.show("broken")
        assert isinstance(page, QLabel)

        bad = PageRegistry(QStackedWidget())
        bad.register("bad", lambda: object())
        with pytest.raises(TypeError):
            bad.show("bad")

    def test_duplicate_registration_rejected(self, qapp):
        registry = PageRegistry(QStackedWidget())
        registry.register("home", lambda: _page("home"))

        with pytest.raises(KeyError):
            registry.register("home", lambda: _page("home2"))

    def test_clear_removes_pages_and_factories(self, qapp):
        stack = QStackedWidget()
        registry = PageRegistry(stack)
        registry.register("home", lambda: _page("home"), eager=True)

        pages = registry.clear()

        assert len(pages) == 1
        assert stack.count() == 0
        assert registry.keys() == []
        assert registry.current_key() is None


class TestMainWindowNavigation:
    def _make_window(self, monkeypatch, qapp, temp_dir):
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

        from services.player_service import PlayerService
        from services.settings_service import SettingsService
        from services.user_manager_service import UserManagerService

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

            def shutdown(self):
                self.shut_down = True
                services.settings_service.shutdown()

            def switch_profile(self, name):
                services.user_manager_service.switch_profile(name)

        application = FakeApplication()
        window = main_window.MainWindow(application)
        return window, application

    def test_direct_navigation_creates_pages_without_index_math(
        self, monkeypatch, qapp, temp_dir
    ):
        window, application = self._make_window(monkeypatch, qapp, temp_dir)
        try:
            assert window.page_registry.keys() == [
                "home", "search", "history", "playlists",
                "liked", "settings", "profile", "analytics",
            ]
            assert window.stack.count() == 2

            window._navigate_to("settings")
            assert window.settings_page is not None
            assert window.stack.currentWidget() is window.settings_page
            assert window.stack.count() == 3

            window._navigate_to("playlists")
            assert window.playlists_page is not None
            assert window.stack.currentWidget() is window.playlists_page
            assert window.stack.count() == 4

            # Revisiting a page must not create a second copy.
            window._navigate_to("settings")
            assert window.stack.count() == 4
            assert window.stack.currentWidget() is window.settings_page
        finally:
            window.close()

        assert application.shut_down is True

    def test_next_and_previous_follow_registration_order(
        self, monkeypatch, qapp, temp_dir
    ):
        window, _ = self._make_window(monkeypatch, qapp, temp_dir)
        try:
            window._navigate_to("home")
            window._next_page()
            assert window.stack.currentWidget() is window.search_page

            window._next_page()
            assert window.stack.currentWidget() is window.history_page

            window._prev_page()
            assert window.stack.currentWidget() is window.search_page

            window._navigate_to("not-a-page")
            assert window.stack.currentWidget() is window.search_page
        finally:
            window.close()

    def test_search_navigation_uses_registry(self, monkeypatch, qapp, temp_dir):
        window, _ = self._make_window(monkeypatch, qapp, temp_dir)
        try:
            window._navigate_to("home")
            window._navigate_to("search")
            assert window.stack.currentWidget() is window.search_page
        finally:
            window.close()
