from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGridLayout, QScrollArea, QFileDialog,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont

from ui.avatar_widget import AvatarWidget
from ui import icons


class StatCard(QWidget):
    def __init__(self, value: str, label: str, parent=None):
        super().__init__(parent)
        self.setObjectName("profileStatsCard")
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        v = QLabel(value)
        v.setObjectName("statValue")
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(v)

        l = QLabel(label)
        l.setObjectName("statLabel")
        l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(l)

        self.setLayout(layout)


class ProfilePage(QWidget):
    def __init__(self, user_manager_service, history_service, likes_service,
                 playlist_service, parent=None):
        super().__init__(parent)
        self._user_manager = user_manager_service
        self._history_service = history_service
        self._likes_service = likes_service
        self._playlist_service = playlist_service

        self._setup_ui()
        self._load_profile()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 20, 24, 24)
        content_layout.setSpacing(24)

        header = QHBoxLayout()
        header.setSpacing(20)

        self._avatar = AvatarWidget(80)
        header.addWidget(self._avatar)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        self._name_label = QLabel("Profile")
        self._name_label.setStyleSheet("font-size: 22px; font-weight: 700; color: #FFFFFF;")
        info_layout.addWidget(self._name_label)

        self._change_avatar_btn = QPushButton("Change Avatar")
        self._change_avatar_btn.setObjectName("iconButton")
        self._change_avatar_btn.setFixedHeight(36)
        self._change_avatar_btn.clicked.connect(self._on_change_avatar)
        info_layout.addWidget(self._change_avatar_btn)

        info_layout.addStretch()
        header.addLayout(info_layout, 1)
        content_layout.addLayout(header)

        stats_grid = QGridLayout()
        stats_grid.setSpacing(12)

        self._watched_card = StatCard("0", "Videos Watched")
        stats_grid.addWidget(self._watched_card, 0, 0)

        self._likes_card = StatCard("0", "Liked Videos")
        stats_grid.addWidget(self._likes_card, 0, 1)

        self._playlists_card = StatCard("0", "Playlists")
        stats_grid.addWidget(self._playlists_card, 0, 2)

        self._wl_card = StatCard("0", "Watch Later")
        stats_grid.addWidget(self._wl_card, 0, 3)

        content_layout.addLayout(stats_grid)

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        self.setLayout(layout)

    def _load_profile(self):
        profile = self._user_manager.current_profile()
        if profile:
            self._name_label.setText(profile.name)
            self._avatar.set_name(profile.name)
            if profile.avatar:
                self._avatar.set_image(profile.avatar)

        watched = self._history_service.count()
        self._watched_card.findChildren(QLabel, "statValue")[0].setText(str(watched))

        likes = self._likes_service.count()
        self._likes_card.findChildren(QLabel, "statValue")[0].setText(str(likes))

        playlists = self._playlist_service.count()
        self._playlists_card.findChildren(QLabel, "statValue")[0].setText(str(playlists))

        wl = len(self._playlist_service.get_watch_later())
        self._wl_card.findChildren(QLabel, "statValue")[0].setText(str(wl))

    def _on_change_avatar(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Avatar", "", "Images (*.png *.jpg *.jpeg *.webp)"
        )
        if path:
            profile = self._user_manager.current_profile()
            if profile:
                self._user_manager.set_profile_avatar(profile.name, path)
                self._avatar.set_image(path)
