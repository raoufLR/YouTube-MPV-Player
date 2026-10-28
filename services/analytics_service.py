"""Profile-scoped local playback statistics.

Statistics are derived from ``VideoStartedEvent`` / ``VideoStoppedEvent``
pairs and stored in ``analytics.json`` inside the active profile directory.
Nothing is sent anywhere: the page is a local summary of watch time, play
counts, rewatches, and the channels played most.

The service is thread-safe: events arrive on the playback worker/monitor
threads while the UI page reads snapshots from the GUI thread.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.events import (
    EVENT_VIDEO_STARTED,
    EVENT_VIDEO_STOPPED,
    VideoStartedEvent,
    VideoStoppedEvent,
)
from core.json_store import JsonStore
from core.validation import coerce_float, coerce_id, coerce_int, coerce_text, coerce_timestamp

if TYPE_CHECKING:
    from core import EventBus

_logger = logging.getLogger(__name__)

STATS_SCHEMA_VERSION = 1
MAX_CHANNELS = 500
MAX_TRACKED_VIDEOS = 2000
MAX_CHANNEL_LENGTH = 256
# A single playback cannot exceed a day; protects the totals from a bogus
# position/duration pair in a hand-edited file or a misbehaving player.
MAX_SESSION_SECONDS = 24 * 60 * 60.0
TOP_CHANNEL_LIMIT = 5


@dataclass
class _Session:
    """The playback currently in flight."""

    video_id: str = ""
    channel: str = ""


def _empty_stats() -> dict:
    return {
        "version": STATS_SCHEMA_VERSION,
        "watch_seconds": 0.0,
        "videos_played": 0,
        "channels": {},
        "videos": {},
        "last_played_at": 0.0,
    }


def _sanitize_counts(raw: object, *, limit: int) -> tuple[dict[str, int], bool]:
    """Return a bounded ``{key: count}`` mapping and whether it was repaired."""
    if not isinstance(raw, dict):
        return {}, raw not in (None, {})
    counts: dict[str, int] = {}
    repaired = False
    for key, value in raw.items():
        name = coerce_text(key, "", max_length=MAX_CHANNEL_LENGTH)
        count = coerce_int(value, 0, minimum=0)
        if not name or count <= 0:
            repaired = True
            continue
        counts[name] = counts.get(name, 0) + count
    if len(counts) > limit:
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))
        counts = dict(ordered[:limit])
        repaired = True
    return counts, repaired


def sanitize_stats(raw: object) -> tuple[dict, bool]:
    """Coerce persisted analytics into a valid, bounded statistics mapping."""
    stats = _empty_stats()
    if not isinstance(raw, dict):
        return stats, raw not in (None, {})

    repaired = False
    schema = raw.get("version")
    if schema != STATS_SCHEMA_VERSION:
        repaired = schema is not None

    stats["watch_seconds"] = coerce_float(
        raw.get("watch_seconds"), 0.0, minimum=0.0
    )
    stats["videos_played"] = coerce_int(raw.get("videos_played"), 0, minimum=0)
    stats["last_played_at"] = coerce_timestamp(raw.get("last_played_at"), 0.0)

    channels, channels_repaired = _sanitize_counts(
        raw.get("channels"), limit=MAX_CHANNELS
    )
    videos, videos_repaired = _sanitize_counts(
        raw.get("videos"), limit=MAX_TRACKED_VIDEOS
    )
    stats["channels"] = channels
    stats["videos"] = videos
    return stats, repaired or channels_repaired or videos_repaired


class AnalyticsService:
    """Aggregate local playback statistics for one profile."""

    def __init__(
        self,
        event_bus: EventBus | None = None,
        data_dir: str = "User",
        filename: str = "analytics.json",
    ):
        self._event_bus = event_bus
        self._filepath = os.path.join(data_dir, filename)
        self._store = JsonStore(self._filepath)
        self._lock = threading.RLock()
        self._stats = _empty_stats()
        self._dirty = False
        self._session: _Session | None = None
        self._started_subscription = None
        self._stopped_subscription = None

        self._load_from_disk()
        self._subscribe_events()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _subscribe_events(self):
        if self._event_bus is None:
            return
        if self._started_subscription is None:
            self._started_subscription = self._event_bus.subscribe(
                EVENT_VIDEO_STARTED, self._on_video_started, weak=False
            )
        if self._stopped_subscription is None:
            self._stopped_subscription = self._event_bus.subscribe(
                EVENT_VIDEO_STOPPED, self._on_video_stopped, weak=False
            )

    def _unsubscribe_events(self):
        if self._event_bus is None:
            return
        if self._started_subscription is not None:
            self._event_bus.unsubscribe(
                EVENT_VIDEO_STARTED, self._started_subscription
            )
            self._started_subscription = None
        if self._stopped_subscription is not None:
            self._event_bus.unsubscribe(
                EVENT_VIDEO_STOPPED, self._stopped_subscription
            )
            self._stopped_subscription = None

    def reload(self, data_dir: str, filename: str = "analytics.json"):
        """Point the service at another profile and reload its statistics."""
        self.flush()
        with self._lock:
            self._filepath = os.path.join(data_dir, filename)
            self._store = JsonStore(self._filepath)
            self._session = None
        self._load_from_disk()

    def shutdown(self):
        """Flush pending statistics and stop listening for playback events."""
        self._unsubscribe_events()
        with self._lock:
            self._session = None
        self.flush()

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def _load_from_disk(self):
        raw = self._store.load(default_factory=dict)
        stats, repaired = sanitize_stats(raw)
        with self._lock:
            self._stats = stats
            self._dirty = repaired
        if repaired:
            _logger.warning(
                "Analytics at %s contained invalid data; it was repaired",
                self._filepath,
            )
            self.flush()

    def flush(self) -> bool:
        """Persist statistics when they changed.  Returns ``True`` on success."""
        with self._lock:
            if not self._dirty:
                return True
            try:
                self._store.save(self._snapshot())
            except (OSError, TypeError, ValueError):
                _logger.exception("Unable to save analytics to %s", self._filepath)
                return False
            self._dirty = False
            return True

    def _snapshot(self) -> dict:
        """A deep-enough copy for serialization."""
        return {
            "version": STATS_SCHEMA_VERSION,
            "watch_seconds": float(self._stats.get("watch_seconds", 0.0)),
            "videos_played": int(self._stats.get("videos_played", 0)),
            "channels": dict(self._stats.get("channels", {})),
            "videos": dict(self._stats.get("videos", {})),
            "last_played_at": float(self._stats.get("last_played_at", 0.0)),
        }

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_video_started(self, event: VideoStartedEvent):
        data = event.video_data if isinstance(event.video_data, dict) else {}
        video_id = coerce_id(event.video_id) or coerce_id(
            data.get("videoId") or data.get("video_id")
        )
        channel = coerce_text(
            event.channel or data.get("channel") or "",
            max_length=MAX_CHANNEL_LENGTH,
        )
        with self._lock:
            self._session = _Session(video_id=video_id, channel=channel)

    def _on_video_stopped(self, event: VideoStoppedEvent):
        with self._lock:
            session = self._session
            self._session = None
        if session is None:
            # A stop that never had a matching start (for example playback
            # started before this service was constructed) is ignored.
            return

        duration = coerce_float(event.duration, 0.0, minimum=0.0)
        position = coerce_float(event.position, 0.0, minimum=0.0)
        if position <= 0.0 and event.reason == "ended":
            position = duration
        if duration > 0.0:
            position = min(position, duration)
        self.record_playback(
            video_id=session.video_id or coerce_id(event.video_id),
            watched_seconds=position,
            channel=session.channel,
        )

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def record_playback(
        self,
        video_id: str = "",
        watched_seconds: float = 0.0,
        channel: str = "",
    ):
        """Record one finished playback and persist the totals."""
        safe_id = coerce_id(video_id)
        safe_channel = coerce_text(channel, "", max_length=MAX_CHANNEL_LENGTH)
        watched = coerce_float(
            watched_seconds, 0.0, minimum=0.0, maximum=MAX_SESSION_SECONDS
        )

        with self._lock:
            stats = self._stats
            stats["watch_seconds"] = coerce_float(
                stats.get("watch_seconds"), 0.0, minimum=0.0
            ) + watched
            stats["videos_played"] = coerce_int(
                stats.get("videos_played"), 0, minimum=0
            ) + 1
            if safe_channel:
                channels = stats["channels"]
                channels[safe_channel] = channels.get(safe_channel, 0) + 1
                stats["channels"] = self._bounded(channels, MAX_CHANNELS)
            if safe_id:
                videos = stats["videos"]
                videos[safe_id] = videos.get(safe_id, 0) + 1
                stats["videos"] = self._bounded(videos, MAX_TRACKED_VIDEOS)
            stats["last_played_at"] = float(time.time())
            self._dirty = True
        self.flush()

    @staticmethod
    def _bounded(counts: dict[str, int], limit: int) -> dict[str, int]:
        if len(counts) <= limit:
            return counts
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))
        return dict(ordered[:limit])

    def reset(self) -> bool:
        """Clear all statistics for the active profile."""
        with self._lock:
            self._stats = _empty_stats()
            self._session = None
            self._dirty = True
        return self.flush()

    # ------------------------------------------------------------------
    # Read model
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return a display-friendly snapshot of the current totals."""
        with self._lock:
            stats = self._snapshot()
        watch_seconds = float(stats.get("watch_seconds", 0.0))
        channels = stats.get("channels", {})
        ordered = sorted(
            channels.items(), key=lambda item: (-item[1], item[0].casefold())
        )
        rewatches = sum(
            max(0, count - 1) for count in stats.get("videos", {}).values()
        )
        videos_played = int(stats.get("videos_played", 0))
        return {
            "watch_seconds": round(watch_seconds, 1),
            "watch_hours": round(watch_seconds / 3600.0, 2),
            "videos_played": videos_played,
            "top_channels": dict(ordered[:TOP_CHANNEL_LIMIT]),
            "top_channel": ordered[0][0] if ordered else "",
            "rewatches": int(rewatches),
            "last_played_at": float(stats.get("last_played_at", 0.0)),
        }
