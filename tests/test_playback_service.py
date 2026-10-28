"""Playback orchestration: async resolution, cancellation, and commit ordering."""

import threading
import time

import pytest

from core.events import (
    PlaybackErrorEvent,
    StreamResolvedEvent,
    StreamResolveFailedEvent,
    StreamResolvingEvent,
    VideoStartedEvent,
)
from core.playback_errors import StreamCancelledError
from core.quality import ResolvedStream
from services.playback_service import PlaybackService
from services.player_service import PlayerService
from services.stream_resolver_service import StreamResolverService

FIRST = "aaaaaaaaaaa"
SECOND = "bbbbbbbbbbb"


def _wait_for(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class BlockingResolver:
    """First request blocks until cancelled; later requests resolve instantly."""

    def __init__(self):
        self.first_started = threading.Event()
        self.calls = []

    def resolve_metadata(self, video_id, cancel_event=None):
        return {"videoId": video_id, "title": video_id}

    def resolve_stream(
        self, video_id, quality="best", *, cancel_event=None, publish_events=True
    ):
        self.calls.append(video_id)
        if video_id == FIRST:
            self.first_started.set()
            if cancel_event is not None:
                cancel_event.wait(3)
            raise StreamCancelledError("superseded")
        return ResolvedStream(
            video_url=f"https://example.com/{video_id}", quality=quality
        )


class FailingResolver:
    def resolve_metadata(self, video_id, cancel_event=None):
        return {"videoId": video_id}

    def resolve_stream(self, *args, **kwargs):
        raise RuntimeError("network down")


class LateFailureResolver(BlockingResolver):
    """Blocks until cancelled, then fails without honouring cancellation."""

    def resolve_stream(
        self, video_id, quality="best", *, cancel_event=None, publish_events=True
    ):
        self.first_started.set()
        if cancel_event is not None:
            cancel_event.wait(3)
        raise RuntimeError("late failure")


class TestPlaybackService:
    def test_play_resolves_plays_and_forwards_audio(
        self, playback_service, fake_mpv, event_bus, mock_youtube_api
    ):
        events = []
        for name in (
            "stream_resolving",
            "stream_resolved",
            "video_started",
            "stream_resolve_failed",
        ):
            event_bus.subscribe(name, events.append, weak=False)

        token = playback_service.play(FIRST, "720p", {"videoId": FIRST})
        assert token == 1
        assert playback_service.wait(3.0)

        assert fake_mpv.play_calls == [
            ("https://example.com/stream", "720p", None)
        ]
        assert fake_mpv.audio_urls == ["https://example.com/audio"]

        kinds = [type(event) for event in events]
        assert kinds == [
            StreamResolvingEvent,
            StreamResolvedEvent,
            VideoStartedEvent,
        ]
        assert events[2].title == "Test Video"
        mock_youtube_api.extract_streams.assert_called_once()
        assert mock_youtube_api.extract_streams.call_args.args[:2] == (FIRST, "720p")

    def test_newer_request_cancels_older_resolution(self, event_bus, fake_mpv):
        resolver = BlockingResolver()
        player = PlayerService(fake_mpv, event_bus, monitor_interval=0)
        service = PlaybackService(resolver, player, event_bus=event_bus)
        try:
            service.play(FIRST, "720p", {"videoId": FIRST})
            assert resolver.first_started.wait(2.0)

            second_token = service.play(SECOND, "720p", {"videoId": SECOND})
            assert second_token == 2
            assert service.wait(3.0)

            assert fake_mpv.play_calls == [
                ("https://example.com/bbbbbbbbbbb", "720p", None)
            ]
        finally:
            service.shutdown()

    def test_stop_cancels_pending_resolution(self, event_bus, fake_mpv):
        resolver = BlockingResolver()
        player = PlayerService(fake_mpv, event_bus, monitor_interval=0)
        service = PlaybackService(resolver, player, event_bus=event_bus)
        try:
            service.play(FIRST, "720p", {"videoId": FIRST})
            assert resolver.first_started.wait(2.0)

            service.stop()
            assert service.wait(3.0)
            assert fake_mpv.play_calls == []
            assert fake_mpv.stopped == 0
        finally:
            service.shutdown()

    def test_resolution_failure_publishes_events_and_does_not_play(
        self, event_bus, fake_mpv
    ):
        player = PlayerService(fake_mpv, event_bus, monitor_interval=0)
        service = PlaybackService(FailingResolver(), player, event_bus=event_bus)
        events = []
        event_bus.subscribe("stream_resolve_failed", events.append, weak=False)
        event_bus.subscribe("playback_error", events.append, weak=False)
        try:
            service.play(FIRST, "720p", {"videoId": FIRST})
            assert service.wait(3.0)

            assert fake_mpv.play_calls == []
            assert [type(event) for event in events] == [
                StreamResolveFailedEvent,
                PlaybackErrorEvent,
            ]
            assert events[0].video_id == FIRST
            assert events[1].stage == "resolve"
            assert "network down" in service.last_error
        finally:
            service.shutdown()

    def test_stale_failure_is_silent(self, event_bus, fake_mpv):
        resolver = LateFailureResolver()
        player = PlayerService(fake_mpv, event_bus, monitor_interval=0)
        service = PlaybackService(resolver, player, event_bus=event_bus)
        events = []
        event_bus.subscribe("playback_error", events.append, weak=False)
        try:
            service.play(FIRST, "720p", {"videoId": FIRST})
            assert resolver.first_started.wait(2.0)
            service.stop()
            assert service.wait(3.0)

            # A superseded request that fails must not surface a UI error.
            assert events == []
            assert fake_mpv.play_calls == []
        finally:
            service.shutdown()

    def test_replay_resolves_again(self, playback_service, fake_mpv):
        playback_service.play(FIRST, "720p", {"videoId": FIRST})
        assert playback_service.wait(3.0)
        assert len(fake_mpv.play_calls) == 1

        fake_mpv.play_calls.clear()
        assert playback_service.replay() == 2
        assert playback_service.wait(3.0)
        assert fake_mpv.play_calls == [
            ("https://example.com/stream", "720p", None)
        ]

    def test_replay_without_history_returns_none(self, playback_service):
        assert playback_service.replay() is None

    def test_invalid_video_id_raises_before_work(self, playback_service):
        with pytest.raises(ValueError):
            playback_service.play("../bad", "720p")
        assert playback_service.last_request is None

    def test_is_resolving_transitions(self, event_bus, fake_mpv):
        resolver = BlockingResolver()
        player = PlayerService(fake_mpv, event_bus, monitor_interval=0)
        service = PlaybackService(resolver, player, event_bus=event_bus)
        try:
            service.play(FIRST, "720p")
            assert resolver.first_started.wait(2.0)
            assert service.is_resolving is True
            service.stop()
            assert service.wait(3.0)
            assert service.is_resolving is False
        finally:
            service.shutdown()

    def test_shutdown_cancels_and_is_idempotent(self, event_bus, fake_mpv):
        resolver = BlockingResolver()
        player = PlayerService(fake_mpv, event_bus, monitor_interval=0)
        service = PlaybackService(resolver, player, event_bus=event_bus)
        service.play(FIRST, "720p")
        assert resolver.first_started.wait(2.0)

        service.shutdown()
        service.shutdown()
        assert service.is_resolving is False
        with pytest.raises(RuntimeError):
            service.play(SECOND, "720p")


class TestPlaybackServiceWithRealResolver:
    def test_metadata_enrichment_uses_optionally_missing_title(
        self, event_bus, fake_mpv, mock_youtube_api
    ):
        resolver = StreamResolverService(event_bus=event_bus, youtube_api=mock_youtube_api)
        player = PlayerService(fake_mpv, event_bus, monitor_interval=0)
        service = PlaybackService(resolver, player, event_bus=event_bus)
        events = []
        event_bus.subscribe("video_started", events.append, weak=False)
        try:
            service.play(FIRST, "720p", {"videoId": FIRST})
            assert service.wait(3.0)

            mock_youtube_api.fetch_video_info.assert_called_once()
            assert events[0].title == "Test Video"
            assert events[0].channel == "Test Channel"
        finally:
            service.shutdown()

    def test_existing_metadata_is_not_overwritten(
        self, event_bus, fake_mpv, mock_youtube_api
    ):
        resolver = StreamResolverService(event_bus=event_bus, youtube_api=mock_youtube_api)
        player = PlayerService(fake_mpv, event_bus, monitor_interval=0)
        service = PlaybackService(resolver, player, event_bus=event_bus)
        events = []
        event_bus.subscribe("video_started", events.append, weak=False)
        try:
            service.play(
                FIRST, "720p", {"videoId": FIRST, "title": "Explicit"}
            )
            assert service.wait(3.0)

            mock_youtube_api.fetch_video_info.assert_not_called()
            assert events[0].title == "Explicit"
        finally:
            service.shutdown()
