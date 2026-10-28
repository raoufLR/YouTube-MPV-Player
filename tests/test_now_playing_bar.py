"""Now-playing bar behaviour: state sync, seeking, and timer-driven progress."""

from types import SimpleNamespace

import pytest

from core.events import (
    VideoPausedEvent,
    VideoStartedEvent,
    VideoStoppedEvent,
)
from services.player_service import PlayerService
from ui.now_playing_bar import NowPlayingBar, format_time

STREAM = "https://example.com/stream"


def _started(title="Video", channel="Channel", thumbnail=""):
    return VideoStartedEvent(
        url=STREAM,
        quality="720p",
        video_id="abc123def45",
        title=title,
        channel=channel,
        thumbnail=thumbnail,
    )


@pytest.fixture
def bar(qapp, event_bus, fake_mpv):
    service = PlayerService(fake_mpv, event_bus, monitor_interval=0)
    widget = NowPlayingBar(
        event_bus,
        service,
        SimpleNamespace(load_thumbnail_data=lambda url: None),
    )
    yield widget, service, fake_mpv, event_bus
    widget.cleanup()
    widget.deleteLater()


class TestFormatTime:
    @pytest.mark.parametrize(
        "seconds,expected",
        [
            (0, "0:00"),
            (5, "0:05"),
            (65, "1:05"),
            (3600, "1:00:00"),
            (3725, "1:02:05"),
            (-5, "0:00"),
            ("bad", "0:00"),
            (None, "0:00"),
        ],
    )
    def test_format_time(self, seconds, expected):
        assert format_time(seconds) == expected


class TestNowPlayingBar:
    def test_starts_hidden(self, bar):
        widget, *_ = bar
        assert widget.isHidden()

    def test_video_started_shows_metadata(self, bar):
        widget, _service, _fake, _bus = bar
        widget._on_video_started(_started())

        assert widget.isVisible()
        assert widget._title_label.text() == "Video"
        assert widget._channel_label.text() == "Channel"
        assert widget._is_playing is True
        assert widget._progress_timer.isActive()
        assert widget._seek_slider.isEnabled() is False

    def test_pause_state_updates_button(self, bar):
        widget, *_ = bar
        widget._on_video_started(_started())

        widget._on_video_paused(VideoPausedEvent(is_paused=True))
        assert widget._is_paused is True
        assert "Resume" in widget._play_btn.toolTip()

        widget._on_video_paused(VideoPausedEvent(is_paused=False))
        assert widget._is_paused is False
        assert "Pause" in widget._play_btn.toolTip()

    def test_progress_uses_cached_state(self, bar):
        widget, service, _fake, _bus = bar
        service.play_video(STREAM, "720p")
        service._duration = 100.0
        service._position = 42.0

        widget._on_video_started(_started())
        widget._refresh_progress()

        assert widget._seek_slider.maximum() == 100
        assert widget._seek_slider.value() == 42
        assert widget._time_label.text() == "0:42"
        assert widget._duration_label.text() == "1:40"

    def test_seek_release_sends_absolute_seconds(self, bar):
        widget, service, fake, _bus = bar
        service.play_video(STREAM, "720p")
        service._duration = 100.0
        widget._on_video_started(_started())
        widget._refresh_progress()

        widget._seek_slider.setValue(75)
        widget._seek_released()

        assert fake.seeks[-1] == (75.0, "absolute")
        assert service.get_position() == 75.0

    def test_volume_slider_updates_service(self, bar):
        widget, service, fake, _bus = bar
        widget._volume_slider.setValue(55)
        assert service.get_volume() == 55
        assert fake.volume == 55

    def test_mute_and_unmute(self, bar):
        widget, service, _fake, _bus = bar
        service.set_volume(60)
        widget._sync_volume_controls()

        widget._toggle_mute()
        assert service.get_volume() == 0
        assert "Unmute" in widget._volume_btn.toolTip()

        widget._toggle_mute()
        assert service.get_volume() == 60
        assert "Mute" in widget._volume_btn.toolTip()

    def test_stop_hides_and_resets(self, bar):
        widget, _service, _fake, _bus = bar
        widget._on_video_started(_started())
        widget._on_video_stopped(VideoStoppedEvent(reason="ended"))

        assert widget.isHidden()
        assert widget._is_playing is False
        assert widget._progress_timer.isActive() is False
        assert widget._title_label.text() == "No video playing"
        assert widget._seek_slider.isEnabled() is False

    def test_stop_button_stops_playback(self, bar):
        widget, service, fake, _bus = bar
        service.play_video(STREAM, "720p")
        widget._on_video_started(_started())

        widget._stop_playback()

        assert service.has_media is False
        assert fake.stopped == 1

    def test_cleanup_unsubscribes(self, bar):
        widget, _service, _fake, bus = bar
        widget.cleanup()
        assert not bus.has_listeners("video_started")
        assert not bus.has_listeners("video_paused")
        assert not bus.has_listeners("video_stopped")

    def test_view_and_fullscreen_buttons_emit_signals(self, bar):
        widget, _, _, _ = bar
        view_emitted = []
        fs_emitted = []
        widget.show_video_requested.connect(lambda: view_emitted.append(True))
        widget.fullscreen_requested.connect(lambda: fs_emitted.append(True))

        widget._view_btn.click()
        assert len(view_emitted) == 1

        widget._fullscreen_btn.click()
        assert len(fs_emitted) == 1
