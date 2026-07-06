import pytest

from core.events import HistoryUpdatedEvent, VideoStartedEvent


class TestHistoryService:
    def test_add_video(self, history_service, event_bus):
        events = []
        event_bus.subscribe("history_updated", events.append, weak=False)
        history_service.add({"id": "v1", "title": "Test Video", "channel": "TC"})
        entries = history_service.get_all()
        assert len(entries) == 1
        assert entries[0]["id"] == "v1"
        assert len(events) == 1
        assert isinstance(events[0], HistoryUpdatedEvent)
        assert events[0].action == "added"
        assert events[0].video_id == "v1"

    def test_add_moves_to_top(self, history_service):
        history_service.add({"id": "v1"})
        history_service.add({"id": "v2"})
        history_service.add({"id": "v1"})
        entries = history_service.get_all()
        assert entries[0]["id"] == "v1"
        assert len(entries) == 2

    def test_add_enforces_capacity(self, history_service):
        from services.history_service import MAX_HISTORY
        for i in range(MAX_HISTORY + 10):
            history_service.add({"id": f"v{i}"})
        assert history_service.count() == MAX_HISTORY

    def test_remove_video(self, history_service, event_bus):
        history_service.add({"id": "v1"})
        events = []
        event_bus.subscribe("history_updated", events.append, weak=False)
        result = history_service.remove("v1")
        assert result is True
        assert history_service.contains("v1") is False
        assert len(events) == 1
        assert events[0].action == "removed"

    def test_remove_nonexistent(self, history_service):
        result = history_service.remove("nonexistent")
        assert result is False

    def test_clear(self, history_service, event_bus):
        history_service.add({"id": "v1"})
        history_service.add({"id": "v2"})
        events = []
        event_bus.subscribe("history_updated", events.append, weak=False)
        history_service.clear()
        assert history_service.count() == 0
        assert len(events) == 1
        assert events[0].action == "cleared"

    def test_get_recent(self, history_service):
        history_service.add({"id": "v1"})
        history_service.add({"id": "v2"})
        history_service.add({"id": "v3"})
        recent = history_service.get_recent(limit=2)
        assert len(recent) == 2
        assert recent[0]["id"] == "v3"

    def test_contains(self, history_service):
        assert history_service.contains("v1") is False
        history_service.add({"id": "v1"})
        assert history_service.contains("v1") is True

    def test_get_stats(self, history_service):
        stats = history_service.get_stats()
        assert stats["count"] == 0
        history_service.add({"id": "v1"})
        stats = history_service.get_stats()
        assert stats["count"] == 1
        assert stats["newest"] > 0

    def test_export(self, history_service):
        history_service.add({"id": "v1"})
        data = history_service.export()
        assert len(data) == 1
        assert data[0]["id"] == "v1"

    def test_reset(self, history_service):
        history_service.add({"id": "v1"})
        history_service.reset()
        assert history_service.count() == 0

    def test_on_video_started_adds_to_history(self, history_service, event_bus):
        event_bus.publish(VideoStartedEvent(
            video_id="v1", title="T", channel="C", thumbnail="th.jpg"
        ))
        assert history_service.contains("v1") is True

    def test_video_id_flexibility(self, history_service):
        history_service.add({"id": "v1"})
        assert history_service.contains("v1") is True
        assert history_service.contains("v1") is True
