"""SVG icon cache behaviour."""

import pytest

from ui import icons

pytestmark = pytest.mark.qt


def test_repeated_icon_requests_share_one_instance(qapp):
    """Cards in a home row must not re-render the same SVG."""

    first = icons.play(20)
    second = icons.play(20)
    assert first is second


def test_icon_cache_is_keyed_by_size(qapp):
    assert icons.play(20) is not icons.play(24)


def test_clear_cache_forces_a_fresh_render(qapp):
    before = icons.search(20)
    icons.clear_cache()
    after = icons.search(20)
    assert after is not before


def test_distinct_svgs_use_separate_entries(qapp):
    icons.clear_cache()
    rect = "<svg viewBox='0 0 24 24'><rect width='24' height='24'/></svg>"
    circle = "<svg viewBox='0 0 24 24'><circle cx='12' cy='12' r='10'/></svg>"
    icons._icon(rect, 16)
    icons._icon(circle, 16)
    assert icons._icon.cache_info().currsize == 2


def test_new_playback_icons_render_properly(qapp):
    assert icons.fullscreen(20) is not None
    assert icons.fullscreen_exit(20) is not None
    assert icons.expand(20) is not None
