from PyQt6.QtWidgets import QStatusBar, QLabel, QProgressBar, QHBoxLayout, QWidget
from PyQt6.QtCore import Qt, QTimer


class StatusBarWidget(QStatusBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)

        self._status_label = QLabel("Ready")
        self._status_label.setStyleSheet("color: #AAAAAA; font-size: 12px; padding: 0 12px;")
        self.addWidget(self._status_label, 1)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedSize(120, 12)
        self._progress.setVisible(False)
        self._progress.setStyleSheet("""
            QProgressBar { background: #303134; border: none; border-radius: 6px; }
            QProgressBar::chunk { background: #3EA6FF; border-radius: 6px; }
        """)
        self.addPermanentWidget(self._progress)

    def show_message(self, message: str, timeout: int = 0):
        self._status_label.setText(message)
        if timeout > 0:
            QTimer.singleShot(timeout, lambda: self._status_label.setText("Ready"))

    def show_searching(self):
        self._status_label.setText("Searching...")
        self._progress.setVisible(True)

    def show_resolving(self):
        self._status_label.setText("Resolving stream...")
        self._progress.setVisible(True)

    def show_playing(self):
        self._status_label.setText("Playing")
        self._progress.setVisible(False)

    def show_ready(self):
        self._status_label.setText("Ready")
        self._progress.setVisible(False)

    def show_error(self, message: str):
        self._status_label.setStyleSheet("color: #FF5252; font-size: 12px; padding: 0 12px;")
        self._status_label.setText(message)
        self._progress.setVisible(False)
        QTimer.singleShot(5000, self._reset_style)

    def show_queue_count(self, count: int):
        self.show_message(f"Queue: {count} videos")

    def _reset_style(self):
        self._status_label.setStyleSheet("color: #AAAAAA; font-size: 12px; padding: 0 12px;")
        self._status_label.setText("Ready")
