"""Window geometry persistence and clamping."""

from PyQt6.QtCore import QRect

from ui.window_state import (
    FALLBACK_SIZE,
    clamp_geometry,
    default_screen_rects,
    restore_window_geometry,
    save_window_geometry,
)


class FakeWindow:
    def __init__(self):
        self._width = 0
        self._height = 0
        self._pos = (0, 0)
        self.min_width = 640
        self.min_height = 480
        self.maximized = False
        self.maximized_calls = 0

    def minimumWidth(self):  # noqa: N802
        return self.min_width

    def minimumHeight(self):  # noqa: N802
        return self.min_height

    def resize(self, size):
        self._width, self._height = size.width(), size.height()

    def move(self, point):
        self._pos = (point.x(), point.y())

    def showMaximized(self):  # noqa: N802
        self.maximized = True
        self.maximized_calls += 1

    def isMaximized(self):  # noqa: N802
        return self.maximized

    def geometry(self):
        return QRect(self._pos[0], self._pos[1], self._width, self._height)

    def normalGeometry(self):  # noqa: N802
        return QRect(10, 20, 1024, 700)


class FakeSettings:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


SCREENS = [QRect(0, 0, 1920, 1080), QRect(1920, 0, 1280, 1024)]


def test_clamp_preserves_visible_geometry():
    rect = QRect(100, 100, 1200, 800)
    assert clamp_geometry(rect, SCREENS) == rect


def test_clamp_moves_offscreen_window_to_primary_screen():
    rect = QRect(5000, 5000, 800, 600)
    clamped = clamp_geometry(rect, SCREENS)
    assert clamped.size() == rect.size()
    assert any(
        screen.intersected(clamped).width() * screen.intersected(clamped).height()
        >= 120 * 80
        for screen in SCREENS
    )


def test_clamp_enforces_minimum_size_and_screen_bounds():
    clamped = clamp_geometry(
        QRect(0, 0, 10, 10), SCREENS, min_width=640, min_height=480
    )
    assert clamped.width() >= 640
    assert clamped.height() >= 480

    oversized = clamp_geometry(QRect(0, 0, 9000, 9000), SCREENS)
    assert oversized.width() <= 1920
    assert oversized.height() <= 1080


def test_clamp_accepts_invalid_screen_list_by_falling_back():
    clamped = clamp_geometry(QRect(0, 0, 300, 200), [])
    assert clamped.width() == 300
    assert clamped.height() == 200


def test_default_screen_rects_without_application(monkeypatch):
    import ui.window_state as window_state

    class _NoApplication:
        @staticmethod
        def instance():
            return None

    monkeypatch.setattr(window_state, "QApplication", _NoApplication)
    rects = default_screen_rects()
    assert rects and rects[0].size().width() == FALLBACK_SIZE[0]


def test_restore_returns_false_without_settings_or_geometry():
    window = FakeWindow()
    assert restore_window_geometry(window, None) is False
    assert restore_window_geometry(window, FakeSettings()) is False
    assert restore_window_geometry(
        window, FakeSettings({"window_width": 0, "window_height": 0})
    ) is False


def test_restore_applies_size_position_and_maximized():
    window = FakeWindow()
    settings = FakeSettings(
        {
            "window_width": 1000,
            "window_height": 700,
            "window_x": 50,
            "window_y": 60,
            "window_maximized": True,
        }
    )
    assert restore_window_geometry(window, settings, SCREENS) is True
    assert (window._width, window._height) == (1000, 700)
    assert window._pos == (50, 60)
    assert window.maximized_calls == 1


def test_restore_repairs_corrupt_values():
    window = FakeWindow()
    settings = FakeSettings({"window_width": "nope", "window_height": "bad"})
    assert restore_window_geometry(window, settings) is False


def test_save_stores_normal_geometry_while_maximized():
    window = FakeWindow()
    window.maximized = True
    settings = FakeSettings()
    save_window_geometry(window, settings)
    assert settings.values["window_maximized"] is True
    assert settings.values["window_width"] == 1024
    assert settings.values["window_height"] == 700


def test_save_skips_invalid_geometry():
    window = FakeWindow()
    settings = FakeSettings()
    save_window_geometry(window, settings)
    assert settings.values == {}
