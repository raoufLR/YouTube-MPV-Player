"""
Models Package
==============

Data models for the application. Each model is a plain data class
with serialization support for JSON persistence.

Models are designed for single-user with future multi-user support
via a user_id field on UserProfile.
"""

from .playlist import Playlist, PlaylistVideo
from .profile import Profile
from .user_profile import UserProfile
from .user_settings import UserSettings

__all__ = ['UserProfile', 'Playlist', 'PlaylistVideo', 'UserSettings', 'Profile']
