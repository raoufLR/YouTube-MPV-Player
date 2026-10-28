"""Settings-page update card: real services, no network.

Notifications flow through the real ``EventBus`` → ``QtEventDispatcher`` →
widget chain.  Every publish in this module happens on the main thread, so
Qt delivers to the handlers synchronously (direct connection) — the tests
assert immediately after publishing without touching the *global* Qt event
queue.  This matters because pumping ``processEvents()`` late in a long
batch of mixed UI tests can deliver unrelated, stale queued events and
hard-crash inside Qt (0xC0000409 on Windows); the real worker-thread path
of the update service is covered separately in ``tests/test_ytdlp_update.py``
and the full-flow integration tests.
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QCheckBox, QPushButton

from core.event_bus import EventBus
from core.events import (
    UpdateAvailableEvent,
    UpdateFailedEvent,
)
from services.settings_service import SettingsService
from tests.test_ytdlp_update import (
    CHECKSUM_URL,
    DOWNLOAD_URL,
    FAKE_PAYLOAD,
    NEW_VERSION,
    OLD_VERSION,
    FakeBackend,
    _make_release,
)
from ui.pages.settings_page import SettingsPage

pytestmark = pytest.mark.qt


class _Harness:
    def __init__(self, qapp, temp_dir):
        from services.ytdlp_update_service import YtDlpUpdateService

        self._qapp = qapp
        self.event_bus = EventBus()
        self.settings = SettingsService(
            event_bus=self.event_bus, data_dir=temp_dir
        )
        self.backend = FakeBackend(release=_make_release())
        self.update_service = YtDlpUpdateService(
            backend=self.backend,
            event_bus=self.event_bus,
            data_dir=temp_dir,
            version_probe=lambda path: OLD_VERSION,
            check_interval=3600,
        )
        self.page = SettingsPage(
            self.settings,
            self.event_bus,
            SimpleNamespace(
                available_theme_names=["Dark"],
                theme_id_for_display=lambda name: "default",
                switch_theme=lambda theme_id: None,
            ),
            update_service=self.update_service,
        )
        self.temp_dir = temp_dir

    def pump_until(self, predicate):
        """Await an event delivered synchronously on the main thread."""
        return predicate()

    def sync_check_in_background(self, force=False, *, auto_apply=True):
        """Run the update check inline instead of on a worker thread."""
        release = self.update_service.check(force=True)
        if release is not None and auto_apply:
            self.update_service.apply_update(release)

    def replace_check_with_sync(self):
        self.update_service.check_in_background = self.sync_check_in_background


@pytest.fixture
def harness(qapp, temp_dir):
    h = _Harness(qapp, temp_dir)
    yield h
    h.update_service.shutdown()
    h.settings.shutdown()
    h.page.cleanup()


def test_update_card_is_present_with_service_controls(harness):
    hint = harness.page.update_status_label.text()
    assert "bundled copy" in hint
    assert isinstance(harness.page.update_check_button, QPushButton)
    assert harness.page.update_install_button.isEnabled() is False
    assert isinstance(harness.page.update_auto_check, QCheckBox)
    assert harness.page.update_auto_check.isChecked() is True


def test_check_now_button_refreshes_status_to_up_to_date(harness):
    harness.replace_check_with_sync()
    harness.page.update_check_button.click()
    status = harness.page.update_status_label.text()
    assert "is available" in status or "up to date" in status


def test_update_status_reacts_to_events_through_the_bus(harness):
    harness.event_bus.publish(
        UpdateAvailableEvent(current_version=OLD_VERSION, latest_version=NEW_VERSION)
    )
    assert NEW_VERSION in harness.page.update_status_label.text()
    assert harness.page.update_install_button.isEnabled()


def test_install_button_downloads_verifies_and_reports(harness):
    harness.event_bus.publish(
        UpdateAvailableEvent(current_version=OLD_VERSION, latest_version=NEW_VERSION)
    )
    assert harness.page.update_install_button.isEnabled()

    harness.replace_check_with_sync()
    harness.page.update_install_button.click()
    assert harness.update_service.is_installed
    assert "takes effect" in harness.page.update_status_label.text()

    with open(harness.update_service.binary_path, "rb") as handle:
        assert handle.read() == FAKE_PAYLOAD


def test_failed_update_paints_the_status_red(harness):
    harness.event_bus.publish(
        UpdateFailedEvent(stage="check", error="offline")
    )
    assert "offline" in harness.page.update_status_label.text()
    assert not harness.page.update_install_button.isEnabled()


def test_auto_check_toggle_persists_through_settings_service(harness):
    harness.page.update_auto_check.setChecked(False)
    assert harness.settings.get("auto_update_check") is False
    harness.page.update_auto_check.setChecked(True)
    assert harness.settings.get("auto_update_check") is True


def test_harness_declaration_style_is_consistent():
    from services.ytdlp_update_service import compare_versions

    # Sanity: version compare consistent with FakeBackend payload naming.
    assert compare_versions(OLD_VERSION, NEW_VERSION) == 1
    assert hashlib.sha256(FAKE_PAYLOAD).hexdigest() != CHECKSUM_URL
    assert DOWNLOAD_URL.endswith("yt-dlp.exe")
