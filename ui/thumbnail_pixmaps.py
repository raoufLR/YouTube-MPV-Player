"""Shared cache and background decoder for display-sized thumbnail pixmaps.

The thumbnail service caches compressed image bytes, but every card still has
to decode those bytes into a ``QPixmap`` and smooth-scale it to the display
size.  Decoding a 480x360 JPEG costs roughly 1.5 ms; a home page holds up to
seventy cards, so doing that on the GUI thread produced a visible spike on
first load.  :func:`request_pixmap` decodes on a small thread pool instead and
publishes :attr:`ThumbnailPixmapLoader.pixmap_ready` once the result is cached.

``QPixmap`` may only be created on the GUI thread, so workers decode to
``QImage``; the loader converts and stores the pixmap in Qt's global
:class:`QPixmapCache` — a bounded LRU shared by every page, keyed by URL and
size because the same URL is shown at different dimensions (cards, list rows,
the mini player).
"""

from __future__ import annotations

import contextlib

from PyQt6.QtCore import QObject, QRunnable, Qt, QThreadPool, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QPixmapCache

_KEY_PREFIX = "thumbnail:"
_MAX_DECODE_THREADS = 3
# 70 card-sized (260x146) frames need ~11 MB; the default 10 MB budget would
# evict frames that are still on screen and force them to be decoded twice.
_CACHE_LIMIT_KB = 32 * 1024


def _key(url: str, width: int, height: int) -> str:
    return f"{_KEY_PREFIX}{width}x{height}:{url}"


def _decode(data: bytes, width: int, height: int) -> QImage:
    image = QImage.fromData(data)
    if image.isNull() or (width, height) == (image.width(), image.height()):
        return image
    return image.scaled(
        width,
        height,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )


def cached_pixmap(url: str, width: int, height: int) -> QPixmap | None:
    """Return an already-decoded pixmap, or ``None`` when it is not cached."""
    if not url:
        return None
    pixmap = QPixmapCache.find(_key(url, width, height))
    if pixmap is None or pixmap.isNull():
        return None
    return pixmap


def load_pixmap(url: str, data: bytes, width: int, height: int) -> QPixmap | None:
    """Decode *data* synchronously, decoding at most once per URL and size.

    Prefer :func:`request_pixmap` from UI code; this variant exists for
    callers that need the image on the spot.
    """
    if not url or not data:
        return None
    cached = cached_pixmap(url, width, height)
    if cached is not None:
        return cached

    image = _decode(data, width, height)
    if image.isNull():
        return None
    pixmap = QPixmap.fromImage(image)
    QPixmapCache.insert(_key(url, width, height), pixmap)
    return pixmap


class _DecodeSignals(QObject):
    finished = pyqtSignal(str, int, int, QImage)


class _DecodeTask(QRunnable):
    def __init__(self, signals: _DecodeSignals, url: str, data: bytes,
                 width: int, height: int):
        super().__init__()
        self._signals = signals
        self._url = url
        self._data = data
        self._width = width
        self._height = height

    def run(self):
        image = _decode(self._data, self._width, self._height)
        # The loader may have been destroyed while this task was queued.
        with contextlib.suppress(RuntimeError):
            self._signals.finished.emit(
                self._url, self._width, self._height, image
            )


class ThumbnailPixmapLoader(QObject):
    """Decode thumbnails off the GUI thread and cache the resulting pixmaps."""

    pixmap_ready = pyqtSignal(str, int, int)

    def __init__(self, parent=None, max_threads: int = _MAX_DECODE_THREADS):
        super().__init__(parent)
        self._pending: set[str] = set()
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max_threads)
        self._signals = _DecodeSignals(self)
        self._signals.finished.connect(self._on_decoded)
        QPixmapCache.setCacheLimit(
            max(QPixmapCache.cacheLimit(), _CACHE_LIMIT_KB)
        )

    def request(self, url: str, data: bytes, width: int, height: int) -> QPixmap | None:
        """Return a cached pixmap, or queue a decode and return ``None``.

        Pending requests are deduplicated by URL and size, so several cards
        sharing an image only decode it once.
        """
        if not url or not data or width <= 0 or height <= 0:
            return None
        cached = cached_pixmap(url, width, height)
        if cached is not None:
            return cached

        key = _key(url, width, height)
        if key not in self._pending:
            self._pending.add(key)
            self._pool.start(
                _DecodeTask(self._signals, url, bytes(data), width, height)
            )
        return None

    def _on_decoded(self, url: str, width: int, height: int, image: QImage):
        self._pending.discard(_key(url, width, height))
        if image.isNull():
            return
        QPixmapCache.insert(_key(url, width, height), QPixmap.fromImage(image))
        self.pixmap_ready.emit(url, width, height)

    def is_pending(self, url: str, width: int, height: int) -> bool:
        return _key(url, width, height) in self._pending

    def shutdown(self):
        """Drop queued work and wait briefly for running decodes."""
        self._pool.clear()
        # Cleared tasks never emit ``finished``, so drop their pending keys now
        # rather than leaving them marked as in flight forever.
        self._pending.clear()
        self._pool.waitForDone(1000)


_loader: ThumbnailPixmapLoader | None = None


def pixmap_loader() -> ThumbnailPixmapLoader:
    """Return the process-wide loader, creating it on first use."""
    global _loader
    if _loader is None:
        _loader = ThumbnailPixmapLoader()
    return _loader


def request_pixmap(url: str, data: bytes, width: int, height: int) -> QPixmap | None:
    """Cached pixmap if available, otherwise start a background decode."""
    return pixmap_loader().request(url, data, width, height)
