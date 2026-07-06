"""
Thumbnail Cache Service
=======================

High-performance thumbnail loading with multi-tier caching.

Architecture:
    1. LRU memory cache  — instant access, bounded by max_memory_entries
    2. Disk cache        — persistent across sessions, optional
    3. Network fetch     — async worker thread, only on cache miss

Thread safety:
    All public methods are guarded by threading.RLock.
    Background worker thread handles network I/O without blocking the caller.

Design decisions:
    - Caller receives bytes immediately from memory/disk cache (synchronous path)
    - On cache miss, returns None and enqueues async download
    - When download completes, caches to memory + disk and notifies via EventBus

Storage layout (when disk_cache=True):
    Cache/
    └── thumbnails/
        ├── {md5(url)}.jpg
        └── ...
"""

import hashlib
import logging
import os
import shutil
import tempfile
import threading
import time
from collections import OrderedDict
from typing import Optional, Dict, Any

import requests

from core import EventBus
from core.events import ThumbnailLoadedEvent, ThumbnailFailedEvent

_logger = logging.getLogger(__name__)

DEFAULT_MEMORY_SIZE = 500
DEFAULT_DISK_DIR = os.path.join("Cache", "thumbnails")
DEFAULT_TTL = 86400 * 7  # 7 days
DEFAULT_MAX_DISK_SIZE = 100 * 1024 * 1024  # 100 MB
MAX_QUEUE_SIZE = 200
BATCH_SIZE = 10


class ThumbnailCacheService:
    """Thumbnail loader with LRU memory cache and optional disk cache"""

    def __init__(self, event_bus: Optional[EventBus] = None,
                 max_memory_entries: int = DEFAULT_MEMORY_SIZE,
                 max_disk_size: int = DEFAULT_MAX_DISK_SIZE,
                 disk_cache: bool = True,
                 disk_dir: str = DEFAULT_DISK_DIR,
                 ttl: int = DEFAULT_TTL):
        self._event_bus = event_bus
        self._max_memory = max_memory_entries
        self._max_disk_size = max_disk_size
        self._disk_cache = disk_cache
        self._disk_dir = disk_dir
        self._ttl = ttl

        self._lock = threading.RLock()
        self._memory: OrderedDict = OrderedDict()
        self._pending: set = set()

        self._queue: list = []
        self._queue_event = threading.Event()
        self._running = False
        self._worker: Optional[threading.Thread] = None

        self._http: Optional[requests.Session] = None

        if self._disk_cache:
            os.makedirs(self._disk_dir, exist_ok=True)
            self.cleanup_expired()
            self._enforce_disk_size_limit()

        self._start_worker()

    def _get_http(self) -> requests.Session:
        if self._http is None:
            self._http = requests.Session()
            self._http.headers.update({
                "User-Agent": "YouTubeMpvPlayer/1.0",
                "Accept": "image/webp,image/jpeg,*/*",
            })
        return self._http

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _start_worker(self):
        self._running = True
        self._worker = threading.Thread(
            target=self._worker_loop, daemon=True, name="thumb-cache-worker"
        )
        self._worker.start()

    def _worker_loop(self):
        while self._running:
            self._queue_event.wait()
            self._queue_event.clear()
            self._process_queue()

    def _process_queue(self):
        batch = []
        with self._lock:
            while self._queue and len(batch) < BATCH_SIZE:
                batch.append(self._queue.pop(0))
        if not batch:
            return

        for url, callback in batch:
            data = self._fetch_from_network(url)
            if data:
                self._store_memory(url, data)
                if self._disk_cache:
                    self._store_disk(url, data)
            if callback:
                callback(url, data)

        if self._queue:
            self._queue_event.set()

    def shutdown(self):
        """Stop the background worker thread."""
        self._running = False
        self._queue_event.set()
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=3.0)
        if self._http:
            self._http.close()
            self._http = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_thumbnail_data(self, url: str) -> Optional[bytes]:
        """
        Synchronous API — returns cached bytes immediately, or None on miss.

        On miss, enqueues async download. When complete, publishes
        ThumbnailLoadedEvent so UI can apply the icon.
        """
        if not url:
            return None

        # 1. Memory cache
        data = self._get_memory(url)
        if data is not None:
            return data

        # 2. Disk cache
        if self._disk_cache:
            data = self._get_disk(url)
            if data is not None:
                self._store_memory(url, data)
                return data

        # 3. Enqueue async download
        self._enqueue(url)
        return None

    def preload(self, url: str):
        """Preemptively enqueue a thumbnail for background download."""
        if not url:
            return
        if self._get_memory(url) is not None:
            return
        if self._disk_cache and self._get_disk(url) is not None:
            return
        self._enqueue(url)

    def clear_memory(self):
        """Evict all entries from the in-memory cache."""
        with self._lock:
            self._memory.clear()

    def reload(self, disk_dir: str = DEFAULT_DISK_DIR):
        self.clear_memory()
        with self._lock:
            self._pending.clear()
            self._queue.clear()
            self._disk_dir = disk_dir
        if self._disk_cache:
            os.makedirs(self._disk_dir, exist_ok=True)
            self.cleanup_expired()
            self._enforce_disk_size_limit()

    def clear_disk(self):
        """Remove all cached files from disk."""
        if not self._disk_cache or not os.path.exists(self._disk_dir):
            return
        for filename in os.listdir(self._disk_dir):
            filepath = os.path.join(self._disk_dir, filename)
            if os.path.isfile(filepath):
                os.remove(filepath)

    def cleanup_expired(self):
        """Remove disk cache entries older than TTL."""
        if not self._disk_cache or not os.path.exists(self._disk_dir):
            return
        now = time.time()
        for filename in os.listdir(self._disk_dir):
            filepath = os.path.join(self._disk_dir, filename)
            if os.path.isfile(filepath):
                if now - os.path.getmtime(filepath) > self._ttl:
                    os.remove(filepath)

    def _enforce_disk_size_limit(self):
        """Evict oldest disk cache files until total size is under max_disk_size."""
        if not self._disk_cache or not os.path.exists(self._disk_dir):
            return
        files = []
        total = 0
        for filename in os.listdir(self._disk_dir):
            filepath = os.path.join(self._disk_dir, filename)
            if os.path.isfile(filepath):
                try:
                    sz = os.path.getsize(filepath)
                    mtime = os.path.getmtime(filepath)
                    files.append((mtime, filepath, sz))
                    total += sz
                except OSError:
                    pass
        if total <= self._max_disk_size:
            return
        files.sort(key=lambda x: x[0])  # oldest first
        for _, filepath, sz in files:
            if total <= self._max_disk_size:
                break
            try:
                os.remove(filepath)
                total -= sz
            except OSError:
                pass

    def stats(self) -> Dict[str, int]:
        """Return cache statistics."""
        with self._lock:
            mem = len(self._memory)
        disk = 0
        if self._disk_cache and os.path.exists(self._disk_dir):
            disk = len([f for f in os.listdir(self._disk_dir)
                        if os.path.isfile(os.path.join(self._disk_dir, f))])
        with self._lock:
            pending = len(self._queue)
        return {"memory": mem, "disk": disk, "pending": pending}

    # ------------------------------------------------------------------
    # Memory cache (LRU)
    # ------------------------------------------------------------------

    def _get_memory(self, url: str) -> Optional[bytes]:
        with self._lock:
            if url in self._memory:
                self._memory.move_to_end(url)
                return self._memory[url]
        return None

    def _store_memory(self, url: str, data: bytes):
        with self._lock:
            if url in self._memory:
                self._memory.move_to_end(url)
            else:
                self._memory[url] = data
                while len(self._memory) > self._max_memory:
                    self._memory.popitem(last=False)

    # ------------------------------------------------------------------
    # Disk cache
    # ------------------------------------------------------------------

    def _disk_path(self, url: str) -> str:
        digest = hashlib.md5(url.encode("utf-8")).hexdigest()
        return os.path.join(self._disk_dir, f"{digest}.jpg")

    def _get_disk(self, url: str) -> Optional[bytes]:
        filepath = self._disk_path(url)
        if not os.path.exists(filepath):
            return None
        try:
            if time.time() - os.path.getmtime(filepath) > self._ttl:
                os.remove(filepath)
                return None
            with open(filepath, "rb") as f:
                return f.read()
        except IOError:
            return None

    def _store_disk(self, url: str, data: bytes):
        filepath = self._disk_path(url)
        dir_path = os.path.dirname(filepath)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=dir_path, delete=False
            ) as tmp:
                tmp.write(data)
                tmp_path = tmp.name
            shutil.move(tmp_path, filepath)
            self._enforce_disk_size_limit()
        except (IOError, OSError) as e:
            _logger.warning("Failed to store thumbnail on disk: %s", e)
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    # ------------------------------------------------------------------
    # Network
    # ------------------------------------------------------------------

    def _fetch_from_network(self, url: str) -> Optional[bytes]:
        try:
            http = self._get_http()
            resp = http.get(url, timeout=5)
            resp.raise_for_status()
            return resp.content
        except (requests.RequestException, IOError, OSError) as e:
            _logger.debug("Failed to fetch thumbnail from %s: %s", url, e)
            return None

    # ------------------------------------------------------------------
    # Queue
    # ------------------------------------------------------------------

    def _enqueue(self, url: str):
        with self._lock:
            if url in self._pending:
                return
            if len(self._queue) >= MAX_QUEUE_SIZE:
                _logger.debug("Queue full, skipping thumbnail: %s", url)
                return
            self._pending.add(url)
            self._queue.append((url, self._on_download_complete))
        self._queue_event.set()

    def _on_download_complete(self, url: str, data: Optional[bytes]):
        with self._lock:
            self._pending.discard(url)

        if data and self._event_bus:
            self._event_bus.publish(ThumbnailLoadedEvent(item=url, icon=data))
        elif not data and self._event_bus:
            self._event_bus.publish(ThumbnailFailedEvent(item=url, error="Download failed"))
