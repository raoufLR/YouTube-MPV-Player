import os

from services.history_service import HistoryService
from services.likes_service import LikesService
from services.playlist_service import PlaylistService
from services.settings_service import SettingsService


def _quarantined(directory):
    return [
        name for name in os.listdir(directory)
        if ".corrupt-" in name
    ]


def test_settings_roundtrip_and_corruption_quarantine(temp_dir):
    service = SettingsService(data_dir=temp_dir)
    service.set("volume", 42)
    service.shutdown()

    reloaded = SettingsService(data_dir=temp_dir)
    try:
        assert reloaded.get("volume") == 42
    finally:
        reloaded.shutdown()

    path = os.path.join(temp_dir, "settings.json")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{broken")

    recovered = SettingsService(data_dir=temp_dir)
    try:
        assert recovered.get("volume") == 80
    finally:
        recovered.shutdown()

    assert _quarantined(temp_dir)


def test_history_roundtrip_and_corruption_quarantine(temp_dir):
    service = HistoryService(data_dir=temp_dir)
    service.add({"id": "v1", "title": "One"})
    service.shutdown()

    reloaded = HistoryService(data_dir=temp_dir)
    try:
        assert reloaded.contains("v1")
    finally:
        reloaded.shutdown()

    with open(os.path.join(temp_dir, "history.json"), "w", encoding="utf-8") as handle:
        handle.write("[broken")

    recovered = HistoryService(data_dir=temp_dir)
    try:
        assert recovered.count() == 0
    finally:
        recovered.shutdown()

    assert _quarantined(temp_dir)


def test_likes_roundtrip(temp_dir):
    service = LikesService(data_dir=temp_dir)
    service.like({"videoId": "v1", "title": "One"})

    reloaded = LikesService(data_dir=temp_dir)

    assert reloaded.is_liked("v1")
    assert reloaded.get_liked_videos()[0]["title"] == "One"


def test_playlists_roundtrip_and_corrupt_file_is_skipped(temp_dir):
    service = PlaylistService(data_dir=temp_dir)
    playlist = service.create_playlist("Mine")
    service.add_video(playlist.id, {"videoId": "v1", "title": "One"})

    reloaded = PlaylistService(data_dir=temp_dir)

    assert reloaded.get_playlist(playlist.id).name == "Mine"
    assert reloaded.get_videos(playlist.id)[0]["video_id"] == "v1"

    broken_id = "brokenfile"
    with open(
        os.path.join(temp_dir, "playlists", f"{broken_id}.json"),
        "w",
        encoding="utf-8",
    ) as handle:
        handle.write("{broken")

    recovered = PlaylistService(data_dir=temp_dir)

    assert recovered.get_playlist(broken_id) is None
    assert recovered.get_playlist(playlist.id) is not None
    assert any(
        ".corrupt-" in name
        for name in os.listdir(os.path.join(temp_dir, "playlists"))
    )


def test_playlist_rejects_unsafe_ids(temp_dir):
    service = PlaylistService(data_dir=temp_dir)

    service.import_all({"../escape": {"name": "Bad", "videos": []}})

    assert "../escape" not in service.export_all()
    assert not os.path.exists(os.path.join(temp_dir, "..", "escape.json"))
