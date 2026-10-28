"""Full-stack integration: MainWindow plus real services, fake MPV only.

Exercises a realistic playback lifecycle end to end without launching MPV
or touching the network:

* window construction on top of real services (no SimpleNamespace stubs)
* search flow through the real SearchPage worker thread
* card click -> PlaybackService worker -> FakeMpvPlayer -> Qt UI updates
* pause / seek / volume through the shortcut handlers
* the status-bar Retry and Open-in-Browser error actions
* event-bus propagation from a worker thread via QtEventDispatcher
* likes / watch-later persistence through the real services
* clean shutdown from ``window.close()``
"""

from __future__ import annotations

import os
import threading
import time
from types import SimpleNamespace

import pytest

import ui.main_window as main_window_module
from core.event_bus import EventBus
from core.events import (
    EVENT_STREAM_RESOLVE_FAILED,
    EVENT_VIDEO_PAUSED,
    EVENT_VIDEO_STARTED,
    EVENT_VIDEO_STOPPED,
    StreamResolveFailedEvent,
    VideoStartedEvent,
    VideoStoppedEvent,
)
from services.analytics_service import AnalyticsService
from services.history_service import HistoryService
from services.likes_service import LikesService
from services.playback_service import PlaybackService
from services.player_service import PlayerService
from services.playlist_service import PlaylistService
from services.recommendation_service import RecommendationService
from services.search_service import SearchService
from services.settings_service import SettingsService
from services.stream_resolver_service import StreamResolverService
from services.thumbnail_cache_service import ThumbnailCacheService
from services.user_manager_service import UserManagerService
from services.user_profile_service import UserProfileService
from tests.fakes import FakeMpvPlayer
from ui.main_window import MainWindow
from ui.pages.search_page import SearchPage

pytestmark = pytest.mark.qt

VID = "abc123def45"
STREAM_URL = "https://example.com/stream"
AUDIO_URL = "https://example.com/audio"
BROWSER_URL = f"https://www.youtube.com/watch?v={VID}"

SHUTDOWN_ORDER = (
    "recommendation_service",
    "playlist_service",
    "likes_service",
    "history_service",
    "user_profile_service",
    "analytics_service",
    "playback_service",
    "player_service",
    "settings_service",
)


class FakeApplication:
    """Application shell holding the real service graph."""

    def __init__(self, services, event_bus):
        self.services = services
        self.event_bus = event_bus
        self.shut_down = False
        self._switch_result = True

    def switch_profile(self, name):
        return self._switch_result

    def shutdown(self):
        if self.shut_down:
            return
        self.shut_down = True
        for name in SHUTDOWN_ORDER:
            service = getattr(self.services, name, None)
            stop = getattr(service, "shutdown", None)
            if callable(stop):
                stop()


@pytest.fixture
def fullapp(qapp, temp_dir, mock_youtube_api):
    """MainWindow wired to real services; MPV is faked in-memory."""
    # Keep the run hermetic: blank thumbnails so no service dials the network.
    mock_youtube_api.search_videos.return_value = [
        {**video, "thumbnail": ""}
        for video in mock_youtube_api.search_videos.return_value
    ]
    mock_youtube_api.fetch_video_info.return_value = {
        **mock_youtube_api.fetch_video_info.return_value,
        "thumbnail": "",
    }

    event_bus = EventBus()
    user_manager = UserManagerService(base_dir=temp_dir, event_bus=event_bus)
    user_manager.switch_profile("Default")
    profile_dir = user_manager.current_profile_dir()

    services = SimpleNamespace(
        settings_service=SettingsService(event_bus=event_bus, data_dir=profile_dir),
        analytics_service=AnalyticsService(event_bus=event_bus, data_dir=profile_dir),
        history_service=HistoryService(event_bus=event_bus, data_dir=profile_dir),
        likes_service=LikesService(event_bus=event_bus, data_dir=profile_dir),
        playlist_service=PlaylistService(event_bus=event_bus, data_dir=profile_dir),
        user_profile_service=UserProfileService(event_bus=event_bus, data_dir=profile_dir),
        user_manager_service=user_manager,
        search_service=SearchService(youtube_api=mock_youtube_api, event_bus=event_bus),
        thumbnail_service=ThumbnailCacheService(
            event_bus=event_bus,
            disk_dir=os.path.join(profile_dir, "cache", "thumbnails"),
        ),
        recommendation_service=RecommendationService(
            youtube_api=mock_youtube_api, event_bus=event_bus
        ),
    )

    fake_mpv = FakeMpvPlayer()
    player = PlayerService(mpv_player=fake_mpv, event_bus=event_bus, monitor_interval=0)
    resolver = StreamResolverService(event_bus=event_bus, youtube_api=mock_youtube_api)
    playback = PlaybackService(resolver, player, event_bus=event_bus)
    services.player_service = player
    services.stream_resolver_service = resolver
    services.playback_service = playback

    app = FakeApplication(services, event_bus)
    window = MainWindow(app)

    harness = SimpleNamespace(
        app=app,
        services=services,
        event_bus=event_bus,
        mpv=fake_mpv,
        window=window,
    )
    yield harness

    window.close()
    qapp.processEvents()
    window.deleteLater()
    qapp.processEvents()


def _wait_until(qapp, predicate, timeout=3.0, step=0.01):
    """Pump the Qt loop until predicate() holds or *timeout* elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(step)
    qapp.processEvents()
    return predicate()


def _subscribe(harness, event_types, callback):
    """Subscribe to event-type constants and keep the tokens alive."""
    subscriptions = [
        harness.event_bus.subscribe(event_type, callback, weak=False)
        for event_type in event_types
    ]
    return subscriptions


def _start_video(harness, qapp):
    """Run a search and click the result card's play button."""
    window = harness.window
    window._navigate_to("search")
    window.header.search_requested.emit("Test Video")
    assert _wait_until(
        qapp,
        lambda: VID in window.search_page._card_by_id
        and window.status_bar.current_message() == "Ready",
    )
    card = window.search_page._card_by_id[VID]
    card._play_btn.click()
    return card


def _stop_video(harness, qapp):
    window = harness.window
    window._on_esc_pressed()
    if not _wait_until(
        qapp,
        lambda: not harness.services.player_service.has_media
        and window.status_bar.current_message() == "Ready",
    ):
        raise AssertionError(
            f"stop did not settle: has_media={harness.services.player_service.has_media!r}"
            f" message={window.status_bar.current_message()!r}"
            f" mpv.stopped={harness.mpv.stopped!r}"
        )


# ---------------------------------------------------------------------------
# Window construction on real services
# ---------------------------------------------------------------------------

def test_window_builds_every_page_on_real_services(fullapp):
    window = fullapp.window
    assert isinstance(window.search_page, SearchPage)
    assert window.home_page is not None
    assert window.status_bar.current_message() == "Ready"

    for key in (
        "playlists", "liked", "history", "profile",
        "analytics", "settings", "home",
    ):
        page = window._navigate_to(key)
        assert page is not None
        assert window.page_registry.get(key) is page
        assert window.status_bar.current_message() == "Ready"


def test_search_flow_end_to_end(fullapp, qapp):
    window = fullapp.window
    window._navigate_to("search")
    window.header.search_requested.emit("Test Video")

    assert _wait_until(
        qapp,
        lambda: VID in window.search_page._card_by_id
        and window.status_bar.current_message() == "Ready",
    )

    card = window.search_page._card_by_id[VID]
    assert card.video_id() == VID
    assert card.video_data()["title"] == "Test Video"


# ---------------------------------------------------------------------------
# Full playback round trip
# ---------------------------------------------------------------------------

def test_click_card_play_pause_seek_volume_stop(fullapp, qapp):
    window = fullapp.window
    services = fullapp.services
    mpv = fullapp.mpv

    seen = []
    _subscribe(
        harness=fullapp,
        event_types=(EVENT_VIDEO_STARTED, EVENT_VIDEO_STOPPED),
        callback=seen.append,
    )

    assert window.status_bar.current_message() == "Ready"
    _start_video(fullapp, qapp)

    # PlaybackService worker resolved the stream; MPV received both URLs.
    assert _wait_until(
        qapp,
        lambda: bool(mpv.play_calls) and mpv.current_url == STREAM_URL,
    )
    assert mpv.audio_urls[-1] == AUDIO_URL
    assert mpv.play_calls[-1][2] is not None  # embedded winId propagated

    # QtEventDispatcher turned the worker-thread event into UI state.
    assert _wait_until(
        qapp,
        lambda: window.status_bar.current_message() == "Playing"
        and not window.video_container.isHidden()
        and window.stack.isHidden(),
    )

    # History observed the start event through the bus.
    assert _wait_until(
        qapp,
        lambda: services.history_service.get_all()
        and services.history_service.get_all()[0]["id"] == VID,
    )

    # Pause/unpause via the Space shortcut path.
    window._on_space_pressed()
    assert _wait_until(qapp, lambda: services.player_service.is_paused)
    assert mpv.paused is True
    window._on_space_pressed()
    assert _wait_until(qapp, lambda: not services.player_service.is_paused)

    # Seek and volume through the shortcut handlers.
    window._seek_relative(30)
    assert (30.0, "absolute") in mpv.seeks
    window._volume_relative(10)
    assert services.player_service.get_volume() == 90

    # Stop via the Escape path: MPV teardown plus UI reset.
    window._on_esc_pressed()
    assert _wait_until(
        qapp,
        lambda: window.status_bar.current_message() == "Ready"
        and window.video_container.isHidden()
        and not window.stack.isHidden(),
    )
    assert mpv.stopped == 1
    assert mpv.process is None

    kinds = [type(event) for event in seen]
    assert VideoStartedEvent in kinds
    assert VideoStoppedEvent in kinds

    # A finished session (start + stop) was recorded by analytics.
    stats = services.analytics_service.get_stats()
    assert stats["videos_played"] >= 1
    assert stats["top_channels"].get("Test Channel", 0) >= 1


def test_pause_events_published_on_the_bus(fullapp, qapp):
    """VideoPausedEvent toggles reach every bus subscriber."""
    window = fullapp.window
    services = fullapp.services

    paused_events = []
    _subscribe(
        harness=fullapp,
        event_types=(EVENT_VIDEO_PAUSED,),
        callback=paused_events.append,
    )

    _start_video(fullapp, qapp)
    assert _wait_until(qapp, lambda: services.player_service.has_media)

    window._on_space_pressed()
    assert _wait_until(qapp, lambda: bool(paused_events))

    window._on_space_pressed()
    assert _wait_until(qapp, lambda: len(paused_events) >= 2)

    assert [event.is_paused for event in paused_events[:2]] == [True, False]

    _stop_video(fullapp, qapp)


# ---------------------------------------------------------------------------
# Status bar error actions (retry / open in browser)
# ---------------------------------------------------------------------------

def test_resolve_failure_shows_retry_and_browser_buttons(
    fullapp, qapp, mock_youtube_api,
):
    window = fullapp.window
    seen = []
    _subscribe(
        harness=fullapp,
        event_types=(EVENT_STREAM_RESOLVE_FAILED,),
        callback=seen.append,
    )
    mock_youtube_api.extract_streams.side_effect = RuntimeError("resolver down")

    _start_video(fullapp, qapp)
    assert any(isinstance(event, StreamResolveFailedEvent) for event in seen)

    assert _wait_until(
        qapp,
        lambda: window.status_bar.current_message() == "Playback error: resolver down",
    )
    assert not window.status_bar._retry_btn.isHidden()
    assert not window.status_bar._browser_btn.isHidden()

    # Retry once the resolver works again.
    mock_youtube_api.extract_streams.side_effect = None
    fullapp.mpv.current_url = None
    window.status_bar.error_retry_requested.emit()

    assert _wait_until(
        qapp,
        lambda: fullapp.mpv.current_url == STREAM_URL
        and window.status_bar.current_message() == "Playing",
    )

    _stop_video(fullapp, qapp)


def test_invalid_video_id_shows_error_actions(fullapp):
    fullapp.window._start_playback("not a valid id!!", "720p", {})
    assert fullapp.window.status_bar.current_message() != "Ready"
    assert not fullapp.window.status_bar._retry_btn.isHidden()
    assert not fullapp.window.status_bar._browser_btn.isHidden()


def test_open_in_browser_uses_last_request(fullapp, qapp, monkeypatch):
    opened = []

    class FakeDesktopServices:
        @staticmethod
        def openUrl(url):
            opened.append(url.toString())

    monkeypatch.setattr(main_window_module, "QDesktopServices", FakeDesktopServices)

    _start_video(fullapp, qapp)
    assert _wait_until(
        qapp,
        lambda: fullapp.mpv.current_url == STREAM_URL
        and fullapp.window.status_bar.current_message() == "Playing",
    )

    fullapp.window.status_bar.open_in_browser_requested.emit()
    assert opened == [BROWSER_URL]

    _stop_video(fullapp, qapp)


# ---------------------------------------------------------------------------
# Event bus -> Qt UI propagation from worker threads
# ---------------------------------------------------------------------------

def test_worker_thread_events_reach_the_ui(fullapp, qapp):
    window = fullapp.window

    def publish_started():
        fullapp.event_bus.publish(
            VideoStartedEvent(
                url=STREAM_URL,
                quality="720p",
                video_id=VID,
                title="Test Video",
                channel="Test Channel",
            )
        )

    thread = threading.Thread(target=publish_started, name="event-sim-start")
    thread.start()
    thread.join(timeout=2.0)

    assert _wait_until(
        qapp,
        lambda: window.status_bar.current_message() == "Playing"
        and not window.video_container.isHidden()
        and window.stack.isHidden(),
    )

    def publish_stopped():
        fullapp.event_bus.publish(
            VideoStoppedEvent(
                reason="ended", video_id=VID, position=10.0, duration=100.0
            )
        )

    thread = threading.Thread(target=publish_stopped, name="event-sim-stop")
    thread.start()
    thread.join(timeout=2.0)

    assert _wait_until(
        qapp,
        lambda: window.status_bar.current_message() == "Ready"
        and window.video_container.isHidden()
        and not window.stack.isHidden(),
    )


# ---------------------------------------------------------------------------
# Likes / watch-later flows through the page signals
# ---------------------------------------------------------------------------

def test_like_and_watch_later_persist_through_services(fullapp, qapp):
    window = fullapp.window
    services = fullapp.services
    data = {"videoId": VID, "title": "Test Video", "channel": "Test Channel"}

    window._on_like_toggled(data)
    assert _wait_until(qapp, lambda: services.likes_service.is_liked(VID))

    window._on_watch_later_toggled(data)
    assert _wait_until(qapp, lambda: services.playlist_service.is_in_watch_later(VID))

    # Toggling again removes the entries.
    window._on_like_toggled(data)
    window._on_watch_later_toggled(data)
    assert _wait_until(
        qapp,
        lambda: not services.likes_service.is_liked(VID)
        and not services.playlist_service.is_in_watch_later(VID),
    )


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------

def test_window_close_shuts_down_the_service_graph(fullapp, qapp):
    window = fullapp.window
    services = fullapp.services

    window.close()
    qapp.processEvents()

    assert fullapp.app.shut_down
    assert window._shortcut_filter is None
    assert services.player_service._shutdown is True

    with pytest.raises(RuntimeError):
        services.playback_service.play(VID)
