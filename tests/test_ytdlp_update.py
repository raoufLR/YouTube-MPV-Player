"""Offline tests for the yt-dlp self-update service.

The network is fully injected through ``FakeBackend``; every safety guard
from the audit has a dedicated test: host allowlist, SHA-256 verification,
size/PE header sanity, atomic install, throttle window, and clean shutdown.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from types import SimpleNamespace

import pytest

from services.ytdlp_update_service import (
    CHECK_INTERVAL,
    SUMS_ASSET,
    GithubReleaseBackend,
    ReleaseInfo,
    YtDlpUpdateService,
    asset_names,
    binary_file_name,
    compare_versions,
    default_install_dir,
    parse_version,
)
from youtube_api import YouTubeAPI

NEW_VERSION = "2026.12.01"
OLD_VERSION = "2026.10.01"
DOWNLOAD_URL = (
    "https://github.com/yt-dlp/yt-dlp/releases/download/"
    f"{NEW_VERSION}/yt-dlp.exe"
)
CHECKSUM_URL = (
    f"https://github.com/yt-dlp/yt-dlp/releases/download/{NEW_VERSION}/yt-dlp.exe.sha256"
)
FAKE_PAYLOAD = b"MZ" + b"\x00yt-dlp-payload" + b"A" * 2048


class FakeBackend:
    """Deterministic release provider — no network involved."""

    def __init__(self, release=None, payload=FAKE_PAYLOAD, sha_fit=True):
        self.release = release
        self.payload = payload
        self.sha_fit = sha_fit
        self.release_calls = 0
        self.download_calls = []
        self.sha_calls = []

    def fetch_latest_release(self):
        self.release_calls += 1
        return self.release

    def download(self, url, dest_path, max_bytes):
        assert max_bytes > 0
        self.download_calls.append((url, dest_path, max_bytes))
        with open(dest_path, "wb") as handle:
            handle.write(self.payload)
        return hashlib.sha256(self.payload).hexdigest()

    def fetch_sha256(self, url, asset_name=""):
        self.sha_calls.append(url)
        digest = hashlib.sha256(self.payload).hexdigest()
        return digest if self.sha_fit else ("f" * 64)


def _make_release(version=NEW_VERSION, url=DOWNLOAD_URL, sha_url=CHECKSUM_URL):
    return ReleaseInfo(
        version=version,
        url=url,
        sha256_url=sha_url,
        size=len(FAKE_PAYLOAD),
    )


def _make_service(temp_dir, backend, event_bus=None, **kwargs):
    defaults = dict(
        version_probe=lambda path: OLD_VERSION,
        check_interval=CHECK_INTERVAL,
    )
    defaults.update(kwargs)
    return YtDlpUpdateService(
        backend=backend,
        event_bus=event_bus,
        data_dir=str(temp_dir),
        **defaults,
    )


def _collect(event_bus, const):
    seen = []
    event_bus.subscribe(const, seen.append, weak=False)
    return seen


# ---------------------------------------------------------------------------
# Version handling
# ---------------------------------------------------------------------------

def test_parse_version_is_numeric_tuple():
    assert parse_version("2026.10.19") == (2026, 10, 19)
    assert parse_version("v2026.10.19") == (2026, 10, 19)
    assert parse_version("2026.10.19.073142") == (2026, 10, 19, 73142)
    assert parse_version("garbage") == (0,)
    assert parse_version("") == (0,)
    assert parse_version(None) == (0,)


def test_compare_versions_orders_release_labels():
    assert compare_versions(OLD_VERSION, NEW_VERSION) == 1
    assert compare_versions(NEW_VERSION, OLD_VERSION) == -1
    assert compare_versions(NEW_VERSION, NEW_VERSION) == 0
    # Optional fourth segment (nightlies) counts.
    assert compare_versions("2026.12.01", "2026.12.01.2") == 1
    # A broken label never outranks a valid one.
    assert compare_versions(OLD_VERSION, "broken") == -1


def test_asset_names_follow_platform(monkeypatch):
    import services.ytdlp_update_service as module

    monkeypatch.setattr(module.sys, "platform", "win32")
    assert asset_names() == ("yt-dlp.exe", "yt-dlp.exe.sha256")
    assert binary_file_name() == "yt-dlp.exe"

    monkeypatch.setattr(module.sys, "platform", "linux")
    assert asset_names() == ("yt-dlp", "yt-dlp.sha256")
    assert binary_file_name() == "yt-dlp"


class _FakeResponse:
    def __init__(self, *, json_payload=None, text=""):
        self._json = json_payload
        self.text = text

    def raise_for_status(self):
        return None

    def json(self):
        return self._json


def test_release_falls_back_to_combined_checksums(monkeypatch):
    binary, _ = asset_names()
    sums_url = (
        "https://github.com/yt-dlp/yt-dlp/releases/download/"
        f"{NEW_VERSION}/{SUMS_ASSET}"
    )
    payload = {
        "tag_name": NEW_VERSION,
        "assets": [
            {
                "name": binary,
                "browser_download_url": DOWNLOAD_URL,
                "size": len(FAKE_PAYLOAD),
            },
            {"name": SUMS_ASSET, "browser_download_url": sums_url},
        ],
    }
    monkeypatch.setattr(
        "services.ytdlp_update_service.requests.get",
        lambda *args, **kwargs: _FakeResponse(json_payload=payload),
    )

    release = GithubReleaseBackend().fetch_latest_release()

    assert release is not None
    assert release.sha256_url == sums_url
    assert release.checksum_asset == binary


def test_combined_checksum_selects_the_matching_asset(monkeypatch):
    body = (
        f"{'a' * 64}  yt-dlp\n"
        f"{'b' * 64}  yt-dlp.exe\n"
    )
    monkeypatch.setattr(
        "services.ytdlp_update_service.requests.get",
        lambda *args, **kwargs: _FakeResponse(text=body),
    )
    backend = GithubReleaseBackend()

    assert backend.fetch_sha256("https://github.com/checksums", "yt-dlp.exe") == "b" * 64
    assert backend.fetch_sha256("https://github.com/checksums") == "a" * 64
    with pytest.raises(ValueError):
        backend.fetch_sha256("https://github.com/checksums", "missing.exe")


# ---------------------------------------------------------------------------
# Binary preference order
# ---------------------------------------------------------------------------

def test_locate_prefers_installed_update_over_bundled(tmp_path):
    installed = tmp_path / "yt-dlp.exe"
    installed.write_bytes(b"MZ")

    assert YouTubeAPI._find_ytdlp(str(installed)) == str(installed)

    # Missing preferred file falls back to the regular resolution order.
    missing = str(tmp_path / "nope.exe")
    assert YouTubeAPI._find_ytdlp(missing) != missing


# ---------------------------------------------------------------------------
# Check flow
# ---------------------------------------------------------------------------

def test_check_detects_newer_release_and_publishes_event(temp_dir, event_bus):
    backend = FakeBackend(release=_make_release())
    service = _make_service(temp_dir, backend, event_bus=event_bus)
    available = _collect(event_bus, "update_available")

    pending = service.check()

    assert pending is not None and pending.version == NEW_VERSION
    assert backend.release_calls == 1
    assert available and available[0].latest_version == NEW_VERSION
    assert available[0].current_version == OLD_VERSION

    state = json.loads(service.state_json())
    assert state["latest_seen_version"] == NEW_VERSION


def test_check_throttled_by_state_window(temp_dir):
    backend = FakeBackend(release=_make_release())
    service = _make_service(temp_dir, backend)
    service.check()

    # A fresh instance reads the same state file and must not re-fetch.
    second = _make_service(temp_dir, FakeBackend(release=_make_release()))
    assert second.check() is None
    assert second._backend.release_calls == 0


def test_check_offline_publishes_failure_and_backs_off(temp_dir, event_bus):
    backend = FakeBackend(release=None)
    service = _make_service(temp_dir, backend, event_bus=event_bus)
    failures = _collect(event_bus, "update_failed")

    assert service.check() is None
    assert failures and failures[0].stage == "check"
    # Failed lookups retry sooner: last_check is pushed back, not to now.
    state = json.loads(service.state_json())
    assert state["latest_seen_version"] == ""
    assert service._check_interval * 0.5 < time.time() - state["last_check"]


def test_check_reports_up_to_date_without_install(temp_dir, event_bus):
    backend = FakeBackend(release=_make_release(version=OLD_VERSION))
    service = _make_service(temp_dir, backend, event_bus=event_bus)
    up_to_date = _collect(event_bus, "update_up_to_date")

    assert service.check() is None
    assert up_to_date and up_to_date[0].version == OLD_VERSION


# ---------------------------------------------------------------------------
# Apply flow
# ---------------------------------------------------------------------------

def test_apply_update_downloads_verifies_and_installs(temp_dir, event_bus):
    backend = FakeBackend(release=_make_release())
    service = _make_service(temp_dir, backend, event_bus=event_bus)
    completed = _collect(event_bus, "update_completed")

    assert service.check() is not None
    assert service.apply_update() is True

    assert service.is_installed
    with open(service.binary_path, "rb") as handle:
        assert handle.read() == FAKE_PAYLOAD
    assert completed and completed[0].version == NEW_VERSION

    state = json.loads(service.state_json())
    assert state["installed_version"] == NEW_VERSION

    staged = os.path.join(default_install_dir(str(temp_dir)), f".{NEW_VERSION}.download")
    assert not os.path.exists(staged)


def test_apply_update_rejects_checksum_mismatch(temp_dir, event_bus):
    backend = FakeBackend(release=_make_release(), sha_fit=False)
    service = _make_service(temp_dir, backend, event_bus=event_bus)
    failures = _collect(event_bus, "update_failed")

    service.check()
    assert service.apply_update() is False
    assert not service.is_installed
    assert failures and failures[-1].stage == "install"

    state = json.loads(service.state_json())
    assert state["installed_version"] == ""


def test_apply_update_rejects_disallowed_host(temp_dir, event_bus):
    backend = FakeBackend(release=_make_release(url="http://127.0.0.1/yt-dlp.exe"))
    service = _make_service(temp_dir, backend, event_bus=event_bus)

    service.check(force=True)
    assert service.apply_update() is False
    assert backend.download_calls == []
    assert not service.is_installed


def test_apply_update_rejects_non_executable_payload(temp_dir, event_bus):
    # Checksum matches, but the payload lacks the MZ header — refused.
    backend = FakeBackend(release=_make_release(), payload=b"plain text junk")
    service = _make_service(temp_dir, backend, event_bus=event_bus)
    failures = _collect(event_bus, "update_failed")

    service.check()
    assert service.apply_update() is False
    assert backend.download_calls and not service.is_installed
    assert any(f.stage == "install" for f in failures)


def test_apply_update_without_pending_release_is_noop(temp_dir):
    backend = FakeBackend(release=None)
    service = _make_service(temp_dir, backend)
    assert service.apply_update() is False
    assert not service.is_installed


# ---------------------------------------------------------------------------
# Background worker + lifecycle
# ---------------------------------------------------------------------------

def test_check_in_background_installs_and_completes(temp_dir, event_bus):
    backend = FakeBackend(release=_make_release())
    service = _make_service(temp_dir, backend, event_bus=event_bus)
    completed = _collect(event_bus, "update_completed")

    service.check_in_background(force=True)
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if completed:
            break
        time.sleep(0.01)
    service.shutdown()

    assert completed and completed[0].version == NEW_VERSION
    assert service.is_installed


def test_auto_check_disabled_via_settings(temp_dir):
    settings = SimpleNamespace(get=lambda name, default=None: False)
    backend = FakeBackend(release=_make_release())
    service = _make_service(temp_dir, backend, settings_service=settings)

    assert service.auto_check_enabled() is False
    # The automatic startup path must be suppressed…
    service.check_in_background()
    time.sleep(0.2)
    assert service._backend.release_calls == 0
    # …but the user forcing a check from the UI still works.
    service.check_in_background(force=True)
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and service._backend.release_calls < 1:
        time.sleep(0.01)
    service.shutdown()
    assert service._backend.release_calls >= 1


def test_shutdown_is_idempotent(temp_dir):
    service = _make_service(temp_dir, FakeBackend(release=_make_release()))
    service.shutdown()
    service.shutdown()
    assert not (service._thread is not None and service._thread.is_alive())


def test_state_survives_reload(temp_dir):
    backend = FakeBackend(release=_make_release())
    service = _make_service(temp_dir, backend)
    service.check()

    state_path = os.path.join(default_install_dir(str(temp_dir)), "update_state.json")
    with open(state_path, encoding="utf-8") as handle:
        restored = json.load(handle)

    assert restored["latest_seen_version"] == NEW_VERSION
    assert 0 < restored["last_check"] <= time.time()
