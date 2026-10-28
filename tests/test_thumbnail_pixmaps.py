"""Decoded-thumbnail pixmap cache."""

import time

import pytest
from PyQt6.QtCore import QBuffer, QCoreApplication
from PyQt6.QtGui import QColor, QPixmap, QPixmapCache
from PyQt6.QtTest import QSignalSpy, QTest

from ui.thumbnail_pixmaps import (
    ThumbnailPixmapLoader,
    cached_pixmap,
    load_pixmap,
)

pytestmark = pytest.mark.qt


@pytest.fixture(autouse=True)
def empty_pixmap_cache(qapp):
    QPixmapCache.clear()
    yield
    QPixmapCache.clear()


def _wait_for_signal(spy: QSignalSpy, timeout_ms: int = 2000) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000
    while len(spy) == 0 and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        QTest.qWait(10)
    return len(spy) > 0


def _png_bytes(width: int = 32, height: int = 18, color: str = "#336699") -> bytes:
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(color))
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    assert pixmap.save(buffer, "PNG")
    return bytes(buffer.data())


def test_decodes_and_scales_to_the_requested_size():
    url = "https://i.ytimg.com/vi/cache-test/hqdefault.jpg"
    pixmap = load_pixmap(url, _png_bytes(), 260, 146)
    assert pixmap is not None
    assert (pixmap.width(), pixmap.height()) == (260, 146)


def test_second_request_returns_the_cached_pixmap():
    url = "https://i.ytimg.com/vi/cache-test/hqdefault.jpg"
    first = load_pixmap(url, _png_bytes(), 260, 146)
    # Different bytes prove the cache was consulted instead of a re-decode.
    second = load_pixmap(url, _png_bytes(color="#AA0000"), 260, 146)
    assert first.cacheKey() == second.cacheKey()


def test_size_is_part_of_the_cache_key():
    url = "https://i.ytimg.com/vi/cache-test/hqdefault.jpg"
    large = load_pixmap(url, _png_bytes(), 260, 146)
    small = load_pixmap(url, _png_bytes(), 120, 68)
    assert large.cacheKey() != small.cacheKey()
    assert (small.width(), small.height()) == (120, 68)


def test_invalid_payloads_return_none():
    assert load_pixmap("", _png_bytes(), 260, 146) is None
    assert load_pixmap("https://i.ytimg.com/vi/x/hq.jpg", b"", 260, 146) is None
    assert load_pixmap("https://i.ytimg.com/vi/x/hq.jpg", b"not-an-image", 260, 146) is None


def test_loader_decodes_off_thread_and_publishes_signal(qapp):
    url = "https://i.ytimg.com/vi/async/hq.jpg"
    loader = ThumbnailPixmapLoader(max_threads=1)
    try:
        spy = QSignalSpy(loader.pixmap_ready)
        assert loader.request(url, _png_bytes(), 260, 146) is None
        assert loader.is_pending(url, 260, 146)

        assert _wait_for_signal(spy)
        assert spy[0][0] == url
        assert (spy[0][1], spy[0][2]) == (260, 146)
        assert not loader.is_pending(url, 260, 146)

        cached = cached_pixmap(url, 260, 146)
        assert cached is not None
        assert (cached.width(), cached.height()) == (260, 146)
    finally:
        loader.shutdown()


def test_loader_deduplicates_pending_requests(qapp):
    url = "https://i.ytimg.com/vi/dedupe/hq.jpg"
    loader = ThumbnailPixmapLoader(max_threads=1)
    try:
        spy = QSignalSpy(loader.pixmap_ready)
        assert loader.request(url, _png_bytes(), 120, 68) is None
        assert loader.request(url, _png_bytes(), 120, 68) is None

        assert _wait_for_signal(spy)
        QTest.qWait(100)
        assert len(spy) == 1
    finally:
        loader.shutdown()


def test_loader_ignores_invalid_image_data(qapp):
    url = "https://i.ytimg.com/vi/broken/hq.jpg"
    loader = ThumbnailPixmapLoader(max_threads=1)
    try:
        loader.request(url, b"not-an-image", 260, 146)
        # Wait for the worker and deliver its queued signal before the loader
        # (and its thread pool) is torn down.
        assert loader._pool.waitForDone(2000)
        QCoreApplication.processEvents()

        assert not loader.is_pending(url, 260, 146)
        assert cached_pixmap(url, 260, 146) is None
    finally:
        loader.shutdown()


def test_loader_cache_hit_is_synchronous(qapp):
    url = "https://i.ytimg.com/vi/hit/hq.jpg"
    loader = ThumbnailPixmapLoader(max_threads=1)
    try:
        assert load_pixmap(url, _png_bytes(), 120, 68) is not None
        spy = QSignalSpy(loader.pixmap_ready)

        pixmap = loader.request(url, _png_bytes(color="#00AA00"), 120, 68)

        assert pixmap is not None
        assert len(spy) == 0
    finally:
        loader.shutdown()
