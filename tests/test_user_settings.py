"""User settings: window maximized flag validation."""

from models.user_settings import UserSettings


def test_window_maximized_defaults_to_false():
    settings = UserSettings.defaults()
    assert settings.window_maximized is False
    assert settings.get("window_maximized") is False
    assert settings.to_dict()["window_maximized"] is False


def test_window_maximized_is_coerced():
    assert UserSettings.from_dict({"window_maximized": True}).window_maximized is True
    assert UserSettings.from_dict({"window_maximized": "yes"}).window_maximized is True
    assert UserSettings.from_dict({"window_maximized": 1}).window_maximized is True
    assert UserSettings.from_dict({"window_maximized": 0}).window_maximized is False


def test_invalid_window_maximized_falls_back_to_false():
    settings = UserSettings.from_dict({"window_maximized": "not-a-bool"})
    assert settings.window_maximized is False


def test_set_validates_window_maximized():
    settings = UserSettings()
    settings.set("window_maximized", "true")
    assert settings.window_maximized is True
    settings.set("window_maximized", 42)
    assert settings.window_maximized is False


def test_missing_window_maximized_needs_repair():
    data = UserSettings.defaults().to_dict()
    data.pop("window_maximized")
    assert UserSettings.needs_repair(data) is True

    repaired = UserSettings.defaults().to_dict()
    assert UserSettings.needs_repair(repaired) is False
