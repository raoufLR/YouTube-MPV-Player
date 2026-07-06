from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox, QSpinBox,
    QSlider, QLabel, QPushButton, QScrollArea, QLineEdit,
)
from PyQt6.QtCore import Qt, QTimer

from core.events import EVENT_SETTINGS_CHANGED
from ui import icons
from ui.themes import ThemeManager, THEME_REGISTRY


class SettingsPage(QWidget):
    def __init__(self, settings_service, event_bus, theme_manager: ThemeManager, parent=None):
        super().__init__(parent)
        self._settings_service = settings_service
        self._event_bus = event_bus
        self._theme_manager = theme_manager
        self._setting_up = False
        self._subscriptions = []

        self._setup_ui()
        self._connect_signals()
        self._load_settings()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(24, 20, 24, 8)

        title = QLabel("Settings")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 0, 24, 24)
        content_layout.setSpacing(12)

        content_layout.addWidget(self._make_playback_section())
        content_layout.addWidget(self._make_appearance_section())
        content_layout.addWidget(self._make_search_section())

        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        self.setLayout(layout)

    def _make_card(self, title: str, icon_fn=None) -> QWidget:
        card = QWidget()
        card.setObjectName("settingsCategoryCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 20)
        card_layout.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        if icon_fn:
            icon_label = QLabel()
            icon_label.setPixmap(icon_fn(20).pixmap(20, 20))
            header_row.addWidget(icon_label)
        section_title = QLabel(title)
        section_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #FFFFFF;")
        header_row.addWidget(section_title)
        header_row.addStretch()
        card_layout.addLayout(header_row)

        return card

    def _make_playback_section(self) -> QWidget:
        card = self._make_card("Playback")
        form = QFormLayout()
        form.setSpacing(12)
        form.setContentsMargins(0, 0, 0, 0)

        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["best", "1080p", "720p", "480p", "360p"])
        form.addRow("Default Quality:", self.quality_combo)

        self.speed_combo = QComboBox()
        for s in ["0.5", "0.75", "1.0", "1.25", "1.5", "1.75", "2.0"]:
            self.speed_combo.addItem(f"{s}x", float(s))
        form.addRow("Playback Speed:", self.speed_combo)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_label = QLabel("80")
        self.volume_label.setFixedWidth(30)
        self.volume_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        volume_row = QHBoxLayout()
        volume_row.addWidget(self.volume_slider, 1)
        volume_row.addWidget(self.volume_label)
        form.addRow("Default Volume:", volume_row)

        card.layout().addLayout(form)
        return card

    def _make_appearance_section(self) -> QWidget:
        card = self._make_card("Appearance")
        form = QFormLayout()
        form.setSpacing(12)
        form.setContentsMargins(0, 0, 0, 0)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(self._theme_manager.available_theme_names)
        form.addRow("Theme:", self.theme_combo)

        self.language_combo = QComboBox()
        self.language_combo.addItems(["en", "es", "fr", "de", "ja", "zh", "pt", "ru", "ar", "ko"])
        form.addRow("Language:", self.language_combo)

        card.layout().addLayout(form)
        return card

    def _make_search_section(self) -> QWidget:
        card = self._make_card("Search")
        form = QFormLayout()
        form.setSpacing(12)
        form.setContentsMargins(0, 0, 0, 0)

        self.results_spin = QSpinBox()
        self.results_spin.setRange(5, 100)
        self.results_spin.setSingleStep(5)
        form.addRow("Results per page:", self.results_spin)

        card.layout().addLayout(form)
        return card

    def _connect_signals(self):
        if self._event_bus:
            self._subscriptions = [(EVENT_SETTINGS_CHANGED, self._on_settings_changed)]
            for event_type, cb in self._subscriptions:
                self._event_bus.subscribe(event_type, cb, weak=False)

        self.quality_combo.currentTextChanged.connect(
            lambda v: self._on_change("default_quality", v)
        )
        self.speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        self.language_combo.currentTextChanged.connect(
            lambda v: self._on_change("language", v)
        )
        self.results_spin.valueChanged.connect(
            lambda v: self._on_change("search_results_count", v)
        )

    def cleanup(self):
        for event_type, cb in getattr(self, '_subscriptions', []):
            self._event_bus.unsubscribe(event_type, cb)
        self._subscriptions = []

    def _on_speed_changed(self, idx):
        speed = self.speed_combo.itemData(idx)
        if speed is not None:
            self._on_change("playback_speed", speed)

    def _on_volume_changed(self, val):
        self.volume_label.setText(str(val))
        self._on_change("volume", val)

    def _on_theme_changed(self, display_name: str):
        if self._setting_up:
            return
        theme_id = self._theme_manager.theme_id_for_display(display_name)
        self._theme_manager.switch_theme(theme_id)

    def _on_change(self, key, value):
        if self._setting_up:
            return
        self._settings_service.set(key, value)

    def _on_settings_changed(self, event):
        if event.key != "__reset__":
            self._load_settings()

    def _load_settings(self):
        self._setting_up = True
        settings = self._settings_service.get_all()
        quality = settings.get("default_quality", "720p")
        idx = self.quality_combo.findText(quality)
        if idx >= 0:
            self.quality_combo.setCurrentIndex(idx)

        speed = settings.get("playback_speed", 1.0)
        for i in range(self.speed_combo.count()):
            if abs(self.speed_combo.itemData(i) - speed) < 0.01:
                self.speed_combo.setCurrentIndex(i)
                break

        volume = settings.get("volume", 80)
        self.volume_slider.setValue(volume)
        self.volume_label.setText(str(volume))

        theme = settings.get("theme", "default")
        display_name = None
        for tid, cls in THEME_REGISTRY.items():
            if tid == theme:
                display_name = cls.display_name
                break
        if display_name:
            idx = self.theme_combo.findText(display_name)
            if idx >= 0:
                self.theme_combo.setCurrentIndex(idx)

        language = settings.get("language", "en")
        idx = self.language_combo.findText(language)
        if idx >= 0:
            self.language_combo.setCurrentIndex(idx)

        count = settings.get("search_results_count", 10)
        self.results_spin.setValue(count)

        self._setting_up = False