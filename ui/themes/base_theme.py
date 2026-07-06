class BaseTheme:
    name: str = "base"
    display_name: str = "Base"

    # Backgrounds
    BG_PRIMARY: str = "#202124"
    BG_SIDEBAR: str = "#1E1E1E"
    BG_CARD: str = "#2A2A2A"
    BG_HOVER: str = "#303134"
    BG_SEARCH: str = "#2A2A2A"
    BG_SEARCH_FOCUS: str = "#303134"

    # Surfaces
    SURFACE_RAISED: str = "#2A2A2A"
    SURFACE_TOOLTIP: str = "#2A2A2A"

    # Text
    TEXT_PRIMARY: str = "#FFFFFF"
    TEXT_SECONDARY: str = "#AAAAAA"
    TEXT_DISABLED: str = "#555555"
    TEXT_PLACEHOLDER: str = "#888888"

    # Accent
    ACCENT_PRIMARY: str = "#3EA6FF"
    ACCENT_HOVER: str = "#65B8FF"
    ACCENT_PRESSED: str = "#2B8FE0"
    ACCENT_SELECTION: str = "#1976D2"

    # Danger / Like
    DANGER: str = "#FF5252"
    DANGER_HOVER_BG: str = "rgba(255, 82, 82, 0.15)"

    # Borders
    BORDER: str = "#3C3C3C"
    BORDER_FOCUS: str = "#3EA6FF"
    BORDER_SIDEBAR: str = "#3C3C3C"

    # Status bar
    STATUS_BG: str = "#1E1E1E"
    STATUS_BORDER: str = "#3C3C3C"

    # Scrollbar
    SCROLLBAR_HANDLE: str = "#5A5A5A"
    SCROLLBAR_HOVER: str = "#7A7A7A"

    # Skeleton
    SKELETON_BG: str = "#303134"
    SKELETON_CHUNK: str = "#3C3C3C"

    # Slider
    SLIDER_GROOVE: str = "#3C3C3C"
    SLIDER_HANDLE: str = "#3EA6FF"
    SLIDER_HANDLE_HOVER: str = "#65B8FF"
    SLIDER_SUB: str = "#3EA6FF"

    # Special
    NOW_PLAYING_BG: str = "#1E1E1E"
    NOW_PLAYING_BORDER: str = "#3C3C3C"
    EMPTY_STATE: str = "#888888"
    INPUT_BG: str = "#2A2A2A"

    # Font
    FONT_FAMILY: str = "'Segoe UI', 'Segoe UI Variable', 'Helvetica Neue', Arial, sans-serif"
    FONT_SIZE: str = "13px"

    # Borders / Radii
    RADIUS_SMALL: str = "4px"
    RADIUS_MEDIUM: str = "8px"
    RADIUS_LARGE: str = "10px"
    RADIUS_XLARGE: str = "24px"
    RADIUS_FULL: str = "20px"
