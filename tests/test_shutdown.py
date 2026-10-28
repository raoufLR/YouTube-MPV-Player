import os

from app import Application
from core.events import SearchStartedEvent
from services.player_service import PlayerService
from tests.fakes import FakeMpvPlayer


def test_application_shutdown_stops_playback_threads_and_subscribers(
    temp_dir, monkeypatch
):
    monkeypatch.chdir(temp_dir)
    monkeypatch.setattr("services.settings_service.FLUSH_INTERVAL", 0.01)
    monkeypatch.setattr("services.history_service.FLUSH_INTERVAL", 0.01)

    application = Application()
    application.startup()

    player_service = application.services.player_service
    fake_player = FakeMpvPlayer()
    player_service.player = fake_player
    fake_player.play("https://example.com/stream", "720p")
    assert fake_player.process is not None

    settings_service = application.services.settings_service
    history_service = application.services.history_service
    delivered = []
    application.event_bus.subscribe(
        "search_started", delivered.append, weak=False
    )

    application.shutdown()

    assert fake_player.stopped == 1
    assert fake_player.process is None
    assert application.is_running() is False
    assert application.services.settings_service is None
    assert not application.event_bus.has_listeners("search_started")
    assert settings_service._flush_thread is None
    assert history_service._flush_thread is None
    assert settings_service._running is False
    assert history_service._running is False
    assert os.path.isdir(os.path.join(temp_dir, "User", "profiles"))

    # Publishing after shutdown is harmless and reaches nobody.
    application.event_bus.publish(SearchStartedEvent(query="after"))
    assert delivered == []

    # Repeated shutdown must not raise or restart anything.
    application.shutdown()


def test_player_service_shutdown_is_idempotent():
    fake_player = FakeMpvPlayer()
    service = PlayerService(mpv_player=fake_player)
    fake_player.play("https://example.com/stream", "720p")

    service.shutdown()
    service.shutdown()

    assert fake_player.stopped == 1
    assert service.is_playing is False
