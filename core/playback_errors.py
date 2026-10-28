"""Playback-related exception types shared across service boundaries."""

from __future__ import annotations


class StreamCancelledError(RuntimeError):
    """Raised when an in-flight stream resolution is superseded or cancelled."""


class StreamResolutionError(RuntimeError):
    """Raised when a playable stream URL cannot be produced."""
