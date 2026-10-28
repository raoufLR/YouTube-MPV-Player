import threading

import pytest

from core.events import (
    StreamResolvedEvent,
    StreamResolveFailedEvent,
    StreamResolvingEvent,
)
from core.playback_errors import StreamCancelledError, StreamResolutionError
from core.quality import ResolvedStream


class TestStreamResolverService:
    def test_resolve_stream_returns_watch_url_without_api(
        self, stream_resolver_service
    ):
        media = stream_resolver_service.resolve_stream("abc123def45", "720p")
        assert isinstance(media, ResolvedStream)
        assert media.video_url == "https://www.youtube.com/watch?v=abc123def45"
        assert media.audio_url == ""
        assert media.quality == "720p"

    def test_resolve_stream_publishes_events(self, stream_resolver_service, event_bus):
        events = []
        event_bus.subscribe("stream_resolving", events.append, weak=False)
        event_bus.subscribe("stream_resolved", events.append, weak=False)
        stream_resolver_service.resolve_stream("abc123def45", "720p")
        assert len(events) == 2
        assert isinstance(events[0], StreamResolvingEvent)
        assert events[0].video_id == "abc123def45"
        assert events[0].quality == "720p"
        assert isinstance(events[1], StreamResolvedEvent)
        assert events[1].video_id == "abc123def45"
        assert events[1].url == "https://www.youtube.com/watch?v=abc123def45"

    def test_resolve_stream_default_quality(self, stream_resolver_service):
        media = stream_resolver_service.resolve_stream("abc123def45")
        assert media.quality == "best"

    def test_resolve_stream_no_event_bus(self):
        from services.stream_resolver_service import StreamResolverService

        svc = StreamResolverService()
        media = svc.resolve_stream("abc123def45")
        assert media.video_url.startswith("https://www.youtube.com/watch")

    def test_uses_injected_api_and_forwards_audio_url(
        self, event_bus, mock_youtube_api
    ):
        from services.stream_resolver_service import StreamResolverService

        svc = StreamResolverService(event_bus=event_bus, youtube_api=mock_youtube_api)
        media = svc.resolve_stream("abc123def45", "1080p")

        assert media.video_url == "https://example.com/stream"
        assert media.audio_url == "https://example.com/audio"
        mock_youtube_api.extract_streams.assert_called_once_with(
            "abc123def45", "1080p", cancel_event=None
        )

    def test_failure_publishes_failure_event_and_raises(
        self, event_bus, mock_youtube_api
    ):
        from services.stream_resolver_service import StreamResolverService

        mock_youtube_api.extract_streams.side_effect = StreamResolutionError("boom")
        svc = StreamResolverService(event_bus=event_bus, youtube_api=mock_youtube_api)
        events = []
        event_bus.subscribe("stream_resolve_failed", events.append, weak=False)

        with pytest.raises(StreamResolutionError):
            svc.resolve_stream("abc123def45", "720p")

        assert len(events) == 1
        assert isinstance(events[0], StreamResolveFailedEvent)
        assert events[0].video_id == "abc123def45"
        assert "boom" in events[0].error

    def test_cancellation_is_silent(self, event_bus, mock_youtube_api):
        from services.stream_resolver_service import StreamResolverService

        mock_youtube_api.extract_streams.side_effect = StreamCancelledError("stop")
        svc = StreamResolverService(event_bus=event_bus, youtube_api=mock_youtube_api)
        events = []
        event_bus.subscribe("stream_resolve_failed", events.append, weak=False)

        with pytest.raises(StreamCancelledError):
            svc.resolve_stream("abc123def45")

        assert events == []

    def test_pre_cancelled_request_never_calls_api(self, mock_youtube_api):
        from services.stream_resolver_service import StreamResolverService

        cancel = threading.Event()
        cancel.set()
        svc = StreamResolverService(youtube_api=mock_youtube_api)

        with pytest.raises(StreamCancelledError):
            svc.resolve_stream("abc123def45", cancel_event=cancel)

        mock_youtube_api.extract_streams.assert_not_called()

    def test_invalid_video_id_rejected(self, stream_resolver_service):
        with pytest.raises(ValueError):
            stream_resolver_service.resolve_stream("../etc/passwd")

    def test_resolve_metadata_returns_stub_without_api(self, stream_resolver_service):
        assert stream_resolver_service.resolve_metadata("abc123def45") == {
            "videoId": "abc123def45"
        }

    def test_resolve_metadata_uses_api(self, mock_youtube_api):
        from services.stream_resolver_service import StreamResolverService

        svc = StreamResolverService(youtube_api=mock_youtube_api)
        info = svc.resolve_metadata("abc123def45")
        assert info["videoId"] == "abc123def45"
        assert info["title"] == "Test Video"

    def test_resolve_metadata_failure_is_best_effort(self, mock_youtube_api):
        from services.stream_resolver_service import StreamResolverService

        mock_youtube_api.fetch_video_info.side_effect = RuntimeError("offline")
        svc = StreamResolverService(youtube_api=mock_youtube_api)
        assert svc.resolve_metadata("abc123def45") == {"videoId": "abc123def45"}
