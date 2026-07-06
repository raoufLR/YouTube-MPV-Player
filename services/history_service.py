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
    - Thread-safe: all mutations guarded by threading.RLock
"""

import logging
import os
import json
import shutil
import tempfile
import threading
import time
from typing import List, Dict, Optional

from core import EventBus
from core.events import HistoryUpdatedEvent, VideoStartedEvent, EVENT_VIDEO_STARTED

_logger = logging.getLogger(__name__)

MAX_HISTORY = 500
FLUSH_INTERVAL = 2.0


class HistoryService:
    """Manages watch history with async disk persistence"""

    def __init__(self, event_bus: Optional[EventBus] = None,
                 data_dir: str = "User", filename: str = "history.json"):
        self._event_bus = event_bus
        self._filepath = os.path.join(data_dir, filename)
        self._lock = threading.RLock()
        self._history: List[Dict] = []
        self._dirty = False
        self._running = False
        self._flush_thread: Optional[threading.Thread] = None

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
        self._running = True
        self._flush_thread = threading.Thread(
            target=self._flush_loop, daemon=True, name="history-flush"
        )
        self._flush_thread.start()

    def _subscribe_events(self):
        if self._event_bus:
            self._event_bus.subscribe(EVENT_VIDEO_STARTED, self._on_video_started, weak=False)

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
            time.sleep(FLUSH_INTERVAL)
            self._flush_if_dirty()

    def _flush_if_dirty(self):
        with self._lock:
            if not self._dirty:
                return
            snapshot = list(self._history)
            self._dirty = False
        self._write_to_disk(snapshot)

    def shutdown(self):
        """Stop the flush thread and force a final write."""
        self._running = False
        if self._flush_thread and self._flush_thread.is_alive():
            self._flush_thread.join(timeout=3.0)
        self._flush_if_dirty()

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def _load_from_disk(self):
        if not os.path.exists(self._filepath):
            self._history = []
            return
        try:
            with open(self._filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._history = data[:MAX_HISTORY]
            else:
                self._history = []
        except (json.JSONDecodeError, IOError):
            self._history = []

    def _write_to_disk(self, snapshot: List[Dict]):
        dir_path = os.path.dirname(self._filepath) or "."
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=dir_path, delete=False, encoding="utf-8"
            ) as tmp:
                json.dump(snapshot, tmp, indent=2, ensure_ascii=False)
                tmp_path = tmp.name
            shutil.move(tmp_path, self._filepath)
        except (IOError, OSError) as e:
            _logger.warning("Failed to write history to disk: %s", e)
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, video_data: Dict):
        """Add a video to history. Moves it to the top if already present."""
        video_id = str(video_data.get("id", video_data.get("videoId", video_data.get("video_id", ""))))
        with self._lock:
            self._history = [
                h for h in self._history if h.get("id") != video_id
            ]
            entry = {
                "id": video_id,
                "title": video_data.get("title", ""),
                "channel": video_data.get("channel", ""),
                "thumbnail": video_data.get("thumbnail", ""),
                "watched_at": time.time(),
            }
            self._history.insert(0, entry)
            if len(self._history) > MAX_HISTORY:
                self._history = self._history[:MAX_HISTORY]
            self._dirty = True

        if self._event_bus:
            self._event_bus.publish(HistoryUpdatedEvent(action="added", video_id=video_id))

    def remove(self, video_id: str) -> bool:
        """Remove a single entry by video id."""
        with self._lock:
            original = len(self._history)
            self._history = [h for h in self._history if h.get("id") != video_id]
            removed = len(self._history) < original
            if removed:
                self._dirty = True

        if removed and self._event_bus:
            self._event_bus.publish(HistoryUpdatedEvent(action="removed", video_id=video_id))
        return removed

    def clear(self):
        """Remove all history entries."""
        with self._lock:
            self._history.clear()
            self._dirty = True
        if self._event_bus:
            self._event_bus.publish(HistoryUpdatedEvent(action="cleared"))

    def get_all(self) -> List[Dict]:
        """Return a snapshot of the full history (newest first)."""
        with self._lock:
            return list(self._history)

    def get_recent(self, limit: int = 50) -> List[Dict]:
        """Return at most *limit* recent entries."""
        with self._lock:
            return list(self._history[:limit])

    def contains(self, video_id: str) -> bool:
        """Check whether a video id exists in the history."""
        with self._lock:
            return any(h.get("id") == video_id for h in self._history)

    def count(self) -> int:
        with self._lock:
            return len(self._history)

    def export(self) -> List[Dict]:
        with self._lock:
            return list(self._history)

    def import_data(self, data: List[Dict]):
        with self._lock:
            self._history = list(data)[:MAX_HISTORY]
            self._dirty = True

    def reset(self):
        with self._lock:
            self._history.clear()
            self._dirty = True

    def reload(self, data_dir: str, filename: str = "history.json"):
        self._running = False
        if self._flush_thread and self._flush_thread.is_alive():
            self._flush_thread.join(timeout=3.0)
        self._flush_if_dirty()
        self._filepath = os.path.join(data_dir, filename)
        self._ensure_directory()
        self._load_from_disk()
        self._start_flush_thread()

    def get_stats(self) -> Dict:
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
