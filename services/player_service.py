import logging
from typing import Optional

from core.events import VideoStartedEvent, VideoStoppedEvent, VideoPausedEvent, PlaybackErrorEvent
from player import MpvPlayer


class PlayerService:
    """Service for managing MPV video playback only.

    Stream URL resolution is handled by StreamResolverService.
    """

    def __init__(self, mpv_player=None, event_bus=None, logger=None):
        self.event_bus = event_bus
        self._logger = logger or logging.getLogger(__name__)
        self.player = mpv_player or MpvPlayer(logger=self._logger)

    def play_video(self, stream_url, quality="best", video_data=None):
        try:
            self.player.play(stream_url, quality)
            if self.event_bus:
                vdata = video_data or {}
                self.event_bus.publish(VideoStartedEvent(
                    url=stream_url, quality=quality, video_data=video_data,
                    video_id=vdata.get("videoId", ""),
                    title=vdata.get("title", ""),
                    channel=vdata.get("channel", ""),
                    thumbnail=vdata.get("thumbnail", ""),
                ))
        except Exception as e:
            if self.event_bus:
                self.event_bus.publish(PlaybackErrorEvent(error=str(e)))
            raise

    def pause_resume(self):
        self.player.pause_resume()
        if self.event_bus:
            self.event_bus.publish(VideoPausedEvent())

    def stop(self):
        self.player.stop()
        if self.event_bus:
            self.event_bus.publish(VideoStoppedEvent())

    def set_volume(self, volume):
        self.player.set_volume(volume)
