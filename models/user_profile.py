"""
User Profile Model
==================

Represents a local user profile. The user_id field enables future
multi-user support while defaulting to "default" for single-user mode.
"""

import time
from dataclasses import dataclass, field

from core.security import sanitize_local_path
from core.validation import coerce_text, coerce_timestamp

DEFAULT_AVATAR_PATH = "User/avatar.png"
MAX_USER_ID = 64
MAX_USERNAME = 64
MAX_DISPLAY_NAME = 128
MAX_AVATAR_PATH = 2048


@dataclass
class UserProfile:
    """Represents a local user profile"""
    user_id: str = "default"
    username: str = "User"
    display_name: str = "User"
    avatar_path: str = DEFAULT_AVATAR_PATH
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def __post_init__(self):
        self.user_id = (
            coerce_text(self.user_id, "default", max_length=MAX_USER_ID)
            or "default"
        )
        self.username = (
            coerce_text(self.username, "User", max_length=MAX_USERNAME) or "User"
        )
        self.display_name = (
            coerce_text(
                self.display_name, "User", max_length=MAX_DISPLAY_NAME
            ) or "User"
        )
        self.avatar_path = sanitize_local_path(
            coerce_text(
                self.avatar_path, DEFAULT_AVATAR_PATH, max_length=MAX_AVATAR_PATH
            ),
            DEFAULT_AVATAR_PATH,
        )
        self.created_at = coerce_timestamp(self.created_at)
        self.updated_at = coerce_timestamp(self.updated_at)

    def to_dict(self) -> dict:
        return {
            'user_id': self.user_id,
            'username': self.username,
            'display_name': self.display_name,
            'avatar_path': self.avatar_path,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> UserProfile:
        if not isinstance(data, dict):
            return cls()
        return cls(
            user_id=data.get('user_id', 'default'),
            username=data.get('username', 'User'),
            display_name=data.get('display_name', 'User'),
            avatar_path=data.get('avatar_path', DEFAULT_AVATAR_PATH),
            created_at=data.get('created_at', time.time()),
            updated_at=data.get('updated_at', time.time()),
        )
