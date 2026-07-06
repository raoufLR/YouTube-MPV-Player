import logging
import os
import json
import shutil
import tempfile
import threading
import time
from typing import List, Dict, Optional

from core import EventBus
from core.events import LikeChangedEvent

_logger = logging.getLogger(__name__)

MAX_LIKES = 2000


class LikesService:
    """Manages liked videos persisted in User/likes.json."""

    def __init__(self, event_bus: Optional[EventBus] = None,
                 data_dir: str = "User", filename: str = "likes.json"):
        self._event_bus = event_bus
        self._filepath = os.path.join(data_dir, filename)
        self._lock = threading.RLock()
        self._likes: List[Dict] = []

        self._ensure_directory()
        self._load()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _ensure_directory(self):
        dir_path = os.path.dirname(self._filepath)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

    def _load(self):
        if not os.path.exists(self._filepath):
            self._likes = []
            return
        try:
            with open(self._filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._likes = data
            else:
                self._likes = []
        except (json.JSONDecodeError, IOError):
            self._likes = []

    def _save(self):
        dir_path = os.path.dirname(self._filepath) or "."
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=dir_path, delete=False, encoding="utf-8"
            ) as tmp:
                json.dump(self._likes, tmp, indent=2, ensure_ascii=False)
                tmp_path = tmp.name
            shutil.move(tmp_path, self._filepath)
        except (IOError, OSError) as e:
            _logger.error("Failed to save likes: %s", e, exc_info=True)
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    def shutdown(self):
        pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _get_video_id(self, video_data: Dict) -> str:
        return str(video_data.get("videoId", video_data.get("video_id", video_data.get("id", ""))))

    def like(self, video_data: Dict) -> bool:
        video_id = self._get_video_id(video_data)
        with self._lock:
            if any(l.get("video_id") == video_id for l in self._likes):
                return False
            entry = {
                "video_id": video_id,
                "title": video_data.get("title", ""),
                "channel": video_data.get("channel", ""),
                "thumbnail": video_data.get("thumbnail", ""),
                "liked_at": time.time(),
            }
            self._likes.insert(0, entry)
            if len(self._likes) > MAX_LIKES:
                self._likes.pop()
            self._save()

        self._publish_changed(video_id, True)
        return True

    def unlike(self, video_id: str) -> bool:
        with self._lock:
            original_len = len(self._likes)
            self._likes = [l for l in self._likes if l.get("video_id") != video_id]
            removed = len(self._likes) < original_len
            if removed:
                self._save()

        if removed:
            self._publish_changed(video_id, False)
        return removed

    def is_liked(self, video_id: str) -> bool:
        with self._lock:
            return any(l.get("video_id") == video_id for l in self._likes)

    def get_liked_videos(self) -> List[Dict]:
        with self._lock:
            return list(self._likes)

    def toggle_like(self, video_data: Dict) -> bool:
        video_id = self._get_video_id(video_data)
        if self.is_liked(video_id):
            self.unlike(video_id)
            return False
        self.like(video_data)
        return True

    def count(self) -> int:
        with self._lock:
            return len(self._likes)

    def export(self) -> List[Dict]:
        with self._lock:
            return list(self._likes)

    def import_data(self, data: List[Dict]):
        with self._lock:
            self._likes = list(data)
            self._save()

    def reload(self, data_dir: str, filename: str = "likes.json"):
        with self._lock:
            self._filepath = os.path.join(data_dir, filename)
            self._ensure_directory()
        self._load()

    def reset(self):
        with self._lock:
            self._likes.clear()
            self._save()

    def _publish_changed(self, video_id: str, is_liked: bool):
        if self._event_bus:
            self._event_bus.publish(LikeChangedEvent(video_id=video_id, is_liked=is_liked))
