"""Thin yt-dlp wrapper used for search, metadata, and stream resolution.

All subprocess work is cancellable so a superseded playback request can stop
its resolver instead of leaving an orphaned yt-dlp process behind.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time

from core.playback_errors import StreamCancelledError, StreamResolutionError
from core.quality import (
    QUALITY_MAP,
    ResolvedStream,
    is_valid_video_id,
    normalize_quality,
    validate_video_id,
)
from core.security import has_control_chars

_MAX_RETRIES = 2
_RETRY_DELAYS = [1.0, 2.0]
_POLL_INTERVAL = 0.1
_MAX_QUERY_LENGTH = 200
_MAX_RESULT_TEXT = 300
_MAX_RESULTS = 100


def _clean_result_text(value: object, max_length: int = _MAX_RESULT_TEXT) -> str:
    """Strip control characters from remote metadata before it reaches the UI."""
    text = "" if value is None else str(value)
    text = "".join(ch for ch in text if ord(ch) >= 32 and ch != "\x7f")
    return text[:max_length]


def _is_valid_result_id(value: object) -> bool:
    return is_valid_video_id(value)


def _resource_path(relative_path: str) -> str:
    """Get absolute path to a bundled resource, works for dev and PyInstaller EXE."""
    base_path = getattr(sys, "_MEIPASS", None)
    if base_path is None:
        # Resolve relative to the application, not the process working
        # directory (shortcuts and "Open with" start elsewhere).
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


class YouTubeAPI:
    def __init__(self, logger: logging.Logger | None = None,
                 preferred_update_path: str | None = None):
        self.ytdlp_path = self._find_ytdlp(preferred_update_path)
        self._logger = logger or logging.getLogger(__name__)

    @staticmethod
    def _find_ytdlp(preferred: str | None = None) -> str:
        """Locate the executable: installed update first, then bundled, then PATH.

        The working directory is deliberately *not* searched: launching the
        app from a downloads folder must never execute a planted
        ``yt-dlp.exe``.  The bundled copy is version-locked with the app,
        unless a newer copy was installed by the update service.
        """
        if preferred and os.path.isfile(preferred):
            return preferred
        bundled = _resource_path("yt-dlp.exe")
        if os.path.isfile(bundled):
            return bundled
        for name in ("yt-dlp", "yt-dlp.exe"):
            found = shutil.which(name)
            if found:
                return found
        # Reported as FileNotFoundError the first time yt-dlp is invoked.
        return "yt-dlp"

    # ------------------------------------------------------------------
    # Process execution
    # ------------------------------------------------------------------

    @staticmethod
    def _terminate(process):
        if process is None or process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=1.0)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
                process.wait(timeout=1.0)
            except (OSError, subprocess.TimeoutExpired):
                pass

    def _run_ytdlp(self, cmd: list, timeout: int, cancel_event=None) -> str:
        last_error: BaseException | None = None
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

        for attempt in range(1 + _MAX_RETRIES):
            if cancel_event is not None and cancel_event.is_set():
                raise StreamCancelledError("Stream resolution cancelled")

            process = None
            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    stdin=subprocess.DEVNULL,
                    text=True,
                    creationflags=creationflags,
                )
                deadline = time.monotonic() + timeout
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        self._terminate(process)
                        raise StreamCancelledError("Stream resolution cancelled")
                    try:
                        stdout, stderr = process.communicate(timeout=_POLL_INTERVAL)
                        break
                    except subprocess.TimeoutExpired:
                        if time.monotonic() >= deadline:
                            self._terminate(process)
                            raise subprocess.TimeoutExpired(cmd, timeout)

                if process.returncode == 0:
                    return stdout

                last_error = RuntimeError(
                    f"yt-dlp exited with code {process.returncode}: "
                    f"{(stderr or '').strip()}"
                )
                self._logger.warning(
                    "yt-dlp attempt %d/%d failed: %s",
                    attempt + 1,
                    1 + _MAX_RETRIES,
                    last_error,
                )
            except StreamCancelledError:
                raise
            except FileNotFoundError as exc:
                raise RuntimeError(
                    f"yt-dlp executable not found: {cmd[0]}"
                ) from exc
            except (subprocess.TimeoutExpired, OSError) as exc:
                last_error = exc
                self._logger.warning(
                    "yt-dlp attempt %d/%d failed: %s",
                    attempt + 1,
                    1 + _MAX_RETRIES,
                    exc,
                )
            finally:
                if process is not None and process.poll() is None:
                    self._terminate(process)

            if attempt < _MAX_RETRIES:
                delay = _RETRY_DELAYS[attempt]
                if cancel_event is not None:
                    if cancel_event.wait(delay):
                        raise StreamCancelledError("Stream resolution cancelled")
                else:
                    time.sleep(delay)

        assert last_error is not None
        raise last_error

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def _validated_query(query) -> str:
        """Reject empty, oversized, or control-character search expressions."""
        if not isinstance(query, str):
            raise ValueError("Search query must be a string")
        cleaned = query.strip()
        if not cleaned:
            raise ValueError("Search query must not be empty")
        if len(cleaned) > _MAX_QUERY_LENGTH:
            raise ValueError("Search query is too long")
        if has_control_chars(cleaned):
            raise ValueError("Search query contains control characters")
        return cleaned

    def search_videos(self, query, max_results=20, offset=0):
        query = self._validated_query(query)
        try:
            max_results = int(max_results)
            offset = int(offset)
        except (TypeError, ValueError) as exc:
            raise ValueError("max_results and offset must be integers") from exc
        max_results = max(1, min(max_results, _MAX_RESULTS))
        offset = max(0, min(offset, 10_000))
        total_needed = offset + max_results
        cmd = [
            self.ytdlp_path,
            f"ytsearch{total_needed}:{query}",
            "--ignore-config",
            "--flat-playlist",
            "--print-json",
            "--no-warnings",
            "--skip-download",
            f"--playlist-start={offset + 1}",
            f"--playlist-end={total_needed}",
        ]
        try:
            stdout = self._run_ytdlp(cmd, timeout=30)
            videos = []
            for line in stdout.strip().split("\n"):
                if not line:
                    continue
                data = json.loads(line)
                video_id = data.get("id", "")
                if not _is_valid_result_id(video_id):
                    continue
                thumbnails = data.get("thumbnails", [])
                thumb_url = thumbnails[-1].get("url", "") if thumbnails else ""
                videos.append(
                    {
                        "title": _clean_result_text(data.get("title", "Unknown")),
                        "videoId": video_id,
                        "thumbnail": thumb_url if isinstance(thumb_url, str) else "",
                        "channel": _clean_result_text(
                            data.get("channel", data.get("uploader", "Unknown"))
                        ),
                    }
                )
            return videos
        except StreamCancelledError:
            raise
        except (RuntimeError, OSError, json.JSONDecodeError) as exc:
            self._logger.error("Search failed: %s", exc)
            return []

    def extract_streams(self, video_id, quality="best", cancel_event=None) -> ResolvedStream:
        """Resolve *video_id* into direct media URLs via ``yt-dlp -g``.

        ``--dump-json`` does not expose a usable URL for merged
        ``bestvideo+bestaudio`` selectors, while ``-g`` returns the video URL
        and, when DASH is used, the separate audio URL on the next line.
        """
        validate_video_id(video_id)
        normalized_quality = normalize_quality(quality)
        url = f"https://www.youtube.com/watch?v={video_id}"
        cmd = [
            self.ytdlp_path,
            "-f",
            QUALITY_MAP[normalized_quality],
            "-g",
            "--ignore-config",
            "--no-warnings",
            "--no-playlist",
            url,
        ]

        try:
            stdout = self._run_ytdlp(cmd, timeout=60, cancel_event=cancel_event)
        except StreamCancelledError:
            raise
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            raise StreamResolutionError(
                f"Stream resolution failed for {video_id}: {exc}"
            ) from exc

        urls = [line.strip() for line in stdout.splitlines() if line.strip()]
        if not urls:
            raise StreamResolutionError(
                f"Could not extract a playable stream URL for {video_id}"
            )
        if len(urls) > 2:
            self._logger.warning(
                "yt-dlp returned %d URLs for %s; using the first two",
                len(urls),
                video_id,
            )
        try:
            return ResolvedStream(
                video_url=urls[0],
                audio_url=urls[1] if len(urls) > 1 else "",
                quality=normalized_quality,
            )
        except ValueError as exc:
            raise StreamResolutionError(
                f"yt-dlp returned an invalid stream URL for {video_id}: {exc}"
            ) from exc

    def fetch_video_info(self, video_id, cancel_event=None) -> dict:
        """Best-effort metadata lookup used to enrich history entries."""
        validate_video_id(video_id)
        url = f"https://www.youtube.com/watch?v={video_id}"
        cmd = [
            self.ytdlp_path,
            "--ignore-config",
            "--dump-json",
            "--skip-download",
            "--no-warnings",
            "--no-playlist",
            url,
        ]

        try:
            stdout = self._run_ytdlp(cmd, timeout=30, cancel_event=cancel_event)
        except StreamCancelledError:
            raise
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            raise StreamResolutionError(
                f"Metadata resolution failed for {video_id}: {exc}"
            ) from exc

        try:
            payload = next(
                json.loads(line)
                for line in reversed(stdout.strip().split("\n"))
                if line.strip()
            )
        except (StopIteration, json.JSONDecodeError) as exc:
            raise StreamResolutionError(
                f"yt-dlp returned invalid metadata for {video_id}"
            ) from exc

        thumbnails = payload.get("thumbnails") or []
        thumbnail = thumbnails[-1].get("url", "") if thumbnails else ""
        return {
            "videoId": video_id,
            "title": payload.get("title", ""),
            "channel": payload.get("channel", payload.get("uploader", "")),
            "thumbnail": thumbnail,
            "duration": payload.get("duration") or 0,
        }
