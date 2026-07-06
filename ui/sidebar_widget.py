from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import pyqtSignal, Qt, QSize

from ui import icons


class SidebarWidget(QWidget):
    page_changed = pyqtSignal(str)
    profile_clicked = pyqtSignal()

    NAV_SECTIONS = [
        ("Library", [
            ("home", "Home", icons.home),
            ("search", "Search", icons.search),
            ("history", "History", icons.history),
        ]),
        ("Playlists", [
            ("playlists", "Playlists", icons.playlist),
            ("liked", "Liked Videos", icons.liked_videos),
        ]),
    ]

    BOTTOM_ITEMS = [
        ("settings", "Settings", icons.settings),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(220)
        self.setObjectName("sidebar")
        self._buttons = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(0)

        title_container = QWidget()
        title_container.setFixedHeight(56)
        title_layout = QVBoxLayout(title_container)
        title_layout.setContentsMargins(16, 0, 16, 0)

        title = QLabel("YouTube MPV")
        title.setObjectName("sidebarTitle")
        title_layout.addWidget(title)
        layout.addWidget(title_container)

        layout.addSpacing(4)

        for section_name, items in self.NAV_SECTIONS:
            section_label = QLabel(section_name)
            section_label.setObjectName("sidebarSection")
            layout.addWidget(section_label)

            for key, label, icon_fn in items:
                btn = QPushButton(icon_fn(20), "  " + label)
                btn.setIconSize(QSize(20, 20))
                btn.setCheckable(True)
                btn.setFixedHeight(40)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setObjectName("navButton")
                btn.clicked.connect(lambda checked, k=key: self._on_nav_clicked(k))
                self._buttons[key] = btn
                layout.addWidget(btn)

        layout.addStretch()

        for key, label, icon_fn in self.BOTTOM_ITEMS:
            btn = QPushButton(icon_fn(20), "  " + label)
            btn.setIconSize(QSize(20, 20))
            btn.setCheckable(True)
            btn.setFixedHeight(40)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setObjectName("navButton")
            btn.clicked.connect(lambda checked, k=key: self._on_nav_clicked(k))
            self._buttons[key] = btn
            layout.addWidget(btn)

        self._profile_btn = QPushButton(icons.profile(20), "  Profile")
        self._profile_btn.setIconSize(QSize(20, 20))
        self._profile_btn.setFixedHeight(44)
        self._profile_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._profile_btn.setObjectName("profileButton")
        self._profile_btn.clicked.connect(self._on_profile_clicked)
        layout.addWidget(self._profile_btn)

        self.setLayout(layout)
        self._select_item("home")

    def _on_nav_clicked(self, key):
        self._select_item(key)
        self.page_changed.emit(key)

    def _on_profile_clicked(self):
        self.profile_clicked.emit()

    def _select_item(self, key):
        for k, btn in self._buttons.items():
            btn.setChecked(k == key)

    def set_active(self, key):
        self._select_item(key)
