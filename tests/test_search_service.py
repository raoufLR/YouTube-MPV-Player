import pytest

from core.events import SearchStartedEvent, SearchCompletedEvent, SearchFailedEvent


class TestSearchService:
    def test_search_returns_videos(self, search_service):
        videos = search_service.search("test query")
        assert len(videos) == 1
        assert videos[0]["videoId"] == "abc123def45"
        assert videos[0]["title"] == "Test Video"

    def test_search_publishes_started_and_completed(self, search_service, event_bus):
        events = []
        event_bus.subscribe("search_started", events.append, weak=False)
        event_bus.subscribe("search_completed", events.append, weak=False)
        search_service.search("test query")
        assert len(events) == 2
        assert isinstance(events[0], SearchStartedEvent)
        assert events[0].query == "test query"
        assert isinstance(events[1], SearchCompletedEvent)
        assert len(events[1].videos) == 1

    def test_search_publishes_failed_on_error(self, search_service, event_bus, mock_youtube_api):
        mock_youtube_api.search_videos.side_effect = RuntimeError("Network error")
        events = []
        event_bus.subscribe("search_failed", events.append, weak=False)
        with pytest.raises(RuntimeError):
            search_service.search("test query")
        assert len(events) == 1
        assert isinstance(events[0], SearchFailedEvent)
        assert "Network error" in events[0].error

    def test_search_paginated(self, search_service, mock_youtube_api):
        mock_youtube_api.search_videos.reset_mock()
        mock_youtube_api.search_videos.side_effect = [
            [{"videoId": "v1"}],
            [{"videoId": "v2"}, {"videoId": "v3"}],
        ]
        r1, more1 = search_service.search_page("q", page=0, page_size=1)
        assert len(r1) == 1
        assert more1 is True
        r2, more2 = search_service.search_page("q", page=1, page_size=2)
        assert len(r2) == 2
        assert more2 is True

    def test_search_page_no_more_results(self, search_service, mock_youtube_api):
        mock_youtube_api.search_videos.return_value = []
        videos, has_more = search_service.search_page("q", page=0, page_size=20)
        assert len(videos) == 0
        assert has_more is False
