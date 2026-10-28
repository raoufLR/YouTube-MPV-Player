"""Focus-aware playback shortcuts.

Space and the arrow keys must type/navigate normally in text fields, lists,
sliders and buttons.  They are handled by an application event filter instead
of window-level ``QShortcut`` objects.
"""

import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSlider,
    QWidget,
)

from ui import shortcuts
from ui.shortcuts import (
    PlaybackShortcutFilter,
    is_navigation_widget,
    is_text_input,
    is_value_input,
    should_handle_key,
)

pytestmark = pytest.mark.qt

ARROWS_AND_SPACE = (
    Qt.Key.Key_Space,
    Qt.Key.Key_Left,
    Qt.Key.Key_Right,
    Qt.Key.Key_Up,
    Qt.Key.Key_Down,
)


@pytest.mark.parametrize(
    "widget_factory",
    [QLineEdit, QListWidget, QComboBox, QSlider, QPushButton],
)
def test_keys_are_not_stolen_from_interactive_widgets(qapp, widget_factory):
    widget = widget_factory()
    for key in ARROWS_AND_SPACE:
        assert should_handle_key(key, widget) is False


def test_escape_is_left_to_text_fields_but_stops_playback_elsewhere(qapp):
    line_edit = QLineEdit()
    assert should_handle_key(Qt.Key.Key_Escape, line_edit) is False
    assert should_handle_key(Qt.Key.Key_Escape, QWidget()) is True


def test_plain_widget_receives_playback_keys(qapp):
    widget = QWidget()
    for key in ARROWS_AND_SPACE:
        assert should_handle_key(key, widget) is True
    assert should_handle_key(Qt.Key.Key_Return, widget) is False


def test_widget_classification_helpers(qapp):
    assert is_text_input(QLineEdit())
    assert is_value_input(QSlider())
    assert is_value_input(QComboBox())
    assert is_value_input(QPushButton())
    assert is_navigation_widget(QListWidget())
    assert not is_text_input(QWidget())


class _FakeApplication:
    active_modal = None
    focus = None

    @classmethod
    def activeModalWidget(cls):
        return cls.active_modal

    @classmethod
    def focusWidget(cls):
        return cls.focus


def _key_event(key, autorepeat=False):
    return QKeyEvent(
        QEvent.Type.KeyPress,
        key,
        Qt.KeyboardModifier.NoModifier,
        "",
        autorepeat,
    )


@pytest.fixture
def fake_app(monkeypatch, qapp):
    monkeypatch.setattr(shortcuts, "QApplication", _FakeApplication)
    _FakeApplication.active_modal = None
    _FakeApplication.focus = QWidget()
    return _FakeApplication


def test_filter_emits_transport_signals(fake_app, qapp):
    filter_ = PlaybackShortcutFilter()
    received = []
    filter_.play_pause_requested.connect(lambda: received.append("play"))
    filter_.stop_requested.connect(lambda: received.append("stop"))
    filter_.seek_requested.connect(lambda delta: received.append(("seek", delta)))
    filter_.volume_requested.connect(
        lambda delta: received.append(("volume", delta))
    )

    cases = [
        (Qt.Key.Key_Space, "play"),
        (Qt.Key.Key_Escape, "stop"),
        (Qt.Key.Key_Left, ("seek", -10)),
        (Qt.Key.Key_Right, ("seek", 10)),
        (Qt.Key.Key_Up, ("volume", 5)),
        (Qt.Key.Key_Down, ("volume", -5)),
    ]
    for key, expected in cases:
        assert filter_.eventFilter(None, _key_event(key)) is True
        assert received[-1] == expected


def test_filter_ignores_text_field_and_consumes_repeats(fake_app, qapp):
    filter_ = PlaybackShortcutFilter()
    emitted = []
    filter_.play_pause_requested.connect(lambda: emitted.append("play"))
    filter_.stop_requested.connect(lambda: emitted.append("stop"))
    _FakeApplication.focus = QLineEdit()

    assert filter_.eventFilter(None, _key_event(Qt.Key.Key_Space)) is False
    assert filter_.eventFilter(None, _key_event(Qt.Key.Key_Escape)) is False
    assert emitted == []

    _FakeApplication.focus = QWidget()
    assert (
        filter_.eventFilter(None, _key_event(Qt.Key.Key_Space, autorepeat=True))
        is True
    )
    assert emitted == []


def test_filter_yields_to_modal_dialogs(fake_app, qapp):
    filter_ = PlaybackShortcutFilter()
    emitted = []
    filter_.stop_requested.connect(lambda: emitted.append("stop"))
    _FakeApplication.active_modal = object()

    assert filter_.eventFilter(None, _key_event(Qt.Key.Key_Escape)) is False
    assert emitted == []


def test_filter_ignores_modified_keys(fake_app, qapp):
    filter_ = PlaybackShortcutFilter()
    emitted = []
    filter_.play_pause_requested.connect(lambda: emitted.append("play"))

    event = QKeyEvent(
        QEvent.Type.KeyPress,
        Qt.Key.Key_Space,
        Qt.KeyboardModifier.ControlModifier,
    )
    assert filter_.eventFilter(None, event) is False
    assert emitted == []
