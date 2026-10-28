"""Application profile switching reports success to the UI."""

from unittest.mock import MagicMock

from app.application import Application


def _application_with_services(switch_result):
    application = Application()
    user_manager = MagicMock()
    user_manager.switch_profile.return_value = switch_result
    user_manager.current_profile_dir.return_value = "profile-dir"
    playback = MagicMock()

    application._container._services = {
        "user_manager_service": user_manager,
        "playback_service": playback,
    }
    reload_services = MagicMock()
    application._container.reload_profile_services = reload_services
    return application, user_manager, playback, reload_services


def test_successful_switch_stops_playback_and_reloads_services():
    application, user_manager, playback, reload_services = (
        _application_with_services(object())
    )

    assert application.load_profile("Alice") is True
    user_manager.switch_profile.assert_called_once_with("Alice")
    playback.stop.assert_called_once()
    reload_services.assert_called_once_with("profile-dir")


def test_failed_switch_returns_false_and_keeps_services_unchanged():
    application, user_manager, playback, reload_services = (
        _application_with_services(None)
    )

    assert application.load_profile("Missing") is False
    assert application.switch_profile("Missing") is False
    # Both attempts stop any current playback before validating the profile.
    assert playback.stop.call_count == 2
    reload_services.assert_not_called()


def test_missing_user_manager_returns_false():
    application = Application()
    application._container._services = {}
    assert application.load_profile("Alice") is False
    assert application.switch_profile("Alice") is False
