"""Search page state seeding, status feedback, and playback badges."""

from types import SimpleNamespace

import pytest

from core.events import (
    PlaybackErrorEvent,
    StreamResolvedEvent,
    StreamResolvingEvent,
    VideoStartedEvent,
)
from ui.pages.search_page import SearchPage

pytestmark = pytest.mark.qt


@pytest.fixture
def thumbnail_service():
    return SimpleNamespace(load_thumbnail_data=lambda url: None)


@pytest.fixture
def page(qapp, event_bus, likes_service, playlist_service, thumbnail_service):
    widget = SearchPage(
        SimpleNamespace(),
        thumbnail_service,
        event_bus,
        likes_service=likes_service,
        playlist_service=playlist_service,
    )
    yield widget, likes_service, playlist_service, event_bus
    widget.cleanup()
    widget.hide()


def _video(video_id, title="Video"):
    return {
        "videoId": video_id,
        "title": title,
        "channel": "Channel",
        "thumbnail": "",
    }


def _feed(widget, videos, has_more=False, request_id=0):
    widget._on_results((videos, has_more, request_id), None)


def test_cards_seed_like_and_watch_later_state(page):
    widget, likes, playlists, _ = page
    likes.like({"video_id": "v1"})
    playlists.toggle_watch_later({"videoId": "v2"})

    _feed(widget, [_video("v1"), _video("v2"), _video("v3")])

    assert widget._card_by_id["v1"].is_liked() is True
    assert widget._card_by_id["v1"].is_watch_later() is False
    assert widget._card_by_id["v2"].is_liked() is False
    assert widget._card_by_id["v2"].is_watch_later() is True
    assert widget._card_by_id["v3"].is_watch_later() is False


def test_watch_later_event_updates_existing_card(page):
    widget, _, playlists, _ = page
    _feed(widget, [_video("v1")])
    card = widget._card_by_id["v1"]
    assert card.is_watch_later() is False

    playlists.toggle_watch_later({"videoId": "v1"})
    assert card.is_watch_later() is True

    playlists.toggle_watch_later({"videoId": "v1"})
    assert card.is_watch_later() is False


def test_stream_events_drive_playback_badge(page):
    widget, _, _, event_bus = page
    _feed(widget, [_video("v1")])
    card = widget._card_by_id["v1"]

    event_bus.publish(StreamResolvingEvent(video_id="v1"))
    assert "Resolving" in card._status_label.text()

    event_bus.publish(StreamResolvedEvent(video_id="v1"))
    assert card._status_label.isHidden() is True

    event_bus.publish(
        VideoStartedEvent(video_id="v1", url="stream", quality="720p")
    )
    assert "Playing" in card._status_label.text()

    event_bus.publish(PlaybackErrorEvent(video_id="v1", error="boom"))
    assert card._status_label.isHidden() is True


def test_successful_search_emits_finished(page):
    widget, _, _, _ = page
    finished = []
    widget.search_finished.connect(
        lambda ok, message: finished.append((ok, message))
    )
    _feed(widget, [_video("v1")])
    assert finished == [(True, "")]


def test_empty_result_sets_message(page):
    widget, _, _, _ = page
    widget._current_query = "nothing"
    _feed(widget, [])
    assert widget._empty_label.isHidden() is False
    assert "No results" in widget._empty_label.text()


def test_search_error_is_surfaced(page):
    widget, _, _, _ = page
    finished = []
    widget.search_finished.connect(
        lambda ok, message: finished.append((ok, message))
    )
    widget._is_loading = True

    widget._on_error("network down", 0)

    assert finished == [(False, "network down")]
    assert widget._empty_label.isHidden() is False
    assert "network down" in widget._empty_label.text()
    assert widget._is_loading is False


def test_stale_result_is_ignored(page):
    widget, _, _, _ = page
    widget._current_request_id = 5
    _feed(widget, [_video("old")], request_id=4)
    assert widget._card_by_id == {}


def test_clear_search_resets_state(page):
    widget, _, _, _ = page
    _feed(widget, [_video("v1")])
    widget._current_query = "query"
    widget.clear_search()

    assert widget._current_query == ""
    assert widget._card_by_id == {}
    assert widget._like_cache == {}
    assert widget._wl_cache == {}
    assert widget._empty_label.isHidden() is False
    assert "get started" in widget._empty_label.text()


def test_page_starts_with_a_prompt(page):
    widget, _, _, _ = page
    assert widget._empty_label.isHidden() is False
    assert "get started" in widget._empty_label.text()
