from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLineEdit, QPushButton, QComboBox, QLabel,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QKeySequence, QShortcut

from ui import icons
from ui.avatar_widget import AvatarWidget


class HeaderWidget(QWidget):
    search_requested = pyqtSignal(str)

    def __init__(self, user_manager_service=None, parent=None):
        super().__init__(parent)
        self._user_manager = user_manager_service
        self.setObjectName("searchHeader")
        self.setFixedHeight(52)

        self._setup_ui()
        self._setup_shortcuts()

    def _setup_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(10)

        search_container = QWidget()
        search_container.setFixedWidth(420)
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)

        self._search_icon = QPushButton()
        self._search_icon.setIcon(icons.search(18))
        self._search_icon.setObjectName("iconButton")
        self._search_icon.setFixedSize(32, 32)
        self._search_icon.setCursor(Qt.CursorShape.ArrowCursor)
        search_layout.addWidget(self._search_icon)

        self._search_input = QLineEdit()
        self._search_input.setObjectName("searchInput")
        self._search_input.setPlaceholderText("Search YouTube or paste URL...")
        self._search_input.returnPressed.connect(self._on_search)
        search_layout.addWidget(self._search_input, 1)

        self._clear_btn = QPushButton()
        self._clear_btn.setIcon(icons.clear(16))
        self._clear_btn.setObjectName("iconButton")
        self._clear_btn.setFixedSize(32, 32)
        self._clear_btn.setVisible(False)
        self._clear_btn.clicked.connect(self._on_clear)
        search_layout.addWidget(self._clear_btn)

        self._search_input.textChanged.connect(
            lambda t: self._clear_btn.setVisible(bool(t))
        )

        layout.addWidget(search_container)
        layout.addStretch()

        quality_label = QLabel("Quality:")
        quality_label.setStyleSheet("color: #888888; font-size: 11px; font-weight: 500;")
        layout.addWidget(quality_label)

        self._quality_combo = QComboBox()
        self._quality_combo.addItems(["best", "1080p", "720p", "480p", "360p"])
        self._quality_combo.setCurrentText("720p")
        layout.addWidget(self._quality_combo)

        self._avatar = AvatarWidget(32)
        self._avatar.set_name("U")
        layout.addWidget(self._avatar)

        self.setLayout(layout)

    def _setup_shortcuts(self):
        self._focus_shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
        self._focus_shortcut.activated.connect(self._focus_search)
        self._focus_shortcut2 = QShortcut(QKeySequence("Ctrl+E"), self)
        self._focus_shortcut2.activated.connect(self._focus_search)
        self._esc_shortcut = QShortcut(QKeySequence("Escape"), self)
        self._esc_shortcut.activated.connect(self._on_clear)

    def _focus_search(self):
        self._search_input.setFocus()
        self._search_input.selectAll()

    def _on_search(self):
        query = self._search_input.text().strip()
        if query:
            self.search_requested.emit(query)

    def _on_clear(self):
        self._search_input.clear()

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
