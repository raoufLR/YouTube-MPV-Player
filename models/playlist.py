"""
Playlist Models
==============

Playlist and PlaylistVideo models with full CRUD operations.
Supports Watch Later as a special built-in playlist.

Load-time parsing is defensive: malformed entries are dropped or normalized
instead of raising and hiding an entire playlist.
"""

import time
import uuid
from dataclasses import dataclass, field

from core.validation import (
    coerce_id,
    coerce_int,
    coerce_text,
    coerce_timestamp,
)

MAX_VIDEO_ID_LENGTH = 128
MAX_PLAYLIST_NAME = 128
MAX_DESCRIPTION = 4000
MAX_TITLE = 512
MAX_CHANNEL = 256
MAX_URL = 2048


@dataclass
class PlaylistVideo:
    """A video entry within a playlist"""
    video_id: str = ""
    title: str = ""
    channel: str = ""
    thumbnail: str = ""
    url: str = ""
    added_at: float = field(default_factory=time.time)
    position: int = 0

    def to_dict(self) -> dict:
        return {
            'video_id': self.video_id,
            'title': self.title,
            'channel': self.channel,
            'thumbnail': self.thumbnail,
            'url': self.url,
            'added_at': self.added_at,
            'position': self.position,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PlaylistVideo:
        if not isinstance(data, dict):
            return cls()
        return cls(
            video_id=coerce_id(
                data.get('video_id', data.get('videoId', data.get('id', ''))),
                max_length=MAX_VIDEO_ID_LENGTH,
            ),
            title=coerce_text(data.get('title', ''), max_length=MAX_TITLE),
            channel=coerce_text(data.get('channel', ''), max_length=MAX_CHANNEL),
            thumbnail=coerce_text(data.get('thumbnail', ''), max_length=MAX_URL),
            url=coerce_text(data.get('url', ''), max_length=MAX_URL),
            added_at=coerce_timestamp(data.get('added_at')),
            position=coerce_int(data.get('position', 0), 0, minimum=0, maximum=10_000_000),
        )


@dataclass
class Playlist:
    """A user playlist containing ordered videos"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "New Playlist"
    description: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    videos: list[PlaylistVideo] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'videos': [v.to_dict() for v in self.videos],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Playlist:
        if not isinstance(data, dict):
            return cls()

        raw_videos = data.get('videos', [])
        if not isinstance(raw_videos, list):
            raw_videos = []

        videos: list[PlaylistVideo] = []
        seen = set()
        for raw in raw_videos:
            if not isinstance(raw, dict):
                continue
            video = PlaylistVideo.from_dict(raw)
            if not video.video_id or video.video_id in seen:
                continue
            seen.add(video.video_id)
            videos.append(video)
        for index, video in enumerate(videos):
            video.position = index

        return cls(
            id=coerce_id(data.get('id', ''), str(uuid.uuid4()), max_length=128),
            name=coerce_text(
                data.get('name', ''), 'Recovered Playlist',
                max_length=MAX_PLAYLIST_NAME,
            ),
            description=coerce_text(
                data.get('description', ''), '',
                max_length=MAX_DESCRIPTION, multiline=True,
            ),
            created_at=coerce_timestamp(data.get('created_at')),
            updated_at=coerce_timestamp(data.get('updated_at')),
            videos=videos,
        )

    def add_video(self, video_data: dict, position: int = -1) -> PlaylistVideo:
        """Add a video to the playlist. Returns the created PlaylistVideo."""
        vid = PlaylistVideo.from_dict(video_data)
        vid.added_at = time.time()
        vid.position = position if position >= 0 else len(self.videos)
        vid.position = max(0, vid.position)

        if position < 0:
            self.videos.append(vid)
        else:
            self.videos.insert(min(position, len(self.videos)), vid)
        self._reindex()

        self.updated_at = time.time()
        return vid

    def remove_video(self, video_id: str) -> bool:
        """Remove a video by video_id. Returns True if removed."""
        original_len = len(self.videos)
        self.videos = [v for v in self.videos if v.video_id != video_id]
        if len(self.videos) < original_len:
            self._reindex()
            self.updated_at = time.time()
            return True
        return False

    def has_video(self, video_id: str) -> bool:
        """Check if a video is in this playlist"""
        return any(v.video_id == video_id for v in self.videos)

    def get_video(self, video_id: str) -> PlaylistVideo | None:
        """Get a video by video_id. Returns None if not found."""
        for v in self.videos:
            if v.video_id == video_id:
                return v
        return None

    def clear(self):
        """Remove all videos from the playlist"""
        self.videos.clear()
        self.updated_at = time.time()

    def _reindex(self):
        """Reassign position indices after insertion/removal"""
        for i, v in enumerate(self.videos):
            v.position = i
