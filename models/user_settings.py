"""
User Settings Model
===================

Application settings scoped to a user. Supports arbitrary key-value
get/set for extensibility.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class UserSettings:
    """User application settings"""
    default_quality: str = "720p"
    volume: int = 80
    auto_play_next: bool = False
    theme: str = "dark"
    language: str = "en"
    playback_speed: float = 1.0
    search_results_count: int = 10
    thumbnail_size: int = 160
    window_width: int = 900
    window_height: int = 700
    window_x: int = 100
    window_y: int = 100
    _extra: dict = None

    def __post_init__(self):
        if self._extra is None:
            object.__setattr__(self, '_extra', {})

    def to_dict(self) -> dict:
        result = {
            'default_quality': self.default_quality,
            'volume': self.volume,
            'auto_play_next': self.auto_play_next,
            'theme': self.theme,
            'language': self.language,
            'playback_speed': self.playback_speed,
            'search_results_count': self.search_results_count,
            'thumbnail_size': self.thumbnail_size,
            'window_width': self.window_width,
            'window_height': self.window_height,
            'window_x': self.window_x,
            'window_y': self.window_y,
        }
        result.update(self._extra)
        return result

    @classmethod
    def from_dict(cls, data: dict) -> 'UserSettings':
        if not data:
            return cls()
        known_keys = {
            'default_quality', 'volume', 'auto_play_next', 'theme', 'language',
            'playback_speed', 'search_results_count', 'thumbnail_size',
            'window_width', 'window_height', 'window_x', 'window_y',
        }
        known = {k: v for k, v in data.items() if k in known_keys}
        extra = {k: v for k, v in data.items() if k not in known_keys and k != '_extra'}
        obj = cls(**known)
        obj._extra = extra
        return obj

    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value by key"""
        if hasattr(self, key) and key != '_extra':
            return getattr(self, key)
        return self._extra.get(key, default)

    def set(self, key: str, value: Any):
        """Set a setting value by key"""
        if hasattr(self, key) and key != '_extra':
            object.__setattr__(self, key, value)
        else:
            self._extra[key] = value

    @classmethod
    def defaults(cls) -> 'UserSettings':
        return cls()
