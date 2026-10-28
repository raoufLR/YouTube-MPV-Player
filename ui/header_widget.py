from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from core.events import EVENT_SETTINGS_CHANGED
from ui import icons
from ui.avatar_widget import AvatarWidget
from ui.event_dispatcher import QtEventDispatcher
from ui.i18n import tr


class HeaderWidget(QWidget):
    search_requested = pyqtSignal(str)

    def __init__(self, user_manager_service=None, parent=None, *,
                 settings_service=None, event_bus=None):
        super().__init__(parent)
        self._user_manager = user_manager_service
        self._settings_service = settings_service
        self._event_bus = event_bus
        self._settings_subscription = None
        self._settings_dispatcher = None
        self.setObjectName("searchHeader")
        self.setFixedHeight(52)

        self._setup_ui()
        self._setup_shortcuts()
        self._connect_settings()

    def _setup_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(10)

        search_container = QWidget()
        # Wide windows keep the familiar 420px pill; narrow ones let the field
        # shrink instead of pushing the quality selector out of the header.
        search_container.setMinimumWidth(200)
        search_container.setMaximumWidth(420)
        search_container.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)

        self._search_icon = QPushButton()
        self._search_icon.setIcon(icons.search(18))
        self._search_icon.setObjectName("iconButton")
        self._search_icon.setFixedSize(32, 32)
        self._search_icon.setCursor(Qt.CursorShape.ArrowCursor)
        self._search_icon.setToolTip(tr("Search"))
        self._search_icon.setAccessibleName(tr("Search"))
        self._search_icon.clicked.connect(self._on_search)
        search_layout.addWidget(self._search_icon)

        self._search_input = QLineEdit()
        self._search_input.setObjectName("searchInput")
        self._search_input.setMinimumWidth(80)
        self._search_input.setPlaceholderText(
            tr("Search YouTube or paste URL...")
        )
        self._search_input.setAccessibleName(tr("Search YouTube or paste URL"))
        self._search_input.returnPressed.connect(self._on_search)
        self._search_input.installEventFilter(self)
        search_layout.addWidget(self._search_input, 1)

        self._clear_btn = QPushButton()
        self._clear_btn.setIcon(icons.clear(16))
        self._clear_btn.setObjectName("iconButton")
        self._clear_btn.setFixedSize(32, 32)
        self._clear_btn.setVisible(False)
        self._clear_btn.setToolTip(tr("Clear search"))
        self._clear_btn.setAccessibleName(tr("Clear search"))
        self._clear_btn.clicked.connect(self._on_clear)
        search_layout.addWidget(self._clear_btn)

        self._search_input.textChanged.connect(
            lambda t: self._clear_btn.setVisible(bool(t))
        )

        layout.addWidget(search_container)
        layout.addStretch()

        quality_label = QLabel(tr("Quality:"))
        quality_label.setObjectName("qualityLabel")
        layout.addWidget(quality_label)

        self._quality_combo = QComboBox()
        self._quality_combo.addItems(["best", "1080p", "720p", "480p", "360p"])
        self._quality_combo.setAccessibleName(tr("Default video quality"))
        self._quality_combo.setToolTip(tr("Default video quality"))
        self._load_quality()
        self._quality_combo.currentTextChanged.connect(self._on_quality_changed)
        layout.addWidget(self._quality_combo)

        self._avatar = AvatarWidget(32)
        self._avatar.set_name("U")
        self._avatar.setAccessibleName(tr("Profile"))
        layout.addWidget(self._avatar)

        self.setLayout(layout)

    def _setup_shortcuts(self):
        self._focus_shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
        self._focus_shortcut.activated.connect(self._focus_search)
        self._focus_shortcut2 = QShortcut(QKeySequence("Ctrl+E"), self)
        self._focus_shortcut2.activated.connect(self._focus_search)

    def _connect_settings(self):
        if self._event_bus is None:
            return
        self._settings_dispatcher = QtEventDispatcher(self._on_settings_changed)
        self._settings_subscription = self._event_bus.subscribe(
            EVENT_SETTINGS_CHANGED,
            self._settings_dispatcher,
            weak=False,
        )

    def _load_quality(self):
        quality = "720p"
        if self._settings_service is not None:
            quality = self._settings_service.get("default_quality", quality)
        self.set_quality(quality)

    def _on_quality_changed(self, quality: str):
        if self._settings_service is not None:
            self._settings_service.set("default_quality", quality)

    def _on_settings_changed(self, event):
        key = getattr(event, "key", "")
        if key not in ("default_quality", "__reset__"):
            return
        if key == "default_quality":
            quality = getattr(event, "value", None)
        elif self._settings_service is not None:
            quality = self._settings_service.get("default_quality", "720p")
        else:
            quality = None
        if not quality:
            return
        self._quality_combo.blockSignals(True)
        self.set_quality(quality)
        self._quality_combo.blockSignals(False)

    def cleanup(self):
        if self._settings_subscription is not None:
            self._settings_subscription.cancel()
            self._settings_subscription = None
        self._settings_dispatcher = None

    def eventFilter(self, obj, event):
        # Escape owns the search box: clear the query instead of stopping
        # playback.  A window-level Escape shortcut previously conflicted with
        # the global stop shortcut (ambiguous activation).
        if (
            obj is self._search_input
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Escape
        ):
            self._on_clear()
            return True
        return super().eventFilter(obj, event)

    def _focus_search(self):
        self._search_input.setFocus()
        self._search_input.selectAll()

    def _on_search(self):
        query = self._search_input.text().strip()
        if query:
            self.search_requested.emit(query)

    def _on_clear(self):
        self._search_input.clear()
        self._search_input.setFocus()

    def current_quality(self) -> str:
        return self._quality_combo.currentText()

    def set_quality(self, quality: str):
        idx = self._quality_combo.findText(quality)
        if idx >= 0:
            self._quality_combo.setCurrentIndex(idx)

    def set_profile_avatar(self, name: str, avatar_path: str = ""):
        self._avatar.set_name(name)
        if avatar_path:
            self._avatar.set_image(avatar_path)
