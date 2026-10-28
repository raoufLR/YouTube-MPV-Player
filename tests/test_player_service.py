import time

import pytest

from core.events import (
    PlaybackErrorEvent,
    VideoPausedEvent,
    VideoStartedEvent,
    VideoStoppedEvent,
)
from services.player_service import PlayerService

STREAM = "https://example.com/stream"
AUDIO = "https://example.com/audio"


def _wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class TestPlayerService:
    def test_play_video_calls_mpv_and_publishes_event(
        self, player_service, event_bus, mock_mpv_player
    ):
        events = []
        event_bus.subscribe("video_started", events.append, weak=False)
        player_service.play_video(
            STREAM,
            "720p",
            {"videoId": "abc123", "title": "Test"},
        )
        mock_mpv_player.play.assert_called_once_with(
            STREAM, "720p", win_id=None, audio_url=""
        )
        assert len(events) == 1
        assert isinstance(events[0], VideoStartedEvent)
        assert events[0].video_id == "abc123"
        assert events[0].title == "Test"

    def test_play_video_forwards_audio_stream(self, player_service, mock_mpv_player):
        player_service.play_video(STREAM, "720p", audio_url=AUDIO)
        mock_mpv_player.play.assert_called_once_with(
            STREAM, "720p", win_id=None, audio_url=AUDIO
        )

    def test_play_video_rejects_non_http_url(self, player_service):
        with pytest.raises(ValueError):
            player_service.play_video("file:///etc/passwd")

    def test_play_video_publishes_error_on_failure(
        self, player_service, event_bus, mock_mpv_player
    ):
        mock_mpv_player.play.side_effect = RuntimeError("MPV error")
        events = []
        event_bus.subscribe("playback_error", events.append, weak=False)
        with pytest.raises(RuntimeError):
            player_service.play_video(STREAM, "720p")
        assert len(events) == 1
        assert isinstance(events[0], PlaybackErrorEvent)
        assert "MPV error" in events[0].error
        assert events[0].stage == "playback"

    def test_pause_resume_uses_explicit_pause_property(
        self, player_service, event_bus, mock_mpv_player
    ):
        player_service.play_video(STREAM, "720p")
        events = []
        event_bus.subscribe("video_paused", events.append, weak=False)

        assert player_service.pause_resume() is True
        assert player_service.is_paused is True
        mock_mpv_player.set_paused.assert_called_with(True)

        assert player_service.pause_resume() is False
        mock_mpv_player.set_paused.assert_called_with(False)

        assert [e.is_paused for e in events] == [True, False]
        assert all(isinstance(e, VideoPausedEvent) for e in events)

    def test_pause_ignored_without_media(self, player_service):
        assert player_service.pause_resume() is None

    def test_stop_only_emits_when_media_was_active(
        self, player_service, event_bus, mock_mpv_player
    ):
        events = []
        event_bus.subscribe("video_stopped", events.append, weak=False)

        player_service.stop()
        assert events == []

        player_service.play_video(STREAM, "720p")
        player_service.stop()
        assert len(events) == 1
        assert isinstance(events[0], VideoStoppedEvent)

        # Idempotent stop must not publish duplicates.
        player_service.stop()
        assert len(events) == 1
        assert player_service.has_media is False

    def test_seek_absolute_clamps_to_duration(self, player_service):
        player_service.play_video(STREAM, "720p")
        player_service._duration = 100.0

        assert player_service.seek_absolute(40) == 40.0
        assert player_service.get_position() == 40.0

        assert player_service.seek_absolute(500) == 100.0
        assert player_service.seek_absolute(-5) == 0.0

    def test_seek_relative(self, player_service):
        player_service.play_video(STREAM, "720p")
        player_service._duration = 100.0
        player_service.seek_absolute(30)
        player_service.seek_relative(10)
        assert player_service.get_position() == 40.0
        player_service.seek_relative(-100)
        assert player_service.get_position() == 0.0

    def test_seek_ignored_without_media(self, player_service):
        assert player_service.seek_absolute(10) is None
        assert player_service.seek_relative(10) is None

    def test_set_volume_clamps(self, player_service, mock_mpv_player):
        assert player_service.set_volume(55) == 55
        mock_mpv_player.set_volume.assert_called_with(55)
        assert player_service.set_volume(999) == 100
        assert player_service.set_volume(-10) == 0
        assert player_service.set_volume("nope") == 0

    def test_play_video_no_event_bus(self, mock_mpv_player):
        svc = PlayerService(
            mpv_player=mock_mpv_player, event_bus=None, monitor_interval=0
        )
        svc.play_video(STREAM, "720p")
        mock_mpv_player.play.assert_called_once()

    def test_play_video_without_video_data(
        self, player_service, event_bus, mock_mpv_player
    ):
        events = []
        event_bus.subscribe("video_started", events.append, weak=False)
        player_service.play_video(STREAM, "720p")
        assert len(events) == 1
        assert events[0].video_id == ""

    def test_contract_fake_matches_service_expectations(self, fake_mpv, event_bus):
        service = PlayerService(
            mpv_player=fake_mpv, event_bus=event_bus, monitor_interval=0
        )
        service.play_video(
            STREAM,
            "720p",
            {"videoId": "abc123def45", "title": "Test"},
            win_id=42,
            audio_url=AUDIO,
        )

        assert fake_mpv.play_calls == [(STREAM, "720p", 42)]
        assert fake_mpv.audio_urls == [AUDIO]

        service.pause_resume()
        assert fake_mpv.paused is True

        service.set_volume(55)
        assert fake_mpv.get_volume() == 55

        service.stop()
        assert fake_mpv.stopped == 1
        assert fake_mpv.process is None


class TestPlayerServiceMonitor:
    def _service(self, event_bus, fake_mpv):
        return PlayerService(
            mpv_player=fake_mpv,
            event_bus=event_bus,
            monitor_interval=0.01,
        )

    def test_monitor_updates_position_duration_and_pause(self, event_bus, fake_mpv):
        service = self._service(event_bus, fake_mpv)
        try:
            service.play_video(STREAM, "720p")
            fake_mpv.properties["duration"] = 120.0
            fake_mpv.properties["time-pos"] = 42.5

            assert _wait_for(lambda: service.get_duration() == 120.0)
            assert service.get_position() == pytest.approx(42.5)

            fake_mpv.properties["pause"] = True
            assert _wait_for(lambda: service.is_paused is True)
        finally:
            service.shutdown()

    def test_monitor_stops_on_end_of_file(self, event_bus, fake_mpv):
        events = []
        event_bus.subscribe("video_stopped", events.append, weak=False)
        service = self._service(event_bus, fake_mpv)
        try:
            service.play_video(STREAM, "720p")
            fake_mpv.properties["eof-reached"] = True

            assert _wait_for(lambda: len(events) == 1)
            assert isinstance(events[0], VideoStoppedEvent)
            assert events[0].reason == "ended"
            assert service.has_media is False
        finally:
            service.shutdown()

    def test_monitor_reports_unexpected_exit(self, event_bus, fake_mpv):
        stopped = []
        errors = []
        event_bus.subscribe("video_stopped", stopped.append, weak=False)
        event_bus.subscribe("playback_error", errors.append, weak=False)
        service = self._service(event_bus, fake_mpv)
        try:
            service.play_video(STREAM, "720p")
            fake_mpv.process.returncode = 1

            assert _wait_for(lambda: len(stopped) == 1)
            assert stopped[0].reason == "exited"
            assert len(errors) == 1
            assert errors[0].stage == "playback"
        finally:
            service.shutdown()

    def test_shutdown_stops_monitor_thread(self, event_bus, fake_mpv):
        service = self._service(event_bus, fake_mpv)
        service.play_video(STREAM, "720p")
        thread = service._monitor_thread
        assert thread is not None and thread.is_alive()

        service.shutdown()
        assert service._monitor_thread is None
        assert not thread.is_alive()
        assert service.is_playing is False

    def test_monitor_tolerates_unavailable_properties(self, event_bus, fake_mpv):
        """MPV answers 'property unavailable' while a file is still loading."""
        from player import MpvPropertyUnavailableError

        service = self._service(event_bus, fake_mpv)
        original_request = fake_mpv.request
        failures = {"count": 0}

        def request(command, timeout=0.5):
            if command == ["get_property", "time-pos"] and failures["count"] < 2:
                failures["count"] += 1
                raise MpvPropertyUnavailableError(
                    "MPV property is not available yet"
                )
            return original_request(command, timeout=timeout)

        fake_mpv.request = request
        try:
            service.play_video(STREAM, "720p")
            fake_mpv.properties["time-pos"] = 12.0
            fake_mpv.properties["duration"] = 60.0

            assert _wait_for(lambda: service.get_position() == 12.0)
            assert service.get_duration() == 60.0
            assert failures["count"] == 2
        finally:
            service.shutdown()

    def test_play_video_after_shutdown_raises(self, event_bus, fake_mpv):
        service = self._service(event_bus, fake_mpv)
        service.shutdown()
        with pytest.raises(RuntimeError):
            service.play_video(STREAM, "720p")
