"""Application bootstrap and shutdown smoke tests."""

import os

REQUIRED_SERVICES = (
    "logging_service",
    "user_manager_service",
    "settings_service",
    "analytics_service",
    "player_service",
    "stream_resolver_service",
    "playback_service",
    "search_service",
    "thumbnail_service",
    "user_profile_service",
    "history_service",
    "likes_service",
    "playlist_service",
    "recommendation_service",
)


def _shorten_flush_intervals(monkeypatch):
    """Keep shutdown tests fast without changing production code."""
    monkeypatch.setattr("services.settings_service.FLUSH_INTERVAL", 0.01)
    monkeypatch.setattr("services.history_service.FLUSH_INTERVAL", 0.01)


def test_application_bootstrap_and_shutdown(temp_dir, monkeypatch):
    monkeypatch.chdir(temp_dir)
    _shorten_flush_intervals(monkeypatch)

    from app import Application

    application = Application()
    application.startup()

    try:
        assert application.is_running()
        assert application.event_bus is not None

        for name in REQUIRED_SERVICES:
            assert getattr(application.services, name) is not None, name

        user_manager = application.services.user_manager_service
        assert user_manager.profile_count() >= 1
        profile_dir = user_manager.current_profile_dir()
        assert os.path.isdir(profile_dir)
        # Profile directories use opaque IDs, never display names.
        assert os.path.basename(profile_dir) != "Default"
        assert os.path.dirname(os.path.abspath(profile_dir)) == os.path.join(
            os.path.abspath(temp_dir), "User", "profiles"
        )
        assert application.services.history_service.count() == 0
    finally:
        application.shutdown()
        # Shutdown must be safe to call more than once.
        application.shutdown()

    assert not application.is_running()
    assert application.services.settings_service is None


def test_application_profile_delete_and_data_bundle(temp_dir, monkeypatch):
    monkeypatch.chdir(temp_dir)
    _shorten_flush_intervals(monkeypatch)

    from app import Application

    application = Application()
    application.startup()

    try:
        services = application.services
        services.settings_service.set("volume", 55)
        services.history_service.add({"id": "v1", "title": "One"})
        services.likes_service.like({"videoId": "v1", "title": "One"})
        playlist = services.playlist_service.create_playlist("Mine")
        services.playlist_service.add_video(playlist.id, {"videoId": "v1"})
        services.user_profile_service.update_profile(username="alice")

        bundle = application.export_data()
        assert bundle["schema_version"] == application.data_schema_version()
        assert bundle["data"]["settings"]["volume"] == 55
        assert bundle["data"]["history"][0]["id"] == "v1"

        services.settings_service.reset()
        services.history_service.clear()
        services.likes_service.reset()
        services.playlist_service.reset()
        services.user_profile_service.reset()

        assert application.import_data(bundle) is True
        assert services.settings_service.get("volume") == 55
        assert services.history_service.contains("v1")
        assert services.likes_service.is_liked("v1")
        assert any(
            item.name == "Mine"
            for item in services.playlist_service.get_all_playlists()
        )
        assert services.user_profile_service.get_profile().username == "alice"

        assert application.import_data({"schema_version": 999, "data": {}}) is False

        assert application.create_profile("Alice") is not None
        application.load_profile("Alice")
        assert services.user_manager_service.current_profile_name() == "Alice"

        # The composition root switches to Default before deleting the
        # active profile, so services never point at a removed directory.
        assert application.delete_profile("Alice") is True
        assert services.user_manager_service.current_profile_name() == "Default"
        assert services.user_manager_service.has_profile("Alice") is False
    finally:
        application.shutdown()

