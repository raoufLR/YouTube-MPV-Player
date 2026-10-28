from .default_theme import DefaultTheme
from .theme_manager import ThemeManager as ThemeManager
from .youtube_theme import YouTubeTheme

THEME_REGISTRY = {
    "default": DefaultTheme,
    "youtube_dark": YouTubeTheme,
}
