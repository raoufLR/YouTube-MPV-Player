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
    from core.quality import ResolvedStream

    api = MagicMock()
    api.search_videos.return_value = [
        {
            "videoId": "abc123def45",
            "title": "Test Video",
            "channel": "Test Channel",
            "thumbnail": "http://example.com/thumb.jpg",
        }
    ]
    api.extract_streams.return_value = ResolvedStream(
        video_url="https://example.com/stream",
        audio_url="https://example.com/audio",
        quality="720p",
    )
    api.fetch_video_info.return_value = {
        "videoId": "abc123def45",
        "title": "Test Video",
        "channel": "Test Channel",
        "thumbnail": "http://example.com/thumb.jpg",
    }
    return api


@pytest.fixture
def mock_mpv_player():
    return MagicMock()


@pytest.fixture
def fake_mpv():
    """Deterministic in-memory player used by player/IPC tests."""
    from tests.fakes import FakeMpvPlayer

    return FakeMpvPlayer()


@pytest.fixture
def fake_ytdlp(tmp_path):
    """Placeholder executable path for code that only checks file existence."""
    path = tmp_path / "yt-dlp.exe"
    path.write_bytes(b"MZ")
    return path


@pytest.fixture(scope="session")
def qapp():
    """Provide a single offscreen QApplication for UI smoke tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def profile_factory(temp_dir, event_bus):
    """Create isolated UserManagerService instances under a temporary root."""
    from services.user_manager_service import UserManagerService

    def make(name: str = "Default") -> UserManagerService:
        manager = UserManagerService(base_dir=temp_dir, event_bus=event_bus)
        if name != "Default":
            manager.create_profile(name)
        manager.switch_profile(name)
        return manager

    return make


@pytest.fixture
def user_manager_service(profile_factory):
    return profile_factory("Default")


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
        mpv_player=mock_mpv_player,
        event_bus=event_bus,
        monitor_interval=0,
    )


@pytest.fixture
def playback_service(event_bus, mock_youtube_api, fake_mpv):
    """Real resolver + PlayerService wired through the async PlaybackService."""
    from services.playback_service import PlaybackService
    from services.player_service import PlayerService
    from services.stream_resolver_service import StreamResolverService

    resolver = StreamResolverService(event_bus=event_bus, youtube_api=mock_youtube_api)
    player = PlayerService(mpv_player=fake_mpv, event_bus=event_bus, monitor_interval=0)
    service = PlaybackService(resolver, player, event_bus=event_bus)
    yield service
    service.shutdown()


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
