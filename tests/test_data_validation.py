"""Milestone 4: data, profile, and settings integrity tests."""

import json
import os
import re

import pytest

from core.data_bundle import DATA_SCHEMA_VERSION, build_bundle, validate_bundle
from models import Playlist, Profile, UserProfile
from models.user_settings import SETTINGS_SCHEMA_VERSION
from services.history_service import HistoryService
from services.likes_service import LikesService
from services.playlist_service import PlaylistService
from services.settings_service import SettingsService
from services.user_manager_service import UserManagerService
from services.user_profile_service import PROFILE_FILENAME, UserProfileService


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle)


def _read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _raise_os_error(_data):
    raise OSError("simulated disk failure")


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class TestSettingsValidation:
    def test_load_sanitizes_invalid_values_and_repairs_file(self, temp_dir):
        path = os.path.join(temp_dir, "settings.json")
        _write_json(path, {
            "volume": "loud",
            "playback_speed": 99,
            "search_results_count": -3,
            "thumbnail_size": 0,
            "default_quality": "4k",
            "auto_play_next": "yes",
            "theme": 7,
            "language": None,
            "window_width": "wide",
            "window_height": -5,
            "window_x": "x",
            "window_y": None,
            "__version__": 2,
            "custom_flag": {"nested": True},
        })

        service = SettingsService(data_dir=temp_dir)
        try:
            assert service.get("volume") == 80
            assert service.get("playback_speed") == 4.0
            assert service.get("search_results_count") == 1
            assert service.get("thumbnail_size") == 32
            assert service.get("default_quality") == "720p"
            assert service.get("auto_play_next") is True
            assert service.get("theme") == "default"
            assert service.get("language") == "en"
            assert service.get("window_width") == 900
            assert service.get("window_height") == 200
            assert service.get("window_x") == 100
            assert service.get("window_y") == 100
            assert service.get("custom_flag") == {"nested": True}
            assert service._dirty is True

            service._flush_if_dirty()
            repaired = _read_json(path)
            assert repaired["volume"] == 80
            assert repaired["playback_speed"] == 4.0
            assert repaired["__version__"] == SETTINGS_SCHEMA_VERSION
            assert repaired["custom_flag"] == {"nested": True}
        finally:
            service.shutdown()

    def test_set_clamps_and_publishes_normalized_value(self, settings_service, event_bus):
        events = []
        event_bus.subscribe("settings_changed", events.append, weak=False)

        settings_service.set("volume", 150)
        assert settings_service.get("volume") == 100
        assert events[-1].value == 100

        settings_service.set("playback_speed", "not-a-number")
        assert settings_service.get("playback_speed") == 1.0
        assert events[-1].value == 1.0

        # Unknown values remain forward-compatible and are not coerced.
        settings_service.set("theme", "light")
        assert settings_service.get("theme") == "light"

    def test_failed_flush_keeps_dirty_until_write_succeeds(
        self, settings_service, monkeypatch
    ):
        path = os.path.join(settings_service._filepath)
        settings_service.set("volume", 33)

        original_save = settings_service._store.save
        monkeypatch.setattr(settings_service._store, "save", _raise_os_error)

        settings_service._flush_if_dirty()
        assert settings_service._dirty is True
        assert settings_service.get("volume") == 33
        assert not os.path.exists(path)

        monkeypatch.setattr(settings_service._store, "save", original_save)
        settings_service._flush_if_dirty()

        assert settings_service._dirty is False
        assert _read_json(path)["volume"] == 33

    def test_import_rejects_non_mapping_and_ignores_schema_key(self, settings_service):
        assert settings_service.import_data(["not", "a", "mapping"]) is False

        assert settings_service.import_data({
            "__version__": 999,
            "volume": "bad",
            "custom": 1,
        }) is True
        assert settings_service.get("volume") == 80
        assert settings_service.get("custom") == 1
        assert settings_service.export()["__version__"] == SETTINGS_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


class TestHistoryValidation:
    def test_load_sanitizes_entries_and_repairs_file(self, temp_dir):
        path = os.path.join(temp_dir, "history.json")
        _write_json(path, [
            {
                "id": "v1",
                "title": 5,
                "channel": None,
                "thumbnail": "thumb.jpg",
                "watched_at": "bad",
                "extra": "drop me",
            },
            "junk",
            {"videoId": "v2", "title": "Two"},
            {"id": "v1", "title": "duplicate"},
            {"id": "bad id!", "title": "unsafe"},
            {"id": "", "title": "empty"},
        ])

        service = HistoryService(data_dir=temp_dir)
        try:
            entries = service.get_all()
            assert [entry["id"] for entry in entries] == ["v1", "v2"]
            assert entries[0]["title"] == ""
            assert entries[0]["channel"] == ""
            assert entries[0]["watched_at"] > 0
            assert entries[1]["title"] == "Two"
            assert service._dirty is True

            service._flush_if_dirty()
            repaired = _read_json(path)
            assert [entry["id"] for entry in repaired] == ["v1", "v2"]
            assert set(repaired[0]) == {
                "id", "title", "channel", "thumbnail", "watched_at"
            }
        finally:
            service.shutdown()

    def test_add_rejects_unsafe_ids_without_events(self, history_service, event_bus):
        events = []
        event_bus.subscribe("history_updated", events.append, weak=False)

        assert history_service.add({"id": ""}) is False
        assert history_service.add({"id": "../escape"}) is False
        assert history_service.add("not a mapping") is False

        assert history_service.count() == 0
        assert events == []

    def test_failed_flush_keeps_dirty_until_write_succeeds(
        self, history_service, monkeypatch
    ):
        history_service.add({"id": "v1"})
        original_save = history_service._store.save
        monkeypatch.setattr(history_service._store, "save", _raise_os_error)

        history_service._flush_if_dirty()
        assert history_service._dirty is True

        monkeypatch.setattr(history_service._store, "save", original_save)
        history_service._flush_if_dirty()
        assert history_service._dirty is False

    def test_import_rejects_non_list_and_deduplicates(self, history_service):
        assert history_service.import_data({"id": "v1"}) == -1
        count = history_service.import_data([
            {"id": "v1"},
            {"id": "v1"},
            {"id": "v2"},
            {"id": "bad id"},
        ])
        assert count == 2
        assert [entry["id"] for entry in history_service.get_all()] == ["v1", "v2"]


# ---------------------------------------------------------------------------
# Likes
# ---------------------------------------------------------------------------


class TestLikesValidation:
    def test_load_sanitizes_entries(self, temp_dir):
        path = os.path.join(temp_dir, "likes.json")
        _write_json(path, [
            {"video_id": "v1", "title": 5},
            {"videoId": "v2", "title": "Two"},
            {"video_id": "v1", "title": "duplicate"},
            {"video_id": "bad id"},
            "junk",
        ])

        service = LikesService(data_dir=temp_dir)

        assert [entry["video_id"] for entry in service.export()] == ["v1", "v2"]
        assert service.export()[0]["title"] == ""
        assert service.export()[1]["title"] == "Two"

    def test_like_write_failure_leaves_memory_unchanged(
        self, likes_service, monkeypatch
    ):
        monkeypatch.setattr(likes_service._store, "save", _raise_os_error)

        assert likes_service.like({"videoId": "v1"}) is False
        assert likes_service.is_liked("v1") is False
        assert likes_service.count() == 0

    def test_unlike_write_failure_leaves_like_in_place(
        self, likes_service, monkeypatch
    ):
        assert likes_service.like({"videoId": "v1"}) is True
        monkeypatch.setattr(likes_service._store, "save", _raise_os_error)

        assert likes_service.unlike("v1") is False
        assert likes_service.is_liked("v1") is True

    def test_import_rejects_non_list(self, likes_service):
        assert likes_service.import_data({"video_id": "v1"}) is False
        assert likes_service.count() == 0


# ---------------------------------------------------------------------------
# Playlists
# ---------------------------------------------------------------------------


class TestPlaylistValidation:
    def test_load_sanitizes_videos_and_reindexes(self, temp_dir):
        playlists_dir = os.path.join(temp_dir, "playlists")
        _write_json(os.path.join(playlists_dir, "pl1.json"), {
            "id": "stale-id",
            "name": "Mix",
            "description": 5,
            "videos": [
                {"video_id": "v1", "title": 5, "position": 99},
                {"videoId": "v2", "position": -1},
                {"video_id": "v1", "title": "duplicate"},
                "junk",
                {"video_id": "bad id"},
                {"title": "missing id"},
            ],
        })

        service = PlaylistService(data_dir=temp_dir)

        playlist = service.get_playlist("pl1")
        assert playlist is not None
        assert playlist.name == "Mix"
        assert playlist.description == ""
        assert [video["video_id"] for video in service.get_videos("pl1")] == [
            "v1", "v2"
        ]
        assert [video["position"] for video in service.get_videos("pl1")] == [0, 1]
        assert service.get_videos("pl1")[0]["title"] == ""

    def test_duplicate_playlist_names_are_recovered_and_persisted(self, temp_dir):
        playlists_dir = os.path.join(temp_dir, "playlists")
        _write_json(os.path.join(playlists_dir, "aaa.json"), {
            "name": "Same", "videos": [],
        })
        _write_json(os.path.join(playlists_dir, "bbb.json"), {
            "name": "Same", "videos": [],
        })

        service = PlaylistService(data_dir=temp_dir)
        names = sorted(playlist.name for playlist in service.get_all_playlists())

        assert "Same" in names
        assert any(name.startswith("Same (") for name in names)
        persisted = _read_json(os.path.join(playlists_dir, "bbb.json"))
        assert persisted["name"].startswith("Same (")

    def test_watch_later_metadata_is_authoritative(self, temp_dir):
        playlists_dir = os.path.join(temp_dir, "playlists")
        _write_json(os.path.join(playlists_dir, "watch-later.json"), {
            "name": "Hijacked",
            "description": "bad",
            "videos": [{"video_id": "v1"}],
        })

        service = PlaylistService(data_dir=temp_dir)

        playlist = service.get_playlist("watch-later")
        assert playlist.name == "Watch Later"
        assert playlist.description == "Videos saved for later viewing"
        assert service.has_video("watch-later", "v1") is True

    def test_create_failure_does_not_mutate_memory(self, playlist_service, monkeypatch):
        monkeypatch.setattr(playlist_service, "_save_playlist", lambda _playlist: False)

        assert playlist_service.create_playlist("Broken") is None
        assert not any(
            playlist.name == "Broken"
            for playlist in playlist_service.get_all_playlists()
        )

    def test_add_video_failure_does_not_mutate_memory(self, playlist_service, monkeypatch):
        playlist = playlist_service.create_playlist("Keep")
        monkeypatch.setattr(playlist_service, "_save_playlist", lambda _playlist: False)

        assert playlist_service.add_video(playlist.id, {"videoId": "v1"}) is False
        assert playlist_service.get_videos(playlist.id) == []

    def test_rename_failure_does_not_mutate_memory(self, playlist_service, monkeypatch):
        playlist = playlist_service.create_playlist("Keep")
        monkeypatch.setattr(playlist_service, "_save_playlist", lambda _playlist: False)

        assert playlist_service.rename_playlist(playlist.id, "Changed") is False
        assert playlist_service.get_playlist(playlist.id).name == "Keep"

    def test_delete_failure_does_not_mutate_memory(self, playlist_service, monkeypatch):
        playlist = playlist_service.create_playlist("Keep")
        monkeypatch.setattr(
            playlist_service, "_delete_playlist_file", lambda _playlist_id: False
        )

        assert playlist_service.delete_playlist(playlist.id) is False
        assert playlist_service.get_playlist(playlist.id) is not None

    def test_import_rejects_malformed_entries(self, playlist_service):
        assert playlist_service.import_all({"../escape": {"name": "Bad"}}) == 0
        assert playlist_service.import_all({"safe": "not a mapping"}) == 0
        assert playlist_service.import_all([]) == 0


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TestModelSanitization:
    def test_profile_from_dict_sanitizes_every_field(self):
        profile = Profile.from_dict({
            "id": "bad id",
            "name": 5,
            "avatar": 7,
            "created_at": "bad",
            "last_opened": -1,
            "theme": None,
            "language": 3,
        })

        assert re.match(r"^[A-Za-z0-9_-]{1,128}$", profile.id)
        assert profile.name == "Default"
        assert profile.avatar == ""
        assert profile.created_at == 0.0
        assert profile.last_opened == 0.0
        assert profile.theme == "dark"
        assert profile.language == "en"

    def test_profile_from_dict_non_mapping_returns_default(self):
        assert Profile.from_dict("junk").name == "Default"

    def test_user_profile_from_dict_sanitizes_fields(self):
        profile = UserProfile.from_dict({
            "user_id": 5,
            "username": "x" * 200,
            "display_name": None,
            "avatar_path": 3,
            "created_at": "bad",
        })

        assert profile.user_id == "default"
        assert len(profile.username) == 64
        assert profile.display_name == "User"
        assert profile.avatar_path == "User/avatar.png"
        assert profile.created_at > 0

    def test_playlist_from_dict_drops_invalid_videos(self):
        playlist = Playlist.from_dict({
            "name": "",
            "videos": [
                {"video_id": "v1"},
                {"video_id": "v1"},
                {"video_id": "bad id"},
                "junk",
                {"video_id": "v2", "position": 42},
            ],
        })

        assert playlist.name == "Recovered Playlist"
        assert [video.video_id for video in playlist.videos] == ["v1", "v2"]
        assert [video.position for video in playlist.videos] == [0, 1]


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


class TestProfileSafety:
    def test_duplicate_profile_names_are_unique_and_persisted(self, temp_dir):
        profiles_dir = os.path.join(temp_dir, "profiles")
        for profile_id in ("aaa", "bbb"):
            profile_dir = os.path.join(profiles_dir, profile_id)
            _write_json(os.path.join(profile_dir, "profile.json"), {
                "id": profile_id,
                "name": "Same",
            })

        manager = UserManagerService(base_dir=temp_dir)
        names = [profile.name for profile in manager.list_profiles()]

        assert len(names) == 2
        assert "Same" in names
        assert any(name.startswith("Same (") for name in names)
        assert len(set(manager.profile_dir(name) for name in names)) == 2

    def test_missing_profile_metadata_is_recovered(self, temp_dir):
        profiles_dir = os.path.join(temp_dir, "profiles")
        profile_dir = os.path.join(profiles_dir, "deadbeef")
        _write_json(os.path.join(profile_dir, "history.json"), [{"id": "v1"}])

        manager = UserManagerService(base_dir=temp_dir)

        assert manager.has_profile("Recovered Profile") is True
        assert os.path.isfile(os.path.join(profile_dir, "profile.json"))
        assert _read_json(os.path.join(profile_dir, "profile.json"))["id"] == "deadbeef"

    def test_delete_refuses_active_profile(self, temp_dir):
        manager = UserManagerService(base_dir=temp_dir)
        manager.create_profile("Alice")
        manager.switch_profile("Alice")

        assert manager.delete_profile("Alice") is False
        assert manager.current_profile_name() == "Alice"

        manager.switch_profile("Default")
        assert manager.delete_profile("Alice") is True

    def test_duplicate_profile_publishes_event(self, temp_dir, event_bus):
        events = []
        event_bus.subscribe("profile_created", events.append, weak=False)
        manager = UserManagerService(base_dir=temp_dir, event_bus=event_bus)
        manager.create_profile("Source")

        duplicate = manager.duplicate_profile("Source", "Copy")

        assert duplicate is not None
        assert any(
            getattr(event, "profile_name", "") == "Copy" for event in events
        )

    def test_invalid_avatar_path_is_rejected(self, temp_dir):
        manager = UserManagerService(base_dir=temp_dir)

        assert manager.set_profile_avatar(
            "Default", os.path.join(temp_dir, "missing.png")
        ) is False
        assert manager.current_profile().avatar == ""

    def test_valid_avatar_path_is_copied(self, temp_dir):
        source = os.path.join(temp_dir, "source.png")
        with open(source, "wb") as handle:
            handle.write(b"not really a png")

        manager = UserManagerService(base_dir=temp_dir)
        assert manager.set_profile_avatar("Default", source) is True

        profile = manager.current_profile()
        assert profile.avatar.endswith("avatar.png")
        assert os.path.isfile(profile.avatar)


# ---------------------------------------------------------------------------
# User profile service
# ---------------------------------------------------------------------------


class TestUserProfileValidation:
    def test_load_normalizes_invalid_payload(self, temp_dir):
        path = os.path.join(temp_dir, PROFILE_FILENAME)
        _write_json(path, {
            "user_id": 5,
            "username": "x" * 200,
            "display_name": None,
            "avatar_path": 3,
            "created_at": "bad",
        })

        service = UserProfileService(data_dir=temp_dir)
        profile = service.get_profile()

        assert profile.user_id == "default"
        assert len(profile.username) == 64
        assert profile.display_name == "User"
        assert profile.avatar_path == "User/avatar.png"
        assert profile.created_at > 0

        repaired = _read_json(path)
        assert repaired["user_id"] == "default"
        assert repaired["display_name"] == "User"

    def test_update_failure_is_transactional(self, temp_dir, monkeypatch):
        service = UserProfileService(data_dir=temp_dir)
        original_username = service.get_profile().username
        monkeypatch.setattr(service._store, "save", _raise_os_error)

        assert service.update_profile(username="changed") is False
        assert service.get_profile().username == original_username

    def test_set_avatar_rejects_missing_file(self, temp_dir):
        service = UserProfileService(data_dir=temp_dir)
        original = service.get_profile().avatar_path

        assert service.set_avatar(os.path.join(temp_dir, "missing.png")) is False
        assert service.get_profile().avatar_path == original

    def test_import_rejects_non_mapping(self, temp_dir):
        service = UserProfileService(data_dir=temp_dir)
        assert service.import_data(["bad"]) is False


# ---------------------------------------------------------------------------
# Export bundle
# ---------------------------------------------------------------------------


class TestDataBundle:
    def test_build_and_validate(self):
        bundle = build_bundle(
            profile_name="Default",
            settings={"volume": 10},
            history=[{"id": "v1"}],
            likes=[{"video_id": "v1"}],
            playlists={"p1": {"name": "P"}},
        )

        valid, reason = validate_bundle(bundle)
        assert valid is True
        assert reason == ""
        assert bundle["schema_version"] == DATA_SCHEMA_VERSION

    @pytest.mark.parametrize("bundle", [
        None,
        [],
        {},
        {"schema_version": "1", "data": {}},
        {"schema_version": True, "data": {}},
        {"schema_version": DATA_SCHEMA_VERSION + 1, "data": {}},
        {"schema_version": 1},
        {"schema_version": 1, "data": []},
        {"schema_version": 1, "data": {"history": {}}},
        {"schema_version": 1, "data": {"settings": []}},
    ])
    def test_invalid_bundles_are_rejected(self, bundle):
        assert validate_bundle(bundle)[0] is False
