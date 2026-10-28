"""Google Takeout YouTube archive parser with security hardening.

Extracts subscriptions, watch history, liked videos, and playlists from
either a Takeout `.zip` archive or an extracted directory without loading
massive files entirely into memory.
"""

from __future__ import annotations

import csv
import html
import io
import json
import os
import re
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import IO, Any

from core.quality import validate_video_id
from core.security import is_safe_local_path
from core.validation import (
    coerce_id,
    coerce_text,
    coerce_timestamp,
)

MAX_MEMBER_UNCOMPRESSED_BYTES = 50 * 1024 * 1024  # 50 MiB per single file
MAX_TOTAL_UNCOMPRESSED_BYTES = 500 * 1024 * 1024  # 500 MiB cumulative limit
MAX_RATIO = 100  # Zip bomb ratio limit

_VIDEO_ID_REGEX = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})"
)

# Takeout translates folder and file names into the account language (e.g.
# "قوائم تشغيل" instead of "playlists"), so discovery must rely on file
# contents and CSV headers rather than English directory names.
_CSV_SNIFF_BYTES = 64 * 1024
_HTML_SNIFF_BYTES = 1024 * 1024

_ARABIC_MARKS_REGEX = re.compile(
    r"[\u0610-\u061A\u061C\u064B-\u065F\u0670\u06D6-\u06ED\u200E\u200F]"
)

_HTML_WATCH_ANCHOR_REGEX = re.compile(
    r'href="https://www\.youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})"[^>]*>'
    r"(.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
_HTML_CHANNEL_ANCHOR_REGEX = re.compile(
    r'href="https://www\.youtube\.com/(?:channel|c|user)/[^"]*"[^>]*>([^<]*)</a>',
    re.IGNORECASE,
)
_HTML_DATE_LINE_REGEX = re.compile(r"<br>\s*([^<]*\d{4}[^<]*?)\s*<br>")

_MONTH_NAMES = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_SUBSCRIPTION_DIR_HINTS = ("subscriptions", "الاشتراكات")
_PLAYLIST_DIR_HINTS = ("playlists", "قوائم تشغيل", "قوائم التشغيل")
_HISTORY_DIR_HINTS = ("history", "السجل")


def _normalize_text(value: object) -> str:
    """Casefold and strip diacritics so localized CSV headers can be matched."""
    text = str(value or "").replace("\ufeff", "").casefold()
    text = _ARABIC_MARKS_REGEX.sub("", text)
    return " ".join(text.split())


def _path_has_hint(lower_path: str, hints: tuple[str, ...]) -> bool:
    return any(hint in lower_path for hint in hints)


def _csv_headers(sample: bytes) -> list[str]:
    text = sample.decode("utf-8-sig", errors="replace")
    first_line = text.splitlines()[0] if text else ""
    if not first_line:
        return []
    try:
        return [_normalize_text(header) for header in next(csv.reader([first_line]))]
    except (StopIteration, csv.Error):
        return []


def _has_video_id_header(headers: list[str]) -> bool:
    return any(
        header == "video id" or header.startswith("video id ") or header == "معرف الفيديو"
        for header in headers
    )


def _has_channel_id_header(headers: list[str]) -> bool:
    return any(header in ("channel id", "معرف القناة") for header in headers)


def _is_playlist_index_csv(headers: list[str]) -> bool:
    for header in headers:
        if header == "playlist id":
            return True
        if "قائمة التشغيل" in header and ("تعريف" in header or "معرف" in header):
            return True
    return False


def _is_playlist_videos_csv(headers: list[str]) -> bool:
    if not _has_video_id_header(headers):
        return False
    return any(
        header == "time added"
        or ("الطابع الزمني" in header and "قائمة التشغيل" in header and "فيديو" in header)
        for header in headers
    )


def _is_subscriptions_csv(headers: list[str]) -> bool:
    if _is_playlist_videos_csv(headers) or _is_playlist_index_csv(headers):
        return False
    has_url = any(
        header in ("channel url", "عنوان url للقناة") for header in headers
    )
    has_title = any(header in ("channel title", "عنوان القناة") for header in headers)
    return _has_channel_id_header(headers) and (has_url or has_title)


def _looks_like_watch_history(reader: TakeoutArchiveReader, path: str) -> bool:
    lower = path.lower()
    base = os.path.basename(lower)
    if "search" in base or "بحث" in base:
        return False
    if "watch-history" in base or "المشاهدة" in base:
        return True

    stream = reader.open_stream(path)
    try:
        sample = stream.read(_HTML_SNIFF_BYTES)
    finally:
        stream.close()
    # Search history exports also contain "watched" rows, but they always
    # carry search links, unlike the dedicated watch-history file.
    return b"youtube.com/watch?v=" in sample and b"search_query=" not in sample


def playlist_name_from_path(path: str) -> str:
    """Return the playlist title encoded in a Takeout per-playlist file name.

    Modern exports wrap localized files as ``Videos in _Title_`` /
    ``فيديوهات _Title_`` while older exports simply use ``Title``.
    """
    base = os.path.splitext(os.path.basename(str(path or "")))[0].strip()
    wrapped = re.search(r"_\s*(.+?)\s*_$", base)
    if wrapped:
        base = wrapped.group(1).strip()
    return coerce_text(base)


def is_liked_playlist_name(name: str) -> bool:
    lower = _normalize_text(name)
    return (
        "liked videos" in lower
        or lower == "liked"
        or "أعجبتني" in lower
        or lower == "أعجبني"
    )


def is_watch_later_playlist_name(name: str) -> bool:
    lower = _normalize_text(name)
    return "watch later" in lower or "مشاهدة لاحق" in lower


def extract_id_from_url(url: str) -> str:
    """Extract 11-char YouTube video ID from URL or return empty string."""
    if not url:
        return ""
    m = _VIDEO_ID_REGEX.search(url)
    return m.group(1) if m else ""


@dataclass
class ParsedPlaylistItem:
    video_id: str
    title: str
    channel: str
    added_at: float


@dataclass
class ParsedPlaylist:
    name: str
    is_liked_videos: bool = False
    is_watch_later: bool = False
    items: list[ParsedPlaylistItem] = field(default_factory=list)


@dataclass
class ParsedHistoryItem:
    video_id: str
    title: str
    channel: str
    watched_at: float


@dataclass
class ParsedSubscription:
    channel_id: str
    title: str
    url: str


@dataclass
class TakeoutInspectionResult:
    archive_format: str  # "zip" | "directory"
    has_subscriptions: bool = False
    subscriptions_count: int = 0
    has_history: bool = False
    history_count: int = 0
    has_likes: bool = False
    likes_count: int = 0
    has_watch_later: bool = False
    watch_later_count: int = 0
    playlists: list[tuple[str, int]] = field(default_factory=list)  # (name, count)
    total_items: int = 0


def _parse_iso_timestamp(text: str) -> float:
    """Defensively parse ISO8601 string to epoch timestamp float."""
    if not text:
        return 0.0
    text = text.strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return float(dt.timestamp())
    except Exception:
        return coerce_timestamp(text)


class TakeoutArchiveReader:
    """Uniform reader for .zip files and extracted Takeout directories."""

    def __init__(self, source_path: str):
        if not is_safe_local_path(source_path):
            raise ValueError(f"Unsafe archive source path: {source_path}")
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Takeout source does not exist: {source_path}")

        self.source_path = source_path
        self.is_zip = zipfile.is_zipfile(source_path)
        self._zip: zipfile.ZipFile | None = None
        if self.is_zip:
            self._zip = zipfile.ZipFile(source_path, "r")
            self._validate_zip_members()

    def _validate_zip_members(self):
        """Guard against Zip Slip and Zip Bomb vulnerabilities."""
        assert self._zip is not None
        total_uncompressed = 0
        for info in self._zip.infolist():
            # Zip Slip check: no directory traversal
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or "../" in name or "..\\" in name:
                raise ValueError(f"Malicious path in zip entry: {info.filename}")

            if info.file_size > MAX_MEMBER_UNCOMPRESSED_BYTES:
                raise ValueError(
                    f"Zip entry {info.filename} exceeds max size ({info.file_size} bytes)"
                )

            total_uncompressed += info.file_size
            if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_BYTES:
                raise ValueError("Cumulative uncompressed archive size exceeds limit")

            if info.compress_size > 0:
                ratio = info.file_size / info.compress_size
                if ratio > MAX_RATIO:
                    raise ValueError(f"High compression ratio ({ratio:.1f}) in {info.filename}")

    def list_files(self) -> list[str]:
        """Return relative paths normalized with forward slashes."""
        if self.is_zip and self._zip:
            return [info.filename.replace("\\", "/") for info in self._zip.infolist() if not info.is_dir()]

        res = []
        for root, _, files in os.walk(self.source_path):
            for file in files:
                full = os.path.join(root, file)
                rel = os.path.relpath(full, self.source_path).replace("\\", "/")
                res.append(rel)
        return res

    def open_stream(self, rel_path: str) -> IO[bytes]:
        """Open a read-only binary stream for a normalized relative path."""
        if self.is_zip and self._zip:
            # Match forward-slash or backslash in zip member names
            for name in self._zip.namelist():
                if name.replace("\\", "/") == rel_path:
                    return self._zip.open(name, "r")
            raise FileNotFoundError(f"Zip entry not found: {rel_path}")

        local_path = os.path.join(self.source_path, rel_path.replace("/", os.sep))
        if not is_safe_local_path(local_path):
            raise ValueError(f"Unsafe local path access: {local_path}")
        return open(local_path, "rb")

    def close(self):
        if self._zip is not None:
            self._zip.close()
            self._zip = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def find_takeout_files(reader: TakeoutArchiveReader) -> dict[str, Any]:
    """Map expected Takeout components to their relative archive paths.

    Files are classified by their headers/content so localized exports
    (Arabic, French, ...) are recognized even though folder and file names
    are translated.
    """
    all_files = reader.list_files()
    found: dict[str, Any] = {
        "subscriptions": None,
        "history": None,
        "playlists": [],
    }
    # JSON history is richer (timestamps) than HTML, so prefer it.
    history_priority = 0

    for path in all_files:
        lower = path.lower()
        suffix = os.path.splitext(lower)[1]

        if suffix == ".html":
            if _looks_like_watch_history(reader, path) and history_priority < 1:
                found["history"] = path
                history_priority = 1
            continue

        if suffix == ".json":
            base = os.path.basename(lower)
            if base == "subscriptions.json" or _path_has_hint(
                lower, _SUBSCRIPTION_DIR_HINTS
            ):
                if found["subscriptions"] is None:
                    found["subscriptions"] = path
            elif "watch-history" in base:
                found["history"] = path
                history_priority = 2
            elif _path_has_hint(lower, _PLAYLIST_DIR_HINTS):
                found["playlists"].append(path)
            continue

        if suffix != ".csv":
            continue

        stream = reader.open_stream(path)
        try:
            sample = stream.read(_CSV_SNIFF_BYTES)
        finally:
            stream.close()
        headers = _csv_headers(sample)
        if not headers:
            continue

        if _is_playlist_index_csv(headers):
            # playlists.csv only contains playlist metadata, not videos.
            continue
        if _is_playlist_videos_csv(headers):
            found["playlists"].append(path)
            continue
        if _is_subscriptions_csv(headers) or (
            _path_has_hint(lower, _SUBSCRIPTION_DIR_HINTS)
            and _has_channel_id_header(headers)
        ):
            if found["subscriptions"] is None:
                found["subscriptions"] = path
            continue
        if _path_has_hint(lower, _PLAYLIST_DIR_HINTS) and _has_video_id_header(
            headers
        ):
            found["playlists"].append(path)

    return found


def parse_subscriptions_data(data: bytes, is_json: bool) -> list[ParsedSubscription]:
    """Parse subscriptions list from JSON or CSV bytes."""
    results: list[ParsedSubscription] = []
    if is_json:
        try:
            payload = json.loads(data.decode("utf-8", errors="replace"))
        except Exception:
            return results
        if not isinstance(payload, list):
            return results
        for item in payload:
            if not isinstance(item, dict):
                continue
            snippet = item.get("snippet", item)
            cid = ""
            if isinstance(snippet, dict):
                res_id = snippet.get("resourceId", {})
                if isinstance(res_id, dict):
                    cid = coerce_id(res_id.get("channelId", ""))
                if not cid:
                    cid = coerce_id(snippet.get("channelId", ""))
                title = coerce_text(snippet.get("title", snippet.get("channelTitle", "")))
            else:
                title = ""
            if cid:
                results.append(
                    ParsedSubscription(
                        channel_id=cid,
                        title=title or "Unknown Channel",
                        url=f"https://www.youtube.com/channel/{cid}",
                    )
                )
    else:
        # CSV parsing (headers follow the export language)
        text_stream = io.StringIO(data.decode("utf-8-sig", errors="replace"))
        reader = csv.DictReader(text_stream)
        for row in reader:
            values = {
                _normalize_text(key): value for key, value in row.items() if key
            }
            cid = coerce_id(
                values.get("channel id") or values.get("معرف القناة") or ""
            )
            title = coerce_text(
                values.get("channel title") or values.get("عنوان القناة") or ""
            )
            url = (
                values.get("channel url")
                or values.get("عنوان url للقناة")
                or f"https://www.youtube.com/channel/{cid}"
            )
            if cid:
                results.append(
                    ParsedSubscription(
                        channel_id=cid, title=title, url=coerce_text(url)
                    )
                )
    return results


def _parse_takeout_html_date(text: str) -> float:
    """Parse the date line of a Takeout HTML history entry (any locale)."""
    raw = _ARABIC_MARKS_REGEX.sub("", str(text or ""))
    if not raw:
        return 0.0

    time_match = re.search(
        r"(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(ص|م|AM|PM)?", raw, re.IGNORECASE
    )
    hour = int(time_match.group(1)) if time_match else 0
    minute = int(time_match.group(2)) if time_match else 0
    second = int(time_match.group(3) or 0) if time_match else 0
    meridiem = (time_match.group(4) or "").casefold() if time_match else ""

    numeric = re.search(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", raw)
    if numeric:
        day, month, year = (
            int(numeric.group(1)),
            int(numeric.group(2)),
            int(numeric.group(3)),
        )
    else:
        named = re.search(r"([A-Za-z]{3,9})\s+(\d{1,2}),\s*(\d{4})", raw)
        if not named:
            return 0.0
        month = _MONTH_NAMES.get(named.group(1)[:3].casefold(), 0)
        day = int(named.group(2))
        year = int(named.group(3))
        if not month:
            return 0.0

    if meridiem in ("م", "pm") and hour < 12:
        hour += 12
    elif meridiem in ("ص", "am") and hour == 12:
        hour = 0

    try:
        return float(datetime(year, month, day, hour, minute, second).timestamp())
    except ValueError:
        return 0.0


def parse_history_data(data: bytes, is_json: bool) -> list[ParsedHistoryItem]:
    """Parse watch history items from JSON or HTML bytes."""
    results: list[ParsedHistoryItem] = []
    if is_json:
        try:
            payload = json.loads(data.decode("utf-8", errors="replace"))
        except Exception:
            return results
        if not isinstance(payload, list):
            return results

        for item in payload:
            if not isinstance(item, dict):
                continue
            title_url = item.get("titleUrl", "")
            vid = extract_id_from_url(title_url)
            if not vid:
                continue

            raw_title = coerce_text(item.get("title", ""))
            # Strip "Watched " prefix from Google Takeout
            if raw_title.startswith("Watched "):
                title = raw_title[8:].strip()
            else:
                title = raw_title or f"Video {vid}"

            # Subtitles list holds the channel
            channel = ""
            subtitles = item.get("subtitles")
            if isinstance(subtitles, list) and subtitles and isinstance(subtitles[0], dict):
                channel = coerce_text(subtitles[0].get("name", ""))

            watched_at = _parse_iso_timestamp(str(item.get("time", "")))
            results.append(
                ParsedHistoryItem(
                    video_id=vid,
                    title=title,
                    channel=channel,
                    watched_at=watched_at,
                )
            )
    else:
        # HTML scraping fallback for watch-history.html (any export language)
        content = data.decode("utf-8", errors="replace")
        for match in _HTML_WATCH_ANCHOR_REGEX.finditer(content):
            vid = match.group(1)
            raw_title = re.sub(r"<[^>]+>", "", match.group(2))
            title = html.unescape(raw_title).strip()
            for prefix in ("Watched ", "تمت مشاهدة "):
                if title.startswith(prefix):
                    title = title[len(prefix):].strip()
                    break

            tail = content[match.end(): match.end() + 600]
            channel_match = _HTML_CHANNEL_ANCHOR_REGEX.search(tail)
            channel = (
                html.unescape(channel_match.group(1)).strip()
                if channel_match
                else ""
            )
            date_match = _HTML_DATE_LINE_REGEX.search(tail)
            watched_at = (
                _parse_takeout_html_date(date_match.group(1)) if date_match else 0.0
            )

            results.append(
                ParsedHistoryItem(
                    video_id=vid,
                    title=title or f"Video {vid}",
                    channel=channel,
                    watched_at=watched_at,
                )
            )
    return results


def parse_playlist_data(data: bytes, is_json: bool, playlist_name: str) -> ParsedPlaylist:
    """Parse playlist videos from JSON or CSV bytes."""
    clean_name = coerce_text(playlist_name)
    playlist = ParsedPlaylist(
        name=clean_name,
        is_liked_videos=is_liked_playlist_name(clean_name),
        is_watch_later=is_watch_later_playlist_name(clean_name),
    )

    if is_json:
        try:
            payload = json.loads(data.decode("utf-8", errors="replace"))
        except Exception:
            return playlist
        if not isinstance(payload, list):
            return playlist

        for item in payload:
            if not isinstance(item, dict):
                continue
            snippet = item.get("snippet", item)
            vid = ""
            title = ""
            channel = ""
            if isinstance(snippet, dict):
                res_id = snippet.get("resourceId", {})
                if isinstance(res_id, dict):
                    vid = coerce_id(res_id.get("videoId", ""))
                if not vid:
                    vid = coerce_id(snippet.get("videoId", ""))
                title = coerce_text(snippet.get("title", ""))
                channel = coerce_text(snippet.get("videoOwnerChannelTitle", ""))

            content_details = item.get("contentDetails", {})
            added_at = 0.0
            if isinstance(content_details, dict):
                added_at = _parse_iso_timestamp(str(content_details.get("videoPublishedAt", "")))

            if not vid:
                # Try url
                vid = extract_id_from_url(str(item.get("url", "")))

            try:
                validate_video_id(vid)
                playlist.items.append(
                    ParsedPlaylistItem(
                        video_id=vid,
                        title=title or f"Video {vid}",
                        channel=channel,
                        added_at=added_at,
                    )
                )
            except ValueError:
                continue
    else:
        # CSV parsing (headers follow the export language; newer exports only
        # carry the video id and the timestamp).
        text_stream = io.StringIO(data.decode("utf-8-sig", errors="replace"))
        reader = csv.DictReader(text_stream)
        for row in reader:
            values = {
                _normalize_text(key): value for key, value in row.items() if key
            }
            vid = coerce_id(
                values.get("video id") or values.get("معرف الفيديو") or ""
            )
            title = coerce_text(
                values.get("title")
                or values.get("video title")
                or values.get("عنوان الفيديو (الأصلي)")
                or values.get("عنوان الفيديو")
                or ""
            )
            channel = coerce_text(
                values.get("channel title") or values.get("عنوان القناة") or ""
            )
            added_at = _parse_iso_timestamp(
                values.get("time added")
                or values.get("الطابع الزمني لإنشاء الفيديو في قائمة التشغيل")
                or ""
            )
            try:
                validate_video_id(vid)
                playlist.items.append(
                    ParsedPlaylistItem(
                        video_id=vid,
                        title=title or f"Video {vid}",
                        channel=channel,
                        added_at=added_at,
                    )
                )
            except ValueError:
                continue

    return playlist


def inspect_takeout_source(source_path: str) -> TakeoutInspectionResult:
    """Analyze a Takeout archive or folder and return item counts."""
    with TakeoutArchiveReader(source_path) as reader:
        mapping = find_takeout_files(reader)
        res = TakeoutInspectionResult(
            archive_format="zip" if reader.is_zip else "directory"
        )

        # Inspect subscriptions
        if mapping["subscriptions"]:
            stream = reader.open_stream(mapping["subscriptions"])
            try:
                data = stream.read()
                subs = parse_subscriptions_data(data, mapping["subscriptions"].lower().endswith(".json"))
                res.has_subscriptions = bool(subs)
                res.subscriptions_count = len(subs)
            finally:
                stream.close()

        # Inspect history
        if mapping["history"]:
            stream = reader.open_stream(mapping["history"])
            try:
                data = stream.read()
                hist = parse_history_data(data, mapping["history"].lower().endswith(".json"))
                res.has_history = bool(hist)
                res.history_count = len(hist)
            finally:
                stream.close()

        # Inspect playlists
        for pl_path in mapping["playlists"]:
            stream = reader.open_stream(pl_path)
            try:
                data = stream.read()
                name = playlist_name_from_path(pl_path)
                pl = parse_playlist_data(
                    data, pl_path.lower().endswith(".json"), name
                )
                count = len(pl.items)
                if pl.is_liked_videos:
                    res.has_likes = True
                    res.likes_count = count
                elif pl.is_watch_later:
                    res.has_watch_later = True
                    res.watch_later_count = count
                else:
                    res.playlists.append((pl.name, count))
            finally:
                stream.close()

        res.total_items = (
            res.subscriptions_count
            + res.history_count
            + res.likes_count
            + res.watch_later_count
            + sum(count for _, count in res.playlists)
        )
        return res
