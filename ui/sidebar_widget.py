from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui import icons
from ui.app_icon import brand_pixmap
from ui.i18n import tr


class SidebarWidget(QWidget):
    page_changed = pyqtSignal(str)
    profile_clicked = pyqtSignal()
    collapsed_changed = pyqtSignal(bool)

    EXPANDED_WIDTH = 220
    COLLAPSED_WIDTH = 72

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
        self._collapsed = False
        self._buttons = {}
        self._labels = {}
        self._section_labels = []
        self._title_label = None
        self._profile_label = "Profile"
        self.setFixedWidth(self.EXPANDED_WIDTH)
        self.setObjectName("sidebar")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(0)

        title_container = QWidget()
        title_container.setFixedHeight(56)
        self._title_row = QHBoxLayout(title_container)
        self._title_row.setContentsMargins(*self._title_margins(False))
        self._title_row.setSpacing(10)

        self._logo_label = QLabel()
        self._logo_label.setPixmap(brand_pixmap(28))
        self._logo_label.setFixedSize(28, 28)
        self._logo_label.setAccessibleName("YouTube MPV Player")
        self._title_row.addWidget(self._logo_label)

        self._title_label = QLabel("YouTube MPV")
        self._title_label.setObjectName("sidebarTitle")
        self._title_row.addWidget(self._title_label)
        self._title_row.addStretch(1)
        layout.addWidget(title_container)

        layout.addSpacing(4)

        for section_name, items in self.NAV_SECTIONS:
            section_label = QLabel(tr(section_name))
            section_label.setObjectName("sidebarSection")
            self._section_labels.append(section_label)
            layout.addWidget(section_label)

            for key, label, icon_fn in items:
                btn = self._make_nav_button(key, label, icon_fn)
                layout.addWidget(btn)

        layout.addStretch()

        for key, label, icon_fn in self.BOTTOM_ITEMS:
            btn = self._make_nav_button(key, label, icon_fn)
            layout.addWidget(btn)

        self._profile_btn = QPushButton(icons.profile(20), "  " + tr(self._profile_label))
        self._profile_btn.setIconSize(QSize(20, 20))
        self._profile_btn.setFixedHeight(44)
        self._profile_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._profile_btn.setObjectName("profileButton")
        self._profile_btn.setToolTip(tr(self._profile_label))
        self._profile_btn.setAccessibleName(tr(self._profile_label))
        self._profile_btn.clicked.connect(self._on_profile_clicked)
        layout.addWidget(self._profile_btn)

        self.setLayout(layout)
        self._select_item("home")

    def _make_nav_button(self, key: str, label: str, icon_fn) -> QPushButton:
        btn = QPushButton(icon_fn(20), "  " + tr(label))
        btn.setIconSize(QSize(20, 20))
        btn.setCheckable(True)
        btn.setFixedHeight(40)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setObjectName("navButton")
        btn.setToolTip(tr(label))
        btn.setAccessibleName(tr(label))
        btn.clicked.connect(lambda checked, k=key: self._on_nav_clicked(k))
        self._buttons[key] = btn
        self._labels[key] = label
        return btn

    @staticmethod
    def _title_margins(collapsed: bool) -> tuple[int, int, int, int]:
        """Keep the logo centred in the narrow rail when the labels hide."""
        return (22, 0, 0, 0) if collapsed else (16, 0, 16, 0)

    def set_collapsed(self, collapsed: bool):
        """Switch between the full sidebar and the icons-only rail."""
        collapsed = bool(collapsed)
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self.setFixedWidth(
            self.COLLAPSED_WIDTH if collapsed else self.EXPANDED_WIDTH
        )
        self.setProperty("collapsed", collapsed)
        self.style().unpolish(self)
        self.style().polish(self)
        for button in [*self._buttons.values(), self._profile_btn]:
            button.style().unpolish(button)
            button.style().polish(button)

        self._title_row.setContentsMargins(*self._title_margins(collapsed))
        self._title_label.setVisible(not collapsed)
        for section_label in self._section_labels:
            section_label.setVisible(not collapsed)
        for key, label in self._labels.items():
            self._buttons[key].setText("" if collapsed else "  " + tr(label))
        self._profile_btn.setText("" if collapsed else "  " + tr(self._profile_label))
        self.collapsed_changed.emit(collapsed)

    def is_collapsed(self) -> bool:
        return self._collapsed

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

    def clear_selection(self):
        """Deselect all navigation items (e.g. while watching a video)."""
        for btn in self._buttons.values():
            btn.setChecked(False)
