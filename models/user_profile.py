"""
User Profile Model
==================

Represents a local user profile. The user_id field enables future
multi-user support while defaulting to "default" for single-user mode.
"""

import time
from dataclasses import dataclass, field


@dataclass
class UserProfile:
    """Represents a local user profile"""
    user_id: str = "default"
    username: str = "User"
    display_name: str = "User"
    avatar_path: str = "User/avatar.png"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

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
    def from_dict(cls, data: dict) -> 'UserProfile':
        if not data:
            return cls()
        return cls(
            user_id=data.get('user_id', 'default'),
            username=data.get('username', 'User'),
            display_name=data.get('display_name', 'User'),
            avatar_path=data.get('avatar_path', 'User/avatar.png'),
            created_at=data.get('created_at', time.time()),
            updated_at=data.get('updated_at', time.time()),
        )
