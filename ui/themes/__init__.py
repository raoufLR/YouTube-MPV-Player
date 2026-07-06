from .theme_manager import ThemeManager
from .default_theme import DefaultTheme
from .youtube_theme import YouTubeTheme

THEME_REGISTRY = {
    "default": DefaultTheme,
    "youtube_dark": YouTubeTheme,
}
