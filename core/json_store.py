"""Crash-safe JSON persistence helpers.

All services that persist user data use :class:`JsonStore` instead of ad-hoc
``NamedTemporaryFile`` + ``shutil.move`` code.  The store provides:

- Atomic replacement via ``os.replace`` on the same filesystem
- ``flush`` + ``fsync`` before the original file is replaced
- A last-known-good ``.bak`` copy
- Quarantine of unreadable/corrupt files instead of silently discarding them
- Per-path process-wide re-entrant locks, shared by every store instance
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
import tempfile
import threading
import time
from typing import TYPE_CHECKING, Any

from core.security import ensure_private_dir, ensure_private_file

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: str) -> threading.RLock:
    key = os.path.normcase(os.path.abspath(path))
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _LOCKS[key] = lock
        return lock


class JsonStore:
    """Read and write JSON with atomic replacement and corruption recovery."""

    def __init__(
        self,
        filepath: str,
        *,
        backup: bool = True,
        indent: int = 2,
        ensure_ascii: bool = False,
    ):
        if not filepath:
            raise ValueError("filepath must not be empty")
        self.filepath = os.fspath(filepath)
        self.backup_path = self.filepath + ".bak"
        self.backup = backup
        self.indent = indent
        self.ensure_ascii = ensure_ascii
        self._lock = _lock_for(self.filepath)

    @property
    def exists(self) -> bool:
        return os.path.exists(self.filepath)

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def load(self, default_factory: Callable[[], Any] = list) -> Any:
        """Load JSON, falling back to the backup, then to a default value.

        A corrupt primary file is moved aside as
        ``<name>.corrupt-<timestamp>-<pid>``.  This method never raises for
        malformed data; I/O errors are logged and the default is returned.
        """
        with self._lock:
            if os.path.exists(self.filepath):
                try:
                    return self._read_json(self.filepath)
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    self._quarantine(self.filepath, exc)
                except OSError as exc:
                    _logger.warning(
                        "Unable to read %s: %s", self.filepath, exc
                    )

            if self.backup and os.path.exists(self.backup_path):
                try:
                    data = self._read_json(self.backup_path)
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    self._quarantine(self.backup_path, exc)
                except OSError as exc:
                    _logger.warning(
                        "Unable to read backup %s: %s", self.backup_path, exc
                    )
                else:
                    _logger.warning(
                        "Recovered %s from backup %s",
                        self.filepath,
                        self.backup_path,
                    )
                    try:
                        self._write_primary(data, make_backup=False)
                    except OSError as exc:
                        _logger.warning(
                            "Recovered data could not be written back to %s: %s",
                            self.filepath,
                            exc,
                        )
                    return data

            return default_factory()

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def save(self, data: Any):
        """Atomically persist *data*.

        Serialization happens before any file is touched, so a non-serializable
        object leaves the existing file intact.
        """
        with self._lock:
            self._write_primary(data, make_backup=self.backup)

    def delete(self):
        """Delete the primary and backup files."""
        with self._lock:
            for path in (self.filepath, self.backup_path):
                with contextlib.suppress(FileNotFoundError):
                    os.remove(path)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _write_primary(self, data: Any, *, make_backup: bool):
        parent = os.path.dirname(os.path.abspath(self.filepath))
        os.makedirs(parent, exist_ok=True)
        ensure_private_dir(parent)

        # Validate/serialize before creating a temporary file.
        payload = json.dumps(
            data,
            indent=self.indent,
            ensure_ascii=self.ensure_ascii,
        )

        if make_backup and os.path.exists(self.filepath):
            self._copy_last_good_to_backup()

        fd, tmp_path = tempfile.mkstemp(
            prefix=f".{os.path.basename(self.filepath)}.",
            suffix=".tmp",
            dir=parent,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, self.filepath)
            tmp_path = ""
            ensure_private_file(self.filepath)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                with contextlib.suppress(OSError):
                    os.remove(tmp_path)

        self._fsync_directory(parent)

    def _copy_last_good_to_backup(self):
        """Copy the current file to ``.bak`` only if it is valid JSON."""
        try:
            self._read_json(self.filepath)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            return
        try:
            shutil.copy2(self.filepath, self.backup_path)
            ensure_private_file(self.backup_path)
        except OSError as exc:  # pragma: no cover - rare filesystem failure
            _logger.warning(
                "Unable to update backup %s: %s", self.backup_path, exc
            )

    @staticmethod
    def _read_json(path: str) -> Any:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    def _quarantine(self, path: str, error: Exception):
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = f"{path}.corrupt-{stamp}-{os.getpid()}"
        counter = 1
        while os.path.exists(target):
            target = f"{path}.corrupt-{stamp}-{os.getpid()}-{counter}"
            counter += 1
        try:
            os.replace(path, target)
            _logger.warning(
                "Quarantined corrupt JSON file %s as %s (%s)",
                path,
                target,
                error,
            )
        except OSError as exc:  # pragma: no cover - rare filesystem failure
            _logger.error("Unable to quarantine %s: %s", path, exc)

    @staticmethod
    def _fsync_directory(path: str):
        if os.name == "nt":
            return
        try:  # pragma: no cover - exercised on POSIX CI
            fd = os.open(path, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            pass


def load_json(path: str, default_factory: Callable[[], Any] = list) -> Any:
    """Convenience wrapper used by read-only callers."""
    return JsonStore(path).load(default_factory)


def save_json(path: str, data: Any, *, backup: bool = True):
    """Convenience wrapper used by one-off writers."""
    JsonStore(path, backup=backup).save(data)
