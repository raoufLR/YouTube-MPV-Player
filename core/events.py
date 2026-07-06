"""
Event Definitions
=================

Strongly typed events for all application activities. Each event contains relevant data
and includes a timestamp for debugging and auditing purposes.

Events are published by service or UI components and subscribed to by interested components.
This enables event-driven architecture where components communicate through events rather
than direct method calls.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ApplicationEvent:
    """Base class for all events"""
    timestamp: float = field(default_factory=time.time)
    event_type: str = ""


@dataclass
class SearchStartedEvent(ApplicationEvent):
    event_type: str = "search_started"
    query: str = ""


@dataclass
class SearchCompletedEvent(ApplicationEvent):
    event_type: str = "search_completed"
    videos: list = None


@dataclass
class SearchFailedEvent(ApplicationEvent):
    event_type: str = "search_failed"
    error: str = ""


@dataclass
class ThumbnailLoadedEvent(ApplicationEvent):
    event_type: str = "thumbnail_loaded"
    item: Any = None
    icon: Any = None


@dataclass
class ThumbnailFailedEvent(ApplicationEvent):
    event_type: str = "thumbnail_failed"
    item: Any = None
    error: str = ""


@dataclass
class StreamResolvingEvent(ApplicationEvent):
    event_type: str = "stream_resolving"
    video_id: str = ""
    quality: str = ""


@dataclass
class StreamResolvedEvent(ApplicationEvent):
    event_type: str = "stream_resolved"
    video_id: str = ""
    url: str = ""
    quality: str = ""


@dataclass
class SearchCancelledEvent(ApplicationEvent):
    event_type: str = "search_cancelled"
    query: str = ""


@dataclass
class LikeChangedEvent(ApplicationEvent):
    event_type: str = "like_changed"
    video_id: str = ""
    is_liked: bool = False


@dataclass
class SettingsChangedEvent(ApplicationEvent):
    event_type: str = "settings_changed"
    key: str = ""
    value: Any = None


@dataclass
class VideoStartedEvent(ApplicationEvent):
    event_type: str = "video_started"
    url: str = ""
    quality: str = ""
    video_data: dict = None
    video_id: str = ""
    title: str = ""
    channel: str = ""
    thumbnail: str = ""


@dataclass
class VideoPausedEvent(ApplicationEvent):
    event_type: str = "video_paused"


@dataclass
class VideoStoppedEvent(ApplicationEvent):
    event_type: str = "video_stopped"


@dataclass
class PlaybackErrorEvent(ApplicationEvent):
    event_type: str = "playback_error"
    error: str = ""


@dataclass
class ApplicationStartedEvent(ApplicationEvent):
    event_type: str = "application_started"


@dataclass
class ApplicationClosingEvent(ApplicationEvent):
    event_type: str = "application_closing"


@dataclass
class HistoryUpdatedEvent(ApplicationEvent):
    event_type: str = "history_updated"
    action: str = ""
    video_id: str = ""


@dataclass
class PlaylistCreatedEvent(ApplicationEvent):
    event_type: str = "playlist_created"
    playlist_id: str = ""
    playlist_name: str = ""


@dataclass
class PlaylistUpdatedEvent(ApplicationEvent):
    event_type: str = "playlist_updated"
    playlist_id: str = ""
    action: str = ""


@dataclass
class PlaylistDeletedEvent(ApplicationEvent):
    event_type: str = "playlist_deleted"
    playlist_id: str = ""
    playlist_name: str = ""


@dataclass
class WatchLaterToggledEvent(ApplicationEvent):
    event_type: str = "watch_later_toggled"
    video_id: str = ""
    is_watch_later: bool = False


@dataclass
class ProfileLoadedEvent(ApplicationEvent):
    event_type: str = "profile_loaded"
    profile_name: str = ""


@dataclass
class ProfileChangedEvent(ApplicationEvent):
    event_type: str = "profile_changed"
    profile_name: str = ""


@dataclass
class ProfileCreatedEvent(ApplicationEvent):
    event_type: str = "profile_created"
    profile_name: str = ""


@dataclass
class ProfileDeletedEvent(ApplicationEvent):
    event_type: str = "profile_deleted"
    profile_name: str = ""


@dataclass
class RecommendationsLoadingEvent(ApplicationEvent):
    event_type: str = "recommendations_loading"
    section: str = ""


@dataclass
class RecommendationsLoadedEvent(ApplicationEvent):
    event_type: str = "recommendations_loaded"
    section: str = ""
    videos: list = None


@dataclass
class RecommendationsFailedEvent(ApplicationEvent):
    event_type: str = "recommendations_failed"
    section: str = ""
    error: str = ""


# Event type constants for direct reference
EVENT_STREAM_RESOLVING = "stream_resolving"
EVENT_STREAM_RESOLVED = "stream_resolved"
EVENT_THUMBNAIL_LOADED = "thumbnail_loaded"
EVENT_VIDEO_STARTED = "video_started"
EVENT_PLAYBACK_ERROR = "playback_error"
EVENT_HISTORY_UPDATED = "history_updated"
EVENT_LIKE_CHANGED = "like_changed"
EVENT_SETTINGS_CHANGED = "settings_changed"
EVENT_PLAYLIST_CREATED = "playlist_created"
EVENT_PLAYLIST_UPDATED = "playlist_updated"
EVENT_PLAYLIST_DELETED = "playlist_deleted"
EVENT_WATCH_LATER_TOGGLED = "watch_later_toggled"
EVENT_PROFILE_LOADED = "profile_loaded"
EVENT_PROFILE_CHANGED = "profile_changed"
EVENT_PROFILE_CREATED = "profile_created"
EVENT_PROFILE_DELETED = "profile_deleted"
EVENT_RECOMMENDATIONS_LOADING = "recommendations_loading"
EVENT_RECOMMENDATIONS_LOADED = "recommendations_loaded"
EVENT_RECOMMENDATIONS_FAILED = "recommendations_failed"
