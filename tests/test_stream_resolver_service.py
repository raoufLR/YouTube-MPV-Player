import pytest

from core.events import StreamResolvingEvent, StreamResolvedEvent


class TestStreamResolverService:
    def test_resolve_stream_returns_youtube_url(self, stream_resolver_service):
        url = stream_resolver_service.resolve_stream("abc123def45", "720p")
        assert url == "https://www.youtube.com/watch?v=abc123def45"

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
        url = stream_resolver_service.resolve_stream("abc123def45")
        assert url == "https://www.youtube.com/watch?v=abc123def45"

    def test_resolve_stream_no_event_bus(self):
        from services.stream_resolver_service import StreamResolverService
        svc = StreamResolverService(event_bus=None)
        url = svc.resolve_stream("abc123def45")
        assert url == "https://www.youtube.com/watch?v=abc123def45"
