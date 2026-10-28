import time
from typing import TYPE_CHECKING

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ui.avatar_widget import AvatarWidget
from ui.i18n import tr

if TYPE_CHECKING:
    from models import Profile


class ProfileManagerDialog(QDialog):
    profile_switched = pyqtSignal(str)

    def __init__(self, user_manager_service, parent=None):
        super().__init__(parent)
        self._user_manager = user_manager_service
        self._picked_name = None
        self.setWindowTitle(tr("Profile Manager"))
        self.setFixedSize(520, 450)
        self.setModal(True)
        self._setup_ui()
        self._refresh()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)

        title = QLabel(tr("Manage Profiles"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = QFont()
        f.setPointSize(14)
        f.setBold(True)
        title.setFont(f)
        layout.addWidget(title)

        self._list = QListWidget()
        self._list.setIconSize(QSize(50, 50))
        self._list.setSpacing(4)
        self._list.itemDoubleClicked.connect(self._on_switch)
        layout.addWidget(self._list, 1)

        btn_layout = QHBoxLayout()

        self._switch_btn = QPushButton(tr("Switch To"))
        self._switch_btn.clicked.connect(self._on_switch_selected)
        btn_layout.addWidget(self._switch_btn)

        self._create_btn = QPushButton(tr("Create"))
        self._create_btn.clicked.connect(self._on_create)
        btn_layout.addWidget(self._create_btn)

        self._rename_btn = QPushButton(tr("Rename"))
        self._rename_btn.clicked.connect(self._on_rename)
        btn_layout.addWidget(self._rename_btn)

        self._duplicate_btn = QPushButton(tr("Duplicate"))
        self._duplicate_btn.clicked.connect(self._on_duplicate)
        btn_layout.addWidget(self._duplicate_btn)

        self._delete_btn = QPushButton(tr("Delete"))
        self._delete_btn.setObjectName("dangerButton")
        self._delete_btn.clicked.connect(self._on_delete)
        btn_layout.addWidget(self._delete_btn)

        layout.addLayout(btn_layout)

        close_layout = QHBoxLayout()
        self._close_btn = QPushButton(tr("Close"))
        self._close_btn.clicked.connect(self.accept)
        close_layout.addStretch()
        close_layout.addWidget(self._close_btn)
        layout.addLayout(close_layout)

        self.setLayout(layout)

    def _refresh(self):
        self._list.clear()
        current = self._user_manager.current_profile_name() or ""
        profiles = self._user_manager.list_profiles()
        for p in profiles:
            self._add_profile_item(
                p, is_current=(p.name.casefold() == current.casefold())
            )

    def _add_profile_item(self, profile: Profile, is_current: bool = False):
        avatar = AvatarWidget(50)
        if profile.avatar and profile.avatar != "":
            avatar.set_image(profile.avatar)
        avatar.set_name(profile.name)

        last_opened = ""
        if profile.last_opened:
            try:
                t = time.localtime(profile.last_opened)
                last_opened = time.strftime("%Y-%m-%d %H:%M", t)
            except (OSError, ValueError):
                last_opened = ""

        suffix = tr(" (current)") if is_current else ""
        display = f"{profile.name}{suffix}"
        if last_opened:
            display += "\n" + tr("Last used: {time}").format(time=last_opened)

        item = QListWidgetItem(display)
        item.setData(Qt.ItemDataRole.UserRole, profile.name)
        item.setIcon(avatar.to_icon())
        self._list.addItem(item)

    def _on_switch(self, item):
        name = item.data(Qt.ItemDataRole.UserRole)
        if name:
            current = self._user_manager.current_profile_name() or ""
            if name.casefold() == str(current).casefold():
                QMessageBox.information(
                    self,
                    tr("Already Active"),
                    tr("Profile '{name}' is already active.").format(name=name),
                )
                return
            self._picked_name = name
            self.profile_switched.emit(name)
            self.accept()

    def _on_switch_selected(self):
        item = self._list.currentItem()
        if item:
            self._on_switch(item)

    def _on_create(self):
        name, ok = QInputDialog.getText(self, tr("Create Profile"), tr("Profile name:"))
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        profile = self._user_manager.create_profile(name)
        if profile is None:
            QMessageBox.warning(
                self,
                tr("Cannot Create Profile"),
                tr("A profile named '{name}' already exists or the name is invalid.").format(
                    name=name
                ),
            )
        self._refresh()

    def _on_rename(self):
        item = self._list.currentItem()
        if not item:
            QMessageBox.information(self, tr("Select"), tr("Select a profile to rename."))
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        if name and name.casefold() == "default":
            QMessageBox.warning(
                self, tr("Cannot Rename"), tr("The Default profile cannot be renamed.")
            )
            return
        if not name:
            return
        new_name, ok = QInputDialog.getText(
            self, tr("Rename Profile"), tr("New name:"), text=name
        )
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name or new_name == name:
            return
        if not self._user_manager.rename_profile(name, new_name):
            QMessageBox.warning(
                self,
                tr("Cannot Rename Profile"),
                tr("'{name}' is already in use or the name is invalid.").format(
                    name=new_name
                ),
            )
        self._refresh()

    def _on_duplicate(self):
        item = self._list.currentItem()
        if not item:
            QMessageBox.information(
                self, tr("Select"), tr("Select a profile to duplicate.")
            )
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        if not name:
            return
        new_name, ok = QInputDialog.getText(
            self,
            tr("Duplicate Profile"),
            tr("New profile name:"),
            text=tr("{name} (Copy)").format(name=name),
        )
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name:
            return
        if self._user_manager.duplicate_profile(name, new_name) is None:
            QMessageBox.warning(
                self,
                tr("Cannot Duplicate Profile"),
                tr("'{name}' is already in use or the profile could not be copied.").format(
                    name=new_name
                ),
            )
        self._refresh()

    def _on_delete(self):
        item = self._list.currentItem()
        if not item:
            QMessageBox.information(
                self, tr("Select"), tr("Select a profile to delete.")
            )
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        if name and name.casefold() == "default":
            QMessageBox.warning(
                self, tr("Cannot Delete"), tr("The Default profile cannot be deleted.")
            )
            return
        if not name:
            return
        current = self._user_manager.current_profile_name() or ""
        if name.casefold() == str(current).casefold():
            QMessageBox.warning(
                self,
                tr("In Use"),
                tr("Cannot delete the currently active profile. Switch first."),
            )
            return
        reply = QMessageBox.question(
            self,
            tr("Delete Profile"),
            tr("Delete profile '{name}'? All data will be lost.").format(name=name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if not self._user_manager.delete_profile(name):
                QMessageBox.warning(
                    self,
                    tr("Cannot Delete Profile"),
                    tr("Profile '{name}' could not be deleted.").format(name=name),
                )
            self._refresh()

    @staticmethod
    def open_manager(user_manager_service, parent=None):
        app = QApplication.instance()
        if not app:
            return None, False
        dialog = ProfileManagerDialog(user_manager_service, parent)
        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            return dialog._picked_name, True
        return None, False
