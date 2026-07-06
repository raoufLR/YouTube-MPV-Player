import logging
import os
import json
import shutil
import tempfile
import threading
import time
from typing import Optional, Dict, Any

from core import EventBus
from models import UserProfile

_logger = logging.getLogger(__name__)


class UserProfileService:
    """Manages the local user profile (User/profile.json, avatar.png)."""

    def __init__(self, event_bus: Optional[EventBus] = None,
                 data_dir: str = "User"):
        self._event_bus = event_bus
        self._user_dir = data_dir
        self._lock = threading.RLock()
        self._profile: Optional[UserProfile] = None

        self._ensure_directory()
        self._load()

    def _ensure_directory(self):
        os.makedirs(self._user_dir, exist_ok=True)

    def _load(self):
        filepath = os.path.join(self._user_dir, "profile.json")
        if not os.path.exists(filepath):
            self._profile = UserProfile()
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._profile = UserProfile.from_dict(data) if data else UserProfile()
        except (json.JSONDecodeError, IOError):
            self._profile = UserProfile()

    def _save(self):
        filepath = os.path.join(self._user_dir, "profile.json")
        dir_path = os.path.dirname(filepath) or "."
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=dir_path, delete=False, encoding="utf-8"
            ) as tmp:
                json.dump(self._profile.to_dict(), tmp, indent=2, ensure_ascii=False)
                tmp_path = tmp.name
            shutil.move(tmp_path, filepath)
        except (IOError, OSError) as e:
            _logger.error("Failed to save user profile: %s", e, exc_info=True)
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    def shutdown(self):
        pass

    def get_profile(self) -> UserProfile:
        with self._lock:
            return UserProfile(
                **{k: getattr(self._profile, k) for k in UserProfile.__dataclass_fields__}
            )

    def update_profile(self, username: str = None, display_name: str = None):
        with self._lock:
            if username is not None:
                self._profile.username = username
            if display_name is not None:
                self._profile.display_name = display_name
            self._profile.updated_at = time.time()
            self._save()

    def set_avatar(self, avatar_path: str):
        with self._lock:
            target_path = os.path.join(self._user_dir, "avatar.png")
            if os.path.exists(avatar_path) and os.path.abspath(avatar_path) != os.path.abspath(target_path):
                shutil.copy2(avatar_path, target_path)
            self._profile.avatar_path = target_path
            self._profile.updated_at = time.time()
            self._save()

    def export(self) -> Dict[str, Any]:
        with self._lock:
            return self._profile.to_dict()

    def import_data(self, data: Dict[str, Any]):
        with self._lock:
            self._profile = UserProfile.from_dict(data)
            self._save()

    def reload(self, data_dir: str):
        with self._lock:
            self._user_dir = data_dir
            self._ensure_directory()
        self._load()

    def reset(self):
        with self._lock:
            self._profile = UserProfile()
            self._save()
