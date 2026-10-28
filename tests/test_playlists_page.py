"""Playlist page playback, selection preservation, and state markers."""

from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt

from ui.pages.playlists_page import PlaylistsPage

pytestmark = pytest.mark.qt


@pytest.fixture
def thumbnail_service():
    return SimpleNamespace(load_thumbnail_data=lambda url: None)


@pytest.fixture
def page(qapp, event_bus, playlist_service, likes_service, thumbnail_service):
    widget = PlaylistsPage(
        SimpleNamespace(),
        thumbnail_service,
        playlist_service,
        event_bus,
        likes_service=likes_service,
    )
    yield widget, playlist_service, likes_service, event_bus
    widget.cleanup()
    widget.hide()


def _make_playlist(service, name="Rock"):
    playlist = service.create_playlist(name)
    assert playlist is not None
    return playlist


def _select(widget, playlist_id):
    for row in range(widget._playlist_list.count()):
        item = widget._playlist_list.item(row)
        if item.data(Qt.ItemDataRole.UserRole) == playlist_id:
            widget._playlist_list.setCurrentItem(item)
            return item
    raise AssertionError(f"playlist {playlist_id} not listed")


def test_playlist_videos_use_video_id_key(page):
    widget, playlists, _, _ = page
    playlist = _make_playlist(playlists)
    playlists.add_video(
        playlist.id,
        {"video_id": "vid123", "title": "Song", "channel": "Band"},
    )

    _select(widget, playlist.id)

    assert widget._video_list.count() == 1
    data = widget._video_list.item(0).data(Qt.ItemDataRole.UserRole)
    assert data["video_id"] == "vid123"


def test_double_click_plays_playlist_video(page):
    widget, playlists, _, _ = page
    playlist = _make_playlist(playlists)
    playlists.add_video(
        playlist.id, {"video_id": "vid123", "title": "Song", "channel": "Band"}
    )
    _select(widget, playlist.id)

    played = []
    widget.play_video_requested.connect(
        lambda vid, quality, data: played.append((vid, quality, data))
    )
    widget._on_video_double_clicked(widget._video_list.item(0))

    assert played and played[0][0] == "vid123"
    assert played[0][2]["title"] == "Song"


def test_playlist_selection_survives_reload(page):
    widget, playlists, _, _ = page
    first = _make_playlist(playlists, "First")
    second = _make_playlist(playlists, "Second")
    _select(widget, first.id)

    playlists.add_video(
        first.id, {"video_id": "vid1", "title": "One", "channel": "C"}
    )

    assert widget._current_playlist_id == first.id
    current = widget._playlist_list.currentItem()
    assert current is not None
    assert current.data(Qt.ItemDataRole.UserRole) == first.id
    assert widget._video_list.count() == 1
    assert second.id in {
        widget._playlist_list.item(i).data(Qt.ItemDataRole.UserRole)
        for i in range(widget._playlist_list.count())
    }


def test_video_selection_survives_reload(page):
    widget, playlists, _, _ = page
    playlist = _make_playlist(playlists)
    playlists.add_video(
        playlist.id, {"video_id": "vid1", "title": "One", "channel": "C"}
    )
    playlists.add_video(
        playlist.id, {"video_id": "vid2", "title": "Two", "channel": "C"}
    )
    _select(widget, playlist.id)
    widget._video_list.setCurrentRow(1)

    widget._load_videos(playlist.id)

    current = widget._video_list.currentItem()
    assert current is not None
    assert current.data(Qt.ItemDataRole.UserRole)["video_id"] == "vid2"


def test_watch_later_playlist_updates_on_toggle(page):
    widget, playlists, _, _ = page
    _select(widget, "watch-later")
    assert widget._video_list.count() == 0

    playlists.toggle_watch_later({"videoId": "vid9", "title": "Later"})

    assert widget._current_playlist_id == "watch-later"
    assert set(widget._video_items) == {"vid9"}


def test_like_marker_updates_existing_row(page):
    widget, playlists, likes, _ = page
    playlist = _make_playlist(playlists)
    playlists.add_video(
        playlist.id, {"video_id": "vid1", "title": "One", "channel": "C"}
    )
    _select(widget, playlist.id)

    likes.like({"video_id": "vid1"})
    item = widget._video_items["vid1"]
    assert PlaylistsPage.LIKE_MARK in item.text()

    likes.unlike("vid1")
    assert PlaylistsPage.LIKE_MARK not in item.text()


def test_create_duplicate_playlist_warns(page, monkeypatch):
    widget, playlists, _, _ = page
    _make_playlist(playlists, "Rock")

    warnings = []
    monkeypatch.setattr(
        "ui.pages.playlists_page.QInputDialog.getText",
        lambda *args, **kwargs: ("Rock", True),
    )
    monkeypatch.setattr(
        "ui.pages.playlists_page.QMessageBox.warning",
        lambda *args, **kwargs: warnings.append(args[2] if len(args) > 2 else ""),
    )

    widget._on_create()
    assert warnings and "already exists" in warnings[0]


def test_missing_playlist_shows_unknown_title(page):
    widget, playlists, _, _ = page
    widget._load_videos("does-not-exist")
    assert widget._playlist_title.text() == "Unknown Playlist"
