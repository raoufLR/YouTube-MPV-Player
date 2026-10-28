import logging
import os
import threading
from typing import TYPE_CHECKING

from core.events import LikeChangedEvent
from core.json_store import JsonStore
from core.validation import coerce_id, coerce_text, coerce_timestamp

if TYPE_CHECKING:
    from core import EventBus

_logger = logging.getLogger(__name__)

MAX_LIKES = 2000
MAX_ID_LENGTH = 128
TITLE_MAX = 512
CHANNEL_MAX = 256
THUMBNAIL_MAX = 2048


def sanitize_like_entry(raw: object) -> dict | None:
    """Return a normalized like entry, or ``None`` when it is unusable."""
    if not isinstance(raw, dict):
        return None
    video_id = coerce_id(
        raw.get("video_id", raw.get("videoId", raw.get("id", ""))),
        max_length=MAX_ID_LENGTH,
    )
    if not video_id:
        return None
    return {
        "video_id": video_id,
        "title": coerce_text(raw.get("title", ""), max_length=TITLE_MAX),
        "channel": coerce_text(raw.get("channel", ""), max_length=CHANNEL_MAX),
        "thumbnail": coerce_text(
            raw.get("thumbnail", ""), max_length=THUMBNAIL_MAX
        ),
        "liked_at": coerce_timestamp(raw.get("liked_at")),
    }


def sanitize_likes(data: object) -> tuple[list[dict], bool]:
    """Return ``(entries, repaired)`` for a persisted likes payload."""
    if not isinstance(data, list):
        return [], True

    entries: list[dict] = []
    seen = set()
    repaired = False
    for raw in data:
        entry = sanitize_like_entry(raw)
        if entry is None:
            repaired = True
            continue
        if entry["video_id"] in seen:
            repaired = True
            continue
        if len(entries) >= MAX_LIKES:
            repaired = True
            break
        if raw != entry:
            repaired = True
        seen.add(entry["video_id"])
        entries.append(entry)
    return entries, repaired


class LikesService:
    """Manages liked videos persisted in ``likes.json``.

    Mutations are transactional with respect to disk: the candidate list is
    written first and only committed to memory after the write succeeds.  A
    failed write therefore leaves memory and disk in agreement.
    """

    def __init__(self, event_bus: EventBus | None = None,
                 data_dir: str = "User", filename: str = "likes.json"):
        self._event_bus = event_bus
        self._filepath = os.path.join(data_dir, filename)
        self._store = JsonStore(self._filepath)
        self._lock = threading.RLock()
        self._likes: list[dict] = []

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
        data = self._store.load(default_factory=list)
        if isinstance(data, dict):
            # Tolerate older wrapper shapes without discarding their contents.
            data = data.get("likes", data.get("items", []))
        entries, repaired = sanitize_likes(data)
        with self._lock:
            self._likes = entries
        if repaired:
            _logger.warning(
                "Likes at %s contained invalid entries; they were repaired",
                self._filepath,
            )
            self._save(entries)

    def _save(self, snapshot: list[dict] | None = None) -> bool:
        """Persist *snapshot* and report success; never raises."""
        data = self._likes if snapshot is None else snapshot
        try:
            self._store.save(data)
        except (OSError, TypeError, ValueError) as exc:
            _logger.error("Failed to save likes: %s", exc, exc_info=True)
            return False
        return True

    def shutdown(self):
        # Likes are written synchronously; nothing to flush.
        pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _get_video_id(self, video_data: dict) -> str:
        return str(video_data.get("videoId", video_data.get("video_id", video_data.get("id", ""))))

    def like(self, video_data: dict) -> bool:
        if not isinstance(video_data, dict):
            return False
        video_id = coerce_id(
            self._get_video_id(video_data), max_length=MAX_ID_LENGTH
        )
        if not video_id:
            _logger.debug("Ignoring like without a safe video id")
            return False

        entry = sanitize_like_entry(video_data)
        if entry is None:
            return False
        # Keep the validated lookup key authoritative even if the caller
        # supplied both ``videoId`` and ``video_id`` with different values.
        entry["video_id"] = video_id

        with self._lock:
            if any(like.get("video_id") == video_id for like in self._likes):
                return False
            candidate = [entry] + self._likes
            if len(candidate) > MAX_LIKES:
                candidate = candidate[:MAX_LIKES]
            if not self._save(candidate):
                return False
            self._likes = candidate

        self._publish_changed(video_id, True)
        return True

    def unlike(self, video_id: str) -> bool:
        safe_id = coerce_id(video_id, max_length=MAX_ID_LENGTH)
        if not safe_id:
            return False
        with self._lock:
            original_len = len(self._likes)
            candidate = [
                like for like in self._likes
                if like.get("video_id") != safe_id
            ]
            if len(candidate) == original_len:
                return False
            if not self._save(candidate):
                return False
            self._likes = candidate

        self._publish_changed(safe_id, False)
        return True

    def is_liked(self, video_id: str) -> bool:
        with self._lock:
            return any(like.get("video_id") == video_id for like in self._likes)

    def get_liked_videos(self) -> list[dict]:
        with self._lock:
            return [dict(like) for like in self._likes]

    def toggle_like(self, video_data: dict) -> bool:
        video_id = self._get_video_id(video_data)
        if self.is_liked(video_id):
            self.unlike(video_id)
            # Return the resulting state, not merely whether the removal
            # succeeded: a failed disk write leaves the like in place.
            return self.is_liked(video_id)
        return self.like(video_data)

    def count(self) -> int:
        with self._lock:
            return len(self._likes)

    def export(self) -> list[dict]:
        with self._lock:
            return [dict(like) for like in self._likes]

    def import_data(self, data: list[dict]) -> bool:
        if not isinstance(data, list):
            _logger.warning("Ignoring likes import with non-list payload")
            return False
        entries, _ = sanitize_likes(data)
        with self._lock:
            if not self._save(entries):
                return False
            self._likes = entries
        return True

    def reload(self, data_dir: str, filename: str = "likes.json"):
        with self._lock:
            self._filepath = os.path.join(data_dir, filename)
            self._store = JsonStore(self._filepath)
            self._ensure_directory()
        self._load()

    def reset(self) -> bool:
        with self._lock:
            if not self._save([]):
                return False
            self._likes.clear()
        return True

    def _publish_changed(self, video_id: str, is_liked: bool):
        if self._event_bus:
            self._event_bus.publish(LikeChangedEvent(video_id=video_id, is_liked=is_liked))
