"""Integration tests for DataImportService and TakeoutImportDialog."""

import json
import os
import time
import zipfile

import pytest
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QMessageBox

from core.event_bus import EventBus
from services.data_import_service import DataImportService, ImportResult
from services.history_service import HistoryService
from services.likes_service import LikesService
from services.playlist_service import PlaylistService
from ui.takeout_import_dialog import TakeoutGuideDialog, TakeoutImportDialog

pytestmark = pytest.mark.qt


@pytest.fixture
def takeout_services(temp_dir):
    bus = EventBus()
    history = HistoryService(event_bus=bus, data_dir=temp_dir)
    likes = LikesService(event_bus=bus, data_dir=temp_dir)
    playlists = PlaylistService(event_bus=bus, data_dir=temp_dir)
    import_service = DataImportService(
        event_bus=bus,
        history_service=history,
        likes_service=likes,
        playlist_service=playlists,
        data_dir=temp_dir,
    )
    return import_service, history, likes, playlists, bus


@pytest.fixture
def sample_takeout_zip(temp_dir):
    zip_path = os.path.join(temp_dir, "sample_takeout.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(
            "Takeout/YouTube and YouTube Music/subscriptions/subscriptions.csv",
            "Channel Id,Channel URL,Channel Title\nUCabc123456789012345678,http://url,Tech Channel\n",
        )
        zf.writestr(
            "Takeout/YouTube and YouTube Music/history/watch-history.json",
            json.dumps([
                {
                    "title": "Watched Python Tutorial",
                    "titleUrl": "https://www.youtube.com/watch?v=hist1234567",
                    "subtitles": [{"name": "Python Org"}],
                    "time": "2024-02-01T10:00:00Z",
                }
            ]),
        )
        zf.writestr(
            "Takeout/YouTube and YouTube Music/playlists/Liked videos.json",
            json.dumps([
                {
                    "snippet": {
                        "title": "Loved Song",
                        "resourceId": {"videoId": "like1234567"},
                        "videoOwnerChannelTitle": "Music Band",
                    }
                }
            ]),
        )
        zf.writestr(
            "Takeout/YouTube and YouTube Music/playlists/Watch later.json",
            json.dumps([
                {
                    "snippet": {
                        "title": "Watch Later Video",
                        "resourceId": {"videoId": "wlater12345"},
                    }
                }
            ]),
        )
        zf.writestr(
            "Takeout/YouTube and YouTube Music/playlists/Favorites.csv",
            "Video ID,Title,Channel Title\nfav12345678,Favorite Video,Fav Channel\n",
        )
    return zip_path


def test_data_import_service_full_execution(takeout_services, sample_takeout_zip):
    import_svc, history_svc, likes_svc, playlist_svc, bus = takeout_services

    selections = {
        "likes": True,
        "watch_later": True,
        "playlists": True,
        "history": True,
        "subscriptions": True,
    }

    res = import_svc.execute_import(
        source_path=sample_takeout_zip,
        selections=selections,
        overwrite=False,
    )

    assert res.success is True
    assert res.imported_likes == 1
    assert res.imported_watch_later == 1
    assert res.imported_history == 1
    assert res.imported_playlists == 1
    assert res.imported_subscriptions == 1

    # Verify state in target services
    assert likes_svc.is_liked("like1234567") is True
    assert history_svc.count() == 1
    assert history_svc.get_all()[0]["id"] == "hist1234567"

    wl = playlist_svc.get_watch_later()
    assert any(v["video_id"] == "wlater12345" for v in wl)

    fav_pl = next(
        (pl for pl in playlist_svc.get_all_playlists() if pl.name == "Favorites"),
        None,
    )
    assert fav_pl is not None
    assert len(fav_pl.videos) == 1
    assert fav_pl.videos[0].video_id == "fav12345678"


def test_data_import_deduplication_skip_existing(takeout_services, sample_takeout_zip):
    import_svc, _, likes_svc, _, _ = takeout_services

    # Pre-add like with different title
    likes_svc.toggle_like({"id": "like1234567", "title": "My Original Title"})
    assert likes_svc.is_liked("like1234567") is True

    res = import_svc.execute_import(
        source_path=sample_takeout_zip,
        selections={"likes": True},
        overwrite=False,
    )

    assert res.success is True
    assert res.imported_likes == 0  # Skipped because already existed!

    # Title preserved
    current = next(x for x in likes_svc.get_liked_videos() if x["video_id"] == "like1234567")
    assert current["title"] == "My Original Title"


def localized_takeout_zip(temp_dir):
    path = os.path.join(temp_dir, "localized_takeout.zip")
    history_html = (
        "<html><body>"
        '<div class="content-cell">تمت مشاهدة '
        '<a href="https://www.youtube.com/watch?v=newestVid01">الأحدث</a> .<br>'
        '<a href="https://www.youtube.com/channel/UCchan123456789012345">قناة الأحدث </a><br>'
        "27‏/10‏/2026، 12:30:34 م CET<br></div>"
        '<div class="content-cell">تمت مشاهدة '
        '<a href="https://www.youtube.com/watch?v=wrkLtrVid01">فيديو محفوظ</a> .<br>'
        '<a href="https://www.youtube.com/channel/UCchan123456789012345">قناة الأقدم </a><br>'
        "20‏/10‏/2026، 9:00:00 ص CET<br></div>"
        "</body></html>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "Takeout/YouTube وYouTube Music/الاشتراكات_/الاشتراكات_.csv",
            "معرّف القناة,عنوان Url للقناة,عنوان القناة\n"
            "UC--7VBMkB-8-fQ7bSxR2puQ,http://url,RandoMan+\n",
        )
        zf.writestr(
            "Takeout/YouTube وYouTube Music/قوائم تشغيل/قوائم تشغيل.csv",
            "رقم تعريف قائمة التشغيل,عنوان قائمة التشغيل (الأصلي)\n"
            "PL123,Watch later\n",
        )
        zf.writestr(
            "Takeout/YouTube وYouTube Music/قوائم تشغيل/فيديوهات _Watch later_.csv",
            "معرّف الفيديو,الطابع الزمني لإنشاء الفيديو في قائمة التشغيل\n"
            "wrkLtrVid01,2026-10-05T22:17:53+00:00\n",
        )
        zf.writestr(
            "Takeout/YouTube وYouTube Music/السجلّ/سجل المشاهدة.html",
            history_html,
        )
        zf.writestr(
            "Takeout/YouTube وYouTube Music/السجلّ/سجلّ البحث.html",
            '<html><body>تم البحث عن <a href="https://www.youtube.com/'
            'results?search_query=test">test</a></body></html>',
        )
    return path


def test_data_import_localized_takeout(takeout_services, temp_dir):
    import_svc, history_svc, _, playlist_svc, _ = takeout_services
    path = localized_takeout_zip(temp_dir)

    res = import_svc.execute_import(
        source_path=path,
        selections={
            "likes": True,
            "watch_later": True,
            "playlists": True,
            "history": True,
            "subscriptions": True,
        },
        overwrite=False,
    )

    assert res.success is True
    assert res.imported_watch_later == 1
    assert res.imported_history == 2
    assert res.imported_subscriptions == 1
    assert res.imported_playlists == 0

    watch_later = playlist_svc.get_watch_later()
    assert len(watch_later) == 1
    # Title/channel are borrowed from the watch history because modern
    # Takeout CSVs only export video ids.
    assert watch_later[0]["title"] == "فيديو محفوظ"
    assert watch_later[0]["channel"] == "قناة الأقدم"

    entries = history_svc.get_all()
    assert [entry["id"] for entry in entries] == ["newestVid01", "wrkLtrVid01"]
    assert entries[0]["watched_at"] > entries[1]["watched_at"]
    assert entries[0]["title"] == "الأحدث"
    assert entries[0]["channel"] == "قناة الأحدث"


def test_import_coalesces_bulk_change_events(takeout_services, temp_dir):
    """One event per type reaches the UI, not one per imported item."""
    import_svc, _, _, _, bus = takeout_services
    zip_path = os.path.join(temp_dir, "bulk_takeout.zip")

    watch_later = [
        {
            "snippet": {
                "title": f"Queued {i}",
                "resourceId": {"videoId": f"wl{i:09d}"},
            }
        }
        for i in range(12)
    ]
    history = [
        {
            "title": f"Watched {i}",
            "titleUrl": f"https://www.youtube.com/watch?v=hv{i:09d}",
            "time": "2026-10-01T10:00:00Z",
        }
        for i in range(12)
    ]
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(
            "Takeout/YouTube and YouTube Music/playlists/Watch later.json",
            json.dumps(watch_later),
        )
        zf.writestr(
            "Takeout/YouTube and YouTube Music/history/watch-history.json",
            json.dumps(history),
        )

    events = []
    for event_type in ("playlist_updated", "history_updated"):
        bus.subscribe(
            event_type,
            lambda event, kind=event_type: events.append(
                (kind, getattr(event, "action", ""))
            ),
            weak=False,
        )

    res = import_svc.execute_import(
        source_path=zip_path,
        selections={"watch_later": True, "history": True},
    )

    assert res.success is True
    assert res.imported_watch_later == 12
    assert res.imported_history == 12
    playlist_events = [event for event in events if event[0] == "playlist_updated"]
    history_events = [event for event in events if event[0] == "history_updated"]
    assert playlist_events == [("playlist_updated", "video_added")]
    assert history_events == [("history_updated", "import")]


def test_takeout_import_dialog_lifecycle(qapp, takeout_services, sample_takeout_zip):
    import_svc, _, _, _, _ = takeout_services
    dlg = TakeoutImportDialog(import_svc)
    guide = TakeoutGuideDialog(dlg)

    try:
        assert dlg.windowTitle() == "Import Google Takeout Archive"
        assert guide.windowTitle() == "How to get your Google Takeout data"

        # Trigger analysis
        dlg._analyze_path(sample_takeout_zip)
        assert dlg._inspect_worker is not None
        dlg._inspect_worker.wait(3000)
        qapp.processEvents()

        assert dlg._inspection_result is not None
        assert dlg._inspection_result.total_items > 0
        assert dlg._import_btn.isEnabled() is True
    finally:
        dlg.close()
        guide.close()


class _SlowImportService:
    """Stand-in that keeps running until the dialog cancels the worker."""

    def execute_import(
        self, source_path, selections, overwrite, progress_callback, cancel_event
    ):
        while not cancel_event.is_set():
            time.sleep(0.01)
        return ImportResult(success=False, error_message="Import was cancelled.")


def test_closing_dialog_stops_running_import(qapp, monkeypatch):
    reported = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda *args, **kwargs: reported.append(args)),
    )

    dlg = TakeoutImportDialog(_SlowImportService())
    try:
        dlg._selected_path = "bulk.zip"
        dlg._start_import()
        assert dlg._import_worker.isRunning()
        QTest.qWait(20)

        # Destroying a dialog with a live QThread aborts the process, so the
        # dialog must cancel and join the worker before closing.
        dlg.reject()

        assert dlg._closing is True
        assert dlg._import_worker.isRunning() is False
        assert dlg._import_worker._cancel_event.is_set() is True

        # The cancelled result arrives after dismissal and must stay silent.
        qapp.processEvents()
        assert reported == []
    finally:
        worker = dlg._import_worker
        if worker is not None and worker.isRunning():
            worker.cancel()
            worker.wait(3000)
