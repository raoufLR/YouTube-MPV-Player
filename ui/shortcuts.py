"""Focus-aware playback shortcuts.

Single-key shortcuts (Space, arrows, Escape) must never steal keystrokes from
text fields, spin boxes, combo boxes, sliders, buttons, or item views.  A
plain ``QShortcut`` on the main window would intercept Space even while the
user is typing a search query, so playback keys are handled by an application
event filter that inspects the focused widget first.
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSlider,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
)

TEXT_INPUT_TYPES = (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)
VALUE_INPUT_TYPES = (QComboBox, QAbstractSlider, QAbstractButton)
NAVIGATION_TYPES = (QAbstractItemView,)

PLAYBACK_KEYS = frozenset(
    {
        Qt.Key.Key_Space,
        Qt.Key.Key_Left,
        Qt.Key.Key_Right,
        Qt.Key.Key_Up,
        Qt.Key.Key_Down,
        Qt.Key.Key_Escape,
        Qt.Key.Key_F,
        Qt.Key.Key_F11,
    }
)


def is_text_input(widget: object) -> bool:
    """Return ``True`` when *widget* accepts typed text."""
    return isinstance(widget, TEXT_INPUT_TYPES)


def is_value_input(widget: object) -> bool:
    """Return ``True`` for widgets where a key press changes a value."""
    return isinstance(widget, VALUE_INPUT_TYPES)


def is_navigation_widget(widget: object) -> bool:
    """Return ``True`` for list/tree/table widgets that use arrow keys."""
    return isinstance(widget, NAVIGATION_TYPES)


def should_handle_key(key: int, focus_widget: object) -> bool:
    """Return ``True`` when *key* should control playback.

    Escape stops playback unless the user is typing, in which case the
    focused field (for example the search box) owns Escape and clears itself.
    Space and the arrow keys are only claimed when focus is not on a widget
    that needs those keys for editing or navigation.
    """
    if key == Qt.Key.Key_Escape:
        return not is_text_input(focus_widget)
    if key not in PLAYBACK_KEYS:
        return False
    if is_text_input(focus_widget):
        return False
    if is_value_input(focus_widget):
        return False
    return not is_navigation_widget(focus_widget)


class PlaybackShortcutFilter(QObject):
    """Application event filter that emits playback intents.

    The filter is intentionally transport-agnostic: it emits signals and lets
    ``MainWindow`` decide which service to call.
    """

    play_pause_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    seek_requested = pyqtSignal(int)
    volume_requested = pyqtSignal(int)
    fullscreen_requested = pyqtSignal()

    SEEK_STEP_SECONDS = 10
    VOLUME_STEP = 5

    def eventFilter(self, obj: object, event: QEvent) -> bool:  # noqa: N802
        if event.type() != QEvent.Type.KeyPress:
            return False

        # A modal dialog owns Escape and its own key handling.
        if QApplication.activeModalWidget() is not None:
            return False

        if event.modifiers() & (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.MetaModifier
        ):
            return False

        key = event.key()
        if key not in PLAYBACK_KEYS:
            return False

        if not should_handle_key(key, QApplication.focusWidget()):
            return False

        # Escape and Space should act once per press; arrow keys may repeat so
        # holding them seeks/volumes continuously.
        if event.isAutoRepeat() and key in (
            Qt.Key.Key_Escape,
            Qt.Key.Key_Space,
            Qt.Key.Key_F,
            Qt.Key.Key_F11,
        ):
            return True

        if key in (Qt.Key.Key_F, Qt.Key.Key_F11):
            self.fullscreen_requested.emit()
            return True
        if key == Qt.Key.Key_Escape:
            self.stop_requested.emit()
            return True
        if key == Qt.Key.Key_Space:
            self.play_pause_requested.emit()
            return True
        if key == Qt.Key.Key_Left:
            self.seek_requested.emit(-self.SEEK_STEP_SECONDS)
            return True
        if key == Qt.Key.Key_Right:
            self.seek_requested.emit(self.SEEK_STEP_SECONDS)
            return True
        if key == Qt.Key.Key_Up:
            self.volume_requested.emit(self.VOLUME_STEP)
            return True
        if key == Qt.Key.Key_Down:
            self.volume_requested.emit(-self.VOLUME_STEP)
            return True
        return False
