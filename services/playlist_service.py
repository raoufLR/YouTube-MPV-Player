import logging
import os
import json
import shutil
import tempfile
import threading
import time
from typing import List, Optional, Dict

from core import EventBus
from core.events import (
    PlaylistCreatedEvent, PlaylistUpdatedEvent, PlaylistDeletedEvent,
    WatchLaterToggledEvent,
)
from models import Playlist, PlaylistVideo

_logger = logging.getLogger(__name__)

WATCH_LATER_ID = "watch-later"


class PlaylistService:
    """Manages playlists stored as individual JSON files in User/playlists/."""

    def __init__(self, event_bus: Optional[EventBus] = None,
                 data_dir: str = "User"):
        self._event_bus = event_bus
        self._playlists_dir = os.path.join(data_dir, "playlists")
        self._lock = threading.RLock()
        self._playlists: Dict[str, Playlist] = {}

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
            if WATCH_LATER_ID not in self._playlists:
                playlist = Playlist(
                    id=WATCH_LATER_ID,
                    name="Watch Later",
                    description="Videos saved for later viewing",
                )
                self._playlists[WATCH_LATER_ID] = playlist
                self._save_playlist(playlist)

    def _load_all(self):
        self._playlists = {}
        if not os.path.exists(self._playlists_dir):
            return
        for filename in os.listdir(self._playlists_dir):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(self._playlists_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                playlist = Playlist.from_dict(data)
                self._playlists[playlist.id] = playlist
            except (json.JSONDecodeError, IOError, KeyError):
                continue

    def _save_playlist(self, playlist: Playlist):
        filepath = os.path.join(self._playlists_dir, f"{playlist.id}.json")
        dir_path = os.path.dirname(filepath) or "."
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=dir_path, delete=False, encoding="utf-8"
            ) as tmp:
                json.dump(playlist.to_dict(), tmp, indent=2, ensure_ascii=False)
                tmp_path = tmp.name
            shutil.move(tmp_path, filepath)
        except (IOError, OSError) as e:
            _logger.error("Failed to save playlist '%s': %s", playlist.name, e, exc_info=True)
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    def _delete_playlist_file(self, playlist_id: str):
        filepath = os.path.join(self._playlists_dir, f"{playlist_id}.json")
        if os.path.exists(filepath):
            os.remove(filepath)

    def shutdown(self):
        pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _name_exists(self, name: str, exclude_id: str = None) -> bool:
        for pl in self._playlists.values():
            if pl.name == name and pl.id != exclude_id:
                return True
        return False

    def _get_video_id(self, video_data: Dict) -> str:
        return str(video_data.get("videoId", video_data.get("video_id", video_data.get("id", ""))))

    # ------------------------------------------------------------------
    # Playlist CRUD
    # ------------------------------------------------------------------

    def create_playlist(self, name: str, description: str = "") -> Optional[Playlist]:
        with self._lock:
            if self._name_exists(name):
                return None
            playlist = Playlist(name=name, description=description)
            self._playlists[playlist.id] = playlist
            self._save_playlist(playlist)

        if self._event_bus:
            self._event_bus.publish(PlaylistCreatedEvent(
                playlist_id=playlist.id, playlist_name=playlist.name
            ))
        return playlist

    def rename_playlist(self, playlist_id: str, new_name: str) -> bool:
        if playlist_id == WATCH_LATER_ID:
            return False
        with self._lock:
            playlist = self._playlists.get(playlist_id)
            if not playlist or self._name_exists(new_name, exclude_id=playlist_id):
                return False
            playlist.name = new_name
            playlist.updated_at = time.time()
            self._save_playlist(playlist)

        if self._event_bus:
            self._event_bus.publish(PlaylistUpdatedEvent(
                playlist_id=playlist_id, action="renamed"
            ))
        return True

    def delete_playlist(self, playlist_id: str) -> bool:
        if playlist_id == WATCH_LATER_ID:
            return False
        with self._lock:
            playlist = self._playlists.pop(playlist_id, None)
            if not playlist:
                return False
            self._delete_playlist_file(playlist_id)

        if self._event_bus:
            self._event_bus.publish(PlaylistDeletedEvent(
                playlist_id=playlist_id, playlist_name=playlist.name
            ))
        return True

    def get_playlist(self, playlist_id: str) -> Optional[Playlist]:
        with self._lock:
            pl = self._playlists.get(playlist_id)
            if pl:
                return Playlist.from_dict(pl.to_dict())
            return None

    def get_all_playlists(self) -> List[Playlist]:
        with self._lock:
            return [Playlist.from_dict(pl.to_dict()) for pl in self._playlists.values()]

    # ------------------------------------------------------------------
    # Video operations
    # ------------------------------------------------------------------

    def add_video(self, playlist_id: str, video_data: Dict) -> bool:
        video_id = self._get_video_id(video_data)
        with self._lock:
            playlist = self._playlists.get(playlist_id)
            if not playlist or playlist.has_video(video_id):
                return False
            playlist.add_video(video_data)
            playlist.updated_at = time.time()
            self._save_playlist(playlist)

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
            removed = playlist.remove_video(video_id)
            if removed:
                playlist.updated_at = time.time()
                self._save_playlist(playlist)

        if removed and self._event_bus:
            self._event_bus.publish(PlaylistUpdatedEvent(
                playlist_id=playlist_id, action="video_removed"
            ))
        return removed

    def has_video(self, playlist_id: str, video_id: str) -> bool:
        with self._lock:
            playlist = self._playlists.get(playlist_id)
            if not playlist:
                return False
            return playlist.has_video(video_id)

    def get_videos(self, playlist_id: str) -> List[Dict]:
        with self._lock:
            playlist = self._playlists.get(playlist_id)
            if not playlist:
                return []
            return [v.to_dict() for v in playlist.videos]

    # ------------------------------------------------------------------
    # Watch Later convenience
    # ------------------------------------------------------------------

    def toggle_watch_later(self, video_data: Dict) -> bool:
        video_id = self._get_video_id(video_data)
        if self.is_in_watch_later(video_id):
            self.remove_from_watch_later(video_id)
            if self._event_bus:
                self._event_bus.publish(
                    WatchLaterToggledEvent(video_id=video_id, is_watch_later=False)
                )
            return False
        self.add_to_watch_later(video_data)
        if self._event_bus:
            self._event_bus.publish(
                WatchLaterToggledEvent(video_id=video_id, is_watch_later=True)
            )
        return True

    def add_to_watch_later(self, video_data: Dict) -> bool:
        return self.add_video(WATCH_LATER_ID, video_data)

    def remove_from_watch_later(self, video_id: str) -> bool:
        return self.remove_video(WATCH_LATER_ID, video_id)

    def is_in_watch_later(self, video_id: str) -> bool:
        return self.has_video(WATCH_LATER_ID, video_id)

    def get_watch_later(self) -> List[Dict]:
        return self.get_videos(WATCH_LATER_ID)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def count(self) -> int:
        with self._lock:
            return len(self._playlists)

    def export_all(self) -> Dict[str, List]:
        with self._lock:
            return {
                pid: pl.to_dict()
                for pid, pl in self._playlists.items()
            }

    def import_all(self, data: Dict[str, Dict]):
        with self._lock:
            for pid, pl_data in data.items():
                playlist = Playlist.from_dict(pl_data)
                self._playlists[pid] = playlist
                self._save_playlist(playlist)

    def reload(self, data_dir: str):
        with self._lock:
            self._playlists_dir = os.path.join(data_dir, "playlists")
            self._ensure_directory()
            self._playlists.clear()
        self._load_all()
        self._ensure_watch_later()

    def reset(self):
        with self._lock:
            keep = {WATCH_LATER_ID}
            to_delete = [pid for pid in self._playlists if pid not in keep]
            for pid in to_delete:
                pl = self._playlists.pop(pid, None)
                if pl:
                    self._delete_playlist_file(pid)
            wl = self._playlists.get(WATCH_LATER_ID)
            if wl:
                wl.videos.clear()
                wl.updated_at = time.time()
                self._save_playlist(wl)
