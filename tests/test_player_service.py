import pytest

from core.events import VideoStartedEvent, VideoPausedEvent, VideoStoppedEvent, PlaybackErrorEvent


class TestPlayerService:
    def test_play_video_calls_mpv_and_publishes_event(self, player_service, event_bus, mock_mpv_player):
        events = []
        event_bus.subscribe("video_started", events.append, weak=False)
        player_service.play_video(
            "https://example.com/stream",
            "720p",
            {"videoId": "abc123", "title": "Test"},
        )
        mock_mpv_player.play.assert_called_once_with(
            "https://example.com/stream", "720p"
        )
        assert len(events) == 1
        assert isinstance(events[0], VideoStartedEvent)
        assert events[0].video_id == "abc123"
        assert events[0].title == "Test"

    def test_play_video_publishes_error_on_failure(self, player_service, event_bus, mock_mpv_player):
        mock_mpv_player.play.side_effect = RuntimeError("MPV error")
        events = []
        event_bus.subscribe("playback_error", events.append, weak=False)
        with pytest.raises(RuntimeError):
            player_service.play_video("https://example.com/stream", "720p")
        assert len(events) == 1
        assert isinstance(events[0], PlaybackErrorEvent)
        assert "MPV error" in events[0].error

    def test_pause_resume(self, player_service, event_bus, mock_mpv_player):
        events = []
        event_bus.subscribe("video_paused", events.append, weak=False)
        player_service.pause_resume()
        mock_mpv_player.pause_resume.assert_called_once()
        assert len(events) == 1
        assert isinstance(events[0], VideoPausedEvent)

    def test_stop(self, player_service, event_bus, mock_mpv_player):
        events = []
        event_bus.subscribe("video_stopped", events.append, weak=False)
        player_service.stop()
        mock_mpv_player.stop.assert_called_once()
        assert len(events) == 1
        assert isinstance(events[0], VideoStoppedEvent)

    def test_set_volume(self, player_service, mock_mpv_player):
        player_service.set_volume(55)
        mock_mpv_player.set_volume.assert_called_once_with(55)

    def test_play_video_no_event_bus(self, mock_mpv_player):
        from services.player_service import PlayerService
        svc = PlayerService(mpv_player=mock_mpv_player, event_bus=None)
        svc.play_video("https://example.com/stream", "720p")
        mock_mpv_player.play.assert_called_once()

    def test_play_video_without_video_data(self, player_service, event_bus, mock_mpv_player):
        events = []
        event_bus.subscribe("video_started", events.append, weak=False)
        player_service.play_video("https://example.com/stream", "720p")
        assert len(events) == 1
        assert events[0].video_id == ""
