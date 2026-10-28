"""Shared playback validation and quality mapping.

Keeping URL/quality rules in one module prevents ``player.py`` and
``youtube_api.py`` from silently drifting apart.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from core.security import MAX_URL_LENGTH, has_control_chars

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

QUALITY_MAP = {
    "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
    "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]",
    "best": "bestvideo+bestaudio/best",
}

DEFAULT_QUALITY = "720p"

_ALLOWED_STREAM_SCHEMES = ("http", "https", "ytdl")


def normalize_quality(quality: str | None) -> str:
    """Return a supported quality key, defaulting to ``best`` for unknown input."""
    if isinstance(quality, str) and quality in QUALITY_MAP:
        return quality
    return "best"


def format_selector(quality: str | None) -> str:
    """Return the yt-dlp/mpv format selector for *quality*."""
    return QUALITY_MAP[normalize_quality(quality)]


def is_valid_video_id(video_id: object) -> bool:
    return isinstance(video_id, str) and bool(VIDEO_ID_RE.match(video_id))


def validate_video_id(video_id: object) -> str:
    """Validate a YouTube video ID and return it unchanged."""
    if not is_valid_video_id(video_id):
        raise ValueError(f"Invalid YouTube video ID: {video_id!r}")
    return video_id  # type: ignore[return-value]


def watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={validate_video_id(video_id)}"


def validate_stream_url(url: object) -> str:
    """Validate a resolved media URL before it is handed to MPV.

    MPV receives the URL as its own argv element, but a value containing
    control characters, embedded credentials, or a non-media scheme can still
    confuse the player or leak secrets into logs.  Parsing the URL (instead of
    a prefix check) also rejects ``https://user:pass@host`` forms.
    """
    if not isinstance(url, str) or not url:
        raise ValueError("Resolved stream URL must be a non-empty string")
    if len(url) > MAX_URL_LENGTH or has_control_chars(url) or " " in url:
        raise ValueError("Resolved stream URL contains whitespace or control characters")
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise ValueError(f"Malformed stream URL: {exc}") from exc
    if parts.scheme.lower() not in _ALLOWED_STREAM_SCHEMES:
        raise ValueError(f"Unsupported stream URL scheme: {parts.scheme!r}")
    if parts.username or parts.password:
        raise ValueError("Stream URL must not contain credentials")
    if not parts.hostname:
        raise ValueError("Stream URL is missing a host")
    return url


@dataclass(frozen=True)
class ResolvedStream:
    """A playable media pair produced by ``yt-dlp``.

    YouTube serves high-resolution video and audio as separate DASH streams.
    MPV therefore needs the video URL plus an optional external audio URL.
    Progressive formats produce a single URL and leave ``audio_url`` empty.
    """

    video_url: str
    audio_url: str = ""
    quality: str = DEFAULT_QUALITY

    def __post_init__(self):
        validate_stream_url(self.video_url)
        if self.audio_url:
            validate_stream_url(self.audio_url)

    @property
    def urls(self) -> tuple[str, ...]:
        return (self.video_url, self.audio_url) if self.audio_url else (self.video_url,)

