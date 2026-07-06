import logging
import os
import json
import shutil
import tempfile
import threading
import time
from typing import Any, Optional, Dict

from core import EventBus
from core.events import SettingsChangedEvent

_logger = logging.getLogger(__name__)
from models import UserSettings

FLUSH_INTERVAL = 1.0


class SettingsService:
    """Manages user settings persisted in User/settings.json.

    Uses debounced async persistence: mutations update memory immediately
    and mark dirty; a background flush thread writes to disk periodically.
    """

    def __init__(self, event_bus: Optional[EventBus] = None,
                 data_dir: str = "User", filename: str = "settings.json"):
        self._event_bus = event_bus
        self._filepath = os.path.join(data_dir, filename)
        self._lock = threading.RLock()
        self._settings: UserSettings = UserSettings()
        self._dirty = False
        self._running = False
        self._flush_thread: Optional[threading.Thread] = None

        self._ensure_directory()
        self._load()
        self._start_flush_thread()

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
            target=self._flush_loop, daemon=True, name="settings-flush"
        )
        self._flush_thread.start()

    def _flush_loop(self):
        while self._running:
            time.sleep(FLUSH_INTERVAL)
            self._flush_if_dirty()

    def _flush_if_dirty(self):
        with self._lock:
            if not self._dirty:
                return
            snapshot = UserSettings(
                **{k: getattr(self._settings, k) for k in UserSettings.__dataclass_fields__}
            )
            self._dirty = False
        self._write(snapshot)

    def _load(self):
        if not os.path.exists(self._filepath):
            self._settings = UserSettings()
            self._dirty = True
            return
        try:
            with open(self._filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._settings = UserSettings.from_dict(data)
            else:
                self._settings = UserSettings()
        except (json.JSONDecodeError, IOError):
            self._settings = UserSettings()

    def _write(self, settings: UserSettings):
        dir_path = os.path.dirname(self._filepath) or "."
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=dir_path, delete=False, encoding="utf-8"
            ) as tmp:
                json.dump(settings.to_dict(), tmp, indent=2, ensure_ascii=False)
                tmp_path = tmp.name
            shutil.move(tmp_path, self._filepath)
        except (IOError, OSError) as e:
            _logger.warning("Failed to write settings to disk: %s", e)
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    def shutdown(self):
        self._running = False
        if self._flush_thread and self._flush_thread.is_alive():
            self._flush_thread.join(timeout=3.0)
        self._flush_if_dirty()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._settings.get(key, default)

    def set(self, key: str, value: Any):
        with self._lock:
            self._settings.set(key, value)
            self._dirty = True
        if self._event_bus:
            self._event_bus.publish(SettingsChangedEvent(key=key, value=value))

    def update(self, settings_dict: Dict[str, Any]):
        with self._lock:
            for key, value in settings_dict.items():
                self._settings.set(key, value)
            self._dirty = True
        if self._event_bus:
            for key, value in settings_dict.items():
                self._event_bus.publish(SettingsChangedEvent(key=key, value=value))

    def get_all(self) -> Dict[str, Any]:
        with self._lock:
            return self._settings.to_dict()

    def get_model(self) -> UserSettings:
        with self._lock:
            return UserSettings(
                **{k: getattr(self._settings, k) for k in UserSettings.__dataclass_fields__}
            )

    def reset(self):
        with self._lock:
            self._settings = UserSettings()
            self._dirty = True
        if self._event_bus:
            self._event_bus.publish(SettingsChangedEvent(key="__reset__", value=None))

    def export(self) -> Dict[str, Any]:
        with self._lock:
            return self._settings.to_dict()

    def import_data(self, data: Dict[str, Any]):
        with self._lock:
            self._settings = UserSettings.from_dict(data)
            self._dirty = True

    def reload(self, data_dir: str, filename: str = "settings.json"):
        self._running = False
        if self._flush_thread and self._flush_thread.is_alive():
            self._flush_thread.join(timeout=3.0)
        self._flush_if_dirty()
        self._filepath = os.path.join(data_dir, filename)
        self._ensure_directory()
        self._load()
        self._start_flush_thread()
