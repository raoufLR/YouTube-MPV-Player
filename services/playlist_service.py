import logging
import os
import re
import threading
import time
from typing import TYPE_CHECKING

from core.events import (
    PlaylistCreatedEvent,
    PlaylistDeletedEvent,
    PlaylistUpdatedEvent,
    WatchLaterToggledEvent,
)
from core.json_store import JsonStore
from core.validation import coerce_id, coerce_text
from models import Playlist
from models.playlist import MAX_DESCRIPTION, MAX_PLAYLIST_NAME

if TYPE_CHECKING:
    from core import EventBus

_logger = logging.getLogger(__name__)

WATCH_LATER_ID = "watch-later"
WATCH_LATER_NAME = "Watch Later"
WATCH_LATER_DESCRIPTION = "Videos saved for later viewing"
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class PlaylistService:
    """Manages playlists stored as individual JSON files in ``playlists/``.

    Mutations are transactional: a playlist is copied, the copy is written,
    and memory is updated only after the write succeeds.  A failed write
    therefore never leaves an in-memory playlist that does not exist on disk.
    """

    def __init__(self, event_bus: EventBus | None = None,
                 data_dir: str = "User"):
        self._event_bus = event_bus
        self._playlists_dir = os.path.join(data_dir, "playlists")
        self._lock = threading.RLock()
        self._playlists: dict[str, Playlist] = {}

        self._ensure_directory()
        self._load_all()
        self._ensure_watch_later()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _ensure_directory(self):
        os.makedirs(self._playlists_dir, exist_ok=True)

    def _ensure_watch_later(self):
        with self._lock:
            existing = self._playlists.get(WATCH_LATER_ID)
            if existing is not None:
                return
            playlist = Playlist(
                id=WATCH_LATER_ID,
                name=WATCH_LATER_NAME,
                description=WATCH_LATER_DESCRIPTION,
            )
            if self._save_playlist(playlist):
                self._playlists[WATCH_LATER_ID] = playlist

    @staticmethod
    def _unique_playlist_name(name: str, existing: set[str]) -> str:
        candidate = name
        index = 2
        while candidate.casefold() in existing:
            suffix = f" ({index})"
            base = name[: max(1, MAX_PLAYLIST_NAME - len(suffix))].rstrip(" .")
            candidate = f"{base}{suffix}"
            index += 1
        return candidate

    def _load_all(self):
        loaded: dict[str, Playlist] = {}
        used_names: set[str] = set()
        try:
            filenames = sorted(os.listdir(self._playlists_dir))
        except OSError as exc:
            _logger.error("Unable to scan playlists directory: %s", exc)
            self._playlists = {}
            return

        for filename in filenames:
            if not filename.endswith(".json"):
                continue
            playlist_id = filename[:-5]
            if not _SAFE_ID_RE.match(playlist_id):
                _logger.warning("Skipping playlist file with unsafe id: %s", filename)
                continue
            store = JsonStore(os.path.join(self._playlists_dir, filename))
            data = store.load(default_factory=dict)
            if not isinstance(data, dict) or not data:
                _logger.warning("Skipping malformed playlist file: %s", filename)
                continue

            playlist = Playlist.from_dict(data)
            # The filename is the authoritative on-disk identity.
            playlist.id = playlist_id
            if playlist_id == WATCH_LATER_ID:
                playlist.name = WATCH_LATER_NAME
                playlist.description = WATCH_LATER_DESCRIPTION

            key = playlist.name.casefold()
            if key in used_names:
                unique = self._unique_playlist_name(playlist.name, used_names)
                _logger.warning(
                    "Duplicate playlist name '%s' in %s; renaming to '%s'",
                    playlist.name,
                    filename,
                    unique,
                )
                playlist.name = unique
                # Persist the repaired name so the next start is stable.
                self._save_playlist(playlist)
                key = unique.casefold()
            used_names.add(key)
            loaded[playlist_id] = playlist

        self._playlists = loaded

    def _playlist_path(self, playlist_id: str) -> str:
        if not isinstance(playlist_id, str) or not _SAFE_ID_RE.match(playlist_id):
            raise ValueError(f"Unsafe playlist id: {playlist_id!r}")
        return os.path.join(self._playlists_dir, f"{playlist_id}.json")

    def _save_playlist(self, playlist: Playlist) -> bool:
        try:
            JsonStore(self._playlist_path(playlist.id)).save(playlist.to_dict())
        except (OSError, TypeError, ValueError) as exc:
            _logger.error(
                "Failed to save playlist '%s': %s",
                getattr(playlist, "name", "?"),
                exc,
                exc_info=True,
            )
            return False
        return True

    def _delete_playlist_file(self, playlist_id: str) -> bool:
        try:
            JsonStore(self._playlist_path(playlist_id)).delete()
        except ValueError:
            _logger.warning("Refusing to delete playlist file for unsafe id: %r", playlist_id)
            return False
        except OSError as exc:
            _logger.error("Failed to delete playlist file for %r: %s", playlist_id, exc)
            return False
        return True

    def shutdown(self):
        # Playlist writes are synchronous and atomic.
        pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _name_exists(self, name: str, exclude_id: str = None) -> bool:
        return any(
            pl.name.casefold() == name.casefold() and pl.id != exclude_id
            for pl in self._playlists.values()
        )

    @staticmethod
    def _clean_name(name: object) -> str:
        return coerce_text(name, "", max_length=MAX_PLAYLIST_NAME)

    @staticmethod
    def _clean_description(description: object) -> str:
        return coerce_text(
            description, "", max_length=MAX_DESCRIPTION, multiline=True
        )

    def _get_video_id(self, video_data: dict) -> str:
        return str(video_data.get("videoId", video_data.get("video_id", video_data.get("id", ""))))

    def _copy_playlist(self, playlist: Playlist) -> Playlist:
        return Playlist.from_dict(playlist.to_dict())

    # ------------------------------------------------------------------
    # Playlist CRUD
    # ------------------------------------------------------------------

    def create_playlist(self, name: str, description: str = "") -> Playlist | None:
        name = self._clean_name(name)
        if not name:
            return None
        with self._lock:
            if self._name_exists(name):
                return None
            playlist = Playlist(
                name=name,
                description=self._clean_description(description),
            )
            if not self._save_playlist(playlist):
                return None
            self._playlists[playlist.id] = playlist

        if self._event_bus:
            self._event_bus.publish(PlaylistCreatedEvent(
                playlist_id=playlist.id, playlist_name=playlist.name
            ))
        return playlist

    def rename_playlist(self, playlist_id: str, new_name: str) -> bool:
        new_name = self._clean_name(new_name)
        if playlist_id == WATCH_LATER_ID or not new_name:
            return False
        with self._lock:
            playlist = self._playlists.get(playlist_id)
            if not playlist or self._name_exists(new_name, exclude_id=playlist_id):
                return False
            candidate = self._copy_playlist(playlist)
            candidate.name = new_name
            candidate.updated_at = time.time()
            if not self._save_playlist(candidate):
                return False
            self._playlists[playlist_id] = candidate

        if self._event_bus:
            self._event_bus.publish(PlaylistUpdatedEvent(
                playlist_id=playlist_id, action="renamed"
            ))
        return True

    def delete_playlist(self, playlist_id: str) -> bool:
        if playlist_id == WATCH_LATER_ID:
            return False
        with self._lock:
            playlist = self._playlists.get(playlist_id)
            if not playlist:
                return False
            if not self._delete_playlist_file(playlist_id):
                return False
            self._playlists.pop(playlist_id, None)

        if self._event_bus:
            self._event_bus.publish(PlaylistDeletedEvent(
                playlist_id=playlist_id, playlist_name=playlist.name
            ))
        return True

    def get_playlist(self, playlist_id: str) -> Playlist | None:
        with self._lock:
            pl = self._playlists.get(playlist_id)
            if pl:
                return self._copy_playlist(pl)
            return None

    def get_all_playlists(self) -> list[Playlist]:
        with self._lock:
            return [self._copy_playlist(pl) for pl in self._playlists.values()]

    # ------------------------------------------------------------------
    # Video operations
    # ------------------------------------------------------------------

    def add_video(self, playlist_id: str, video_data: dict) -> bool:
        if not isinstance(video_data, dict):
            return False
        video_id = coerce_id(self._get_video_id(video_data), max_length=128)
        if not video_id:
            _logger.debug("Ignoring playlist video without a safe id")
            return False
        with self._lock:
            playlist = self._playlists.get(playlist_id)
            if not playlist or playlist.has_video(video_id):
                return False
            candidate = self._copy_playlist(playlist)
            safe_video_data = dict(video_data)
            safe_video_data["video_id"] = video_id
            candidate.add_video(safe_video_data)
            candidate.updated_at = time.time()
            if not self._save_playlist(candidate):
                return False
            self._playlists[playlist_id] = candidate

        if self._event_bus:
            self._event_bus.publish(PlaylistUpdatedEvent(
                playlist_id=playlist_id, action="video_added"
            ))
        return True

    def remove_video(self, playlist_id: str, video_id: str) -> bool:
        with self._lock:
            playlist = self._playlists.get(playlist_id)
            if not playlist:
                return False
            candidate = self._copy_playlist(playlist)
            removed = candidate.remove_video(video_id)
            if not removed:
                return False
            candidate.updated_at = time.time()
            if not self._save_playlist(candidate):
                return False
            self._playlists[playlist_id] = candidate

        if self._event_bus:
            self._event_bus.publish(PlaylistUpdatedEvent(
                playlist_id=playlist_id, action="video_removed"
            ))
        return True

    def has_video(self, playlist_id: str, video_id: str) -> bool:
        with self._lock:
            playlist = self._playlists.get(playlist_id)
            if not playlist:
                return False
            return playlist.has_video(video_id)

    def get_videos(self, playlist_id: str) -> list[dict]:
        with self._lock:
            playlist = self._playlists.get(playlist_id)
            if not playlist:
                return []
            return [v.to_dict() for v in playlist.videos]

    # ------------------------------------------------------------------
    # Watch Later convenience
    # ------------------------------------------------------------------

    def toggle_watch_later(self, video_data: dict) -> bool:
        video_id = self._get_video_id(video_data)
        if self.is_in_watch_later(video_id):
            removed = self.remove_from_watch_later(video_id)
            if removed and self._event_bus:
                self._event_bus.publish(
                    WatchLaterToggledEvent(video_id=video_id, is_watch_later=False)
                )
            return False
        added = self.add_to_watch_later(video_data)
        if added and self._event_bus:
            self._event_bus.publish(
                WatchLaterToggledEvent(video_id=video_id, is_watch_later=True)
            )
        return added

    def add_to_watch_later(self, video_data: dict) -> bool:
        return self.add_video(WATCH_LATER_ID, video_data)

    def remove_from_watch_later(self, video_id: str) -> bool:
        return self.remove_video(WATCH_LATER_ID, video_id)

    def is_in_watch_later(self, video_id: str) -> bool:
        return self.has_video(WATCH_LATER_ID, video_id)

    def get_watch_later(self) -> list[dict]:
        return self.get_videos(WATCH_LATER_ID)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def count(self) -> int:
        with self._lock:
            return len(self._playlists)

    def export_all(self) -> dict[str, dict]:
        with self._lock:
            return {
                pid: pl.to_dict()
                for pid, pl in self._playlists.items()
            }

    def import_all(self, data: dict[str, dict]) -> int:
        if not isinstance(data, dict):
            return 0
        imported = 0
        with self._lock:
            used_names = {pl.name.casefold() for pl in self._playlists.values()}
            for pid, pl_data in data.items():
                if not isinstance(pid, str) or not _SAFE_ID_RE.match(pid):
                    _logger.warning("Skipping import of unsafe playlist id: %r", pid)
                    continue
                if not isinstance(pl_data, dict):
                    _logger.warning("Skipping import of malformed playlist %r", pid)
                    continue
                playlist = Playlist.from_dict(pl_data)
                playlist.id = pid
                if pid == WATCH_LATER_ID:
                    playlist.name = WATCH_LATER_NAME
                    playlist.description = WATCH_LATER_DESCRIPTION
                elif playlist.name.casefold() in used_names:
                    playlist.name = self._unique_playlist_name(
                        playlist.name, used_names
                    )
                if not self._save_playlist(playlist):
                    continue
                self._playlists[pid] = playlist
                used_names.add(playlist.name.casefold())
                imported += 1
        return imported

    def reload(self, data_dir: str):
        with self._lock:
            self._playlists_dir = os.path.join(data_dir, "playlists")
            self._ensure_directory()
            self._load_all()
            self._ensure_watch_later()

    def reset(self) -> bool:
        with self._lock:
            keep = {WATCH_LATER_ID}
            for pid in [pid for pid in self._playlists if pid not in keep]:
                if self._delete_playlist_file(pid):
                    self._playlists.pop(pid, None)
            wl = self._playlists.get(WATCH_LATER_ID)
            if wl is not None:
                candidate = self._copy_playlist(wl)
                candidate.videos.clear()
                candidate.updated_at = time.time()
                if self._save_playlist(candidate):
                    self._playlists[WATCH_LATER_ID] = candidate
        return True
