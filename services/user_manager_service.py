import json
import logging
import os
import shutil
import tempfile
import threading
import time
from typing import List, Optional

from core import EventBus
from core.events import (
    ProfileCreatedEvent, ProfileDeletedEvent, ProfileChangedEvent, ProfileLoadedEvent,
)
from models import Profile

_logger = logging.getLogger(__name__)

PROFILE_FILENAME = "profile.json"
DEFAULT_AVATAR = ""


class UserManagerService:
    def __init__(self, base_dir: str = "User", event_bus: Optional[EventBus] = None):
        self._base_dir = base_dir
        self._event_bus = event_bus
        self._lock = threading.RLock()
        self._current_profile_name: Optional[str] = None

        os.makedirs(self._base_dir, exist_ok=True)
        self._ensure_default_profile()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _ensure_default_profile(self):
        profiles = self._list_profile_names()
        if not profiles:
            self._create_profile_dir("Default")
            profiles = self._list_profile_names()
        if not self._current_profile_name and profiles:
            self.load_profile(profiles[0])

    def _list_profile_names(self) -> List[str]:
        result = []
        if not os.path.exists(self._base_dir):
            return result
        for entry in os.listdir(self._base_dir):
            entry_path = os.path.join(self._base_dir, entry)
            if os.path.isdir(entry_path) and os.path.exists(
                os.path.join(entry_path, PROFILE_FILENAME)
            ):
                result.append(entry)
        return sorted(result)

    def _create_profile_dir(self, name: str) -> Profile:
        profile_dir = os.path.join(self._base_dir, name)
        os.makedirs(profile_dir, exist_ok=True)
        os.makedirs(os.path.join(profile_dir, "playlists"), exist_ok=True)
        os.makedirs(os.path.join(profile_dir, "cache", "thumbnails"), exist_ok=True)

        profile = Profile(name=name)
        self._write_profile(profile_dir, profile)
        return profile

    def _write_profile(self, profile_dir: str, profile: Profile):
        filepath = os.path.join(profile_dir, PROFILE_FILENAME)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=profile_dir, delete=False, encoding="utf-8"
            ) as tmp:
                json.dump(profile.to_dict(), tmp, indent=2, ensure_ascii=False)
                tmp_path = tmp.name
            shutil.move(tmp_path, filepath)
        except (IOError, OSError) as e:
            _logger.error("Failed to save profile: %s", e, exc_info=True)
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    def _read_profile(self, name: str) -> Profile:
        filepath = os.path.join(self._base_dir, name, PROFILE_FILENAME)
        if not os.path.exists(filepath):
            profile = Profile(name=name)
            self._write_profile(os.path.join(self._base_dir, name), profile)
            return profile
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Profile.from_dict(data)
        except (json.JSONDecodeError, IOError):
            return Profile(name=name)

    def _profile_dir(self, name: str) -> str:
        return os.path.join(self._base_dir, name)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_profile(self, name: str) -> Optional[Profile]:
        name = name.strip()
        if not name:
            return None
        with self._lock:
            if name in self._list_profile_names():
                _logger.warning("Profile '%s' already exists", name)
                return None
            profile = self._create_profile_dir(name)
        if self._event_bus:
            self._event_bus.publish(ProfileCreatedEvent(profile_name=name))
        return profile

    def delete_profile(self, name: str) -> bool:
        if name.lower() == "default":
            _logger.warning("Cannot delete the Default profile")
            return False
        with self._lock:
            if name not in self._list_profile_names():
                return False
            profile_dir = self._profile_dir(name)
            try:
                shutil.rmtree(profile_dir)
            except OSError as e:
                _logger.error("Failed to delete profile '%s': %s", name, e)
                return False
            if self._current_profile_name == name:
                self._current_profile_name = None
        if self._event_bus:
            self._event_bus.publish(ProfileDeletedEvent(profile_name=name))
        return True

    def rename_profile(self, old_name: str, new_name: str) -> bool:
        new_name = new_name.strip()
        if not new_name:
            return False
        if old_name.lower() == "default":
            _logger.warning("Cannot rename the Default profile")
            return False
        with self._lock:
            profile_names = self._list_profile_names()
            if old_name not in profile_names or new_name in profile_names:
                return False
            old_dir = self._profile_dir(old_name)
            new_dir = self._profile_dir(new_name)
            try:
                os.rename(old_dir, new_dir)
            except OSError as e:
                _logger.error("Failed to rename profile '%s': %s", old_name, e)
                return False
            profile = self._read_profile(new_name)
            profile.name = new_name
            self._write_profile(new_dir, profile)
            if self._current_profile_name == old_name:
                self._current_profile_name = new_name
        if self._event_bus:
            self._event_bus.publish(ProfileChangedEvent(profile_name=new_name))
        return True

    def duplicate_profile(self, source_name: str, new_name: str) -> Optional[Profile]:
        new_name = new_name.strip()
        if not new_name:
            return None
        with self._lock:
            profile_names = self._list_profile_names()
            if source_name not in profile_names or new_name in profile_names:
                return None
            src_dir = self._profile_dir(source_name)
            dst_dir = self._profile_dir(new_name)
            try:
                shutil.copytree(src_dir, dst_dir)
            except OSError as e:
                _logger.error("Failed to duplicate profile '%s': %s", source_name, e)
                return None
            profile = self._read_profile(new_name)
            profile.name = new_name
            profile.id = Profile().id
            profile.created_at = time.time()
            profile.last_opened = time.time()
            self._write_profile(dst_dir, profile)
        return profile

    def list_profiles(self) -> List[Profile]:
        with self._lock:
            return [self._read_profile(name) for name in self._list_profile_names()]

    def profile_count(self) -> int:
        with self._lock:
            return len(self._list_profile_names())

    def load_profile(self, name: str) -> Optional[Profile]:
        with self._lock:
            if name not in self._list_profile_names():
                _logger.warning("Profile '%s' not found", name)
                return None
            self._current_profile_name = name
            profile = self._read_profile(name)
            profile.touch()
            self._write_profile(self._profile_dir(name), profile)
        if self._event_bus:
            self._event_bus.publish(ProfileLoadedEvent(profile_name=name))
        return profile

    def switch_profile(self, name: str) -> Optional[Profile]:
        old_name = self._current_profile_name
        profile = self.load_profile(name)
        if profile and old_name != name and self._event_bus:
            self._event_bus.publish(ProfileChangedEvent(profile_name=name))
        return profile

    def current_profile(self) -> Optional[Profile]:
        if not self._current_profile_name:
            return None
        return self._read_profile(self._current_profile_name)

    def current_profile_name(self) -> Optional[str]:
        return self._current_profile_name

    def current_profile_dir(self) -> str:
        name = self._current_profile_name
        if not name:
            name = "Default"
            self._current_profile_name = name
        return self._profile_dir(name)

    def profile_dir(self, name: str) -> str:
        return self._profile_dir(name)

    def has_profile(self, name: str) -> bool:
        return name in self._list_profile_names()

    def set_profile_avatar(self, name: str, avatar_path: str):
        with self._lock:
            if name not in self._list_profile_names():
                return
            profile_dir = self._profile_dir(name)
            profile = self._read_profile(name)
            if avatar_path:
                dest = os.path.join(profile_dir, "avatar.png")
                if os.path.exists(avatar_path) and os.path.abspath(avatar_path) != os.path.abspath(dest):
                    shutil.copy2(avatar_path, dest)
                profile.avatar = dest
            else:
                profile.avatar = ""
            self._write_profile(profile_dir, profile)

    def shutdown(self):
        pass
