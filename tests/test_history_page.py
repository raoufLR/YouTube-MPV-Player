"""History page duplicate handling, indicators, and live updates."""

from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QBuffer, QIODevice, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtTest import QSignalSpy

from core.events import ThumbnailLoadedEvent
from ui.pages.history_page import HistoryPage
from ui.thumbnail_pixmaps import pixmap_loader

pytestmark = pytest.mark.qt


@pytest.fixture
def thumbnail_service():
    return SimpleNamespace(load_thumbnail_data=lambda url: None)


@pytest.fixture
def page(qapp, event_bus, history_service, likes_service, playlist_service,
         thumbnail_service):
    widget = HistoryPage(
        history_service,
        SimpleNamespace(),
        thumbnail_service,
        event_bus,
        likes_service=likes_service,
        playlist_service=playlist_service,
    )
    yield widget, history_service, likes_service, playlist_service, event_bus
    widget.cleanup()
    widget.hide()


def _entry(video_id, title="Video", thumbnail="", duration=""):
    return {
        "id": video_id,
        "title": title,
        "channel": "Channel",
        "thumbnail": thumbnail,
        "duration": duration,
    }


def test_empty_history_shows_empty_state(page):
    widget, history, _, _, _ = page
    assert widget._list_widget.isHidden() is True
    assert widget._empty_label.isHidden() is False
    assert widget.clear_btn.isEnabled() is False


def test_entries_are_grouped_and_counted(page):
    widget, history, _, _, _ = page
    history.add(_entry("v1", "One"))
    history.add(_entry("v2", "Two"))
    widget._load_history()

    assert set(widget._items_by_id) == {"v1", "v2"}
    assert widget._list_widget.count() == 3  # header + two entries
    assert widget.clear_btn.isEnabled() is True
    assert widget._count_label.text() == "2 videos"


def test_replaying_video_does_not_duplicate_row(page):
    widget, history, _, _, _ = page
    history.add(_entry("v1", "One"))
    history.add(_entry("v2", "Two"))
    # Replay v1: the service moves the existing entry to the top and emits
    # "added".  The page must rebuild rather than insert a second row.
    history.add(_entry("v1", "One"))

    assert set(widget._items_by_id) == {"v1", "v2"}
    assert widget._list_widget.count() == 3
    assert widget._list_widget.item(1).data(
        Qt.ItemDataRole.UserRole
    )["id"] == "v1"


def test_like_and_watch_later_markers(page):
    widget, history, likes, playlists, _ = page
    history.add(_entry("v1", "One"))
    likes.like({"video_id": "v1"})
    playlists.toggle_watch_later({"videoId": "v1"})

    item = widget._items_by_id["v1"]
    assert HistoryPage.LIKE_MARK in item.text()
    assert HistoryPage.WL_MARK in item.text()

    likes.unlike("v1")
    assert HistoryPage.LIKE_MARK not in item.text()


def test_remove_entry_rebuilds_list(page):
    widget, history, _, _, _ = page
    history.add(_entry("v1"))
    history.add(_entry("v2"))

    history.remove("v1")
    assert set(widget._items_by_id) == {"v2"}


def test_clear_history_shows_empty_state(page):
    widget, history, _, _, _ = page
    history.add(_entry("v1"))
    history.clear()

    assert widget._items_by_id == {}
    assert widget._empty_label.isHidden() is False
    assert widget.clear_btn.isEnabled() is False


def test_double_click_emits_play(page):
    widget, history, _, _, _ = page
    history.add(_entry("v1", "One"))
    played = []
    widget.play_video_requested.connect(
        lambda vid, quality, data: played.append((vid, quality, data))
    )

    widget._on_item_double_clicked(widget._items_by_id["v1"])
    assert played and played[0][0] == "v1"
    assert played[0][2]["title"] == "One"


def test_section_header_is_not_playable(page):
    widget, history, _, _, _ = page
    history.add(_entry("v1"))
    header = widget._list_widget.item(0)
    played = []
    widget.play_video_requested.connect(
        lambda *args: played.append(args)
    )
    widget._on_item_double_clicked(header)
    assert played == []


def test_thumbnail_event_updates_item(page):
    widget, history, _, _, event_bus = page
    history.add(_entry("v1", thumbnail="https://thumb/history-1.jpg"))

    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.blue)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")

    spy = QSignalSpy(pixmap_loader().pixmap_ready)
    event_bus.publish(
        ThumbnailLoadedEvent(item="https://thumb/history-1.jpg", icon=bytes(buffer.data()))
    )

    assert spy.wait(2000)
    item = widget._items_by_id["v1"]
    assert not item.icon().isNull()


def test_list_fills_the_available_page_height(page):
    from PyQt6.QtCore import QCoreApplication

    widget, history, _, _, _ = page
    for index in range(8):
        history.add(_entry(f"v{index}", f"Video {index}"))

    widget.resize(900, 700)
    widget.show()
    for _ in range(5):
        QCoreApplication.processEvents()
    try:
        # A trailing stretch used to steal the space and leave the list at its
        # 192px size hint, clipping most rows on a 700px page.
        assert widget._list_widget.height() > 400
    finally:
        widget.hide()
