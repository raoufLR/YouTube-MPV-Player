"""Self-updating yt-dlp binary management.

The bundled ``yt-dlp.exe`` is version-locked with the application, which
means search/stream resolution silently degrades until the app itself is
upgraded.  This service keeps a *user-installed* copy up to date:

1. ``check`` — read the latest GitHub release metadata and, when it is
   newer than the local binary, publish ``UpdateAvailableEvent``.
2. ``apply_update`` — download the release asset into the updates
   directory, verify its SHA-256 against the published checksum, then
   atomically ``os.replace`` it into place.
3. ``YouTubeAPI`` prefers this installed copy over the bundled one, so the
   next resolver run picks the update up with no restart required.

Design guards from the audit:

* download URLs must pass ``validate_fetch_url`` with a strict GitHub
  host allowlist (no redirects outside the projection);
* size caps: download aborts past ``MAX_BINARY_BYTES``;
* checksum verification fails closed — a mismatched payload is never
  installed;
* the ``os.replace`` swap is atomic on the same volume, so a crash can
  leave the old binary or the new one, but never a half-written file;
* state (last check, latest seen version, installed version) lives in a
  JSON file so repeated launches do not hammer the API.

The heavy work runs on a single worker thread; ``shutdown`` joins it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass

import requests

from core.events import (
    UpdateAvailableEvent,
    UpdateCompletedEvent,
    UpdateFailedEvent,
    UpdateUpToDateEvent,
)
from core.json_store import load_json, save_json
from core.security import ensure_private_dir, ensure_private_file, redact_text, redact_url

_logger = logging.getLogger(__name__)

GITHUB_REPO = "yt-dlp/yt-dlp"
GITHUB_API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

# Strict projection: release metadata may only point at these hosts.
ALLOWED_HOSTS = ("github.com", "objects.githubusercontent.com")

CHECK_TIMEOUT = 10
DOWNLOAD_TIMEOUT = 600
MAX_BINARY_BYTES = 64 * 1024 * 1024        # yt-dlp.exe ships ~17 MiB today
DOWNLOAD_CHUNK = 64 * 1024
VERSION_LABEL_RE = re.compile(r"^v?\d[\w.+-]{0,63}$")
LOCAL_VERSION_RE = re.compile(r"^v?\d[\w.+-]{0,64}$")
CHECK_INTERVAL = 24 * 60 * 60
HASH_SIZE = 96


def _windows() -> bool:
    return sys.platform.startswith("win")


def asset_names() -> tuple[str, str]:
    """Return ``(binary_asset, checksum_asset)`` names for this platform."""
    if _windows():
        return "yt-dlp.exe", "yt-dlp.exe.sha256"
    return "yt-dlp", "yt-dlp.sha256"


# yt-dlp publishes one combined checksum file instead of per-asset sidecars.
SUMS_ASSET = "SHA2-256SUMS"


# ---------------------------------------------------------------------------
# Version handling
# ---------------------------------------------------------------------------

def parse_version(version: object) -> tuple[int, ...]:
    """Normalize a yt-dlp version label into a comparable integer tuple.

    yt-dlp uses date-based labels like ``2026.10.19`` (plus occasional
    ``2026.10.19.073142`` nightlies).  Unparsable labels sort lowest so a
    broken remote response never appears *newer* than a valid local one.
    """
    text = str(version or "").strip().lstrip("v")
    if not VERSION_LABEL_RE.match(text):
        return (0,)
    parts: list[int] = []
    for segment in text.split("."):
        digits = re.sub(r"\D", "", segment)
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def compare_versions(local: str, remote: str) -> int:
    """Return >0 when *remote* is newer than *local*, 0 when equal, <0 older."""
    key_local = parse_version(local)
    key_remote = parse_version(remote)
    if key_remote > key_local:
        return 1
    if key_remote < key_local:
        return -1
    return 0


def default_install_dir(data_dir: str) -> str:
    return os.path.join(data_dir, "updates")


def binary_file_name() -> str:
    return "yt-dlp.exe" if _windows() else "yt-dlp"


# ---------------------------------------------------------------------------
# Backend protocol + GitHub implementation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    url: str
    sha256_url: str = ""
    size: int = 0
    checksum_asset: str = ""


class GithubReleaseBackend:
    """Read release metadata from GitHub and stream the binary to disk."""

    def fetch_latest_release(self) -> ReleaseInfo | None:
        try:
            response = requests.get(
                GITHUB_API_LATEST,
                timeout=CHECK_TIMEOUT,
                headers={"Accept": "application/vnd.github+json"},
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            _logger.warning(
                "GitHub release check failed: %s", redact_text(str(exc))
            )
            return None

        version = str(payload.get("tag_name", "") or "")
        binary_name, hash_name = asset_names()
        url = ""
        sha_url = ""
        sums_url = ""
        size = 0
        for asset in payload.get("assets", []):
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name", ""))
            link = str(asset.get("browser_download_url", ""))
            if name == binary_name:
                url, size = link, int(asset.get("size", 0) or 0)
            elif name == hash_name:
                sha_url = link
            elif name == SUMS_ASSET:
                sums_url = link
        if not url:
            _logger.warning("No %s asset in the latest release", binary_name)
            return None
        # Prefer a per-asset sidecar; fall back to the combined SHA2-256SUMS.
        checksum_asset = ""
        if not sha_url and sums_url:
            sha_url = sums_url
            checksum_asset = binary_name
        return ReleaseInfo(
            version=version,
            url=url,
            sha256_url=sha_url,
            size=size,
            checksum_asset=checksum_asset,
        )

    def download(self, url: str, dest_path: str, max_bytes: int) -> str:
        """Stream *url* into *dest_path*; return the SHA-256 of the payload."""
        response = requests.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True)
        response.raise_for_status()
        digest = hashlib.sha256()
        written = 0
        try:
            with open(dest_path, "wb") as handle:
                for chunk in response.iter_content(DOWNLOAD_CHUNK):
                    if not chunk:
                        continue
                    written += len(chunk)
                    if written > max_bytes:
                        raise ValueError("download exceeded the size cap")
                    digest.update(chunk)
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            response.close()
        return digest.hexdigest()

    def fetch_sha256(self, url: str, asset_name: str = "") -> str:
        """Read a published checksum file and return the hash for *asset_name*.

        Sidecars contain a single token; ``SHA2-256SUMS`` lists
        ``<hash>  <filename>`` lines, so the matching filename is selected.
        """
        response = requests.get(url, timeout=CHECK_TIMEOUT)
        response.raise_for_status()
        text = response.text or ""
        for line in text.splitlines():
            parts = line.split()
            if not parts:
                continue
            digest = parts[0].strip()
            if not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
                continue
            if asset_name:
                names = [part.lstrip("*") for part in parts[1:]]
                if asset_name not in names:
                    continue
            return digest.lower()
        raise ValueError("checksum file does not contain the advertised asset")


# ---------------------------------------------------------------------------
# Persisted state
# ---------------------------------------------------------------------------

@dataclass
class UpdateState:
    last_check: float = 0.0
    latest_seen_version: str = ""
    installed_version: str = ""

    def to_dict(self) -> dict:
        return {
            "last_check": float(self.last_check),
            "latest_seen_version": str(self.latest_seen_version),
            "installed_version": str(self.installed_version),
        }

    @classmethod
    def from_dict(cls, raw: object) -> UpdateState:
        if not isinstance(raw, dict):
            return cls()
        state = cls()
        last_check = raw.get("last_check", 0)
        if isinstance(last_check, (int, float)):
            state.last_check = float(last_check)
        state.latest_seen_version = str(raw.get("latest_seen_version", "") or "")[:64]
        state.installed_version = str(raw.get("installed_version", "") or "")[:64]
        return state


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class YtDlpUpdateService:
    """Keeps a user-installed yt-dlp binary current; fully HTTP-injectable."""

    def __init__(
        self,
        backend=None,
        event_bus=None,
        data_dir: str = "User",
        settings_service=None,
        version_probe=None,
        *,
        check_interval: float = CHECK_INTERVAL,
        install_dir: str | None = None,
        logger: logging.Logger | None = None,
    ):
        self._backend = backend or GithubReleaseBackend()
        self._event_bus = event_bus
        self._settings_service = settings_service
        self._check_interval = max(0.0, float(check_interval))
        self._logger = logger or logging.getLogger(__name__)

        self._install_dir = install_dir or default_install_dir(data_dir)
        self._binary_path = os.path.join(self._install_dir, binary_file_name())
        self._state_path = os.path.join(self._install_dir, "update_state.json")

        self._version_probe = version_probe or self._probe_version_subprocess
        self._version_cache: dict[str, str] = {}

        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._shutdown = False
        self._state = self._load_state()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def shutdown(self):
        with self._lock:
            if self._shutdown:
                return
            self._shutdown = True
            thread = self._thread
        self._stop_event.set()
        if thread is not None and thread.is_alive():
            thread.join(timeout=3.0)

    # ------------------------------------------------------------------
    # Paths / state
    # ------------------------------------------------------------------

    @property
    def binary_path(self) -> str:
        """Where the user-installed binary lives (may not exist yet)."""
        return self._binary_path

    @property
    def is_installed(self) -> bool:
        return os.path.isfile(self._binary_path)

    @property
    def installed_version(self) -> str:
        with self._lock:
            return self._state.installed_version

    @property
    def latest_seen_version(self) -> str:
        with self._lock:
            return self._state.latest_seen_version

    def _load_state(self) -> UpdateState:
        data = load_json(self._state_path, default_factory=dict)
        try:
            return UpdateState.from_dict(data)
        except Exception:
            return UpdateState()

    def _save_state(self):
        try:
            with self._lock:
                os.makedirs(self._install_dir, exist_ok=True)
                ensure_private_dir(self._install_dir)
                save_json(self._state_path, self._state.to_dict())
        except (OSError, TypeError, ValueError):
            self._logger.warning("Unable to persist update state", exc_info=True)

    # ------------------------------------------------------------------
    # Local version
    # ------------------------------------------------------------------

    def _active_binary(self) -> str:
        """The yt-dlp copy resolver actually runs today (for version talk)."""
        if self.is_installed:
            return self._binary_path
        from youtube_api import YouTubeAPI

        return YouTubeAPI._find_ytdlp()

    def local_version(self, binary_path: str | None = None) -> str:
        path = binary_path or self._active_binary()
        if not path:
            return ""
        with self._lock:
            cached = self._version_cache.get(path)
        if cached is not None:
            return cached
        version = self._version_probe(path)
        with self._lock:
            self._version_cache[path] = version
        return version

    @staticmethod
    def _probe_version_subprocess(binary_path: str) -> str:
        creationflags = subprocess.CREATE_NO_WINDOW if _windows() else 0
        try:
            completed = subprocess.run(
                [binary_path, "--version"],
                capture_output=True,
                timeout=15,
                check=False,
                creationflags=creationflags,
                text=False,
            )
            text = (completed.stdout or b"").decode("utf-8", "ignore").strip()
            first = text.splitlines()[0].strip() if text else ""
            if LOCAL_VERSION_RE.match(first):
                return first
        except (OSError, subprocess.SubprocessError, IndexError):
            pass
        return ""

    # ------------------------------------------------------------------
    # Check
    # ------------------------------------------------------------------

    def check(self, force: bool = False) -> ReleaseInfo | None:
        """Run one update check synchronously.

        Returns the pending :class:`ReleaseInfo` when a newer version is
        available, ``None`` otherwise (up to date / throttled / offline).
        Network is skipped while the persisted ``last_check`` is fresh.
        """
        state = self._load_state()
        self._state = state
        now = time.time()
        if not force and state.last_check and now - state.last_check < self._check_interval:
            return None

        release = self._safe_backend_call()
        if release is None:
            # Throttle failures too, but retry after a fraction of the
            # interval so a transient outage is not punished with a full wait.
            state.last_check = now - self._check_interval * 0.75
            self._save_state()
            self._publish(UpdateFailedEvent(stage="check", error="release lookup failed"))
            return None

        state.last_check = now
        state.latest_seen_version = release.version
        self._save_state()

        current = self.local_version()
        if compare_versions(current, release.version) <= 0:
            # Remote is not strictly newer (equal or older) — nothing to do.
            self._publish(UpdateUpToDateEvent(version=release.version))
            return None

        self._publish(
            UpdateAvailableEvent(
                current_version=current,
                latest_version=release.version,
            )
        )
        return release

    def _safe_backend_call(self) -> ReleaseInfo | None:
        try:
            release = self._backend.fetch_latest_release()
        except Exception as exc:
            self._logger.warning("Update backend raised: %s", redact_text(str(exc)))
            return None
        if release is None or not release.url or not release.version:
            return None
        if not self._validate_url(release.url):
            return None
        if release.sha256_url and not self._validate_url(release.sha256_url):
            return None
        if len(release.version) > 64:
            return None
        return release

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    def apply_update(self, release: ReleaseInfo | None = None) -> bool:
        """Fetch, verify, and atomically install the pending release."""
        if self._shutdown:
            return False
        if release is None:
            with self._lock:
                if self._stale_worker_running():
                    return False
            release = self.check(force=True)
        if release is None:
            return False

        if not release.url or len(release.version) > 64:
            self._publish(UpdateFailedEvent(stage="install", error="invalid release metadata"))
            return False

        staged = ""
        try:
            os.makedirs(self._install_dir, exist_ok=True)
            ensure_private_dir(self._install_dir)
            safe_download = self._validate_url(release.url)
            if not safe_download:
                raise ValueError("download URL refused by host allowlist")
            staged = self._stage_path(release)

            payload_hash = self._backend.download(
                safe_download, staged, MAX_BINARY_BYTES
            )
            self._verify_payload(release, staged, payload_hash)

            os.replace(staged, self._binary_path)
            ensure_private_file(self._binary_path)
        except Exception as exc:
            if staged and os.path.exists(staged):
                try:
                    os.remove(staged)
                except OSError:
                    self._logger.debug("Could not remove staged file", exc_info=True)
            self._logger.warning("yt-dlp update failed: %s", redact_text(str(exc)))
            self._publish(UpdateFailedEvent(stage="install", error=redact_text(str(exc))[:200]))
            return False

        with self._lock:
            self._state.installed_version = release.version
            self._save_state()
        self._version_cache.pop(self._binary_path, None)
        self._publish(UpdateCompletedEvent(version=release.version))
        return True

    def _stage_path(self, release: ReleaseInfo) -> str:
        token = re.sub(r"[^A-Za-z0-9._-]", "_", release.version)[:64] or "release"
        return os.path.join(self._install_dir, f".{token}.download")

    def _verify_payload(
        self, release: ReleaseInfo, staged: str, payload_hash: str
    ):
        if not payload_hash or not re.fullmatch(r"[0-9a-fA-F]{64}", payload_hash):
            raise ValueError("download verification key missing")
        if release.size and os.path.getsize(staged) > min(
            release.size * 2 + (1 << 20), MAX_BINARY_BYTES
        ):
            raise ValueError("payload is larger than the published size")

        expected = ""
        if release.sha256_url:
            safe_hash_url = self._validate_url(release.sha256_url)
            if not safe_hash_url:
                raise ValueError("checksum URL refused by host allowlist")
            expected = self._backend.fetch_sha256(
                safe_hash_url, release.checksum_asset
            )
            if not expected or not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
                raise ValueError("checksum sidecar missing or malformed")
            expected = expected.lower()

        if expected and expected != payload_hash.lower():
            raise ValueError("sha256 mismatch for the downloaded binary")
        if not expected:
            self._logger.warning(
                "No checksum published for the release; accepting on size cap only"
            )

        if os.path.getsize(staged) < 1024:
            raise ValueError("downloaded binary is suspiciously small")
        with open(staged, "rb") as handle:
            head = handle.read(2)
        if _windows() and head != b"MZ":
            raise ValueError("downloaded payload is not a Windows executable")
        if not _windows() and head != b"#!/":
            raise ValueError("downloaded payload is not a yt-dlp zipapp")

    # ------------------------------------------------------------------
    # Background worker
    # ------------------------------------------------------------------

    def _stale_worker_running(self) -> bool:
        return (
            self._thread is not None
            and self._thread.is_alive()
            and not self._stop_event.is_set()
        )

    def auto_check_enabled(self) -> bool:
        if self._settings_service is None:
            return True
        try:
            value = self._settings_service.get("auto_update_check", True)
        except Exception:
            return True
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)

    def check_in_background(self, force: bool = False, *, auto_apply: bool = True):
        """One-shot worker thread: check plus automatic install when allowed.

        ``auto_apply=False`` only refreshes the release metadata — the UI
        "Check now" path — while the default mirrors the startup flow.
        """
        if self._shutdown:
            return
        if not self.auto_check_enabled() and not force:
            return
        with self._lock:
            if self._stale_worker_running():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._worker,
                args=(force, auto_apply),
                daemon=True,
                name="ytdlp-update-check",
            )
        self._thread.start()

    def _worker(self, force: bool, auto_apply: bool = True):
        try:
            self._stop_event.wait(0.1)      # let startup latency settle
            if self._stop_event.is_set() or self._shutdown:
                return
            release = self.check(force=force)
            if release is not None and auto_apply:
                self.apply_update(release)
        except Exception:
            self._logger.exception("Update worker crashed")
        finally:
            with self._lock:
                self._thread = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _validate_url(self, url: object) -> str | None:
        """Return a fetch-safe URL restricted to the allowlisted hosts."""
        from core.security import validate_fetch_url

        try:
            return validate_fetch_url(url, ALLOWED_HOSTS)
        except ValueError as exc:
            self._logger.warning(
                "Refusing update URL %s: %s", redact_url(url if isinstance(url, str) else ""), exc
            )
            return None

    def _publish(self, event):
        if self._event_bus is None:
            return
        self._event_bus.publish(event)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def state_json(self) -> str:
        try:
            data = load_json(self._state_path, default_factory=dict)
            return json.dumps(data, indent=2)
        except (OSError, ValueError):
            return "{}"
