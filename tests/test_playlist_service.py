import pytest

from core.events import PlaylistCreatedEvent, PlaylistUpdatedEvent, PlaylistDeletedEvent, WatchLaterToggledEvent


class TestPlaylistService:
    def test_create_playlist(self, playlist_service, event_bus):
        events = []
        event_bus.subscribe("playlist_created", events.append, weak=False)
        pl = playlist_service.create_playlist("My Playlist", "Description")
        assert pl is not None
        assert pl.name == "My Playlist"
        assert pl.description == "Description"
        assert len(events) == 1
        assert isinstance(events[0], PlaylistCreatedEvent)
        assert events[0].playlist_name == "My Playlist"

    def test_create_duplicate_name_returns_none(self, playlist_service):
        playlist_service.create_playlist("My Playlist")
        pl = playlist_service.create_playlist("My Playlist")
        assert pl is None

    def test_rename_playlist(self, playlist_service):
        pl = playlist_service.create_playlist("Old Name")
        result = playlist_service.rename_playlist(pl.id, "New Name")
        assert result is True
        renamed = playlist_service.get_playlist(pl.id)
        assert renamed.name == "New Name"

    def test_rename_watch_later_fails(self, playlist_service):
        result = playlist_service.rename_playlist("watch-later", "New Name")
        assert result is False

    def test_delete_playlist(self, playlist_service, event_bus):
        events = []
        event_bus.subscribe("playlist_deleted", events.append, weak=False)
        pl = playlist_service.create_playlist("To Delete")
        result = playlist_service.delete_playlist(pl.id)
        assert result is True
        assert playlist_service.get_playlist(pl.id) is None
        assert len(events) == 1
        assert isinstance(events[0], PlaylistDeletedEvent)

    def test_delete_watch_later_fails(self, playlist_service):
        result = playlist_service.delete_playlist("watch-later")
        assert result is False

    def test_get_all_playlists_includes_watch_later(self, playlist_service):
        playlists = playlist_service.get_all_playlists()
        names = [p.name for p in playlists]
        assert "Watch Later" in names

    def test_add_video(self, playlist_service):
        pl = playlist_service.create_playlist("Videos")
        video_data = {
            "videoId": "abc123",
            "title": "Test Video",
            "channel": "Test Channel",
            "thumbnail": "http://example.com/thumb.jpg",
        }
        result = playlist_service.add_video(pl.id, video_data)
        assert result is True
        videos = playlist_service.get_videos(pl.id)
        assert len(videos) == 1
        assert videos[0]["video_id"] == "abc123"

    def test_add_duplicate_video_fails(self, playlist_service):
        pl = playlist_service.create_playlist("Videos")
        video_data = {"videoId": "abc123"}
        playlist_service.add_video(pl.id, video_data)
        result = playlist_service.add_video(pl.id, video_data)
        assert result is False

    def test_remove_video(self, playlist_service):
        pl = playlist_service.create_playlist("Videos")
        playlist_service.add_video(pl.id, {"videoId": "abc123"})
        result = playlist_service.remove_video(pl.id, "abc123")
        assert result is True
        assert len(playlist_service.get_videos(pl.id)) == 0

    def test_has_video(self, playlist_service):
        pl = playlist_service.create_playlist("Videos")
        playlist_service.add_video(pl.id, {"videoId": "abc123"})
        assert playlist_service.has_video(pl.id, "abc123") is True
        assert playlist_service.has_video(pl.id, "nonexistent") is False

    def test_watch_later_toggle_add(self, playlist_service, event_bus):
        events = []
        event_bus.subscribe("watch_later_toggled", events.append, weak=False)
        video_data = {"videoId": "wl1", "title": "Watch Later Video"}
        result = playlist_service.toggle_watch_later(video_data)
        assert result is True
        assert playlist_service.is_in_watch_later("wl1") is True
        assert len(events) == 1
        assert isinstance(events[0], WatchLaterToggledEvent)
        assert events[0].video_id == "wl1"
        assert events[0].is_watch_later is True

    def test_watch_later_toggle_remove(self, playlist_service, event_bus):
        video_data = {"videoId": "wl1", "title": "Watch Later Video"}
        playlist_service.toggle_watch_later(video_data)
        events = []
        event_bus.subscribe("watch_later_toggled", events.append, weak=False)
        result = playlist_service.toggle_watch_later(video_data)
        assert result is False
        assert playlist_service.is_in_watch_later("wl1") is False
        assert len(events) == 1
        assert isinstance(events[0], WatchLaterToggledEvent)
        assert events[0].is_watch_later is False

    def test_count(self, playlist_service):
        playlist_service.create_playlist("P1")
        playlist_service.create_playlist("P2")
        assert playlist_service.count() >= 3  # includes Watch Later

    def test_export_all(self, playlist_service):
        playlist_service.create_playlist("Export Test")
        data = playlist_service.export_all()
        assert "watch-later" in data
        assert any(d["name"] == "Export Test" for d in data.values())

    def test_reset_clears_non_watch_later(self, playlist_service):
        pl = playlist_service.create_playlist("To Remove")
        playlist_service.reset()
        assert playlist_service.get_playlist("watch-later") is not None
        assert playlist_service.get_playlist(pl.id) is None
