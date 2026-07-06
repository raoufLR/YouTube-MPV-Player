from .base_theme import BaseTheme


class YouTubeTheme(BaseTheme):
    name: str = "youtube_dark"
    display_name: str = "YouTube Dark"

    # Backgrounds
    BG_PRIMARY: str = "#0F0F0F"
    BG_SIDEBAR: str = "#181818"
    BG_CARD: str = "#202020"
    BG_HOVER: str = "#2A2A2A"
    BG_SEARCH: str = "#121212"
    BG_SEARCH_FOCUS: str = "#1A1A1A"

    # Surfaces
    SURFACE_RAISED: str = "#202020"
    SURFACE_TOOLTIP: str = "#212121"

    # Text
    TEXT_PRIMARY: str = "#FFFFFF"
    TEXT_SECONDARY: str = "#AAAAAA"
    TEXT_DISABLED: str = "#555555"
    TEXT_PLACEHOLDER: str = "#717171"

    # Accent - YouTube Red
    ACCENT_PRIMARY: str = "#FF0000"
    ACCENT_HOVER: str = "#FF3333"
    ACCENT_PRESSED: str = "#CC0000"
    ACCENT_SELECTION: str = "#FF3333"

    # Danger / Like
    DANGER: str = "#FF5252"
    DANGER_HOVER_BG: str = "rgba(255, 82, 82, 0.15)"

    # Borders
    BORDER: str = "#303030"
    BORDER_FOCUS: str = "#FF0000"
    BORDER_SIDEBAR: str = "#303030"

    # Status bar
    STATUS_BG: str = "#181818"
    STATUS_BORDER: str = "#303030"

    # Scrollbar
    SCROLLBAR_HANDLE: str = "#555555"
    SCROLLBAR_HOVER: str = "#777777"

    # Skeleton
    SKELETON_BG: str = "#282828"
    SKELETON_CHUNK: str = "#333333"

    # Slider
    SLIDER_GROOVE: str = "#303030"
    SLIDER_HANDLE: str = "#FF0000"
    SLIDER_HANDLE_HOVER: str = "#FF3333"
    SLIDER_SUB: str = "#FF0000"

    # Special
    NOW_PLAYING_BG: str = "#181818"
    NOW_PLAYING_BORDER: str = "#303030"
    EMPTY_STATE: str = "#717171"
    INPUT_BG: str = "#121212"

    # Font
    FONT_FAMILY: str = "'Roboto', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif"
    FONT_SIZE: str = "13px"
