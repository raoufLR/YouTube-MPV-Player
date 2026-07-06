import logging
import re
import subprocess
import json
import os
import time
from typing import Optional


QUALITY_MAP = {
    "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
    "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]",
    "best": "bestvideo+bestaudio/best",
}

_VIDEO_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")
_MAX_RETRIES = 2
_RETRY_DELAYS = [1.0, 2.0]


class YouTubeAPI:
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.ytdlp_path = self._find_ytdlp()
        self._logger = logger or logging.getLogger(__name__)

    def _find_ytdlp(self):
        local = os.path.join(os.getcwd(), "yt-dlp.exe")
        if os.path.exists(local):
            return local
        return os.path.join(os.getcwd(), "yt-dlp")

    def _run_ytdlp(self, cmd: list, timeout: int) -> str:
        last_error = None
        for attempt in range(1 + _MAX_RETRIES):
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=timeout
                )
                if result.returncode == 0:
                    return result.stdout
                last_error = RuntimeError(
                    f"yt-dlp exited with code {result.returncode}: {result.stderr.strip()}"
                )
            except (subprocess.TimeoutExpired, OSError) as e:
                last_error = e
                self._logger.warning(
                    "yt-dlp attempt %d/%d failed: %s", attempt, 1 + _MAX_RETRIES, e
                )

            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAYS[attempt])

        raise last_error

    def search_videos(self, query, max_results=20, offset=0):
        total_needed = offset + max_results
        cmd = [
            self.ytdlp_path,
            f"ytsearch{total_needed}:{query}",
            "--flat-playlist",
            "--print-json",
            "--no-warnings",
            "--skip-download",
            f"--playlist-start={offset + 1}",
            f"--playlist-end={total_needed}"
        ]
        try:
            stdout = self._run_ytdlp(cmd, timeout=30)
            videos = []
            for line in stdout.strip().split('\n'):
                if not line:
                    continue
                data = json.loads(line)
                thumbnails = data.get('thumbnails', [])
                thumb_url = thumbnails[-1]['url'] if thumbnails else ''
                videos.append({
                    'title': data.get('title', 'Unknown'),
                    'videoId': data.get('id', ''),
                    'thumbnail': thumb_url,
                    'channel': data.get('channel', data.get('uploader', 'Unknown'))
                })
            return videos
        except (RuntimeError, json.JSONDecodeError) as e:
            self._logger.error("Search failed: %s", e, exc_info=True)
            return []

    def extract_stream_url(self, video_id, quality="best"):
        if not _VIDEO_ID_RE.match(video_id):
            raise ValueError(f"Invalid video ID format: {video_id!r}")

        ytdl_format = QUALITY_MAP.get(quality, "bestvideo+bestaudio/best")
        url = f"https://www.youtube.com/watch?v={video_id}"
        cmd = [
            self.ytdlp_path,
            "-f", ytdl_format,
            "--print-json",
            "--no-warnings",
            url,
        ]
        try:
            stdout = self._run_ytdlp(cmd, timeout=60)
        except (RuntimeError, OSError) as e:
            raise RuntimeError(f"Stream resolution failed for {video_id}: {e}") from e

        data = json.loads(stdout)
        stream_url = data.get("url", "")
        if not stream_url:
            raise RuntimeError(f"Could not extract stream URL for {video_id}")
        return stream_url
