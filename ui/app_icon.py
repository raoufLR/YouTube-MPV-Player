"""Brand assets: the application icon shipped in ``icon/``."""

from __future__ import annotations

import os
import sys
from functools import lru_cache

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon, QPixmap

ICON_FILENAME = "yt-mpv-icon-fusion.svg"


def _root() -> str:
    """Return the project root, or the PyInstaller extraction directory."""
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        return frozen
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@lru_cache(maxsize=1)
def icon_path() -> str:
    return os.path.join(_root(), "icon", ICON_FILENAME)


@lru_cache(maxsize=1)
def app_icon() -> QIcon:
    """Return the window/taskbar icon, or a null icon when it is missing."""
    path = icon_path()
    if not os.path.isfile(path):
        return QIcon()
    return QIcon(path)


def brand_pixmap(size: int = 28, ratio: float = 2.0) -> QPixmap:
    """Return a crisp logo pixmap for the sidebar header.

    The pixmap is rendered at ``size`` logical pixels with a 2x device pixel
    ratio, so it stays sharp on high-DPI screens and in 2x screenshots.
    """
    return app_icon().pixmap(QSize(size, size), ratio)
