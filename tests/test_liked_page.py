"""Liked Videos page behaviour and live updates."""

from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QBuffer, QIODevice, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtTest import QSignalSpy

from services.likes_service import LikesService
from services.playlist_service import PlaylistService
from ui.pages.liked_page import LikedPage
from ui.thumbnail_pixmaps import cached_pixmap, pixmap_loader

pytestmark = pytest.mark.qt


@pytest.fixture
def thumbnail_service():
    return SimpleNamespace(load_thumbnail_data=lambda url: None)


@pytest.fixture
def page(qapp, event_bus, temp_dir, thumbnail_service):
    likes = LikesService(event_bus=event_bus, data_dir=temp_dir)
    playlists = PlaylistService(event_bus=event_bus, data_dir=temp_dir)
    widget = LikedPage(likes, playlists, thumbnail_service, event_bus)
    yield widget, likes, playlists
    widget.cleanup()
    widget.deleteLater()


def _like(likes_service, video_id, title=None, thumbnail=""):
    assert likes_service.like(
        {
            "video_id": video_id,
            "title": title or f"Video {video_id}",
            "channel": "Channel",
            "thumbnail": thumbnail,
        }
    )


def test_empty_state_is_shown(page):
    widget, likes, _ = page
    assert likes.count() == 0
    assert widget._empty_label.isHidden() is False
    assert widget._list_widget.isHidden() is True
    assert widget._count_label.text() == "0 videos"


def test_liked_videos_are_listed_newest_first(page):
    widget, likes, _ = page
    _like(likes, "v1", "First")
    _like(likes, "v2", "Second")
    widget.refresh()

    assert widget._list_widget.count() == 2
    assert widget._empty_label.isHidden() is True
    assert widget._count_label.text() == "2 videos"
    first = widget._list_widget.item(0)
    assert "Second" in first.text()
    assert first.data(Qt.ItemDataRole.UserRole)["video_id"] == "v2"
    assert set(widget._items) == {"v1", "v2"}


def test_double_click_plays_liked_video(page):
    widget, likes, _ = page
    _like(likes, "v1", "First")
    widget.refresh()

    played = []
    widget.play_video_requested.connect(
        lambda vid, quality, data: played.append((vid, quality, data))
    )
    widget._on_item_double_clicked(widget._list_widget.item(0))

    assert len(played) == 1
    assert played[0][0] == "v1"
    assert played[0][2]["title"] == "First"


def test_unlike_event_removes_row_live(page):
    widget, likes, _ = page
    _like(likes, "v1")
    widget.refresh()
    assert widget._list_widget.count() == 1

    likes.unlike("v1")
    assert widget._list_widget.count() == 0
    assert widget._empty_label.isHidden() is False


def test_like_event_adds_row_live(page):
    widget, likes, _ = page
    _like(likes, "v1")
    assert widget._list_widget.count() == 1
    assert widget._items.get("v1") is not None


def test_refresh_preserves_selection(page):
    widget, likes, _ = page
    _like(likes, "v1")
    _like(likes, "v2")
    widget.refresh()
    widget._list_widget.setCurrentItem(widget._list_widget.item(1))
    widget.refresh()

    current = widget._list_widget.currentItem()
    assert current is not None
    assert current.data(Qt.ItemDataRole.UserRole)["video_id"] == "v1"


def test_thumbnail_is_applied(page):
    widget, likes, _ = page
    url = "https://thumb/liked-1.jpg"
    _like(likes, "v1", thumbnail=url)
    widget.refresh()
    item = widget._list_widget.item(0)

    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.red)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    data = bytes(buffer.data())

    spy = QSignalSpy(pixmap_loader().pixmap_ready)
    widget._apply_thumbnail((data, url), item)

    assert spy.wait(2000)
    assert spy[0][0] == url
    assert not item.icon().isNull()
    assert cached_pixmap(url, *LikedPage.THUMBNAIL_SIZE) is not None


def test_cleanup_unsubscribes(page):
    widget, likes, _ = page
    widget.cleanup()
    _like(likes, "v1")
    # A cleaned-up page must not react to events.
    assert widget._list_widget.count() == 0


def test_list_fills_the_available_page_height(page):
    from PyQt6.QtCore import QCoreApplication

    widget, likes, _ = page
    for index in range(8):
        _like(likes, f"v{index}")

    widget.resize(900, 700)
    widget.show()
    for _ in range(5):
        QCoreApplication.processEvents()
    try:
        assert widget._list_widget.height() > 400
    finally:
        widget.hide()
