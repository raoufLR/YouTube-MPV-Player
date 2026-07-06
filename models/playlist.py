"""
Playlist Models
===============

Playlist and PlaylistVideo models with full CRUD operations.
Supports Watch Later as a special built-in playlist.
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import List, Dict


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
    def from_dict(cls, data: dict) -> 'PlaylistVideo':
        if not data:
            return cls()
        return cls(
            video_id=data.get('video_id', ''),
            title=data.get('title', ''),
            channel=data.get('channel', ''),
            thumbnail=data.get('thumbnail', ''),
            url=data.get('url', ''),
            added_at=data.get('added_at', time.time()),
            position=data.get('position', 0),
        )


@dataclass
class Playlist:
    """A user playlist containing ordered videos"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "New Playlist"
    description: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    videos: List[PlaylistVideo] = field(default_factory=list)

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
    def from_dict(cls, data: dict) -> 'Playlist':
        if not data:
            return cls()
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            name=data.get('name', 'New Playlist'),
            description=data.get('description', ''),
            created_at=data.get('created_at', time.time()),
            updated_at=data.get('updated_at', time.time()),
            videos=[PlaylistVideo.from_dict(v) for v in data.get('videos', [])],
        )

    def add_video(self, video_data: Dict, position: int = -1) -> PlaylistVideo:
        """Add a video to the playlist. Returns the created PlaylistVideo."""
        vid = PlaylistVideo(
            video_id=video_data.get('videoId', video_data.get('video_id', '')),
            title=video_data.get('title', ''),
            channel=video_data.get('channel', ''),
            thumbnail=video_data.get('thumbnail', ''),
            url=video_data.get('url', ''),
            position=position if position >= 0 else len(self.videos),
        )

        if position < 0:
            self.videos.append(vid)
        else:
            self.videos.insert(position, vid)
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

    def get_video(self, video_id: str) -> PlaylistVideo:
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
