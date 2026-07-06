import pytest

from core.events import SettingsChangedEvent


class TestSettingsService:
    def test_get_default_value(self, settings_service):
        val = settings_service.get("default_quality")
        assert val == "720p"

    def test_set_and_get(self, settings_service, event_bus):
        events = []
        event_bus.subscribe("settings_changed", events.append, weak=False)
        settings_service.set("volume", 55)
        assert settings_service.get("volume") == 55
        assert len(events) == 1
        assert isinstance(events[0], SettingsChangedEvent)
        assert events[0].key == "volume"
        assert events[0].value == 55

    def test_get_with_default(self, settings_service):
        val = settings_service.get("nonexistent", "fallback")
        assert val == "fallback"

    def test_get_all(self, settings_service):
        settings_service.set("volume", 50)
        settings_service.set("theme", "light")
        all_settings = settings_service.get_all()
        assert all_settings["volume"] == 50
        assert all_settings["theme"] == "light"
        assert all_settings["default_quality"] == "720p"

    def test_update_multiple(self, settings_service, event_bus):
        events = []
        event_bus.subscribe("settings_changed", events.append, weak=False)
        settings_service.update({"volume": 30, "theme": "light"})
        assert settings_service.get("volume") == 30
        assert settings_service.get("theme") == "light"
        assert len(events) == 2

    def test_get_model(self, settings_service):
        settings_service.set("volume", 42)
        model = settings_service.get_model()
        assert model.volume == 42
        assert model.default_quality == "720p"

    def test_reset(self, settings_service, event_bus):
        settings_service.set("volume", 99)
        events = []
        event_bus.subscribe("settings_changed", events.append, weak=False)
        settings_service.reset()
        assert settings_service.get("volume") == 80
        assert len(events) == 1
        assert events[0].key == "__reset__"

    def test_export(self, settings_service):
        settings_service.set("volume", 77)
        data = settings_service.export()
        assert data["volume"] == 77
        assert data["default_quality"] == "720p"

    def test_extra_keys(self, settings_service, event_bus):
        events = []
        event_bus.subscribe("settings_changed", events.append, weak=False)
        settings_service.set("custom_key", "custom_value")
        assert settings_service.get("custom_key") == "custom_value"
        assert len(events) == 1

    def test_import_data(self, settings_service):
        settings_service.import_data({"volume": 10, "theme": "light"})
        assert settings_service.get("volume") == 10
        assert settings_service.get("theme") == "light"
