"""Resolve YouTube video IDs into playable media URLs.

Production uses the injected :class:`YouTubeAPI` (yt-dlp) so playback failures
are reported consistently instead of depending on MPV's internal yt-dlp
integration.  When no API is injected the resolver keeps the legacy behaviour
of returning a YouTube watch URL, which is useful for tests and embedded use.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.events import (
    StreamResolvedEvent,
    StreamResolveFailedEvent,
    StreamResolvingEvent,
)
from core.playback_errors import StreamCancelledError
from core.quality import (
    ResolvedStream,
    normalize_quality,
    validate_stream_url,
    validate_video_id,
    watch_url,
)

if TYPE_CHECKING:
    from core import EventBus


class StreamResolverService:
    """Resolves YouTube video IDs to playable URLs for MPV."""

    def __init__(
        self,
        event_bus: EventBus | None = None,
        logger: logging.Logger | None = None,
        youtube_api=None,
    ):
        self._event_bus = event_bus
        self._logger = logger or logging.getLogger(__name__)
        self._youtube_api = youtube_api

    def resolve_stream(
        self,
        video_id: str,
        quality: str = "best",
        *,
        cancel_event=None,
        publish_events: bool = True,
    ) -> ResolvedStream:
        """Resolve *video_id* at *quality*.

        ``cancel_event`` lets callers abandon a superseded request.  Cancellation
        is silent: no failure event is published because the request is stale.
        """
        validate_video_id(video_id)
        normalized_quality = normalize_quality(quality)

        if cancel_event is not None and cancel_event.is_set():
            raise StreamCancelledError("Stream resolution cancelled")

        if publish_events and self._event_bus:
            self._event_bus.publish(
                StreamResolvingEvent(video_id=video_id, quality=normalized_quality)
            )

        try:
            if self._youtube_api is None:
                media = ResolvedStream(
                    video_url=watch_url(video_id), quality=normalized_quality
                )
            else:
                media = self._youtube_api.extract_streams(
                    video_id,
                    normalized_quality,
                    cancel_event=cancel_event,
                )
                if not isinstance(media, ResolvedStream):
                    media = ResolvedStream(
                        video_url=validate_stream_url(media),
                        quality=normalized_quality,
                    )
            if cancel_event is not None and cancel_event.is_set():
                raise StreamCancelledError("Stream resolution cancelled")
        except StreamCancelledError:
            raise
        except Exception as exc:
            self._logger.warning(
                "Stream resolution failed for %s: %s", video_id, exc
            )
            if publish_events and self._event_bus:
                self._event_bus.publish(
                    StreamResolveFailedEvent(
                        video_id=video_id,
                        quality=normalized_quality,
                        error=str(exc),
                    )
                )
            raise

        if publish_events and self._event_bus:
            self._event_bus.publish(
                StreamResolvedEvent(
                    video_id=video_id,
                    url=media.video_url,
                    quality=normalized_quality,
                )
            )
        return media

    def resolve_metadata(self, video_id: str, *, cancel_event=None) -> dict:
        """Return video metadata for *video_id*, or a minimal stub on failure."""
        validate_video_id(video_id)
        if self._youtube_api is None:
            return {"videoId": video_id}

        try:
            info = self._youtube_api.fetch_video_info(
                video_id, cancel_event=cancel_event
            )
        except StreamCancelledError:
            raise
        except Exception as exc:
            self._logger.debug("Metadata lookup failed for %s: %s", video_id, exc)
            return {"videoId": video_id}

        if not isinstance(info, dict):
            return {"videoId": video_id}
        result = dict(info)
        result["videoId"] = video_id
        return result
