"""Defensive parsing helpers for persisted user data.

User-controlled JSON files can contain values written by older versions, by
hand, or by a partial write.  Models and services use these helpers so a
malformed value can never propagate into the UI or into MPV.

The helpers are deliberately total: they never raise for bad input and always
return a value of the expected type.
"""

from __future__ import annotations

import math
import re
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

# YouTube IDs are 11 characters today, but tests and future sources may use
# shorter opaque IDs.  Restrict the character set rather than the length.
MAX_ID_LENGTH = 128
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_TRUE_TEXT = {"1", "true", "yes", "on", "enabled"}
_FALSE_TEXT = {"0", "false", "no", "off", "disabled", ""}


def is_safe_id(value: object, *, max_length: int = MAX_ID_LENGTH) -> bool:
    """Return ``True`` for a non-empty opaque identifier safe for a filename.

    IDs are used as playlist filenames, profile directory names, and video
    keys.  They must never contain path separators, dots, or control
    characters.
    """
    if not isinstance(value, str):
        return False
    value = value.strip()
    return bool(value) and len(value) <= max_length and bool(_SAFE_ID_RE.match(value))


def coerce_id(value: object, default: str = "", *, max_length: int = MAX_ID_LENGTH) -> str:
    """Return *value* if it is a safe ID, otherwise *default*."""
    if not isinstance(value, str):
        return default
    value = value.strip()
    if not value or len(value) > max_length or not _SAFE_ID_RE.match(value):
        return default
    return value


def coerce_text(
    value: object,
    default: str = "",
    *,
    max_length: int = 512,
    multiline: bool = False,
) -> str:
    """Return a sanitized string, falling back to *default* for bad input.

    Control characters are removed.  Single-line fields collapse newlines and
    tabs into spaces so they cannot break list rows or log lines.
    """
    if not isinstance(value, str):
        return default

    if multiline:
        text = value.replace("\r\n", "\n").replace("\r", "\n")
        text = _CONTROL_CHARS_RE.sub("", text)
    else:
        text = _CONTROL_CHARS_RE.sub(" ", value)
        text = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")

    text = text.strip()
    if not text:
        return default
    if max_length > 0:
        text = text[:max_length].rstrip()
    return text


def coerce_bool(value: object, default: bool = False) -> bool:
    """Coerce common JSON representations of truth to ``bool``."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
        return default
    if isinstance(value, float):
        if value == 1.0:
            return True
        if value == 0.0:
            return False
        return default
    if isinstance(value, str):
        token = value.strip().casefold()
        if token in _TRUE_TEXT:
            return True
        if token in _FALSE_TEXT:
            return False
    return default


def _clamp(number: int, minimum: int | None, maximum: int | None) -> int:
    if minimum is not None and number < minimum:
        return minimum
    if maximum is not None and number > maximum:
        return maximum
    return number


def coerce_int(
    value: object,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    """Coerce an integer and clamp it to the supplied range.

    Floats are accepted only when they are integral.  Booleans are rejected so
    a corrupted ``true`` never silently becomes a numeric setting.
    """
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        number = value
    elif isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            return default
        number = int(value)
    elif isinstance(value, str):
        try:
            number = int(value.strip(), 10)
        except (TypeError, ValueError):
            return default
    else:
        return default
    return _clamp(number, minimum, maximum)


def coerce_float(
    value: object,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    """Coerce a finite float and clamp it to the supplied range."""
    if isinstance(value, bool):
        return default
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(number):
        return default
    if minimum is not None and number < minimum:
        number = minimum
    if maximum is not None and number > maximum:
        number = maximum
    return number


def coerce_timestamp(value: object, default: float | None = None) -> float:
    """Coerce a Unix timestamp to a finite, non-negative float."""
    fallback = time.time() if default is None else default
    if isinstance(value, bool):
        return fallback
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return fallback
    if not math.isfinite(number) or number < 0:
        return fallback
    return number


def coerce_choice(value: object, choices: Iterable[str], default: str) -> str:
    """Return *value* when it is one of *choices*, otherwise *default*."""
    if not isinstance(value, str):
        return default
    value = value.strip().casefold()
    allowed = {str(choice).casefold() for choice in choices}
    return value if value in allowed else default


def coerce_optional_str(
    value: Any,
    *,
    max_length: int = 2048,
    multiline: bool = False,
) -> str:
    """Return a sanitized string or ``""`` for a missing value."""
    return coerce_text(value, "", max_length=max_length, multiline=multiline)
