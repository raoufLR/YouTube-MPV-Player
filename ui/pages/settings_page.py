from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.events import (
    EVENT_SETTINGS_CHANGED,
    EVENT_UPDATE_AVAILABLE,
    EVENT_UPDATE_COMPLETED,
    EVENT_UPDATE_FAILED,
    EVENT_UPDATE_UP_TO_DATE,
)
from ui.event_dispatcher import QtEventDispatcher
from ui.i18n import tr
from ui.themes import THEME_REGISTRY, ThemeManager


class SettingsPage(QWidget):
    def __init__(self, settings_service, event_bus, theme_manager: ThemeManager,
                 update_service=None, data_import_service=None, parent=None):
        super().__init__(parent)
        self._settings_service = settings_service
        self._event_bus = event_bus
        self._theme_manager = theme_manager
        self._update_service = update_service
        self._data_import_service = data_import_service
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

        title = QLabel(tr("Settings"))
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
        content_layout.addWidget(self._make_updates_section())
        content_layout.addWidget(self._make_data_management_section())
        content_layout.addWidget(self._make_shortcuts_section())

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
        section_title.setObjectName("settingsSectionTitle")
        header_row.addWidget(section_title)
        header_row.addStretch()
        card_layout.addLayout(header_row)

        return card

    def _make_playback_section(self) -> QWidget:
        card = self._make_card(tr("Playback"))
        form = QFormLayout()
        form.setSpacing(12)
        form.setContentsMargins(0, 0, 0, 0)

        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["best", "1080p", "720p", "480p", "360p"])
        form.addRow(tr("Default Quality:"), self.quality_combo)

        self.speed_combo = QComboBox()
        for s in ["0.5", "0.75", "1.0", "1.25", "1.5", "1.75", "2.0"]:
            self.speed_combo.addItem(f"{s}x", float(s))
        form.addRow(tr("Playback Speed:"), self.speed_combo)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_label = QLabel("80")
        self.volume_label.setFixedWidth(30)
        self.volume_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        volume_row = QHBoxLayout()
        volume_row.addWidget(self.volume_slider, 1)
        volume_row.addWidget(self.volume_label)
        form.addRow(tr("Default Volume:"), volume_row)

        card.layout().addLayout(form)
        return card

    def _make_appearance_section(self) -> QWidget:
        card = self._make_card(tr("Appearance"))
        form = QFormLayout()
        form.setSpacing(12)
        form.setContentsMargins(0, 0, 0, 0)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(self._theme_manager.available_theme_names)
        form.addRow(tr("Theme:"), self.theme_combo)

        self.language_combo = QComboBox()
        self.language_combo.addItems(["en", "es", "fr", "de", "ja", "zh", "pt", "ru", "ar", "ko"])
        form.addRow(tr("Language:"), self.language_combo)

        card.layout().addLayout(form)
        return card

    def _make_search_section(self) -> QWidget:
        card = self._make_card(tr("Search"))
        form = QFormLayout()
        form.setSpacing(12)
        form.setContentsMargins(0, 0, 0, 0)

        self.results_spin = QSpinBox()
        self.results_spin.setRange(5, 100)
        self.results_spin.setSingleStep(5)
        form.addRow(tr("Results per page:"), self.results_spin)

        card.layout().addLayout(form)
        return card

    def _make_updates_section(self) -> QWidget:
        """Update-status card: auto-check toggle, refresh, and apply."""
        card = self._make_card(tr("yt-dlp Updates"))
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        self.update_auto_check = QCheckBox(tr("Check for updates automatically"))
        self.update_auto_check.setChecked(
            bool(self._settings_service.get("auto_update_check", True))
        )
        self.update_auto_check.toggled.connect(self._on_auto_update_toggled)
        layout.addWidget(self.update_auto_check)

        self.update_status_label = QLabel(self._initial_update_hint())
        self.update_status_label.setObjectName("updateStatus")
        self.update_status_label.setWordWrap(True)
        layout.addWidget(self.update_status_label)

        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(8)

        self.update_check_button = QPushButton(tr("Check now"))
        self.update_check_button.setEnabled(self._update_service is not None)
        self.update_check_button.clicked.connect(self._on_check_updates_now)
        buttons_row.addWidget(self.update_check_button)

        self.update_install_button = QPushButton(tr("Install update"))
        self.update_install_button.setEnabled(False)
        self.update_install_button.clicked.connect(self._on_install_update)
        buttons_row.addWidget(self.update_install_button)

        buttons_row.addStretch()
        layout.addLayout(buttons_row)
        card.layout().addLayout(layout)
        return card

    def _initial_update_hint(self) -> str:
        if self._update_service is None:
            return tr("yt-dlp updates unavailable (service not loaded)")
        state = self._update_service
        if state.is_installed:
            hint = tr("yt-dlp updated copy installed ({version})").format(
                version=state.installed_version or tr("unknown version")
            )
        else:
            hint = tr("yt-dlp is running from the bundled copy")
        if state.latest_seen_version:
            hint += tr(" \u2014 last seen release: {version}").format(
                version=state.latest_seen_version
            )
        return hint

    def _set_update_error(self, is_error: bool):
        label = self.update_status_label
        if bool(label.property("error")) == bool(is_error):
            return
        label.setProperty("error", bool(is_error))
        label.style().unpolish(label)
        label.style().polish(label)
        label.update()

    def _on_check_updates_now(self):
        if self._update_service is None:
            return
        self._set_update_error(False)
        self.update_status_label.setText(tr("Checking for updates..."))
        self._update_service.check_in_background(force=True, auto_apply=False)

    def _on_install_update(self):
        if self._update_service is None:
            return
        self._set_update_error(False)
        self.update_status_label.setText(tr("Downloading update..."))
        self._update_service.check_in_background(force=True, auto_apply=True)

    def _on_auto_update_toggled(self, checked: bool):
        if self._setting_up:
            return
        self._on_change("auto_update_check", bool(checked))

    def _reset_update_buttons(self, *, install_enabled: bool):
        self.update_check_button.setEnabled(True)
        self.update_install_button.setEnabled(install_enabled)

    def _on_update_available(self, event):
        self._reset_update_buttons(install_enabled=True)
        self._set_update_error(False)
        current = event.current_version or tr("unknown")
        self.update_status_label.setText(
            tr("yt-dlp {latest} is available (current: {current})").format(
                latest=event.latest_version, current=current
            )
        )

    def _on_update_completed(self, event):
        self._reset_update_buttons(install_enabled=False)
        self._set_update_error(False)
        self.update_status_label.setText(
            tr("yt-dlp updated to {version} \u2014 takes effect immediately").format(
                version=event.version
            )
        )

    def _on_update_up_to_date(self, event):
        self._reset_update_buttons(install_enabled=False)
        self._set_update_error(False)
        self.update_status_label.setText(
            tr("yt-dlp {version} is up to date").format(version=event.version)
        )

    def _on_update_failed(self, event):
        self._reset_update_buttons(install_enabled=False)
        self._set_update_error(True)
        self.update_status_label.setText(
            tr("Update failed ({stage}): {error}").format(
                stage=event.stage, error=event.error or tr("unknown error")
            )
        )

    def _make_data_management_section(self) -> QWidget:
        """Card for local data management and Google Takeout import."""
        card = self._make_card(tr("Google Takeout & Data Import"))
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        desc = QLabel(
            tr(
                "Import your YouTube playlists, liked videos, watch history, and "
                "subscriptions directly from a Google Takeout archive (.zip or "
                "folder) without signing into an account."
            )
        )
        desc.setWordWrap(True)
        desc.setObjectName("settingsDescription")
        layout.addWidget(desc)

        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(10)

        self.import_takeout_button = QPushButton(tr("Import from Google Takeout..."))
        self.import_takeout_button.setObjectName("primaryButton")
        self.import_takeout_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_takeout_button.setEnabled(self._data_import_service is not None)
        self.import_takeout_button.clicked.connect(self._on_import_takeout_clicked)
        buttons_row.addWidget(self.import_takeout_button)

        self.guide_button = QPushButton(tr("💡 How to get Takeout file? (دليل المبتدئين)"))
        self.guide_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.guide_button.clicked.connect(self._on_guide_clicked)
        buttons_row.addWidget(self.guide_button)

        buttons_row.addStretch()
        layout.addLayout(buttons_row)
        card.layout().addLayout(layout)
        return card

    def _on_import_takeout_clicked(self):
        if self._data_import_service is None:
            return
        from ui.takeout_import_dialog import TakeoutImportDialog

        dlg = TakeoutImportDialog(self._data_import_service, self)
        dlg.exec()

    def _on_guide_clicked(self):
        from ui.takeout_import_dialog import TakeoutGuideDialog

        dlg = TakeoutGuideDialog(self)
        dlg.exec()

    def _make_shortcuts_section(self) -> QWidget:
        card = self._make_card(tr("Keyboard Shortcuts"))
        form = QFormLayout()
        form.setSpacing(8)
        form.setContentsMargins(0, 0, 0, 0)

        shortcuts = [
            ("Play / Pause", "Space"),
            ("Stop Playback", "Esc"),
            ("Seek Backward / Forward", "Left / Right Arrow (±10s)"),
            ("Volume Up / Down", "Up / Down Arrow (±5%)"),
        ]

        for action, key in shortcuts:
            key_label = QLabel(key)
            key_label.setObjectName("shortcutKey")
            form.addRow(tr(action) + ":", key_label)

        card.layout().addLayout(form)
        return card

    def _connect_signals(self):
        if self._event_bus:
            self._subscriptions = [(EVENT_SETTINGS_CHANGED, self._on_settings_changed)]
            if self._update_service is not None:
                # Updates publish from a worker thread; QtEventDispatcher
                # queues the callbacks onto the UI thread.
                self._subscriptions += [
                    (EVENT_UPDATE_AVAILABLE, QtEventDispatcher(self._on_update_available)),
                    (EVENT_UPDATE_COMPLETED, QtEventDispatcher(self._on_update_completed)),
                    (EVENT_UPDATE_UP_TO_DATE, QtEventDispatcher(self._on_update_up_to_date)),
                    (EVENT_UPDATE_FAILED, QtEventDispatcher(self._on_update_failed)),
                ]
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

        auto_update = settings.get("auto_update_check", True)
        self.update_auto_check.setChecked(bool(auto_update))

        self._setting_up = False