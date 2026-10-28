from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QStatusBar, QWidget

from ui.i18n import tr


class StatusBarWidget(QStatusBar):
    """Status bar whose delayed resets cannot clobber newer messages."""

    error_retry_requested = pyqtSignal()
    open_in_browser_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self._generation = 0

        # Own the reset timer: a bare ``QTimer.singleShot`` outlives the status
        # bar and later touches deleted labels, which PyQt turns into a
        # process abort.
        self._reset_generation = 0
        self._reset_timer = QTimer(self)
        self._reset_timer.setSingleShot(True)
        self._reset_timer.timeout.connect(self._on_reset_timeout)

        self._left_container = QWidget()
        self._left_layout = QHBoxLayout(self._left_container)
        self._left_layout.setContentsMargins(0, 0, 0, 0)
        self._left_layout.setSpacing(8)

        self._status_label = QLabel(tr("Ready"))
        self._status_label.setObjectName("statusLabel")
        self._left_layout.addWidget(self._status_label, 1)

        self._retry_btn = QPushButton(tr("Retry"))
        self._retry_btn.setObjectName("statusActionButton")
        self._retry_btn.setAccessibleName(tr("Retry playback"))
        self._retry_btn.setVisible(False)
        self._retry_btn.clicked.connect(lambda: self.error_retry_requested.emit())
        self._left_layout.addWidget(self._retry_btn)

        self._browser_btn = QPushButton(tr("Open in Browser"))
        self._browser_btn.setObjectName("statusActionButton")
        self._browser_btn.setAccessibleName(tr("Open in Browser"))
        self._browser_btn.setVisible(False)
        self._browser_btn.clicked.connect(lambda: self.open_in_browser_requested.emit())
        self._left_layout.addWidget(self._browser_btn)

        self.addWidget(self._left_container, 1)

        self._progress = QProgressBar()
        self._progress.setObjectName("statusProgress")
        self._progress.setRange(0, 0)
        self._progress.setFixedSize(120, 12)
        self._progress.setVisible(False)
        self._progress.setAccessibleName(tr("Loading"))
        self.addPermanentWidget(self._progress)

    # ------------------------------------------------------------------
    # Message plumbing
    # ------------------------------------------------------------------

    def _begin_message(self) -> int:
        self._generation += 1
        self._set_error_state(False)
        return self._generation

    def _set_error_state(self, is_error: bool):
        label = self._status_label
        is_error = bool(is_error)
        if bool(label.property("error")) == is_error:
            return
        label.setProperty("error", is_error)
        label.style().unpolish(label)
        label.style().polish(label)
        label.update()

    def _apply_if_current(self, generation: int, text: str,
                          is_error: bool = False, show_actions: bool = False) -> bool:
        if generation != self._generation:
            return False
        self._set_error_state(is_error)
        self._status_label.setText(text)
        self._retry_btn.setVisible(show_actions)
        self._browser_btn.setVisible(show_actions)
        return True

    def _reset_if_current(self, generation: int):
        self._apply_if_current(generation, tr("Ready"), is_error=False, show_actions=False)

    def _arm_reset(self, timeout: int, generation: int):
        self._reset_generation = generation
        self._reset_timer.start(timeout)

    def _on_reset_timeout(self):
        self._reset_if_current(self._reset_generation)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_message(self, message: str, timeout: int = 0):
        generation = self._begin_message()
        self._status_label.setText(message)
        if timeout > 0:
            self._arm_reset(timeout, generation)

    def show_searching(self):
        self._begin_message()
        self._status_label.setText(tr("Searching..."))
        self._progress.setVisible(True)

    def show_resolving(self):
        self._begin_message()
        self._status_label.setText(tr("Resolving stream..."))
        self._progress.setVisible(True)

    def show_playing(self):
        generation = self._begin_message()
        self._apply_if_current(generation, tr("Playing"), is_error=False, show_actions=False)
        self._progress.setVisible(False)

    def show_ready(self):
        generation = self._begin_message()
        self._apply_if_current(generation, tr("Ready"), is_error=False, show_actions=False)
        self._progress.setVisible(False)

    def show_error(self, message: str, allow_actions: bool = False):
        generation = self._begin_message()
        self._apply_if_current(generation, message, is_error=True, show_actions=allow_actions)
        self._progress.setVisible(False)
        self._arm_reset(8000, generation)

    def show_queue_count(self, count: int):
        self.show_message(tr("Queue: {count} videos").format(count=count))

    def current_message(self) -> str:
        return self._status_label.text()
