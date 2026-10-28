"""Versioned export/import bundle for all per-profile user data.

The on-disk files keep their existing layouts.  A bundle is only used when
moving data between installations, so it carries an explicit schema version
instead of silently depending on the current model defaults.
"""

from __future__ import annotations

import time
from typing import Any

DATA_SCHEMA_VERSION = 1

_DATA_KEYS = ("user_profile", "settings", "history", "likes", "playlists")
_MAPPING_KEYS = ("user_profile", "settings", "playlists")
_SEQUENCE_KEYS = ("history", "likes")


def build_bundle(
    *,
    profile_name: str = "",
    user_profile: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
    history: list | None = None,
    likes: list | None = None,
    playlists: dict[str, Any] | None = None,
    app_version: str = "",
    exported_at: float | None = None,
) -> dict[str, Any]:
    """Build a JSON-serializable bundle with a schema version."""
    return {
        "schema_version": DATA_SCHEMA_VERSION,
        "exported_at": float(exported_at if exported_at is not None else time.time()),
        "app_version": str(app_version or ""),
        "profile_name": str(profile_name or ""),
        "data": {
            "user_profile": dict(user_profile or {}),
            "settings": dict(settings or {}),
            "history": list(history or []),
            "likes": list(likes or []),
            "playlists": dict(playlists or {}),
        },
    }


def validate_bundle(bundle: object) -> tuple[bool, str]:
    """Validate bundle structure and schema version.

    Returns ``(True, "")`` for a supported bundle or ``(False, reason)``.
    Data values are validated further by the individual services on import.
    """
    if not isinstance(bundle, dict):
        return False, "bundle must be a JSON object"

    version = bundle.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        return False, "bundle is missing an integer schema_version"
    if version < 1:
        return False, f"unsupported bundle schema version: {version}"
    if version > DATA_SCHEMA_VERSION:
        return False, (
            f"bundle schema version {version} is newer than supported "
            f"version {DATA_SCHEMA_VERSION}"
        )

    data = bundle.get("data")
    if not isinstance(data, dict):
        return False, "bundle is missing a data object"

    for key in _MAPPING_KEYS:
        if key in data and not isinstance(data[key], dict):
            return False, f"data.{key} must be an object"
    for key in _SEQUENCE_KEYS:
        if key in data and not isinstance(data[key], list):
            return False, f"data.{key} must be an array"
    return True, ""


def bundle_sections(bundle: dict[str, Any]) -> dict[str, Any]:
    """Return the ``data`` mapping with missing sections filled with defaults."""
    data = bundle.get("data") or {}
    return {
        "user_profile": data.get("user_profile") or {},
        "settings": data.get("settings") or {},
        "history": data.get("history") or [],
        "likes": data.get("likes") or [],
        "playlists": data.get("playlists") or {},
    }
