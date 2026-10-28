"""Single-instance guard backed by a lock file in the data directory.

Two copies of the app must never write the same profile directory at once:
history, settings and playlist stores are plain JSON files with atomic
replacement, not a multi-process database.  ``QLockFile`` records the owning
PID, so a lock left behind by a crashed process is reclaimed instead of
blocking every later launch.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QLockFile

LOCK_FILENAME = "app.lock"


class SingleInstanceGuard:
    """Hold an exclusive lock for the lifetime of one application process."""

    def __init__(self, path: str, stale_ms: int = 30_000):
        self._path = path
        self._lock = QLockFile(path)
        self._lock.setStaleLockTime(stale_ms)

    @property
    def path(self) -> str:
        return self._path

    def acquire(self, timeout_ms: int = 0) -> bool:
        """Try to take the lock; ``False`` means another copy holds it."""
        parent = os.path.dirname(os.path.abspath(self._path))
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError:
            # Without a writable data directory there is nothing to protect;
            # startup reports the real problem instead of a bogus lock error.
            return True

        if self._lock.tryLock(timeout_ms):
            return True
        # A PermissionError means the lock file cannot be created at all;
        # startup reports the real problem instead of a bogus lock conflict.
        return self._lock.error() == QLockFile.LockError.PermissionError

    def release(self) -> None:
        self._lock.unlock()
