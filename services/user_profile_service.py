import json
import logging
import os
import threading
import time
from typing import TYPE_CHECKING, Any

from core.json_store import JsonStore
from core.security import copy_private_file, is_safe_local_path
from core.validation import coerce_text
from models import UserProfile

if TYPE_CHECKING:
    from core import EventBus

_logger = logging.getLogger(__name__)

PROFILE_FILENAME = "user_profile.json"
LEGACY_PROFILE_FILENAME = "profile.json"
MAX_USERNAME = 64
MAX_DISPLAY_NAME = 128


class UserProfileService:
    """Manages the rendered user-profile details for the active profile.

    ``UserManagerService`` owns ``profile.json`` (the profile registry model).
    This service deliberately uses a separate file so the two models can never
    overwrite each other.  On first run, user-facing fields from a legacy
    ``profile.json`` are imported without writing that file.
    """

    def __init__(self, event_bus: EventBus | None = None,
                 data_dir: str = "User"):
        self._event_bus = event_bus
        self._user_dir = data_dir
        self._lock = threading.RLock()
        self._profile: UserProfile | None = None
        self._store = JsonStore(os.path.join(self._user_dir, PROFILE_FILENAME))

        self._ensure_directory()
        self._load()

    def _ensure_directory(self):
        os.makedirs(self._user_dir, exist_ok=True)

    def _load(self):
        data = self._store.load(default_factory=dict)
        if isinstance(data, dict) and data:
            self._profile = UserProfile.from_dict(data)
            if self._profile.to_dict() != data:
                _logger.warning(
                    "User profile at %s contained invalid values; "
                    "they were normalized",
                    self._store.filepath,
                )
                self._save()
            return

        legacy_path = os.path.join(self._user_dir, LEGACY_PROFILE_FILENAME)
        if os.path.isfile(legacy_path):
            # Read-only migration: never modify the profile registry file.
            try:
                with open(legacy_path, encoding="utf-8") as handle:
                    legacy = json.load(handle)
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                legacy = None
            if isinstance(legacy, dict) and any(
                key in legacy
                for key in ("user_id", "username", "display_name", "avatar_path")
            ):
                self._profile = UserProfile.from_dict(legacy)
                self._save()
                return

        self._profile = UserProfile()

    def _save(self, profile: UserProfile | None = None) -> bool:
        """Persist *profile* and report success; never raises."""
        target = self._profile if profile is None else profile
        if target is None:
            return False
        try:
            self._store.save(target.to_dict())
        except (OSError, TypeError, ValueError) as exc:
            _logger.error("Failed to save user profile: %s", exc, exc_info=True)
            return False
        return True

    def shutdown(self):
        pass

    def _copy_profile(self) -> UserProfile:
        return UserProfile.from_dict(self._profile.to_dict())

    def get_profile(self) -> UserProfile:
        with self._lock:
            if self._profile is None:
                return UserProfile()
            return self._copy_profile()

    def update_profile(self, username: str = None, display_name: str = None) -> bool:
        with self._lock:
            if self._profile is None:
                return False
            candidate = self._copy_profile()
            if username is not None:
                candidate.username = (
                    coerce_text(username, "User", max_length=MAX_USERNAME) or "User"
                )
            if display_name is not None:
                candidate.display_name = (
                    coerce_text(
                        display_name, "User", max_length=MAX_DISPLAY_NAME
                    ) or "User"
                )
            candidate.updated_at = time.time()
            if not self._save(candidate):
                return False
            self._profile = candidate
            return True

    def set_avatar(self, avatar_path: str) -> bool:
        with self._lock:
            if self._profile is None:
                return False
            candidate = self._copy_profile()
            if avatar_path:
                if (
                    not isinstance(avatar_path, str)
                    or not is_safe_local_path(avatar_path)
                    or not os.path.isfile(avatar_path)
                ):
                    _logger.warning(
                        "Ignoring avatar path that is not a local file: %r",
                        avatar_path,
                    )
                    return False
                target_path = os.path.join(self._user_dir, "avatar.png")
                try:
                    if os.path.abspath(avatar_path) != os.path.abspath(target_path):
                        copy_private_file(avatar_path, target_path)
                except OSError as exc:
                    _logger.error("Failed to copy avatar: %s", exc)
                    return False
                candidate.avatar_path = target_path
            else:
                candidate.avatar_path = ""
            candidate.updated_at = time.time()
            if not self._save(candidate):
                return False
            self._profile = candidate
            return True

    def export(self) -> dict[str, Any]:
        with self._lock:
            if self._profile is None:
                return UserProfile().to_dict()
            return self._profile.to_dict()

    def import_data(self, data: dict[str, Any]) -> bool:
        if not isinstance(data, dict):
            _logger.warning("Ignoring user-profile import with non-mapping payload")
            return False
        candidate = UserProfile.from_dict(data)
        with self._lock:
            if not self._save(candidate):
                return False
            self._profile = candidate
        return True

    def reload(self, data_dir: str):
        with self._lock:
            self._user_dir = data_dir
            self._ensure_directory()
            self._store = JsonStore(os.path.join(self._user_dir, PROFILE_FILENAME))
            self._load()

    def reset(self) -> bool:
        candidate = UserProfile()
        with self._lock:
            if not self._save(candidate):
                return False
            self._profile = candidate
        return True
