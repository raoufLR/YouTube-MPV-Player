"""Analytics service: event wiring, totals, persistence, and repair."""

import json
import os

import pytest

from core.events import VideoStartedEvent, VideoStoppedEvent
from services.analytics_service import AnalyticsService, sanitize_stats


@pytest.fixture
def analytics(event_bus, temp_dir):
    service = AnalyticsService(event_bus=event_bus, data_dir=temp_dir)
    yield service
    service.shutdown()


def test_record_playback_accumulates_totals(analytics):
    analytics.record_playback("abc123def45", watched_seconds=90.0, channel="Chan")
    analytics.record_playback("abc123def45", watched_seconds=30.0, channel="Chan")
    analytics.record_playback("xyz987uvw65", watched_seconds=10.0, channel="Other")

    stats = analytics.get_stats()
    assert stats["watch_seconds"] == 130.0
    assert stats["watch_hours"] == pytest.approx(0.04, abs=0.01)
    assert stats["videos_played"] == 3
    assert stats["top_channels"] == {"Chan": 2, "Other": 1}
    assert stats["top_channel"] == "Chan"
    assert stats["rewatches"] == 1


def test_start_and_stop_events_record_position(analytics, event_bus):
    event_bus.publish(
        VideoStartedEvent(video_id="vid1", channel="Chan", title="Title")
    )
    event_bus.publish(
        VideoStoppedEvent(reason="stopped", position=42.5, duration=200.0)
    )

    stats = analytics.get_stats()
    assert stats["videos_played"] == 1
    assert stats["watch_seconds"] == 42.5
    assert stats["top_channels"] == {"Chan": 1}


def test_started_event_falls_back_to_video_data(analytics, event_bus):
    event_bus.publish(
        VideoStartedEvent(video_data={"videoId": "abc123def45", "channel": "Chan"})
    )
    event_bus.publish(VideoStoppedEvent(position=5.0, duration=10.0))

    assert analytics.get_stats()["videos_played"] == 1


def test_end_of_file_uses_duration_when_position_is_missing(analytics, event_bus):
    event_bus.publish(VideoStartedEvent(video_id="vid1", channel="Chan"))
    event_bus.publish(
        VideoStoppedEvent(reason="ended", position=0.0, duration=300.0)
    )

    assert analytics.get_stats()["watch_seconds"] == 300.0


def test_position_is_clamped_to_duration(analytics, event_bus):
    event_bus.publish(VideoStartedEvent(video_id="vid1", channel="Chan"))
    event_bus.publish(
        VideoStoppedEvent(reason="stopped", position=999.0, duration=120.0)
    )

    assert analytics.get_stats()["watch_seconds"] == 120.0


def test_stop_without_start_is_ignored(analytics, event_bus):
    event_bus.publish(VideoStoppedEvent(position=10.0, duration=10.0))

    assert analytics.get_stats()["videos_played"] == 0
    assert analytics.get_stats()["watch_seconds"] == 0.0


def test_statistics_persist_across_instances(event_bus, temp_dir):
    service = AnalyticsService(event_bus=event_bus, data_dir=temp_dir)
    service.record_playback("abc123def45", watched_seconds=61.0, channel="Chan")
    service.shutdown()

    reloaded = AnalyticsService(data_dir=temp_dir)
    try:
        stats = reloaded.get_stats()
        assert stats["watch_seconds"] == 61.0
        assert stats["videos_played"] == 1
        assert stats["top_channel"] == "Chan"
    finally:
        reloaded.shutdown()


def test_reload_switches_profiles(event_bus, temp_dir):
    service = AnalyticsService(event_bus=event_bus, data_dir=temp_dir)
    try:
        service.record_playback("abc123def45", 60.0, "First")
        other_dir = os.path.join(temp_dir, "other")
        service.reload(data_dir=other_dir)
        assert service.get_stats()["videos_played"] == 0

        service.record_playback("abc123def45", 30.0, "Second")
        service.reload(data_dir=temp_dir)
        stats = service.get_stats()
        assert stats["videos_played"] == 1
        assert stats["top_channel"] == "First"
    finally:
        service.shutdown()


def test_invalid_persisted_data_is_repaired(event_bus, temp_dir):
    path = os.path.join(temp_dir, "analytics.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "watch_seconds": "nonsense",
                "videos_played": -5,
                "channels": {"Chan": 2, "": 9},
                "videos": {"vid1": 3},
            },
            handle,
        )

    service = AnalyticsService(event_bus=event_bus, data_dir=temp_dir)
    try:
        stats = service.get_stats()
        assert stats["watch_seconds"] == 0.0
        assert stats["videos_played"] == 0
        assert stats["top_channels"] == {"Chan": 2}
        assert stats["rewatches"] == 2
    finally:
        service.shutdown()

    with open(path, encoding="utf-8") as handle:
        repaired = json.load(handle)
    assert repaired["version"] == 1
    assert repaired["channels"] == {"Chan": 2}


def test_sanitize_stats_handles_wrong_shapes():
    stats, repaired = sanitize_stats(None)
    assert stats["videos_played"] == 0
    assert repaired is False

    stats, repaired = sanitize_stats(["not", "a", "mapping"])
    assert repaired is True
    assert stats["channels"] == {}


def test_channel_map_is_bounded(analytics, monkeypatch):
    monkeypatch.setattr("services.analytics_service.MAX_CHANNELS", 3)
    for index in range(10):
        analytics.record_playback("vid1", 1.0, f"Channel {index}")

    assert len(analytics.get_stats()["top_channels"]) == 3


def test_unsafe_video_ids_are_not_tracked(analytics, temp_dir):
    analytics.record_playback("../escape", watched_seconds=5.0, channel="Chan")
    analytics.flush()

    with open(os.path.join(temp_dir, "analytics.json"), encoding="utf-8") as handle:
        stored = json.load(handle)
    assert stored["videos"] == {}
    assert analytics.get_stats()["videos_played"] == 1


def test_reset_clears_statistics(analytics, temp_dir):
    analytics.record_playback("abc123def45", 120.0, "Chan")
    assert analytics.reset() is True

    stats = analytics.get_stats()
    assert stats["videos_played"] == 0
    assert stats["watch_seconds"] == 0.0
    assert stats["top_channels"] == {}

    with open(os.path.join(temp_dir, "analytics.json"), encoding="utf-8") as handle:
        assert json.load(handle)["videos_played"] == 0


def test_shutdown_unsubscribes_from_playback_events(analytics, event_bus):
    analytics.shutdown()

    event_bus.publish(VideoStartedEvent(video_id="vid1", channel="Chan"))
    event_bus.publish(VideoStoppedEvent(position=10.0, duration=10.0))

    assert analytics.get_stats()["videos_played"] == 0
