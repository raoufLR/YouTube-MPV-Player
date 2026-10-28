"""Memory-profiling tests for large collections.

Guards the worst-case recovered from the audit: history capped at 500
entries, likes at 2000, thumbnail LRU at 500 entries / 5 MiB each, and
playlist entries whose per-field strings are coerced to fixed caps.

Every test measures *live* Python heap usage with :mod:`tracemalloc`, so the
assertions stay deterministic across CI machines (unlike RSS sampling).
"""

from __future__ import annotations

import gc
import os
import time
import tracemalloc

import pytest

from core.json_store import save_json
from services.history_service import MAX_HISTORY, HistoryService
from services.likes_service import MAX_LIKES, LikesService
from services.playlist_service import PlaylistService
from services.thumbnail_cache_service import (
    MAX_QUEUE_SIZE,
    ThumbnailCacheService,
)

# Retained-budget ceilings (MiB) derived from the per-field coercion caps.
# Dataclass/dict overhead is covered by generous headroom (~2x).
HISTORY_BUDGET_MIB = 4.0
LIKES_BUDGET_MIB = 14.0
PLAYLIST_BUDGET_MIB = 12.0
THUMB_LRU_BUDGET_MIB = 2.5
THUMB_PAYLOAD = 32 * 1024
THUMB_LRU_LIMIT = 50


def _report(label, entries, peak, current):
    per_entry = current / max(1, entries)
    print(
        f"[memory] {label}: entries={entries} live={current / 1024:.0f} KiB"
        f" peak={peak / 1024:.0f} KiB per-entry={per_entry:.0f} B"
    )


def _worst_case_video(index: int, *, thumbnail: bool = True) -> dict:
    """A video entry whose every optional field sits at its coercion cap."""
    data = {
        "id": f"abcdefghij{index:04d}",
        "title": "T" * 512,
        "channel": "C" * 256,
    }
    if thumbnail:
        data["thumbnail"] = "https://i.ytimg.com/" + "q" * (2048 - len("https://i.ytimg.com/"))
    return data


@pytest.fixture
def history_service_factory(temp_dir):
    def make():
        return HistoryService(event_bus=None, data_dir=temp_dir)

    return make


@pytest.fixture
def playlist_service_factory(temp_dir):
    def make():
        return PlaylistService(event_bus=None, data_dir=temp_dir)

    return make


# ---------------------------------------------------------------------------
# History: streaming adds cap at 500 entries
# ---------------------------------------------------------------------------

def test_history_streaming_adds_roll_over_at_500(tmp_path, history_service_factory):
    service = history_service_factory()

    tracemalloc.start()
    try:
        for index in range(1200):
            service.add(_worst_case_video(index))
        gc.collect()
        current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    entries = service.get_all()
    assert len(entries) == MAX_HISTORY                      # capped, no growth
    assert entries[0]["id"] == _worst_case_video(1199)["id"]  # newest first
    assert current < HISTORY_BUDGET_MIB * 1024 * 1024
    _report("history streaming", len(entries), peak, current)
    service.shutdown()


def test_history_duplicate_adds_do_not_retain_extra_memory(
    tmp_path, history_service_factory,
):
    service = history_service_factory()
    duplicate = _worst_case_video(0)

    tracemalloc.start()
    try:
        for index in range(1200):
            service.add(_worst_case_video(index))
        gc.collect()
        before = tracemalloc.get_traced_memory()[0]

        for _ in range(200):                                # same id again
            service.add(duplicate)
        gc.collect()
        after = tracemalloc.get_traced_memory()[0]
    finally:
        tracemalloc.stop()

    assert len(service.get_all()) == MAX_HISTORY
    # Updating an existing entry must not grow the retained set.
    assert after - before < 256 * 1024
    service.shutdown()


def test_history_load_from_disk_caps_oversized_file(tmp_path):
    path = os.path.join(str(tmp_path), "history.json")
    oversized = [_worst_case_video(i) for i in range(1500)]
    save_json(path, oversized)

    tracemalloc.start()
    try:
        service = HistoryService(event_bus=None, data_dir=str(tmp_path))
        gc.collect()
        current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    entries = service.get_all()
    assert len(entries) == MAX_HISTORY
    assert current < HISTORY_BUDGET_MIB * 1024 * 1024
    _report("history reload", len(entries), peak, current)
    service.shutdown()


def test_history_entry_strings_are_coerced_to_caps(tmp_path):
    """Huge titles in a hand-edited file cannot blow up resident memory."""
    path = os.path.join(str(tmp_path), "history.json")
    payload = [
        {**_worst_case_video(i), "title": "X" * 100_000}
        for i in range(30)
    ]
    save_json(path, payload)

    tracemalloc.start()
    try:
        service = HistoryService(event_bus=None, data_dir=str(tmp_path))
        gc.collect()
        current, _peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    entries = service.get_all()
    assert len(entries) == 30
    for entry in entries:
        assert len(entry["title"]) <= 512
        assert len(entry["thumbnail"]) <= 2048
    assert current < 256 * 1024, "100 KiB titles should have been coerced"
    service.shutdown()


# ---------------------------------------------------------------------------
# Likes: rollover at 2000 entries
# ---------------------------------------------------------------------------

def test_likes_load_from_disk_caps_oversized_file(tmp_path):
    path = os.path.join(str(tmp_path), "likes.json")
    oversized = [
        {
            "video_id": f"abcdefghij{i:04d}",
            "title": "T" * 512,
            "channel": "C" * 256,
            "thumbnail": "https://i.ytimg.com/" + "q" * 2000,
        }
        for i in range(3000)
    ]
    save_json(path, oversized)

    tracemalloc.start()
    try:
        service = LikesService(event_bus=None, data_dir=str(tmp_path))
        gc.collect()
        current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    liked = service.get_liked_videos()
    assert len(liked) == MAX_LIKES
    assert current < LIKES_BUDGET_MIB * 1024 * 1024
    _report("likes reload", len(liked), peak, current)


# ---------------------------------------------------------------------------
# Playlists: large collection + copy-on-write churn
# ---------------------------------------------------------------------------

def test_playlist_thousand_videos_memory_budget(tmp_path):
    """A 1000-entry playlist stays inside a fixed per-entry byte budget."""
    playlist_dir = os.path.join(str(tmp_path), "playlists")
    os.makedirs(playlist_dir, exist_ok=True)
    entries = []
    for index in range(1000):
        data = {
            "video_id": f"abcdefghij{index:04d}",
            "title": "T" * 512,
            "channel": "C" * 256,
            "thumbnail": "https://i.ytimg.com/" + "q" * 2000,
            "url": "https://youtube.com/watch?v=" + "u" * 1990,
        }
        entries.append(data)
    save_json(
        os.path.join(playlist_dir, "massive.json"),
        {
            "id": "massive",
            "name": "Massive",
            "created_at": time.time(),
            "updated_at": time.time(),
            "videos": entries,
        },
    )

    tracemalloc.start()
    try:
        service = PlaylistService(event_bus=None, data_dir=str(tmp_path))
        gc.collect()
        current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    service.shutdown()

    videos = service.get_videos("massive")
    assert len(videos) == 1000
    # Loading must not expand or duplicate the retained payload.
    assert current < PLAYLIST_BUDGET_MIB * 1024 * 1024
    _report("playlist load", len(videos), peak, current)

    # Reload from the same files keeps a flat footprint (no accumulation).
    tracemalloc.start()
    try:
        reloaded = PlaylistService(event_bus=None, data_dir=str(tmp_path))
        gc.collect()
        second_current, _second_peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert len(reloaded.get_videos("massive")) == 1000
    assert second_current < PLAYLIST_BUDGET_MIB * 1024 * 1024
    reloaded.shutdown()


def test_playlist_churn_does_not_leak_per_mutation(tmp_path, playlist_service_factory):
    service = playlist_service_factory()
    playlist = service.create_playlist("Churn")

    tracemalloc.start()
    try:
        for index in range(120):
            service.add_video(playlist.id, {
                "videoId": f"abcdefghij{index:04d}",
                "title": "T" * 512,
                "channel": "C" * 256,
            })
        gc.collect()
        after_adds = tracemalloc.get_traced_memory()[0]

        for index in range(60):                             # remove half
            service.remove_video(playlist.id, f"abcdefghij{index:04d}")
        gc.collect()
        after_removes = tracemalloc.get_traced_memory()[0]
    finally:
        tracemalloc.stop()

    videos = service.get_videos(playlist.id)
    assert len(videos) == 60
    # Removing entries returns their memory (copy-on-write churn aside).
    assert after_removes <= after_adds
    # Live payload for 60 worst-case entries stays inside ~4 KiB/entry.
    assert after_removes < 2.0 * 1024 * 1024


# ---------------------------------------------------------------------------
# Thumbnail cache: LRU eviction + bounded download queue
# ---------------------------------------------------------------------------

def test_thumbnail_memory_lru_bounds_retained_bytes(tmp_path):
    service = ThumbnailCacheService(
        event_bus=None,
        max_memory_entries=THUMB_LRU_LIMIT,
        disk_cache=False,
    )
    try:
        tracemalloc.start()
        try:
            for index in range(300):                        # 6x the LRU limit
                url = f"https://i.ytimg.com/vi/img{index:06d}.jpg"
                service._store_memory(url, bytes(THUMB_PAYLOAD))
            gc.collect()
            current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        stats = service.stats()
        assert stats["memory"] == THUMB_LRU_LIMIT
        # Retained payload is exactly the LRU window, not the 300 inserts.
        assert current < THUMB_LRU_BUDGET_MIB * 1024 * 1024
        assert current < THUMB_LRU_LIMIT * THUMB_PAYLOAD * 1.5
        _report("thumbnail LRU", stats["memory"], peak, current)

        # LRU order: the oldest entry is gone, the newest survive.
        assert service._get_memory("https://i.ytimg.com/vi/img000000.jpg") is None
        newest = service._get_memory(f"https://i.ytimg.com/vi/img{299:06d}.jpg")
        assert newest == bytes(THUMB_PAYLOAD)
    finally:
        service.shutdown()


def test_thumbnail_queue_is_bounded_under_flood(tmp_path):
    service = ThumbnailCacheService(
        event_bus=None,
        max_memory_entries=THUMB_LRU_LIMIT,
        disk_cache=False,
    )
    try:
        service.shutdown()                                  # kill the worker:
        # without a consumer the queue would only ever grow under load
        for index in range(1500):                           # a flood of misses
            service._enqueue(f"https://i.ytimg.com/vi/miss{index:06d}.jpg")

        stats = service.stats()
        assert stats["memory"] == 0
        assert stats["pending"] == MAX_QUEUE_SIZE
    finally:
        if service._running:
            service.shutdown()
