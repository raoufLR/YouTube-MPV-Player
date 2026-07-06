import time

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QInputDialog,
    QApplication,
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QFont

from models import Profile
from ui.avatar_widget import AvatarWidget


class ProfileManagerDialog(QDialog):
    profile_switched = pyqtSignal(str)

    def __init__(self, user_manager_service, parent=None):
        super().__init__(parent)
        self._user_manager = user_manager_service
        self._picked_name = None
        self.setWindowTitle("Profile Manager")
        self.setFixedSize(520, 450)
        self.setModal(True)
        self._setup_ui()
        self._refresh()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)

        title = QLabel("Manage Profiles")
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

        self._switch_btn = QPushButton("Switch To")
        self._switch_btn.clicked.connect(self._on_switch_selected)
        btn_layout.addWidget(self._switch_btn)

        self._create_btn = QPushButton("Create")
        self._create_btn.clicked.connect(self._on_create)
        btn_layout.addWidget(self._create_btn)

        self._rename_btn = QPushButton("Rename")
        self._rename_btn.clicked.connect(self._on_rename)
        btn_layout.addWidget(self._rename_btn)

        self._duplicate_btn = QPushButton("Duplicate")
        self._duplicate_btn.clicked.connect(self._on_duplicate)
        btn_layout.addWidget(self._duplicate_btn)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setObjectName("dangerButton")
        self._delete_btn.clicked.connect(self._on_delete)
        btn_layout.addWidget(self._delete_btn)

        layout.addLayout(btn_layout)

        close_layout = QHBoxLayout()
        self._close_btn = QPushButton("Close")
        self._close_btn.clicked.connect(self.accept)
        close_layout.addStretch()
        close_layout.addWidget(self._close_btn)
        layout.addLayout(close_layout)

        self.setLayout(layout)

    def _refresh(self):
        self._list.clear()
        current = self._user_manager.current_profile_name()
        profiles = self._user_manager.list_profiles()
        for p in profiles:
            self._add_profile_item(p, is_current=(p.name == current))

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

        suffix = " (current)" if is_current else ""
        display = f"{profile.name}{suffix}"
        if last_opened:
            display += f"\nLast used: {last_opened}"

        item = QListWidgetItem(display)
        item.setData(Qt.ItemDataRole.UserRole, profile.name)
        item.setIcon(avatar.to_icon())
        self._list.addItem(item)

    def _on_switch(self, item):
        name = item.data(Qt.ItemDataRole.UserRole)
        if name:
            current = self._user_manager.current_profile_name()
            if name == current:
                QMessageBox.information(self, "Already Active", f"Profile '{name}' is already active.")
                return
            self._picked_name = name
            self.profile_switched.emit(name)
            self.accept()

    def _on_switch_selected(self):
        item = self._list.currentItem()
        if item:
            self._on_switch(item)

    def _on_create(self):
        name, ok = QInputDialog.getText(self, "Create Profile", "Profile name:")
        if ok and name.strip():
            p = self._user_manager.create_profile(name.strip())
            if p is None:
                QMessageBox.warning(self, "Error", f"Cannot create profile '{name}'.")
            self._refresh()

    def _on_rename(self):
        item = self._list.currentItem()
        if not item:
            QMessageBox.information(self, "Select", "Select a profile to rename.")
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        if name and name.lower() == "default":
            QMessageBox.warning(self, "Cannot Rename", "The Default profile cannot be renamed.")
            return
        if name:
            new_name, ok = QInputDialog.getText(self, "Rename Profile", "New name:", text=name)
            if ok and new_name.strip() and new_name.strip() != name:
                self._user_manager.rename_profile(name, new_name.strip())
                self._refresh()

    def _on_duplicate(self):
        item = self._list.currentItem()
        if not item:
            QMessageBox.information(self, "Select", "Select a profile to duplicate.")
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        if name:
            new_name, ok = QInputDialog.getText(
                self, "Duplicate Profile", "New profile name:", text=f"{name} (Copy)"
            )
            if ok and new_name.strip():
                self._user_manager.duplicate_profile(name, new_name.strip())
                self._refresh()

    def _on_delete(self):
        item = self._list.currentItem()
        if not item:
            QMessageBox.information(self, "Select", "Select a profile to delete.")
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        if name and name.lower() == "default":
            QMessageBox.warning(self, "Cannot Delete", "The Default profile cannot be deleted.")
            return
        if name:
            current = self._user_manager.current_profile_name()
            if name == current:
                QMessageBox.warning(self, "In Use", "Cannot delete the currently active profile. Switch first.")
                return
            reply = QMessageBox.question(
                self, "Delete Profile",
                f"Delete profile '{name}'? All data will be lost.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._user_manager.delete_profile(name)
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
