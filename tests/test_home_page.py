"""Home feed refresh coalescing and card state seeding."""

from types import SimpleNamespace

import pytest
from PyQt6.QtGui import QPixmap

from ui.components.home_section import HomeSection
from ui.pages.home_page import SECTION_LOADERS, HomePage

pytestmark = pytest.mark.qt


@pytest.fixture
def no_thread_home(monkeypatch, qapp):
    calls = []

    def fake_async(self, section_key, generation):
        calls.append((section_key, generation))

    monkeypatch.setattr(HomePage, "_load_section_async", fake_async)
    page = HomePage(
        None,
        None,
        None,
        None,
        recommendation_service=None,
        thumbnail_service=None,
    )
    yield page, calls
    page.hide()


def test_initial_load_starts_every_section_once(no_thread_home):
    page, calls = no_thread_home
    assert len(calls) == len(SECTION_LOADERS)
    assert {generation for _, generation in calls} == {0}
    assert set(page._inflight) == set(SECTION_LOADERS)


def test_refresh_is_coalesced_while_loads_are_in_flight(no_thread_home):
    page, calls = no_thread_home
    page.refresh()
    page.refresh()

    assert page._pending_refresh is True
    assert len(calls) == len(SECTION_LOADERS)

    # Finish the stale generation; exactly one new run is scheduled.
    for key in list(SECTION_LOADERS):
        page._on_section_loaded(key, [], 0)

    assert page._pending_refresh is False
    assert len(calls) == 2 * len(SECTION_LOADERS)
    assert {generation for _, generation in calls[len(SECTION_LOADERS):]} == {2}
    assert set(page._inflight) == set(SECTION_LOADERS)


def test_stale_results_are_not_rendered(no_thread_home):
    page, _ = no_thread_home
    page.refresh()
    for key in list(SECTION_LOADERS):
        page._on_section_loaded(key, [{"videoId": "stale"}], 0)

    assert page._loaded == set()


def test_refresh_starts_immediately_when_idle(no_thread_home):
    page, calls = no_thread_home
    page._inflight.clear()

    page.refresh()

    assert page._pending_refresh is False
    assert len(calls) == 2 * len(SECTION_LOADERS)
    assert {generation for _, generation in calls[len(SECTION_LOADERS):]} == {1}


def test_refresh_without_inflight_renders_new_results(no_thread_home):
    page, _ = no_thread_home
    page._inflight.clear()
    page.refresh()

    for key in list(SECTION_LOADERS):
        page._on_section_loaded(key, [], 1)

    assert page._loaded == set(SECTION_LOADERS)
    assert page._inflight == {}


def test_home_section_seeds_like_and_watch_later_state(qapp):
    likes = SimpleNamespace(is_liked=lambda vid: vid == "v1")
    playlists = SimpleNamespace(is_in_watch_later=lambda vid: vid == "v2")
    section = HomeSection("Test")

    section.set_videos(
        [{"videoId": "v1"}, {"videoId": "v2"}, {"videoId": "v3"}],
        likes_service=likes,
        playlist_service=playlists,
    )

    cards = [
        section._scroll_layout.itemAt(i).widget()
        for i in range(section._scroll_layout.count() - 1)
    ]
    assert [card.is_liked() for card in cards] == [True, False, False]
    assert [card.is_watch_later() for card in cards] == [False, True, False]


def test_cards_do_not_overlap_after_skeleton_to_video_transition(qapp):
    from PyQt6.QtCore import QCoreApplication

    section = HomeSection("Test")
    section.resize(1000, 320)
    section.show()
    section.show_skeleton(6)
    QCoreApplication.processEvents()

    section.set_videos([{"videoId": f"v{i}", "title": f"Video {i}"} for i in range(10)])
    for _ in range(5):
        QCoreApplication.processEvents()

    cards = [
        section._scroll_layout.itemAt(i).widget()
        for i in range(section._scroll_layout.count() - 1)
    ]
    try:
        assert len(cards) == 10
        for previous, current in zip(cards, cards[1:]):
            assert current.x() >= previous.x() + previous.width(), (
                f"cards overlap: {previous.geometry()} vs {current.geometry()}"
            )
        required = (
            sum(card.width() for card in cards)
            + section._scroll_layout.spacing() * (len(cards) - 1)
        )
        assert section._scroll_content.width() >= required
    finally:
        section.hide()


# ---------------------------------------------------------------------------
# Asynchronous thumbnails
# ---------------------------------------------------------------------------

def _png_bytes(color="#336699"):
    from PyQt6.QtCore import QBuffer
    from PyQt6.QtGui import QColor, QPixmap

    pixmap = QPixmap(16, 9)
    pixmap.fill(QColor(color))
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    assert pixmap.save(buffer, "PNG")
    return bytes(buffer.data())


def _cards(section):
    return [
        section._scroll_layout.itemAt(i).widget()
        for i in range(section._scroll_layout.count() - 1)
    ]


def _loaded_cards(section):
    return [
        card for card in _cards(section)
        if card._pixmap is not None and not card._pixmap.isNull()
    ]


def test_home_section_keeps_thumbnail_index_per_url(qapp):
    section = HomeSection("Test")
    url = "https://i.ytimg.com/vi/a/hq.jpg"
    section.set_videos([{"videoId": "v1", "thumbnail": url}])
    try:
        assert _loaded_cards(section) == []
        assert section.apply_thumbnail(url, QPixmap(4, 4)) == 1
        assert len(_loaded_cards(section)) == 1
        assert section.apply_thumbnail("https://i.ytimg.com/vi/other.jpg",
                                       QPixmap(4, 4)) == 0

        # Rebuilding the row must drop stale index entries.
        section.set_videos([{"videoId": "v2", "thumbnail": url}])
        assert _loaded_cards(section) == []
        assert section.apply_thumbnail(url, QPixmap(4, 4)) == 1
    finally:
        section.hide()


def test_thumbnail_event_updates_home_cards(qapp):
    from PyQt6.QtTest import QSignalSpy

    from core.event_bus import EventBus
    from core.events import ThumbnailLoadedEvent
    from ui.thumbnail_pixmaps import pixmap_loader

    bus = EventBus()
    page = HomePage(None, None, None, None, event_bus=bus)
    page._load_section_async = lambda *a, **k: None
    # In-flight loads started by the constructor would overwrite the rows
    # installed below once the event loop runs; make them stale.
    page._load_generation += 1
    url = "https://i.ytimg.com/vi/a/hq.jpg"

    try:
        page._sections["recommended"].set_videos(
            [{"videoId": "v1", "thumbnail": url}]
        )
        page._sections["trending"].set_videos(
            [{"videoId": "v2", "thumbnail": url}]
        )
        assert _loaded_cards(page._sections["recommended"]) == []

        spy = QSignalSpy(pixmap_loader().pixmap_ready)
        bus.publish(ThumbnailLoadedEvent(item=url, icon=_png_bytes()))

        assert spy.wait(2000)
        for key in ("recommended", "trending"):
            loaded = _loaded_cards(page._sections[key])
            assert len(loaded) == 1
            assert loaded[0]._pixmap.width() == 260
    finally:
        page.cleanup()
        page.hide()


def test_thumbnail_event_with_invalid_payload_is_ignored(qapp):
    from core.event_bus import EventBus
    from core.events import ThumbnailLoadedEvent

    bus = EventBus()
    page = HomePage(None, None, None, None, event_bus=bus)
    page._load_section_async = lambda *a, **k: None
    page._load_generation += 1
    url = "https://i.ytimg.com/vi/invalid/hq.jpg"
    try:
        page._sections["recommended"].set_videos(
            [{"videoId": "v1", "thumbnail": url}]
        )
        bus.publish(ThumbnailLoadedEvent(item=url, icon=b"not-an-image"))
        bus.publish(ThumbnailLoadedEvent(item=None, icon=None))

        assert _loaded_cards(page._sections["recommended"]) == []
    finally:
        page.cleanup()
        page.hide()


def test_cleanup_unsubscribes_thumbnail_events(qapp):
    from core.event_bus import EventBus

    bus = EventBus()
    page = HomePage(None, None, None, None, event_bus=bus)
    page._load_section_async = lambda *a, **k: None
    assert page._subscriptions

    page.cleanup()

    assert page._subscriptions == []
    page.hide()
