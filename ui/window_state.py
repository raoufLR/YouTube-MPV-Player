"""Persist and restore the main-window geometry safely.

Saved window positions can become invalid when monitors are disconnected or
the resolution changes between runs.  Restored geometry is therefore clamped
to the available screens and only accepted when a meaningful part of the
window would be visible.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import QApplication

if TYPE_CHECKING:
    from collections.abc import Iterable

MIN_VISIBLE_WIDTH = 120
MIN_VISIBLE_HEIGHT = 80
FALLBACK_SIZE = (1280, 800)


def default_screen_rects() -> list[QRect]:
    """Return available geometry for every attached screen."""
    app = QApplication.instance()
    if app is None:
        return [QRect(0, 0, *FALLBACK_SIZE)]
    rects = [screen.availableGeometry() for screen in app.screens()]
    rects = [rect for rect in rects if rect.isValid() and not rect.isEmpty()]
    return rects or [QRect(0, 0, *FALLBACK_SIZE)]


def _normalized_screens(screen_rects: Iterable[QRect] | None) -> list[QRect]:
    if screen_rects is None:
        return default_screen_rects()
    rects = [QRect(rect) for rect in screen_rects if QRect(rect).isValid()]
    return rects or [QRect(0, 0, *FALLBACK_SIZE)]


def _visible_area(window_rect: QRect, screen_rect: QRect) -> int:
    intersection = screen_rect.intersected(window_rect)
    if intersection.isEmpty():
        return 0
    return intersection.width() * intersection.height()


def clamp_geometry(
    rect: QRect,
    screen_rects: Iterable[QRect] | None = None,
    *,
    min_width: int = 0,
    min_height: int = 0,
) -> QRect:
    """Clamp *rect* to a usable position and size on the available screens."""
    screens = _normalized_screens(screen_rects)
    result = QRect(rect)

    min_width = max(1, int(min_width or 1))
    min_height = max(1, int(min_height or 1))
    result.setWidth(max(min_width, result.width()))
    result.setHeight(max(min_height, result.height()))

    largest_width = max(screen.width() for screen in screens)
    largest_height = max(screen.height() for screen in screens)
    result.setWidth(min(result.width(), max(min_width, largest_width)))
    result.setHeight(min(result.height(), max(min_height, largest_height)))

    required_area = MIN_VISIBLE_WIDTH * MIN_VISIBLE_HEIGHT
    if not any(_visible_area(result, screen) >= required_area for screen in screens):
        # The saved position no longer belongs to any monitor: center the
        # window on the primary screen instead of opening it off-screen.
        result.moveCenter(screens[0].center())

    return result


def restore_window_geometry(window, settings, screen_rects=None) -> bool:
    """Apply persisted geometry to *window*.  Returns ``True`` if applied."""
    if settings is None:
        return False

    try:
        width = int(settings.get("window_width", 0) or 0)
        height = int(settings.get("window_height", 0) or 0)
        x = int(settings.get("window_x", 0) or 0)
        y = int(settings.get("window_y", 0) or 0)
    except (TypeError, ValueError):
        return False

    if width <= 0 or height <= 0:
        return False

    rect = clamp_geometry(
        QRect(x, y, width, height),
        screen_rects,
        min_width=window.minimumWidth(),
        min_height=window.minimumHeight(),
    )
    window.resize(rect.size())
    window.move(rect.topLeft())

    try:
        maximized = bool(settings.get("window_maximized", False))
    except (TypeError, ValueError):
        maximized = False
    if maximized:
        window.showMaximized()
    return True


def save_window_geometry(window, settings) -> None:
    """Persist the window's normal geometry and maximized state."""
    if settings is None:
        return

    maximized = bool(window.isMaximized())
    geometry = window.normalGeometry() if maximized else window.geometry()
    if not geometry.isValid() or geometry.isEmpty():
        return

    settings.set("window_maximized", maximized)
    settings.set("window_width", int(geometry.width()))
    settings.set("window_height", int(geometry.height()))
    settings.set("window_x", int(geometry.x()))
    settings.set("window_y", int(geometry.y()))
