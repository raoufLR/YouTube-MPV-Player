"""Central security boundaries for remote input, local paths, and logs.

The application parses untrusted data at two edges: yt-dlp output (titles,
thumbnail URLs, media URLs) and user data files that can be imported or
hand-edited.  The helpers in this module are deliberately small and total:
they either return a validated value or raise :class:`ValueError`, and they
never perform I/O that could trigger a network request.

Rules live here so services cannot drift apart:

* remote URLs: scheme, credentials, control characters, port, IP literals,
  optional host allowlist
* local paths: URL schemes, UNC/device prefixes, Windows alternate data
  streams
* logs: signed URLs / tokens are redacted before a record reaches a handler
* files: restrictive permissions on POSIX (Windows inherits the user's ACLs)
"""

from __future__ import annotations

import contextlib
import ipaddress
import logging
import os
import re
import shutil
import tempfile
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from collections.abc import Iterable

MAX_URL_LENGTH = 2048
MAX_LOG_TEXT = 4096

# YouTube serves thumbnails from these domains (and their subdomains).
DEFAULT_THUMBNAIL_HOSTS = (
    "ytimg.com",
    "youtube.com",
    "ggpht.com",
    "googleusercontent.com",
)

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_SECRET_PARAM = re.compile(
    r"(?i)\b(key|api_key|token|access_token|auth|authorization|sig|signature|"
    r"expire|expires|password|passwd|secret|session|sessionid)"
    r"=([^&\s\"'<>]+)"
)
_AUTH_SCHEME = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]+")
_URL_PATTERN = re.compile(r"(?i)\b(?:https?|ytdl)://[^\s\"'<>]+")
# urllib3 logs request lines as ``GET /vi/x.jpg?sqp=...&rs=... HTTP/1.1``;
# the query holds short-lived signed tokens and must be scrubbed too.
_REQUEST_LINE = re.compile(
    r"(?i)\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(/[^\s\"'<>]*)"
)

_ALLOWED_FETCH_SCHEMES = ("http", "https")
_ALLOWED_FETCH_PORTS = (None, 80, 443)


def has_control_chars(value: str) -> bool:
    """Return ``True`` when *value* contains ASCII control characters."""
    return bool(_CONTROL_CHARS.search(value))


# ---------------------------------------------------------------------------
# Log redaction
# ---------------------------------------------------------------------------

def redact_url(url: str) -> str:
    """Return *url* without query, fragment, or embedded credentials.

    Signed media URLs carry short-lived credentials in their query string;
    those must never reach a log file.  The result is always safe to log.
    """
    if not isinstance(url, str):
        return "<invalid-url>"
    if len(url) > MAX_URL_LENGTH:
        url = url[:MAX_URL_LENGTH]
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<invalid-url>"

    scheme = (parts.scheme or "").lower()
    host = parts.hostname or ""
    if not scheme or not host:
        # Not a parsable URL: drop anything that looks like a query anyway.
        return url.split("?", 1)[0].split("#", 1)[0]

    try:
        port = parts.port
    except ValueError:
        port = None
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    result = f"{scheme}://{netloc}{parts.path or ''}"
    if parts.query:
        result += "?<redacted>"
    if parts.fragment:
        result += "#<redacted>"
    return result


def redact_text(text: object, max_length: int = MAX_LOG_TEXT) -> str:
    """Redact secrets and bound the size of a log message or error string."""
    value = "" if text is None else str(text)

    def _clean_url(match: re.Match) -> str:
        return redact_url(match.group(0))

    def _clean_request(match: re.Match) -> str:
        target = match.group(2)
        if "?" in target or "#" in target:
            base = target.split("?", 1)[0].split("#", 1)[0]
            target = base + ("?<redacted>" if "?" in target else "")
            if "#" in match.group(2):
                target += "#<redacted>"
        return f"{match.group(1)} {target}"

    value = _REQUEST_LINE.sub(_clean_request, value)
    value = _URL_PATTERN.sub(_clean_url, value)
    value = _SECRET_PARAM.sub(r"\1=<redacted>", value)
    value = _AUTH_SCHEME.sub(lambda m: f"{m.group(1)} <redacted>", value)
    # Log forging protection: no raw newlines from untrusted content.
    value = "".join(
        ch for ch in value if ch == "\t" or (ord(ch) >= 32 and ch != "\x7f")
    )
    if len(value) > max_length:
        value = value[: max_length - 1] + "\u2026"
    return value


class RedactionFilter(logging.Filter):
    """Scrub signed URLs and tokens from every record passing through."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - malformed format arguments
            return True
        redacted = redact_text(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def install_redaction(logger: logging.Logger | None = None) -> None:
    """Attach :class:`RedactionFilter` to *logger*'s handlers (idempotent)."""
    target = logger or logging.getLogger()
    for handler in target.handlers:
        if not any(isinstance(f, RedactionFilter) for f in handler.filters):
            handler.addFilter(RedactionFilter())


# ---------------------------------------------------------------------------
# Remote URL validation
# ---------------------------------------------------------------------------

def validate_fetch_url(
    url: object,
    allowed_hosts: Iterable[str] | None = None,
) -> str:
    """Validate a URL before the application performs a network request.

    ``allowed_hosts`` entries match the host itself or any subdomain of it.
    IP literals are always required to be globally routable, which keeps a
    malicious feed entry from pointing the fetcher at loopback or LAN hosts.
    """
    if not isinstance(url, str) or not url:
        raise ValueError("URL must be a non-empty string")
    if len(url) > MAX_URL_LENGTH:
        raise ValueError("URL is too long")
    if has_control_chars(url) or " " in url:
        raise ValueError("URL contains whitespace or control characters")

    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise ValueError(f"Malformed URL: {exc}") from exc

    if parts.scheme.lower() not in _ALLOWED_FETCH_SCHEMES:
        raise ValueError(f"Unsupported URL scheme: {parts.scheme!r}")
    if parts.username or parts.password:
        raise ValueError("URL must not contain credentials")
    if port not in _ALLOWED_FETCH_PORTS:
        raise ValueError(f"Unsupported URL port: {port}")

    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise ValueError("URL is missing a host")

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError(f"Refusing non-public address: {host}")
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("Refusing loopback host")

    if allowed_hosts is not None:
        allowed = tuple(
            str(entry).strip().lower().lstrip(".").rstrip(".")
            for entry in allowed_hosts
            if entry
        )
        if not any(host == entry or host.endswith("." + entry) for entry in allowed):
            raise ValueError(f"Host is not allowed: {host}")

    return url


# ---------------------------------------------------------------------------
# Local path validation
# ---------------------------------------------------------------------------

def is_safe_local_path(path: object) -> bool:
    """Return ``True`` when *path* is a plain local filesystem path.

    Rejected: empty values, control characters, URL schemes (``file:``,
    ``http:``), UNC/device prefixes (``\\\\server\\share``, ``\\\\?\\``), and
    Windows alternate data streams (``file.txt:stream``).  The path does not
    have to exist; profile metadata outlives moves between machines.
    """
    if not isinstance(path, str) or not path:
        return False
    if len(path) > MAX_URL_LENGTH or has_control_chars(path):
        return False
    if "://" in path:
        return False
    if path.startswith("\\\\") or path.startswith("//"):
        return False
    if os.name == "nt":
        # Allow "C:\..." and "C:/..." but reject "C:relative" and "name:stream".
        colon_positions = [i for i, ch in enumerate(path) if ch == ":"]
        for position in colon_positions:
            if position != 1 or not path[0].isalpha():
                return False
            if len(path) < 3 or path[2] not in "\\/":
                return False
    return True


def sanitize_local_path(value: object, default: str = "") -> str:
    """Return *value* if it is a safe local path, else *default*."""
    return value if is_safe_local_path(value) else default


# ---------------------------------------------------------------------------
# File permissions
# ---------------------------------------------------------------------------

def ensure_private_file(path: str) -> None:
    """Restrict *path* to the owner on POSIX; no-op on Windows."""
    if os.name == "nt":
        return
    with contextlib.suppress(OSError):  # pragma: no cover - exercised on POSIX CI
        os.chmod(path, 0o600)


def ensure_private_dir(path: str) -> None:
    """Restrict *path* to the owner on POSIX; no-op on Windows."""
    if os.name == "nt":
        return
    with contextlib.suppress(OSError):  # pragma: no cover - exercised on POSIX CI
        os.chmod(path, 0o700)


def copy_private_file(src: str, dst: str) -> None:
    """Copy *src* over *dst* atomically and restrict the destination.

    Used for avatar files: a crash mid-copy must not truncate the existing
    avatar, and other POSIX users must not be able to read it.
    """
    directory = os.path.dirname(os.path.abspath(dst))
    os.makedirs(directory, exist_ok=True)
    ensure_private_dir(directory)
    fd, tmp_path = tempfile.mkstemp(prefix=".copy-", suffix=".tmp", dir=directory)
    os.close(fd)
    try:
        shutil.copy2(src, tmp_path)
        ensure_private_file(tmp_path)
        os.replace(tmp_path, dst)
        ensure_private_file(dst)
        tmp_path = ""
    finally:
        if tmp_path and os.path.exists(tmp_path):
            with contextlib.suppress(OSError):
                os.remove(tmp_path)
