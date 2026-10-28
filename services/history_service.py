"""
History Service
===============

Dedicated service for managing local watch history with asynchronous
persistence. Mutations are applied in-memory immediately (non-blocking),
and a background thread flushes dirty state to disk periodically.

Storage: history.json (flat JSON array)

Features:
    - Deduplication: re-watching a video moves it to the top
    - Capacity: hard-capped at 500 entries
    - Async writes: background flush thread, no I/O on caller thread
    - Atomic, crash-safe persistence through ``JsonStore``
    - Thread-safe: all mutations guarded by threading.RLock
    - Defensive load-time sanitization for hand-edited or partial files
"""

import logging
import os
import threading
import time
from typing import TYPE_CHECKING

from core.events import EVENT_VIDEO_STARTED, HistoryUpdatedEvent, VideoStartedEvent
from core.json_store import JsonStore
from core.validation import (
    coerce_id,
    coerce_text,
    coerce_timestamp,
)

if TYPE_CHECKING:
    from core import EventBus

_logger = logging.getLogger(__name__)

MAX_HISTORY = 500
FLUSH_INTERVAL = 2.0
MAX_ID_LENGTH = 128
TITLE_MAX = 512
CHANNEL_MAX = 256
THUMBNAIL_MAX = 2048


def sanitize_history_entry(raw: object) -> dict | None:
    """Return a normalized history entry, or ``None`` when it is unusable."""
    if not isinstance(raw, dict):
        return None
    video_id = coerce_id(
        raw.get("id", raw.get("videoId", raw.get("video_id", ""))),
        max_length=MAX_ID_LENGTH,
    )
    if not video_id:
        return None
    return {
        "id": video_id,
        "title": coerce_text(raw.get("title", ""), max_length=TITLE_MAX),
        "channel": coerce_text(raw.get("channel", ""), max_length=CHANNEL_MAX),
        "thumbnail": coerce_text(
            raw.get("thumbnail", ""), max_length=THUMBNAIL_MAX
        ),
        "watched_at": coerce_timestamp(raw.get("watched_at")),
    }


def sanitize_history(data: object) -> tuple[list[dict], bool]:
    """Return ``(entries, repaired)`` for a persisted history payload."""
    if not isinstance(data, list):
        return [], True

    entries: list[dict] = []
    seen = set()
    repaired = False
    for raw in data:
        entry = sanitize_history_entry(raw)
        if entry is None:
            repaired = True
            continue
        if entry["id"] in seen:
            repaired = True
            continue
        if len(entries) >= MAX_HISTORY:
            repaired = True
            break
        if raw != entry:
            repaired = True
        seen.add(entry["id"])
        entries.append(entry)
    return entries, repaired


class HistoryService:
    """Manages watch history with async disk persistence."""

    def __init__(self, event_bus: EventBus | None = None,
                 data_dir: str = "User", filename: str = "history.json"):
        self._event_bus = event_bus
        self._filepath = os.path.join(data_dir, filename)
        self._store = JsonStore(self._filepath)
        self._lock = threading.RLock()
        self._history: list[dict] = []
        self._dirty = False
        self._revision = 0
        self._written_revision = 0
        self._running = False
        self._stop_event = threading.Event()
        self._flush_thread: threading.Thread | None = None
        self._subscription = None

        self._ensure_directory()
        self._load_from_disk()
        self._start_flush_thread()
        self._subscribe_events()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _ensure_directory(self):
        dir_path = os.path.dirname(self._filepath)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

    def _start_flush_thread(self):
        if self._flush_thread is not None and self._flush_thread.is_alive():
            return
        self._running = True
        self._stop_event.clear()
        self._flush_thread = threading.Thread(
            target=self._flush_loop, daemon=True, name="history-flush"
        )
        self._flush_thread.start()

    def _stop_flush_thread(self):
        self._running = False
        self._stop_event.set()
        thread = self._flush_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=3.0)
        self._flush_thread = None

    def _subscribe_events(self):
        if self._event_bus and self._subscription is None:
            self._subscription = self._event_bus.subscribe(
                EVENT_VIDEO_STARTED, self._on_video_started, weak=False
            )

    def _unsubscribe_events(self):
        if self._event_bus and self._subscription is not None:
            self._event_bus.unsubscribe(EVENT_VIDEO_STARTED, self._subscription)
            self._subscription = None

    def _on_video_started(self, event: VideoStartedEvent):
        if event.video_id:
            self.add({
                "id": event.video_id,
                "title": event.title,
                "channel": event.channel,
                "thumbnail": event.thumbnail,
            })
        elif event.video_data:
            self.add(event.video_data)

    def _flush_loop(self):
        while self._running:
            if self._stop_event.wait(FLUSH_INTERVAL):
                break
            self._flush_if_dirty()

    def _mark_dirty(self):
        self._revision += 1
        self._dirty = True

    def _flush_if_dirty(self):
        with self._lock:
            if not self._dirty:
                return
            snapshot = list(self._history)
            revision = self._revision
        self._write_to_disk(snapshot, revision=revision)

    def shutdown(self):
        """Stop the flush thread, force a final write, and unsubscribe."""
        self._stop_flush_thread()
        self._flush_if_dirty()
        self._unsubscribe_events()

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def _load_from_disk(self):
        data = self._store.load(default_factory=list)
        if isinstance(data, dict):
            # Tolerate older wrapper shapes without discarding their contents.
            data = data.get("history", data.get("items", []))
        entries, repaired = sanitize_history(data)
        self._history = entries
        self._revision = 0
        self._written_revision = 0
        self._dirty = repaired
        if repaired:
            _logger.warning(
                "History at %s contained invalid entries; they were repaired",
                self._filepath,
            )

    def _write_to_disk(self, snapshot: list[dict],
                       revision: int | None = None) -> bool:
        try:
            self._store.save(snapshot)
        except (OSError, TypeError, ValueError) as exc:
            _logger.warning("Failed to write history to disk: %s", exc)
            with self._lock:
                self._dirty = True
            return False

        with self._lock:
            if revision is not None:
                self._written_revision = max(self._written_revision, revision)
            if self._revision <= self._written_revision:
                self._dirty = False
        return True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, video_data: dict) -> bool:
        """Add a video to history. Moves it to the top if already present."""
        entry = sanitize_history_entry(video_data)
        if entry is None:
            _logger.debug("Ignoring history entry without a safe video id")
            return False

        video_id = entry["id"]
        # Imports pass the original watch time; live playback has none.
        entry["watched_at"] = entry["watched_at"] or time.time()
        with self._lock:
            self._history = [
                h for h in self._history if h.get("id") != video_id
            ]
            self._history.insert(0, entry)
            if len(self._history) > MAX_HISTORY:
                self._history = self._history[:MAX_HISTORY]
            self._mark_dirty()

        if self._event_bus:
            self._event_bus.publish(HistoryUpdatedEvent(action="added", video_id=video_id))
        return True

    def remove(self, video_id: str) -> bool:
        """Remove a single entry by video id."""
        safe_id = coerce_id(video_id, max_length=MAX_ID_LENGTH)
        if not safe_id:
            return False
        with self._lock:
            original = len(self._history)
            self._history = [h for h in self._history if h.get("id") != safe_id]
            removed = len(self._history) < original
            if removed:
                self._mark_dirty()

        if removed and self._event_bus:
            self._event_bus.publish(HistoryUpdatedEvent(action="removed", video_id=safe_id))
        return removed

    def clear(self):
        """Remove all history entries."""
        with self._lock:
            if not self._history:
                return
            self._history.clear()
            self._mark_dirty()
        if self._event_bus:
            self._event_bus.publish(HistoryUpdatedEvent(action="cleared"))

    def get_all(self) -> list[dict]:
        """Return a snapshot of the full history (newest first)."""
        with self._lock:
            return [dict(entry) for entry in self._history]

    def get_recent(self, limit: int = 50) -> list[dict]:
        """Return at most *limit* recent entries."""
        with self._lock:
            return [dict(entry) for entry in self._history[:limit]]

    def contains(self, video_id: str) -> bool:
        """Check whether a video id exists in the history."""
        with self._lock:
            return any(h.get("id") == video_id for h in self._history)

    def count(self) -> int:
        with self._lock:
            return len(self._history)

    def export(self) -> list[dict]:
        with self._lock:
            return [dict(entry) for entry in self._history]

    def import_data(self, data: list[dict]) -> int:
        if not isinstance(data, list):
            _logger.warning("Ignoring history import with non-list payload")
            return -1
        entries, _ = sanitize_history(data)
        with self._lock:
            self._history = entries
            self._mark_dirty()
        return len(entries)

    def reset(self):
        with self._lock:
            if not self._history:
                return
            self._history.clear()
            self._mark_dirty()

    def reload(self, data_dir: str, filename: str = "history.json"):
        self._stop_flush_thread()
        self._flush_if_dirty()
        with self._lock:
            self._filepath = os.path.join(data_dir, filename)
            self._store = JsonStore(self._filepath)
        self._ensure_directory()
        self._load_from_disk()
        self._start_flush_thread()

    def get_stats(self) -> dict:
        with self._lock:
            if not self._history:
                return {"count": 0}
            newest = self._history[0].get("watched_at", 0)
            oldest = self._history[-1].get("watched_at", 0)
            return {
                "count": len(self._history),
                "oldest": oldest,
                "newest": newest,
            }
