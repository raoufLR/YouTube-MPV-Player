"""
User Settings Model
===================

Application settings scoped to a user.  Known settings are validated on the
way in so a hand-edited or partially-written ``settings.json`` cannot inject a
string where the UI expects an integer.  Unknown keys are preserved in the
``_extra`` mapping for forward compatibility.
"""

import copy
from dataclasses import dataclass
from typing import Any, ClassVar

from core.quality import QUALITY_MAP
from core.validation import (
    coerce_bool,
    coerce_float,
    coerce_int,
    coerce_text,
)

SETTINGS_SCHEMA_VERSION = 2

SUPPORTED_QUALITIES = frozenset(QUALITY_MAP)

VOLUME_MIN = 0
VOLUME_MAX = 100
PLAYBACK_SPEED_MIN = 0.25
PLAYBACK_SPEED_MAX = 4.0
SEARCH_RESULTS_MIN = 1
SEARCH_RESULTS_MAX = 100
THUMBNAIL_SIZE_MIN = 32
THUMBNAIL_SIZE_MAX = 1024
WINDOW_MIN = 200
WINDOW_MAX = 20000
WINDOW_POSITION_MIN = -100000
WINDOW_POSITION_MAX = 100000
TEXT_SETTING_MAX = 64


@dataclass
class UserSettings:
    """User application settings"""

    default_quality: str = "720p"
    volume: int = 80
    auto_play_next: bool = False
    auto_update_check: bool = True
    theme: str = "default"
    language: str = "en"
    playback_speed: float = 1.0
    search_results_count: int = 10
    thumbnail_size: int = 160
    window_width: int = 900
    window_height: int = 700
    window_x: int = 100
    window_y: int = 100
    window_maximized: bool = False
    _extra: dict = None

    KNOWN_FIELDS: ClassVar[frozenset] = frozenset({
        "default_quality", "volume", "auto_play_next", "auto_update_check",
        "theme", "language", "playback_speed", "search_results_count",
        "thumbnail_size", "window_width", "window_height", "window_x",
        "window_y", "window_maximized",
    })

    def __post_init__(self):
        if not isinstance(self._extra, dict):
            self._extra = {}
        for key in self.KNOWN_FIELDS:
            setattr(self, key, self.normalize_value(key, getattr(self, key)))

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_value(key: str, value: Any) -> Any:
        """Return a safe value for a known setting *key*."""
        if key == "default_quality":
            if isinstance(value, str) and value.strip().casefold() in SUPPORTED_QUALITIES:
                return value.strip().casefold()
            return "720p"
        if key == "volume":
            return coerce_int(value, 80, minimum=VOLUME_MIN, maximum=VOLUME_MAX)
        if key == "auto_play_next":
            return coerce_bool(value, False)
        if key == "auto_update_check":
            return coerce_bool(value, True)
        if key == "theme":
            return coerce_text(value, "default", max_length=TEXT_SETTING_MAX) or "default"
        if key == "language":
            return coerce_text(value, "en", max_length=TEXT_SETTING_MAX) or "en"
        if key == "playback_speed":
            return coerce_float(
                value, 1.0,
                minimum=PLAYBACK_SPEED_MIN,
                maximum=PLAYBACK_SPEED_MAX,
            )
        if key == "search_results_count":
            return coerce_int(
                value, 10,
                minimum=SEARCH_RESULTS_MIN,
                maximum=SEARCH_RESULTS_MAX,
            )
        if key == "thumbnail_size":
            return coerce_int(
                value, 160,
                minimum=THUMBNAIL_SIZE_MIN,
                maximum=THUMBNAIL_SIZE_MAX,
            )
        if key == "window_width":
            return coerce_int(value, 900, minimum=WINDOW_MIN, maximum=WINDOW_MAX)
        if key == "window_height":
            return coerce_int(value, 700, minimum=WINDOW_MIN, maximum=WINDOW_MAX)
        if key == "window_x":
            return coerce_int(
                value, 100,
                minimum=WINDOW_POSITION_MIN,
                maximum=WINDOW_POSITION_MAX,
            )
        if key == "window_y":
            return coerce_int(
                value, 100,
                minimum=WINDOW_POSITION_MIN,
                maximum=WINDOW_POSITION_MAX,
            )
        if key == "window_maximized":
            return coerce_bool(value, False)
        return value

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        result = {
            'default_quality': self.default_quality,
            'volume': self.volume,
            'auto_play_next': self.auto_play_next,
            'auto_update_check': self.auto_update_check,
            'theme': self.theme,
            'language': self.language,
            'playback_speed': self.playback_speed,
            'search_results_count': self.search_results_count,
            'thumbnail_size': self.thumbnail_size,
            'window_width': self.window_width,
            'window_height': self.window_height,
            'window_x': self.window_x,
            'window_y': self.window_y,
            'window_maximized': self.window_maximized,
        }
        result.update(
            {
                key: value
                for key, value in copy.deepcopy(self._extra).items()
                if key not in result
            }
        )
        return result

    @classmethod
    def from_dict(cls, data: dict) -> UserSettings:
        if not isinstance(data, dict):
            return cls()

        # ``__version__`` is schema metadata, not a user setting.  ``_extra``
        # is an internal container and must never be treated as an extra key.
        ignored = {"__version__", "_extra"}
        known: dict[str, Any] = {
            k: v for k, v in data.items()
            if k in cls.KNOWN_FIELDS
        }
        extra = {
            k: copy.deepcopy(v) for k, v in data.items()
            if k not in cls.KNOWN_FIELDS and k not in ignored
        }
        obj = cls(**known)
        obj._extra = extra
        return obj

    @classmethod
    def needs_repair(cls, data: object) -> bool:
        """Return ``True`` when persisted *data* differs from canonical form."""
        if not isinstance(data, dict):
            return True
        expected = {
            k: v for k, v in data.items()
            if k not in {"__version__", "_extra"}
        }
        return cls.from_dict(data).to_dict() != expected

    # ------------------------------------------------------------------
    # Mapping-style access
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value by key."""
        if key in self.KNOWN_FIELDS:
            return getattr(self, key)
        return self._extra.get(key, default)

    def set(self, key: str, value: Any):
        """Set a setting value, validating known keys."""
        if key in self.KNOWN_FIELDS:
            setattr(self, key, self.normalize_value(key, value))
        else:
            self._extra[key] = value

    @classmethod
    def defaults(cls) -> UserSettings:
        return cls()
