import copy
import logging
import os
import threading
from typing import TYPE_CHECKING, Any

from core.events import SettingsChangedEvent
from core.json_store import JsonStore
from models import UserSettings
from models.user_settings import SETTINGS_SCHEMA_VERSION

if TYPE_CHECKING:
    from core import EventBus

_logger = logging.getLogger(__name__)

FLUSH_INTERVAL = 1.0


class SettingsService:
    """Manages user settings persisted in ``settings.json``.

    Mutations update memory immediately and mark the state dirty.  A background
    thread flushes to disk periodically; shutdown and profile switches wake
    that thread instead of waiting for the sleep interval to expire.

    Writes are retried until they succeed: a failed flush keeps the dirty flag
    set (and the in-memory value authoritative) instead of silently pretending
    the data reached disk.
    """

    def __init__(self, event_bus: EventBus | None = None,
                 data_dir: str = "User", filename: str = "settings.json"):
        self._event_bus = event_bus
        self._filepath = os.path.join(data_dir, filename)
        self._store = JsonStore(self._filepath)
        self._lock = threading.RLock()
        self._settings: UserSettings = UserSettings()
        self._dirty = False
        self._revision = 0
        self._written_revision = 0
        self._running = False
        self._stop_event = threading.Event()
        self._flush_thread: threading.Thread | None = None

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
        if self._flush_thread is not None and self._flush_thread.is_alive():
            return
        self._running = True
        self._stop_event.clear()
        self._flush_thread = threading.Thread(
            target=self._flush_loop, daemon=True, name="settings-flush"
        )
        self._flush_thread.start()

    def _stop_flush_thread(self):
        self._running = False
        self._stop_event.set()
        thread = self._flush_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=3.0)
        self._flush_thread = None

    def _flush_loop(self):
        while self._running:
            if self._stop_event.wait(FLUSH_INTERVAL):
                break
            self._flush_if_dirty()

    def _mark_dirty(self):
        self._revision += 1
        self._dirty = True

    def _flush_if_dirty(self):
        with self._lock:
            if not self._dirty:
                return
            snapshot = copy.deepcopy(self._settings)
            revision = self._revision
        self._write(snapshot, revision=revision)

    def _load(self):
        existed = self._store.exists
        data = self._store.load(default_factory=dict)
        repaired = False

        if isinstance(data, dict):
            self._settings = UserSettings.from_dict(data)
            repaired = existed and (
                UserSettings.needs_repair(data)
                or data.get("__version__") != SETTINGS_SCHEMA_VERSION
            )
        else:
            self._settings = UserSettings()
            repaired = existed

        if repaired:
            _logger.warning(
                "Settings at %s contained invalid or incomplete values; "
                "canonical defaults have been applied",
                self._filepath,
            )

        self._revision = 0
        self._written_revision = 0
        self._dirty = (not existed) or repaired

    def _write(self, settings: UserSettings, revision: int | None = None) -> bool:
        """Persist *settings*.  On failure the dirty flag stays set."""
        try:
            data = settings.to_dict()
            data["__version__"] = SETTINGS_SCHEMA_VERSION
            self._store.save(data)
        except (OSError, TypeError, ValueError) as exc:
            _logger.warning("Failed to write settings to disk: %s", exc)
            with self._lock:
                self._dirty = True
            return False

        with self._lock:
            if revision is not None:
                self._written_revision = max(self._written_revision, revision)
            if self._revision <= self._written_revision:
                self._dirty = False
        return True

    def shutdown(self):
        """Stop the flush thread and persist any pending changes."""
        self._stop_flush_thread()
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
            normalized = self._settings.get(key)
            self._mark_dirty()
        if self._event_bus:
            self._event_bus.publish(SettingsChangedEvent(key=key, value=normalized))

    def update(self, settings_dict: dict[str, Any]) -> bool:
        if not isinstance(settings_dict, dict):
            _logger.warning("Ignoring settings update with non-mapping payload")
            return False
        normalized_values = {}
        with self._lock:
            for key, value in settings_dict.items():
                if not isinstance(key, str):
                    _logger.warning("Ignoring non-string settings key: %r", key)
                    continue
                self._settings.set(key, value)
                normalized_values[key] = self._settings.get(key)
            self._mark_dirty()
        if self._event_bus:
            for key, value in normalized_values.items():
                self._event_bus.publish(SettingsChangedEvent(key=key, value=value))
        return True

    def get_all(self) -> dict[str, Any]:
        with self._lock:
            return self._settings.to_dict()

    def get_model(self) -> UserSettings:
        with self._lock:
            return copy.deepcopy(self._settings)

    def reset(self):
        with self._lock:
            self._settings = UserSettings()
            self._mark_dirty()
        if self._event_bus:
            self._event_bus.publish(SettingsChangedEvent(key="__reset__", value=None))

    def export(self) -> dict[str, Any]:
        with self._lock:
            data = self._settings.to_dict()
        data["__version__"] = SETTINGS_SCHEMA_VERSION
        return data

    def import_data(self, data: dict[str, Any]) -> bool:
        if not isinstance(data, dict):
            _logger.warning("Ignoring settings import with non-mapping payload")
            return False
        with self._lock:
            self._settings = UserSettings.from_dict(data)
            self._mark_dirty()
        if self._event_bus:
            self._event_bus.publish(SettingsChangedEvent(key="__reset__", value=None))
        return True

    def reload(self, data_dir: str, filename: str = "settings.json"):
        self._stop_flush_thread()
        self._flush_if_dirty()
        with self._lock:
            self._filepath = os.path.join(data_dir, filename)
            self._store = JsonStore(self._filepath)
        self._ensure_directory()
        self._load()
        self._start_flush_thread()
