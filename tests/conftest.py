import logging
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from core.event_bus import EventBus


# ---------------------------------------------------------------------------
# Disable logging noise during tests
# ---------------------------------------------------------------------------
logging.disable(logging.CRITICAL)


# ---------------------------------------------------------------------------
# Core fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


# ---------------------------------------------------------------------------
# Mock external dependencies
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_youtube_api():
    api = MagicMock()
    api.search_videos.return_value = [
        {
            "videoId": "abc123def45",
            "title": "Test Video",
            "channel": "Test Channel",
            "thumbnail": "http://example.com/thumb.jpg",
        }
    ]
    api.extract_stream_url.return_value = "https://example.com/stream"
    return api


@pytest.fixture
def mock_mpv_player():
    return MagicMock()


# ---------------------------------------------------------------------------
# Service fixtures without background threads
# ---------------------------------------------------------------------------

@pytest.fixture
def search_service(event_bus, mock_youtube_api):
    from services.search_service import SearchService
    return SearchService(youtube_api=mock_youtube_api, event_bus=event_bus)


@pytest.fixture
def stream_resolver_service(event_bus):
    from services.stream_resolver_service import StreamResolverService
    return StreamResolverService(event_bus=event_bus)


@pytest.fixture
def player_service(event_bus, mock_mpv_player):
    from services.player_service import PlayerService
    return PlayerService(
        mpv_player=mock_mpv_player, event_bus=event_bus
    )


@pytest.fixture
def playlist_service(event_bus, temp_dir):
    from services.playlist_service import PlaylistService
    return PlaylistService(
        event_bus=event_bus, data_dir=temp_dir
    )


@pytest.fixture
def likes_service(event_bus, temp_dir):
    from services.likes_service import LikesService
    return LikesService(
        event_bus=event_bus, data_dir=temp_dir, filename="likes.json"
    )


@pytest.fixture
def history_service(event_bus, temp_dir):
    from services.history_service import HistoryService

    with patch.object(
        HistoryService, "_start_flush_thread", lambda self: None
    ):
        svc = HistoryService(
            event_bus=event_bus,
            data_dir=temp_dir,
            filename="history.json",
        )
        svc._running = False
        svc._flush_thread = None
        yield svc
        svc._running = False


@pytest.fixture
def settings_service(event_bus, temp_dir):
    from services.settings_service import SettingsService

    with patch.object(
        SettingsService, "_start_flush_thread", lambda self: None
    ):
        svc = SettingsService(
            event_bus=event_bus,
            data_dir=temp_dir,
            filename="settings.json",
        )
        svc._running = False
        svc._flush_thread = None
        yield svc
        svc._running = False
