from __future__ import annotations

from typing import TYPE_CHECKING

from .default_theme import DefaultTheme

if TYPE_CHECKING:
    from .base_theme import BaseTheme

_active_theme: BaseTheme = DefaultTheme()


def set_active_theme(theme: BaseTheme) -> None:
    global _active_theme
    _active_theme = theme


def active_theme() -> BaseTheme:
    return _active_theme
