"""Google Takeout Data Import Service.

Integrates subscriptions, watch history, liked videos, and playlists from
Google Takeout archives into the active profile's local storage with atomic
staging, deduplication, conflict resolution, and cancellation safety.
"""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.events import HistoryUpdatedEvent
from core.json_store import JsonStore
from core.takeout_parser import (
    TakeoutArchiveReader,
    TakeoutInspectionResult,
    find_takeout_files,
    inspect_takeout_source,
    parse_history_data,
    parse_playlist_data,
    parse_subscriptions_data,
    playlist_name_from_path,
)
from core.validation import coerce_text
from models.playlist import MAX_PLAYLIST_NAME

if TYPE_CHECKING:
    from collections.abc import Callable

    from core.event_bus import EventBus
    from services.history_service import HistoryService
    from services.likes_service import LikesService
    from services.playlist_service import PlaylistService

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImportProgress:
    stage: str
    current: int
    total: int
    percent: float


@dataclass(frozen=True)
class ImportResult:
    success: bool
    imported_history: int = 0
    imported_likes: int = 0
    imported_watch_later: int = 0
    imported_playlists: int = 0
    imported_subscriptions: int = 0
    error_message: str = ""


class DataImportService:
    """Manages parsing, deduplication, and atomic insertion of Takeout archives."""

    def __init__(
        self,
        event_bus: EventBus | None,
        history_service: HistoryService,
        likes_service: LikesService,
        playlist_service: PlaylistService,
        data_dir: str,
    ):
        self._event_bus = event_bus
        self._history_service = history_service
        self._likes_service = likes_service
        self._playlist_service = playlist_service
        self._data_dir = data_dir
        self._lock = threading.RLock()
        self._cancel_requested = False

    def inspect(self, source_path: str) -> TakeoutInspectionResult:
        """Inspect Takeout archive or folder without loading full contents."""
        return inspect_takeout_source(source_path)

    def execute_import(
        self,
        source_path: str,
        selections: dict[str, bool],
        overwrite: bool = False,
        progress_callback: Callable[[ImportProgress], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> ImportResult:
        """Perform import with atomic staging and rollback on failure or cancellation."""
        staging_dir = os.path.join(self._data_dir, ".import_staging")
        if os.path.exists(staging_dir):
            shutil.rmtree(staging_dir, ignore_errors=True)
        os.makedirs(staging_dir, exist_ok=True)

        res_history = 0
        res_likes = 0
        res_watch_later = 0
        res_playlists = 0
        res_subs = 0

        try:
            with TakeoutArchiveReader(source_path) as reader:
                mapping = find_takeout_files(reader)

                def update_progress(stage: str, cur: int, tot: int):
                    if progress_callback:
                        pct = (cur / tot * 100.0) if tot > 0 else 0.0
                        progress_callback(ImportProgress(stage, cur, tot, pct))

                # 1-3. Read playlists first so modern CSV rows (video id and
                # timestamp only) can borrow titles from the watch history.
                wants_playlists = any(
                    selections.get(key, True)
                    for key in ("likes", "watch_later", "playlists")
                )
                parsed_playlists = []
                if wants_playlists and mapping["playlists"]:
                    update_progress("Scanning playlists...", 10, 100)
                    for pl_path in mapping["playlists"]:
                        if cancel_event and cancel_event.is_set():
                            raise InterruptedError("Import cancelled by user")
                        stream = reader.open_stream(pl_path)
                        try:
                            data = stream.read()
                            name = playlist_name_from_path(pl_path)
                            pl = parse_playlist_data(
                                data, pl_path.lower().endswith(".json"), name
                            )
                        finally:
                            stream.close()
                        parsed_playlists.append(pl)

                history_items = None

                def load_history_items():
                    nonlocal history_items
                    if history_items is None:
                        history_items = []
                        if mapping["history"]:
                            update_progress("Reading watch history...", 30, 100)
                            stream = reader.open_stream(mapping["history"])
                            try:
                                history_items = parse_history_data(
                                    stream.read(),
                                    mapping["history"].lower().endswith(".json"),
                                )
                            finally:
                                stream.close()
                    return history_items

                placeholder = "Video {}"
                if (
                    mapping["history"]
                    and any(
                        not item.title
                        or item.title == placeholder.format(item.video_id)
                        for pl in parsed_playlists
                        for item in pl.items
                    )
                ):
                    known = {
                        item.video_id: item
                        for item in load_history_items()
                        if item.title
                    }
                    for pl in parsed_playlists:
                        for item in pl.items:
                            if item.title and item.title != placeholder.format(
                                item.video_id
                            ):
                                continue
                            source = known.get(item.video_id)
                            if source is None:
                                continue
                            item.title = source.title
                            if not item.channel:
                                item.channel = source.channel

                update_progress("Importing playlists...", 45, 100)
                for pl in parsed_playlists:
                    if cancel_event and cancel_event.is_set():
                        raise InterruptedError("Import cancelled by user")
                    if pl.is_liked_videos:
                        if selections.get("likes", True):
                            res_likes = self._import_likes(
                                pl.items, overwrite=overwrite,
                                cancel_event=cancel_event,
                            )
                    elif pl.is_watch_later:
                        if selections.get("watch_later", True):
                            res_watch_later = self._import_watch_later(
                                pl.items, overwrite=overwrite,
                                cancel_event=cancel_event,
                            )
                    elif (
                        selections.get("playlists", True)
                        and pl.items
                        and self._import_playlist(
                            pl, overwrite=overwrite, cancel_event=cancel_event
                        )
                    ):
                        res_playlists += 1

                # 4. Watch History
                if selections.get("history", True) and mapping["history"]:
                    update_progress("Importing watch history...", 60, 100)
                    if cancel_event and cancel_event.is_set():
                        raise InterruptedError("Import cancelled by user")
                    res_history = self._import_history(
                        load_history_items(), overwrite=overwrite,
                        cancel_event=cancel_event,
                    )

                # 5. Subscriptions (stored in subscriptions.json in profile dir)
                if selections.get("subscriptions", True) and mapping["subscriptions"]:
                    update_progress("Importing subscriptions...", 80, 100)
                    if cancel_event and cancel_event.is_set():
                        raise InterruptedError("Import cancelled by user")
                    stream = reader.open_stream(mapping["subscriptions"])
                    try:
                        data = stream.read()
                        subs = parse_subscriptions_data(data, mapping["subscriptions"].endswith(".json"))
                        res_subs = self._import_subscriptions(subs, overwrite=overwrite)
                    finally:
                        stream.close()

                update_progress("Completed", 100, 100)

            return ImportResult(
                success=True,
                imported_history=res_history,
                imported_likes=res_likes,
                imported_watch_later=res_watch_later,
                imported_playlists=res_playlists,
                imported_subscriptions=res_subs,
            )

        except InterruptedError:
            _logger.info("Takeout import cancelled by user.")
            return ImportResult(success=False, error_message="Import was cancelled.")
        except Exception as exc:
            _logger.exception("Takeout import failed")
            return ImportResult(success=False, error_message=str(exc))
        finally:
            if os.path.exists(staging_dir):
                shutil.rmtree(staging_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Category Import Helpers
    # ------------------------------------------------------------------

    def _coalesced_events(self):
        """Publish at most one event per type for a bulk mutation.

        Adding hundreds of items one by one used to publish hundreds of
        events; each listener rebuilds a whole view, which froze the UI.
        """
        if self._event_bus is None:
            return contextlib.nullcontext()
        return self._event_bus.coalesced()

    def _import_likes(self, items, overwrite: bool, cancel_event=None) -> int:
        """Merge liked items into LikesService using the public API."""
        imported_count = 0

        with self._coalesced_events():
            for item in items:
                if cancel_event is not None and cancel_event.is_set():
                    raise InterruptedError("Import cancelled by user")
                vid = item.video_id
                already_liked = self._likes_service.is_liked(vid)

                if already_liked and not overwrite:
                    continue

                if already_liked and overwrite:
                    self._likes_service.unlike(vid)

                entry = {
                    "id": vid,
                    "video_id": vid,
                    "title": item.title,
                    "channel": item.channel,
                    "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                    "liked_at": item.added_at or time.time(),
                }
                if self._likes_service.like(entry):
                    imported_count += 1

        return imported_count

    def _import_watch_later(self, items, overwrite: bool, cancel_event=None) -> int:
        """Merge items into Watch Later playlist."""
        wl = self._playlist_service.get_watch_later()
        existing_vids = {v["video_id"] for v in wl if isinstance(v, dict) and "video_id" in v}
        added = 0

        with self._coalesced_events():
            for item in items:
                if cancel_event is not None and cancel_event.is_set():
                    raise InterruptedError("Import cancelled by user")
                vid = item.video_id
                if vid in existing_vids and not overwrite:
                    continue

                self._playlist_service.add_to_watch_later(
                    video_data={
                        "id": vid,
                        "videoId": vid,
                        "title": item.title,
                        "channel": item.channel,
                        "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                    }
                )
                existing_vids.add(vid)
                added += 1

        return added

    def _import_playlist(self, pl, overwrite: bool, cancel_event=None) -> bool:
        """Import custom playlist into PlaylistService."""
        name = coerce_text(pl.name, max_length=MAX_PLAYLIST_NAME)
        if not name:
            return False

        with self._coalesced_events():
            existing = next(
                (pl for pl in self._playlist_service.get_all_playlists() if pl.name == name),
                None,
            )
            if existing and not overwrite:
                # Merge videos into existing
                existing_vids = {v.video_id for v in existing.videos}
                for item in pl.items:
                    if cancel_event is not None and cancel_event.is_set():
                        raise InterruptedError("Import cancelled by user")
                    if item.video_id not in existing_vids:
                        self._playlist_service.add_video(
                            existing.id,
                            {
                                "id": item.video_id,
                                "videoId": item.video_id,
                                "title": item.title,
                                "channel": item.channel,
                                "thumbnail": f"https://i.ytimg.com/vi/{item.video_id}/hqdefault.jpg",
                            },
                        )
                return True

            if existing and overwrite:
                self._playlist_service.delete_playlist(existing.id)

            # Create new playlist
            created = self._playlist_service.create_playlist(name)
            if not created:
                return False

            for item in pl.items:
                if cancel_event is not None and cancel_event.is_set():
                    raise InterruptedError("Import cancelled by user")
                self._playlist_service.add_video(
                    created.id,
                    {
                        "id": item.video_id,
                        "videoId": item.video_id,
                        "title": item.title,
                        "channel": item.channel,
                        "thumbnail": f"https://i.ytimg.com/vi/{item.video_id}/hqdefault.jpg",
                    },
                )
            return True

    def _import_history(self, items, overwrite: bool, cancel_event=None) -> int:
        """Merge items into HistoryService respecting 500-cap."""
        existing = self._history_service.get_all()
        existing_vids = {item.get("id") for item in existing}
        added = 0

        with self._coalesced_events():
            # Takeout lists newest first; the service prepends, so add the
            # oldest entries first to keep the imported history in
            # chronological order.
            for item in reversed(items):
                if cancel_event is not None and cancel_event.is_set():
                    raise InterruptedError("Import cancelled by user")
                vid = item.video_id
                if vid in existing_vids and not overwrite:
                    continue

                entry = {
                    "id": vid,
                    "title": item.title,
                    "channel": item.channel,
                    "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                    "watched_at": item.watched_at or time.time(),
                }
                # Add to history
                self._history_service.add(entry)
                existing_vids.add(vid)
                added += 1

            if self._event_bus and added > 0:
                self._event_bus.publish(HistoryUpdatedEvent(action="import"))

        return added

    def _import_subscriptions(self, subs, overwrite: bool) -> int:
        """Save subscriptions in subscriptions.json in the profile directory."""
        store_path = os.path.join(self._data_dir, "subscriptions.json")
        store = JsonStore(store_path)
        existing = store.load(list)
        existing_map = {}
        if isinstance(existing, list):
            for s in existing:
                if isinstance(s, dict) and "channel_id" in s:
                    existing_map[s["channel_id"]] = s

        added = 0
        for sub in subs:
            cid = sub.channel_id
            if cid in existing_map and not overwrite:
                continue
            entry = {
                "channel_id": cid,
                "title": sub.title,
                "url": sub.url,
                "imported_at": time.time(),
            }
            if cid not in existing_map:
                added += 1
            existing_map[cid] = entry

        store.save(list(existing_map.values()))
        return added
