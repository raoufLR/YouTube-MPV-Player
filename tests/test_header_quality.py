"""Header quality combo and the persisted default stay in sync."""

import pytest

from ui.header_widget import HeaderWidget

pytestmark = pytest.mark.qt


@pytest.fixture
def header(qapp, settings_service, event_bus):
    widget = HeaderWidget(settings_service=settings_service, event_bus=event_bus)
    yield widget
    widget.cleanup()


def test_initial_quality_comes_from_settings(header, settings_service):
    assert header.current_quality() == settings_service.get("default_quality")


def test_combo_change_persists_setting(header, settings_service):
    header._quality_combo.setCurrentText("480p")
    assert settings_service.get("default_quality") == "480p"


def test_settings_change_updates_combo(header, settings_service):
    settings_service.set("default_quality", "360p")
    assert header.current_quality() == "360p"
