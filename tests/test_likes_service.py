import pytest

from core.events import LikeChangedEvent


class TestLikesService:
    def test_like_video(self, likes_service, event_bus):
        events = []
        event_bus.subscribe("like_changed", events.append, weak=False)
        video_data = {"videoId": "v1", "title": "Test"}
        result = likes_service.like(video_data)
        assert result is True
        assert likes_service.is_liked("v1") is True
        assert len(events) == 1
        assert isinstance(events[0], LikeChangedEvent)
        assert events[0].video_id == "v1"
        assert events[0].is_liked is True

    def test_like_duplicate_returns_false(self, likes_service):
        video_data = {"videoId": "v1"}
        likes_service.like(video_data)
        result = likes_service.like(video_data)
        assert result is False

    def test_unlike_video(self, likes_service, event_bus):
        likes_service.like({"videoId": "v1"})
        events = []
        event_bus.subscribe("like_changed", events.append, weak=False)
        result = likes_service.unlike("v1")
        assert result is True
        assert likes_service.is_liked("v1") is False
        assert len(events) == 1
        assert isinstance(events[0], LikeChangedEvent)
        assert events[0].video_id == "v1"
        assert events[0].is_liked is False

    def test_unlike_not_liked_returns_false(self, likes_service):
        result = likes_service.unlike("nonexistent")
        assert result is False

    def test_toggle_like(self, likes_service, event_bus):
        video_data = {"videoId": "v1"}
        result1 = likes_service.toggle_like(video_data)
        assert result1 is True
        assert likes_service.is_liked("v1") is True
        result2 = likes_service.toggle_like(video_data)
        assert result2 is False
        assert likes_service.is_liked("v1") is False

    def test_get_liked_videos(self, likes_service):
        likes_service.like({"videoId": "v1", "title": "A"})
        likes_service.like({"videoId": "v2", "title": "B"})
        liked = likes_service.get_liked_videos()
        assert len(liked) == 2
        video_ids = [v["video_id"] for v in liked]
        assert "v1" in video_ids
        assert "v2" in video_ids

    def test_count(self, likes_service):
        assert likes_service.count() == 0
        likes_service.like({"videoId": "v1"})
        assert likes_service.count() == 1

    def test_export(self, likes_service):
        likes_service.like({"videoId": "v1"})
        data = likes_service.export()
        assert len(data) == 1

    def test_reset(self, likes_service):
        likes_service.like({"videoId": "v1"})
        likes_service.reset()
        assert likes_service.count() == 0

    def test_video_id_flexibility(self, likes_service):
        result1 = likes_service.like({"videoId": "v1"})
        assert result1 is True
        result2 = likes_service.like({"video_id": "v1"})
        assert result2 is False
        result3 = likes_service.like({"id": "v1"})
        assert result3 is False
