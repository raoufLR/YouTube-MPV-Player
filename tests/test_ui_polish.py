"""Sidebar collapse mode and seek-slider hover preview."""

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QSignalSpy
from PyQt6.QtWidgets import QToolTip

from ui.now_playing_bar import SeekSlider, format_time
from ui.sidebar_widget import SidebarWidget

pytestmark = pytest.mark.qt


def test_sidebar_collapses_to_an_icon_rail(qapp):
    sidebar = SidebarWidget()
    spy = QSignalSpy(sidebar.collapsed_changed)
    try:
        sidebar.set_collapsed(True)

        assert sidebar.is_collapsed()
        assert sidebar.width() == SidebarWidget.COLLAPSED_WIDTH
        assert sidebar.property("collapsed") is True
        assert sidebar._buttons["home"].text() == ""
        assert sidebar._buttons["home"].toolTip() == "Home"
        assert sidebar._profile_btn.text() == ""
        assert sidebar._title_label.isHidden()
        assert all(label.isHidden() for label in sidebar._section_labels)
        assert spy[0][0] is True

        sidebar.set_collapsed(False)

        assert not sidebar.is_collapsed()
        assert sidebar.width() == SidebarWidget.EXPANDED_WIDTH
        assert sidebar.property("collapsed") is False
        assert sidebar._buttons["home"].text().strip() == "Home"
        assert not sidebar._title_label.isHidden()
        assert all(not label.isHidden() for label in sidebar._section_labels)
        assert spy[1][0] is False
    finally:
        sidebar.hide()


def test_sidebar_keeps_the_brand_logo_when_collapsed(qapp):
    sidebar = SidebarWidget()
    try:
        assert not sidebar._logo_label.pixmap().isNull()
        assert sidebar._title_row.contentsMargins().left() == 16

        sidebar.set_collapsed(True)

        assert not sidebar._logo_label.isHidden()
        assert sidebar._title_row.contentsMargins().left() == 22

        sidebar.set_collapsed(False)

        assert not sidebar._logo_label.isHidden()
        assert sidebar._title_row.contentsMargins().left() == 16
    finally:
        sidebar.hide()


def test_sidebar_collapse_is_idempotent(qapp):
    sidebar = SidebarWidget()
    spy = QSignalSpy(sidebar.collapsed_changed)
    try:
        sidebar.set_collapsed(False)
        assert len(spy) == 0

        sidebar.set_collapsed(True)
        sidebar.set_collapsed(True)
        assert len(spy) == 1
    finally:
        sidebar.hide()


def test_seek_slider_previews_target_time(qapp, monkeypatch):
    previews = []
    monkeypatch.setattr(
        QToolTip,
        "showText",
        lambda pos, text, widget: previews.append((pos, text)),
    )

    slider = SeekSlider()
    slider.setRange(0, 200)
    slider.resize(200, 20)

    event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(100, 10),
        QPointF(100, 10),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    slider.mouseMoveEvent(event)

    assert previews
    assert previews[-1][1] == format_time(100)
    slider.hide()


def test_seek_slider_skips_preview_when_disabled(qapp, monkeypatch):
    previews = []
    monkeypatch.setattr(
        QToolTip,
        "showText",
        lambda pos, text, widget: previews.append(text),
    )

    slider = SeekSlider()
    slider.setRange(0, 200)
    slider.resize(200, 20)
    slider.setEnabled(False)

    event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(100, 10),
        QPointF(100, 10),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    slider.mouseMoveEvent(event)

    assert previews == []
    slider.hide()
