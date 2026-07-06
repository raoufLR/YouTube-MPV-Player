from PyQt6.QtCore import QObject, pyqtSignal

from .default_theme import DefaultTheme
from .youtube_theme import YouTubeTheme


THEME_REGISTRY = {
    "default": DefaultTheme,
    "youtube_dark": YouTubeTheme,
}


class ThemeManager(QObject):
    theme_changed = pyqtSignal(str)

    def __init__(self, settings_service=None, parent=None):
        super().__init__(parent)
        self._settings_service = settings_service
        self._current_theme_name = "default"
        self._theme = DefaultTheme()

    def initialize(self, settings_service=None):
        if settings_service:
            self._settings_service = settings_service
        saved = self._load_saved_theme()
        self.apply(saved)

    def _load_saved_theme(self) -> str:
        if not self._settings_service:
            return "default"
        saved = self._settings_service.get("theme", "default")
        if saved not in THEME_REGISTRY:
            return "default"
        return saved

    def apply(self, theme_name: str):
        if theme_name not in THEME_REGISTRY:
            theme_name = "default"
        cls = THEME_REGISTRY[theme_name]
        self._theme = cls()
        self._current_theme_name = theme_name
        self.theme_changed.emit(theme_name)

    def save_theme(self, theme_name: str):
        if self._settings_service:
            self._settings_service.set("theme", theme_name)

    def switch_theme(self, theme_name: str):
        if theme_name not in THEME_REGISTRY:
            return
        self.apply(theme_name)
        self.save_theme(theme_name)

    @property
    def current_theme_name(self) -> str:
        return self._current_theme_name

    @property
    def theme(self):
        return self._theme

    @property
    def available_themes(self):
        return list(THEME_REGISTRY.keys())

    @property
    def available_theme_names(self):
        return [cls.display_name for cls in THEME_REGISTRY.values()]

    def theme_id_for_display(self, display_name: str) -> str:
        for tid, cls in THEME_REGISTRY.items():
            if cls.display_name == display_name:
                return tid
        return "default"

    def stylesheet(self) -> str:
        t = self._theme
        return f"""
QMainWindow, QWidget#centralWidget {{
    background-color: {t.BG_PRIMARY};
    color: {t.TEXT_PRIMARY};
    font-family: {t.FONT_FAMILY};
    font-size: {t.FONT_SIZE};
}}

QWidget {{
    background-color: transparent;
    color: {t.TEXT_PRIMARY};
}}

QWidget#centralWidget {{
    background-color: {t.BG_PRIMARY};
}}

*:focus {{
    outline: 2px solid {t.ACCENT_PRIMARY};
    outline-offset: 2px;
}}

QPushButton:focus, QComboBox:focus, QListWidget:focus {{
    outline: none;
}}

QScrollBar:vertical {{
    background-color: transparent;
    width: 8px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background-color: {t.SCROLLBAR_HANDLE};
    border-radius: 4px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {t.SCROLLBAR_HOVER};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background-color: transparent;
    height: 8px;
    margin: 0;
}}

QScrollBar::handle:horizontal {{
    background-color: {t.SCROLLBAR_HANDLE};
    border-radius: 4px;
    min-width: 30px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {t.SCROLLBAR_HOVER};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

QLineEdit {{
    background-color: {t.INPUT_BG};
    color: {t.TEXT_PRIMARY};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_MEDIUM};
    padding: 8px 12px;
    font-size: 13px;
    selection-background-color: {t.ACCENT_SELECTION};
}}

QLineEdit:focus {{
    border: 1px solid {t.ACCENT_PRIMARY};
}}

QLineEdit::placeholder {{
    color: {t.TEXT_PLACEHOLDER};
}}

QPushButton {{
    background-color: {t.BG_CARD};
    color: {t.TEXT_PRIMARY};
    border: none;
    border-radius: {t.RADIUS_MEDIUM};
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: {t.BG_HOVER};
}}

QPushButton:pressed {{
    background-color: {t.BORDER};
}}

QPushButton:disabled {{
    background-color: {t.BG_SIDEBAR};
    color: {t.TEXT_DISABLED};
}}

QPushButton#primaryButton {{
    background-color: {t.ACCENT_PRIMARY};
    color: #000000;
    font-weight: 600;
}}

QPushButton#primaryButton:hover {{
    background-color: {t.ACCENT_HOVER};
}}

QPushButton#primaryButton:pressed {{
    background-color: {t.ACCENT_PRESSED};
}}

QPushButton#dangerButton {{
    background-color: transparent;
    color: {t.DANGER};
    border: 1px solid {t.DANGER};
}}

QPushButton#dangerButton:hover {{
    background-color: {t.DANGER_HOVER_BG};
}}

QPushButton#iconButton {{
    background-color: transparent;
    border-radius: {t.RADIUS_FULL};
    padding: 8px;
    min-width: 36px;
    min-height: 36px;
}}

QPushButton#iconButton:hover {{
    background-color: {t.BG_HOVER};
}}

QListWidget {{
    background-color: transparent;
    color: {t.TEXT_PRIMARY};
    border: none;
    outline: none;
    padding: 4px;
}}

QListWidget::item {{
    background-color: {t.BG_CARD};
    border-radius: {t.RADIUS_MEDIUM};
    padding: 8px;
    margin: 2px 0;
}}

QListWidget::item:hover {{
    background-color: {t.BG_HOVER};
}}

QListWidget::item:selected {{
    background-color: {t.ACCENT_SELECTION};
    color: {t.TEXT_PRIMARY};
}}

QComboBox {{
    background-color: {t.BG_CARD};
    color: {t.TEXT_PRIMARY};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_MEDIUM};
    padding: 6px 12px;
    font-size: 13px;
    min-width: 80px;
}}

QComboBox:hover {{
    border-color: {t.ACCENT_PRIMARY};
}}

QComboBox::drop-down {{
    border: none;
    width: 28px;
}}

QComboBox::down-arrow {{
    image: none;
    width: 0;
}}

QComboBox QAbstractItemView {{
    background-color: {t.SURFACE_RAISED};
    color: {t.TEXT_PRIMARY};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_MEDIUM};
    selection-background-color: {t.ACCENT_SELECTION};
    outline: none;
    padding: 4px;
}}

QComboBox QAbstractItemView::item {{
    padding: 8px 12px;
    border-radius: 4px;
}}

QComboBox QAbstractItemView::item:hover {{
    background-color: {t.BG_HOVER};
}}

QLabel {{
    color: {t.TEXT_PRIMARY};
    background-color: transparent;
}}

QLabel#pageTitle {{
    font-size: 20px;
    font-weight: 700;
    padding: 16px 0 8px 0;
}}

QLabel#sectionTitle {{
    font-size: 14px;
    font-weight: 600;
    color: {t.TEXT_SECONDARY};
    padding: 12px 0 4px 0;
}}

QLabel#emptyState {{
    color: {t.EMPTY_STATE};
    font-size: 15px;
    padding: 40px;
}}

QLabel#duration {{
    color: {t.TEXT_PRIMARY};
    font-size: 12px;
    font-weight: 600;
    background-color: rgba(0, 0, 0, 0.8);
    border-radius: 4px;
    padding: 2px 6px;
}}

QLabel#statValue {{
    font-size: 24px;
    font-weight: 700;
    color: {t.TEXT_PRIMARY};
}}

QLabel#statLabel {{
    font-size: 12px;
    color: {t.TEXT_SECONDARY};
}}

QGroupBox {{
    background-color: {t.BG_CARD};
    border: none;
    border-radius: {t.RADIUS_LARGE};
    padding: 20px 16px 16px 16px;
    margin-top: 8px;
    font-size: 14px;
    font-weight: 600;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 4px;
}}

QSpinBox {{
    background-color: {t.BG_CARD};
    color: {t.TEXT_PRIMARY};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_MEDIUM};
    padding: 6px 12px;
    font-size: 13px;
}}

QSpinBox:focus {{
    border-color: {t.ACCENT_PRIMARY};
}}

QSpinBox::up-button, QSpinBox::down-button {{
    border: none;
    background-color: transparent;
    width: 20px;
}}

QSlider::groove:horizontal {{
    background-color: {t.SLIDER_GROOVE};
    height: 4px;
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background-color: {t.SLIDER_HANDLE};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}

QSlider::handle:horizontal:hover {{
    background-color: {t.SLIDER_HANDLE_HOVER};
}}

QSlider::sub-page:horizontal {{
    background-color: {t.SLIDER_SUB};
    border-radius: 2px;
}}

QStatusBar {{
    background-color: {t.STATUS_BG};
    color: {t.TEXT_SECONDARY};
    border-top: 1px solid {t.STATUS_BORDER};
    font-size: 12px;
    padding: 2px 12px;
    min-height: 24px;
}}

QStatusBar::item {{
    border: none;
}}

QMenu {{
    background-color: {t.SURFACE_RAISED};
    color: {t.TEXT_PRIMARY};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_MEDIUM};
    padding: 4px;
    font-size: 13px;
}}

QMenu::item {{
    padding: 8px 24px;
    border-radius: 4px;
}}

QMenu::item:selected {{
    background-color: {t.BG_HOVER};
}}

QMenu::separator {{
    height: 1px;
    background-color: {t.BORDER};
    margin: 4px 8px;
}}

QToolTip {{
    background-color: {t.SURFACE_TOOLTIP};
    color: {t.TEXT_PRIMARY};
    border: 1px solid {t.BORDER};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}}

QDialog {{
    background-color: {t.BG_PRIMARY};
    color: {t.TEXT_PRIMARY};
}}

QDialog QPushButton {{
    min-width: 80px;
}}

QMessageBox {{
    background-color: {t.BG_PRIMARY};
    color: {t.TEXT_PRIMARY};
}}

QMessageBox QPushButton {{
    min-width: 80px;
}}

QSplitter::handle {{
    background-color: {t.BORDER};
    width: 1px;
}}

QProgressBar {{
    background-color: {t.SKELETON_BG};
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
}}

QProgressBar::chunk {{
    background-color: {t.SKELETON_CHUNK};
    border-radius: 4px;
}}

QWidget#sidebar {{
    background-color: {t.BG_SIDEBAR};
    border-right: 1px solid {t.BORDER_SIDEBAR};
}}

QLabel#sidebarTitle {{
    font-size: 16px;
    font-weight: 700;
    color: {t.TEXT_PRIMARY};
    padding: 16px;
    background-color: {t.BG_SIDEBAR};
}}

QPushButton#navButton {{
    background-color: transparent;
    color: {t.TEXT_SECONDARY};
    border: none;
    border-radius: {t.RADIUS_MEDIUM};
    text-align: left;
    padding: 10px 16px;
    margin: 1px 8px;
    font-size: 13px;
    font-weight: 500;
}}

QPushButton#navButton:hover {{
    background-color: {t.BG_HOVER};
    color: {t.TEXT_PRIMARY};
}}

QPushButton#navButton:checked {{
    background-color: rgba(62, 166, 255, 0.15);
    color: {t.ACCENT_PRIMARY};
    font-weight: 600;
}}

QLabel#sidebarSection {{
    color: {t.TEXT_DISABLED};
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    padding: 16px 16px 4px 16px;
    letter-spacing: 0.5px;
}}

QPushButton#profileButton {{
    background-color: transparent;
    color: {t.TEXT_SECONDARY};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_MEDIUM};
    text-align: left;
    padding: 10px 16px;
    margin: 4px 8px;
    font-size: 13px;
}}

QPushButton#profileButton:hover {{
    background-color: {t.BG_HOVER};
    color: {t.TEXT_PRIMARY};
    border-color: {t.ACCENT_PRIMARY};
}}

QWidget#searchHeader {{
    background-color: {t.BG_PRIMARY};
    border-bottom: 1px solid {t.BORDER};
    padding: 12px 20px;
}}

QLineEdit#searchInput {{
    background-color: {t.BG_SEARCH};
    color: {t.TEXT_PRIMARY};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_XLARGE};
    padding: 10px 44px 10px 44px;
    font-size: 14px;
    min-height: 20px;
}}

QLineEdit#searchInput:focus {{
    border: 1px solid {t.ACCENT_PRIMARY};
    background-color: {t.BG_SEARCH_FOCUS};
}}

QLineEdit#searchInput::placeholder {{
    color: {t.TEXT_PLACEHOLDER};
}}

QWidget#videoCard {{
    background-color: {t.BG_CARD};
    border-radius: {t.RADIUS_LARGE};
}}

QWidget#videoCard:hover {{
    background-color: {t.BG_HOVER};
}}

QLabel#videoTitle {{
    font-size: 14px;
    font-weight: 600;
    color: {t.TEXT_PRIMARY};
}}

QLabel#videoSubtitle {{
    font-size: 12px;
    color: {t.TEXT_SECONDARY};
}}

QWidget#settingsCard {{
    background-color: {t.BG_CARD};
    border-radius: {t.RADIUS_LARGE};
}}

QWidget#settingsCategoryCard {{
    background-color: {t.BG_CARD};
    border-radius: {t.RADIUS_LARGE};
    padding: 16px;
}}

QLabel#historyDateHeader {{
    font-size: 15px;
    font-weight: 700;
    color: {t.TEXT_PRIMARY};
    padding: 16px 0 8px 0;
}}

QWidget#profileStatsCard {{
    background-color: {t.BG_CARD};
    border-radius: 12px;
    padding: 20px;
}}

QWidget#playlistCard {{
    background-color: {t.BG_CARD};
    border-radius: {t.RADIUS_LARGE};
    padding: 12px;
}}

QWidget#playlistCard:hover {{
    background-color: {t.BG_HOVER};
}}

QLabel#playlistName {{
    font-size: 14px;
    font-weight: 600;
    color: {t.TEXT_PRIMARY};
}}

QLabel#playlistCount {{
    font-size: 12px;
    color: {t.TEXT_SECONDARY};
}}

QPushButton#likeButton {{
    background-color: transparent;
    border: none;
    border-radius: 16px;
    padding: 6px;
    min-width: 32px;
    min-height: 32px;
}}

QPushButton#likeButton:hover {{
    background-color: {t.DANGER_HOVER_BG};
}}

QPushButton#likeButton:checked {{
    color: {t.DANGER};
}}

QPushButton#sectionTab {{
    background-color: transparent;
    color: {t.TEXT_SECONDARY};
    border: none;
    border-radius: {t.RADIUS_MEDIUM};
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
}}

QPushButton#sectionTab:hover {{
    background-color: {t.BG_HOVER};
    color: {t.TEXT_PRIMARY};
}}

QPushButton#sectionTab:checked {{
    background-color: rgba(62, 166, 255, 0.15);
    color: {t.ACCENT_PRIMARY};
    font-weight: 600;
}}

QWidget#nowPlayingBar {{
    background-color: {t.NOW_PLAYING_BG};
    border-top: 1px solid {t.NOW_PLAYING_BORDER};
    min-height: 64px;
    max-height: 64px;
}}

QLabel#nowPlayingTitle {{
    font-size: 13px;
    font-weight: 600;
    color: {t.TEXT_PRIMARY};
}}

QLabel#nowPlayingChannel {{
    font-size: 11px;
    color: {t.TEXT_SECONDARY};
}}

QPushButton#nowPlayingBtn {{
    background-color: transparent;
    border: none;
    border-radius: 16px;
    padding: 6px;
    min-width: 32px;
    min-height: 32px;
}}

QPushButton#nowPlayingBtn:hover {{
    background-color: {t.BG_HOVER};
}}

QPushButton#nowPlayingBtn:pressed {{
    background-color: {t.BORDER};
}}

QWidget#homeSection {{
    background-color: transparent;
}}

QLabel#homeSectionTitle {{
    font-size: 16px;
    font-weight: 700;
    color: {t.TEXT_PRIMARY};
    padding: 0 0 8px 0;
}}

QWidget#homeSectionCard {{
    background-color: {t.BG_CARD};
    border-radius: {t.RADIUS_LARGE};
    padding: 12px;
}}

QWidget#homeSectionCard:hover {{
    background-color: {t.BG_HOVER};
}}

QLabel#homeStatValue {{
    font-size: 20px;
    font-weight: 700;
    color: {t.TEXT_PRIMARY};
}}

QLabel#homeStatLabel {{
    font-size: 11px;
    color: {t.TEXT_SECONDARY};
}}
"""
