"""Theme tokens must drive the generated stylesheet."""

import pytest

from ui.themes.theme_context import active_theme
from ui.themes.theme_manager import ThemeManager, hex_to_rgba

pytestmark = pytest.mark.qt


class TestHexToRgba:
    def test_converts_hex_with_alpha(self):
        assert hex_to_rgba("#3EA6FF", 0.15) == "rgba(62, 166, 255, 0.15)"

    def test_expands_short_hex(self):
        assert hex_to_rgba("#abc", 1) == "rgba(170, 187, 204, 1)"

    def test_keeps_unparseable_values(self):
        assert hex_to_rgba("not-a-color", 0.5) == "not-a-color"


def test_checked_states_follow_active_accent(qapp):
    manager = ThemeManager()
    manager.apply("youtube_dark")

    stylesheet = manager.stylesheet()

    assert "rgba(255, 0, 0, 0.15)" in stylesheet
    assert "rgba(62, 166, 255, 0.15)" not in stylesheet
    assert active_theme() is manager.theme
