import logging
import os
import shutil
import threading
import time
import uuid
from typing import TYPE_CHECKING

from core.events import (
    ProfileChangedEvent,
    ProfileCreatedEvent,
    ProfileDeletedEvent,
    ProfileLoadedEvent,
)
from core.json_store import JsonStore
from core.security import copy_private_file, is_safe_local_path
from models import Profile

if TYPE_CHECKING:
    from core import EventBus

_logger = logging.getLogger(__name__)

PROFILE_FILENAME = "profile.json"
PROFILES_DIRNAME = "profiles"
DEFAULT_AVATAR = ""
MAX_PROFILE_NAME_LENGTH = 64

_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_INVALID_NAME_CHARS = set('<>:"/\\|?*')


def normalize_profile_name(name: str) -> str | None:
    """Return a safe display name, or ``None`` if the name is invalid.

    Profile names are display labels only; directories use opaque IDs.  The
    validation still rejects path separators, control characters, Windows
    reserved device names, and trailing dots so names remain portable.
    """
    if not isinstance(name, str):
        return None
    name = name.strip()
    if not name or len(name) > MAX_PROFILE_NAME_LENGTH:
        return None
    if name in {".", ".."} or name.endswith("."):
        return None
    if any(ord(ch) < 32 or ch in _INVALID_NAME_CHARS for ch in name):
        return None
    if name.split(".")[0].strip().upper() in _RESERVED_NAMES:
        return None
    return name


def _sanitize_legacy_name(name: str) -> str:
    cleaned = "".join(
        ch for ch in str(name)
        if ord(ch) >= 32 and ch not in _INVALID_NAME_CHARS
    ).strip(" .")
    if not cleaned:
        cleaned = "Recovered Profile"
    if cleaned.split(".")[0].strip().upper() in _RESERVED_NAMES:
        cleaned = f"{cleaned} Profile"
    return cleaned[:MAX_PROFILE_NAME_LENGTH].rstrip(" .") or "Recovered Profile"


class UserManagerService:
    """Manages profiles stored under ``base_dir/profiles/<opaque-id>/``.

    Existing installations used ``base_dir/<profile-name>/``.  Those
    directories are migrated once at startup; the directory names become
    opaque IDs so profile names can never escape the profile root.
    """

    def __init__(self, base_dir: str = "User", event_bus: EventBus | None = None):
        self._base_dir = base_dir
        self._profiles_dir = os.path.join(base_dir, PROFILES_DIRNAME)
        self._event_bus = event_bus
        self._lock = threading.RLock()
        self._current_profile_name: str | None = None

        os.makedirs(self._base_dir, exist_ok=True)
        os.makedirs(self._profiles_dir, exist_ok=True)
        self._migrate_legacy_profiles()
        self._ensure_default_profile()

    # ------------------------------------------------------------------
    # Initialization and migration
    # ------------------------------------------------------------------

    def _migrate_legacy_profiles(self):
        """Move ``base/<name>`` profile directories to ``base/profiles/<id>``."""
        try:
            entries = list(os.scandir(self._base_dir))
        except OSError as exc:
            _logger.error("Unable to scan profile base %s: %s", self._base_dir, exc)
            return

        for entry in entries:
            try:
                if not entry.is_dir() or os.path.normcase(entry.path) == os.path.normcase(
                    self._profiles_dir
                ):
                    continue
            except OSError:
                continue
            profile_file = os.path.join(entry.path, PROFILE_FILENAME)
            if not os.path.isfile(profile_file):
                continue
            self._migrate_legacy_profile(entry.path, entry.name)

    def _migrate_legacy_profile(self, source_dir: str, legacy_name: str):
        store = JsonStore(os.path.join(source_dir, PROFILE_FILENAME))
        data = store.load(default_factory=dict)
        if not isinstance(data, dict):
            data = {}

        existing = self._scan_profiles()
        existing_keys = set(existing)
        raw_name = data.get("name") or legacy_name
        name = normalize_profile_name(raw_name) or _sanitize_legacy_name(raw_name)
        name = self._unique_name(name, existing_keys)

        profile_id = uuid.uuid4().hex
        target_dir = os.path.join(self._profiles_dir, profile_id)
        try:
            os.replace(source_dir, target_dir)
        except OSError as exc:
            _logger.error(
                "Unable to migrate legacy profile directory %s: %s",
                source_dir,
                exc,
            )
            return

        profile = Profile.from_dict(data)
        profile.id = profile_id
        profile.name = name
        try:
            self._write_profile(target_dir, profile)
        except (OSError, TypeError) as exc:
            _logger.error(
                "Unable to write metadata for migrated profile %s: %s",
                target_dir,
                exc,
            )

    def _ensure_default_profile(self):
        profiles = self._scan_profiles()
        if not profiles:
            try:
                self._create_profile_dir("Default")
            except OSError as exc:
                _logger.error("Unable to create the Default profile: %s", exc)
                return
            profiles = self._scan_profiles()
        if not self._current_profile_name and profiles:
            default_key = "default"
            key = default_key if default_key in profiles else sorted(profiles)[0]
            self.load_profile(profiles[key][0].name)

    # ------------------------------------------------------------------
    # Storage helpers
    # ------------------------------------------------------------------

    def _scan_profiles(self) -> dict[str, tuple[Profile, str]]:
        """Return ``{casefolded name: (profile, directory)}``.

        Directory names are opaque and stable, so they determine which
        duplicate keeps its name.  Additional duplicates are renamed and the
        repaired metadata is persisted instead of silently hiding a profile.
        """
        result: dict[str, tuple[Profile, str]] = {}
        if not os.path.isdir(self._profiles_dir):
            return result

        try:
            entries = sorted(os.scandir(self._profiles_dir), key=lambda e: e.name)
        except OSError as exc:
            _logger.error("Unable to scan profiles directory: %s", exc)
            return result

        for entry in entries:
            try:
                if not entry.is_dir():
                    continue
            except OSError:
                continue
            profile = self._read_profile_dir(entry.path, fallback_name="Recovered Profile")
            if profile is None:
                profile = self._recover_profile_dir(entry.path)
            if profile is None:
                continue

            name = normalize_profile_name(profile.name) or _sanitize_legacy_name(
                profile.name or "Recovered Profile"
            )
            profile.name = name
            key = name.casefold()
            if key in result:
                unique = self._unique_name(name, set(result))
                _logger.warning(
                    "Duplicate profile name '%s' in %s; renaming to '%s'",
                    name,
                    entry.path,
                    unique,
                )
                profile.name = unique
                try:
                    self._write_profile(entry.path, profile)
                except (OSError, TypeError) as exc:
                    _logger.error(
                        "Unable to persist duplicate profile rename in %s: %s",
                        entry.path,
                        exc,
                    )
                key = unique.casefold()
            result[key] = (profile, entry.path)
        return result

    @staticmethod
    def _looks_like_profile_dir(profile_dir: str) -> bool:
        """Return ``True`` when a directory contains recoverable profile data."""
        markers = (
            PROFILE_FILENAME,
            "user_profile.json",
            "settings.json",
            "history.json",
            "likes.json",
        )
        if any(os.path.isfile(os.path.join(profile_dir, name)) for name in markers):
            return True
        return any(
            os.path.isdir(os.path.join(profile_dir, name))
            for name in ("playlists", "cache")
        )

    def _recover_profile_dir(self, profile_dir: str) -> Profile | None:
        """Create metadata for a data directory whose ``profile.json`` is gone."""
        if not self._looks_like_profile_dir(profile_dir):
            return None
        profile = Profile(
            id=os.path.basename(profile_dir), name="Recovered Profile"
        )
        try:
            self._write_profile(profile_dir, profile)
            _logger.warning(
                "Recovered profile metadata for %s", profile_dir
            )
        except (OSError, TypeError) as exc:
            _logger.error(
                "Unable to recover profile metadata for %s: %s",
                profile_dir,
                exc,
            )
        return profile

    def _read_profile_dir(
        self, profile_dir: str, fallback_name: str = "Recovered Profile"
    ) -> Profile | None:
        filepath = os.path.join(profile_dir, PROFILE_FILENAME)
        if not os.path.isfile(filepath):
            return None
        data = JsonStore(filepath).load(default_factory=dict)
        repaired = not isinstance(data, dict) or not data
        if repaired:
            profile = Profile(
                id=os.path.basename(profile_dir), name=fallback_name
            )
        else:
            profile = Profile.from_dict(data)
            repaired = profile.to_dict() != data

        # The directory name is the authoritative identity.
        profile_id = os.path.basename(profile_dir)
        if profile.id != profile_id:
            profile.id = profile_id
            repaired = True
        if repaired:
            try:
                self._write_profile(profile_dir, profile)
            except (OSError, TypeError) as exc:
                _logger.error(
                    "Unable to repair profile metadata in %s: %s",
                    profile_dir,
                    exc,
                )
        return profile

    def _write_profile(self, profile_dir: str, profile: Profile):
        os.makedirs(profile_dir, exist_ok=True)
        JsonStore(os.path.join(profile_dir, PROFILE_FILENAME)).save(profile.to_dict())

    def _create_profile_dir(self, name: str) -> Profile:
        profile_id = uuid.uuid4().hex
        profile_dir = os.path.join(self._profiles_dir, profile_id)
        os.makedirs(profile_dir, exist_ok=False)
        os.makedirs(os.path.join(profile_dir, "playlists"), exist_ok=True)
        os.makedirs(os.path.join(profile_dir, "cache", "thumbnails"), exist_ok=True)

        profile = Profile(id=profile_id, name=name)
        try:
            self._write_profile(profile_dir, profile)
        except Exception:
            shutil.rmtree(profile_dir, ignore_errors=True)
            raise
        return profile

    def _find_profile(self, name: str) -> tuple[Profile, str] | None:
        if not isinstance(name, str):
            return None
        key = name.strip().casefold()
        if not key:
            return None
        return self._scan_profiles().get(key)

    def _profile_dir(self, name: str) -> str:
        found = self._find_profile(name)
        return found[1] if found else ""

    @staticmethod
    def _unique_name(name: str, existing_keys) -> str:
        candidate = name
        index = 2
        while candidate.casefold() in existing_keys:
            suffix = f" ({index})"
            base = name[: max(1, MAX_PROFILE_NAME_LENGTH - len(suffix))].rstrip(" .")
            candidate = f"{base}{suffix}"
            index += 1
        return candidate

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_profile(self, name: str) -> Profile | None:
        clean_name = normalize_profile_name(name)
        if clean_name is None:
            _logger.warning("Rejected invalid profile name: %r", name)
            return None
        with self._lock:
            if clean_name.casefold() in self._scan_profiles():
                _logger.warning("Profile '%s' already exists", clean_name)
                return None
            try:
                profile = self._create_profile_dir(clean_name)
            except OSError as exc:
                _logger.error("Failed to create profile '%s': %s", clean_name, exc)
                return None
        if self._event_bus:
            self._event_bus.publish(ProfileCreatedEvent(profile_name=clean_name))
        return profile

    def delete_profile(self, name: str) -> bool:
        if isinstance(name, str) and name.strip().casefold() == "default":
            _logger.warning("Cannot delete the Default profile")
            return False
        with self._lock:
            found = self._find_profile(name)
            if found is None:
                return False
            profile, profile_dir = found
            if (
                self._current_profile_name
                and self._current_profile_name.casefold() == profile.name.casefold()
            ):
                # Deleting the active profile would leave every service
                # pointing at a directory that no longer exists.
                _logger.warning(
                    "Refusing to delete the active profile '%s'", profile.name
                )
                return False
            try:
                shutil.rmtree(profile_dir)
            except OSError as exc:
                _logger.error("Failed to delete profile '%s': %s", profile.name, exc)
                return False
        if self._event_bus:
            self._event_bus.publish(ProfileDeletedEvent(profile_name=profile.name))
        return True

    def rename_profile(self, old_name: str, new_name: str) -> bool:
        if isinstance(old_name, str) and old_name.strip().casefold() == "default":
            _logger.warning("Cannot rename the Default profile")
            return False
        clean_new_name = normalize_profile_name(new_name)
        if clean_new_name is None:
            return False
        with self._lock:
            found = self._find_profile(old_name)
            if found is None:
                return False
            profile, profile_dir = found
            if (
                clean_new_name.casefold() in self._scan_profiles()
                and clean_new_name.casefold() != profile.name.casefold()
            ):
                return False
            was_current = bool(
                self._current_profile_name
                and self._current_profile_name.casefold() == profile.name.casefold()
            )
            profile.name = clean_new_name
            try:
                self._write_profile(profile_dir, profile)
            except (OSError, TypeError) as exc:
                _logger.error("Failed to rename profile '%s': %s", old_name, exc)
                return False
            if was_current:
                self._current_profile_name = clean_new_name
        if self._event_bus:
            self._event_bus.publish(ProfileChangedEvent(profile_name=clean_new_name))
        return True

    def duplicate_profile(self, source_name: str, new_name: str) -> Profile | None:
        clean_new_name = normalize_profile_name(new_name)
        if clean_new_name is None:
            return None
        with self._lock:
            found = self._find_profile(source_name)
            if found is None or clean_new_name.casefold() in self._scan_profiles():
                return None
            source_profile, source_dir = found
            profile_id = uuid.uuid4().hex
            target_dir = os.path.join(self._profiles_dir, profile_id)
            try:
                shutil.copytree(source_dir, target_dir)
            except OSError as exc:
                shutil.rmtree(target_dir, ignore_errors=True)
                _logger.error(
                    "Failed to duplicate profile '%s': %s", source_profile.name, exc
                )
                return None
            for relative in (("playlists",), ("cache", "thumbnails")):
                try:
                    os.makedirs(os.path.join(target_dir, *relative), exist_ok=True)
                except OSError as exc:
                    shutil.rmtree(target_dir, ignore_errors=True)
                    _logger.error("Failed to prepare duplicated profile: %s", exc)
                    return None
            profile = self._read_profile_dir(
                target_dir, fallback_name=clean_new_name
            ) or Profile(name=clean_new_name)
            profile.id = profile_id
            profile.name = clean_new_name
            profile.created_at = time.time()
            profile.last_opened = time.time()
            try:
                self._write_profile(target_dir, profile)
            except (OSError, TypeError) as exc:
                shutil.rmtree(target_dir, ignore_errors=True)
                _logger.error("Failed to write duplicated profile: %s", exc)
                return None
        if self._event_bus:
            self._event_bus.publish(ProfileCreatedEvent(profile_name=clean_new_name))
        return profile

    def list_profiles(self) -> list[Profile]:
        with self._lock:
            profiles = self._scan_profiles()
            result = [profile for profile, _ in profiles.values()]
            result.sort(key=lambda p: p.name.casefold())
            return [Profile.from_dict(profile.to_dict()) for profile in result]

    def profile_count(self) -> int:
        with self._lock:
            return len(self._scan_profiles())

    def load_profile(self, name: str) -> Profile | None:
        with self._lock:
            found = self._find_profile(name)
            if found is None:
                _logger.warning("Profile '%s' not found", name)
                return None
            profile, profile_dir = found
            self._current_profile_name = profile.name
            profile.touch()
            try:
                self._write_profile(profile_dir, profile)
            except (OSError, TypeError) as exc:
                _logger.warning("Unable to update profile timestamp: %s", exc)
        if self._event_bus:
            self._event_bus.publish(ProfileLoadedEvent(profile_name=profile.name))
        return profile

    def switch_profile(self, name: str) -> Profile | None:
        old_name = self._current_profile_name
        profile = self.load_profile(name)
        if (
            profile
            and (old_name is None or old_name.casefold() != profile.name.casefold())
            and self._event_bus
        ):
            self._event_bus.publish(ProfileChangedEvent(profile_name=profile.name))
        return profile

    def current_profile(self) -> Profile | None:
        if not self._current_profile_name:
            return None
        found = self._find_profile(self._current_profile_name)
        return found[0] if found else None

    def current_profile_name(self) -> str | None:
        return self._current_profile_name

    def current_profile_dir(self) -> str:
        with self._lock:
            found = (
                self._find_profile(self._current_profile_name)
                if self._current_profile_name
                else None
            )
            if found is None:
                profiles = self._scan_profiles()
                if not profiles:
                    try:
                        self._create_profile_dir("Default")
                    except OSError as exc:
                        _logger.error("Unable to create a profile directory: %s", exc)
                        return ""
                    profiles = self._scan_profiles()
                if not profiles:
                    return ""
                key = "default" if "default" in profiles else sorted(profiles)[0]
                self.load_profile(profiles[key][0].name)
                found = profiles[key]
            return found[1]

    def profile_dir(self, name: str) -> str:
        return self._profile_dir(name)

    def has_profile(self, name: str) -> bool:
        return self._find_profile(name) is not None

    def set_profile_avatar(self, name: str, avatar_path: str) -> bool:
        with self._lock:
            found = self._find_profile(name)
            if found is None:
                return False
            profile, profile_dir = found
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
                dest = os.path.join(profile_dir, "avatar.png")
                try:
                    if os.path.abspath(avatar_path) != os.path.abspath(dest):
                        copy_private_file(avatar_path, dest)
                except OSError as exc:
                    _logger.error("Failed to copy profile avatar: %s", exc)
                    return False
                profile.avatar = dest
            else:
                profile.avatar = ""
            try:
                self._write_profile(profile_dir, profile)
            except (OSError, TypeError) as exc:
                _logger.error("Failed to save profile avatar: %s", exc)
                return False
        return True

    def shutdown(self):
        # Profile metadata is written synchronously and atomically.
        pass
