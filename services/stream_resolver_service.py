import logging
from typing import Optional

from core import EventBus
from core.events import (
    StreamResolvingEvent, StreamResolvedEvent,
)


class StreamResolverService:
    """Resolves YouTube video IDs to playable YouTube URLs for mpv."""

    def __init__(self, event_bus: Optional[EventBus] = None,
                 logger: Optional[logging.Logger] = None):
        self._event_bus = event_bus
        self._logger = logger or logging.getLogger(__name__)

    def resolve_stream(self, video_id: str, quality: str = "best") -> str:
        if self._event_bus:
            self._event_bus.publish(
                StreamResolvingEvent(video_id=video_id, quality=quality)
            )

        youtube_url = f"https://www.youtube.com/watch?v={video_id}"

        if self._event_bus:
            self._event_bus.publish(
                StreamResolvedEvent(video_id=video_id, url=youtube_url, quality=quality)
            )
        return youtube_url
