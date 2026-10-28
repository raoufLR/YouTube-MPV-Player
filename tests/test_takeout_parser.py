"""Tests for Google Takeout archive inspection and parsing."""

import json
import os
import zipfile
from datetime import datetime

import pytest

from core.takeout_parser import (
    TakeoutArchiveReader,
    extract_id_from_url,
    find_takeout_files,
    inspect_takeout_source,
    parse_history_data,
    parse_playlist_data,
    parse_subscriptions_data,
    playlist_name_from_path,
)


def test_extract_id_from_url():
    assert extract_id_from_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_id_from_url("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_id_from_url("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_id_from_url("https://example.com/other") == ""


def test_zip_slip_rejection(temp_dir):
    """Ensure zip members attempting directory traversal are rejected."""
    bad_zip_path = os.path.join(temp_dir, "malicious.zip")
    with zipfile.ZipFile(bad_zip_path, "w") as zf:
        zf.writestr("../../etc/passwd", "evil content")

    with pytest.raises(ValueError, match="Malicious path"):
        TakeoutArchiveReader(bad_zip_path)


def test_parse_subscriptions_json_and_csv():
    # JSON test
    json_data = json.dumps([
        {
            "snippet": {
                "title": "Channel One",
                "resourceId": {"channelId": "UC1234567890123456789012"}
            }
        }
    ]).encode("utf-8")
    subs_json = parse_subscriptions_data(json_data, is_json=True)
    assert len(subs_json) == 1
    assert subs_json[0].channel_id == "UC1234567890123456789012"
    assert subs_json[0].title == "Channel One"

    # CSV test
    csv_data = (
        b"Channel Id,Channel URL,Channel Title\n"
        b"UC9999999999999999999999,https://youtube.com/c/two,Channel Two\n"
    )
    subs_csv = parse_subscriptions_data(csv_data, is_json=False)
    assert len(subs_csv) == 1
    assert subs_csv[0].channel_id == "UC9999999999999999999999"
    assert subs_csv[0].title == "Channel Two"


def test_parse_history_json_and_html():
    json_data = json.dumps([
        {
            "header": "YouTube",
            "title": "Watched Amazing Video Title",
            "titleUrl": "https://www.youtube.com/watch?v=12345678901",
            "subtitles": [{"name": "Great Creator", "url": "https://youtube.com"}],
            "time": "2024-01-15T12:00:00.000Z"
        }
    ]).encode("utf-8")
    hist_json = parse_history_data(json_data, is_json=True)
    assert len(hist_json) == 1
    assert hist_json[0].video_id == "12345678901"
    assert hist_json[0].title == "Amazing Video Title"
    assert hist_json[0].channel == "Great Creator"
    assert hist_json[0].watched_at > 0

    html_data = (
        b'<html><body><a href="https://www.youtube.com/watch?v=09876543210">Watched HTML Video</a></body></html>'
    )
    hist_html = parse_history_data(html_data, is_json=False)
    assert len(hist_html) == 1
    assert hist_html[0].video_id == "09876543210"
    assert hist_html[0].title == "HTML Video"


def test_parse_playlist_json_and_csv():
    json_data = json.dumps([
        {
            "snippet": {
                "title": "Song Title",
                "resourceId": {"videoId": "abcdefghijk"},
                "videoOwnerChannelTitle": "Artist"
            }
        }
    ]).encode("utf-8")
    pl_json = parse_playlist_data(json_data, is_json=True, playlist_name="My Music")
    assert pl_json.name == "My Music"
    assert len(pl_json.items) == 1
    assert pl_json.items[0].video_id == "abcdefghijk"
    assert pl_json.items[0].title == "Song Title"

    csv_data = (
        b"Video ID,Title,Channel Title,Time Added\n"
        b"xyz12345678,Cool Video,Creator,2023-05-10T10:00:00Z\n"
    )
    pl_csv = parse_playlist_data(csv_data, is_json=False, playlist_name="Liked videos")
    assert pl_csv.is_liked_videos is True
    assert len(pl_csv.items) == 1
    assert pl_csv.items[0].video_id == "xyz12345678"


ARABIC_WATCH_HISTORY_HTML = (
    '<html><body>'
    '<div class="content-cell">تمت مشاهدة '
    '<a href="https://www.youtube.com/watch?v=histVid0001">فيديو عربي</a> .<br>'
    '<a href="https://www.youtube.com/channel/UCchannel123456789012">قناة عربية </a><br>'
    "27‏/10‏/2026، 12:30:34 ص CET<br>"
    "</div></body></html>"
)


def localized_takeout_zip(temp_dir, name="arabic_takeout.zip"):
    path = os.path.join(temp_dir, name)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "Takeout/YouTube وYouTube Music/الاشتراكات_/الاشتراكات_.csv",
            "معرّف القناة,عنوان Url للقناة,عنوان القناة\n"
            "UC--7VBMkB-8-fQ7bSxR2puQ,"
            "http://www.youtube.com/channel/UC--7VBMkB-8-fQ7bSxR2puQ,RandoMan+\n",
        )
        zf.writestr(
            "Takeout/YouTube وYouTube Music/قوائم تشغيل/قوائم تشغيل.csv",
            "رقم تعريف قائمة التشغيل,عنوان قائمة التشغيل (الأصلي),"
            "مستوى عرض قائمة التشغيل\n"
            "PL123,Watch later,خاصة\n",
        )
        zf.writestr(
            "Takeout/YouTube وYouTube Music/قوائم تشغيل/فيديوهات _Watch later_.csv",
            "معرّف الفيديو,الطابع الزمني لإنشاء الفيديو في قائمة التشغيل\n"
            "wrkLtrVid01,2026-10-05T22:17:53+00:00\n",
        )
        zf.writestr(
            "Takeout/YouTube وYouTube Music/السجلّ/سجل المشاهدة.html",
            ARABIC_WATCH_HISTORY_HTML,
        )
        zf.writestr(
            "Takeout/YouTube وYouTube Music/السجلّ/سجلّ البحث.html",
            '<html><body>تم البحث عن <a href="https://www.youtube.com/'
            'results?search_query=test">test</a></body></html>',
        )
    return path


def test_find_localized_arabic_takeout_files(temp_dir):
    path = localized_takeout_zip(temp_dir)
    with TakeoutArchiveReader(path) as reader:
        mapping = find_takeout_files(reader)

    assert mapping["subscriptions"].endswith("الاشتراكات_.csv")
    assert mapping["history"].endswith("سجل المشاهدة.html")
    assert [os.path.basename(p) for p in mapping["playlists"]] == [
        "فيديوهات _Watch later_.csv"
    ]


def test_parse_localized_subscriptions_and_playlist_csv():
    subs = parse_subscriptions_data(
        (
            "معرّف القناة,عنوان Url للقناة,عنوان القناة\n"
            "UC--7VBMkB-8-fQ7bSxR2puQ,http://url,RandoMan+\n"
        ).encode(),
        is_json=False,
    )
    assert len(subs) == 1
    assert subs[0].channel_id == "UC--7VBMkB-8-fQ7bSxR2puQ"
    assert subs[0].title == "RandoMan+"

    name = playlist_name_from_path(
        "Takeout/YouTube وYouTube Music/قوائم تشغيل/فيديوهات _Watch later_.csv"
    )
    assert name == "Watch later"

    pl = parse_playlist_data(
        (
            "معرّف الفيديو,الطابع الزمني لإنشاء الفيديو في قائمة التشغيل\n"
            "wrkLtrVid01,2026-10-05T22:17:53+00:00\n"
        ).encode(),
        is_json=False,
        playlist_name=name,
    )
    assert pl.is_watch_later is True
    assert len(pl.items) == 1
    assert pl.items[0].video_id == "wrkLtrVid01"
    assert pl.items[0].added_at > 0


def test_parse_localized_history_html_extracts_channel_and_time():
    hist = parse_history_data(
        ARABIC_WATCH_HISTORY_HTML.encode("utf-8"), is_json=False
    )
    assert len(hist) == 1
    assert hist[0].video_id == "histVid0001"
    assert hist[0].title == "فيديو عربي"
    assert hist[0].channel == "قناة عربية"
    parsed = datetime.fromtimestamp(hist[0].watched_at)
    assert (parsed.year, parsed.month, parsed.day) == (2026, 10, 27)
    assert (parsed.hour, parsed.minute, parsed.second) == (0, 30, 34)


def test_inspect_localized_arabic_takeout(temp_dir):
    res = inspect_takeout_source(localized_takeout_zip(temp_dir))
    assert res.has_subscriptions is True
    assert res.subscriptions_count == 1
    assert res.has_history is True
    assert res.history_count == 1
    assert res.has_watch_later is True
    assert res.watch_later_count == 1
    assert res.playlists == []
    assert res.total_items == 3


def test_inspect_takeout_zip_and_folder(temp_dir):
    # Create sample Takeout zip
    zip_path = os.path.join(temp_dir, "takeout.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(
            "Takeout/YouTube and YouTube Music/subscriptions/subscriptions.json",
            json.dumps([{"snippet": {"title": "Ch1", "resourceId": {"channelId": "UC1111111111111111111111"}}}]),
        )
        zf.writestr(
            "Takeout/YouTube and YouTube Music/history/watch-history.json",
            json.dumps([{"title": "Watched V1", "titleUrl": "https://www.youtube.com/watch?v=11111111111"}]),
        )
        zf.writestr(
            "Takeout/YouTube and YouTube Music/playlists/Liked videos.json",
            json.dumps([{"snippet": {"title": "Liked V1", "resourceId": {"videoId": "22222222222"}}}]),
        )
        zf.writestr(
            "Takeout/YouTube and YouTube Music/playlists/Custom Playlist.csv",
            "Video ID,Title,Channel Title\n33333333333,Custom V1,Channel\n",
        )

    res = inspect_takeout_source(zip_path)
    assert res.archive_format == "zip"
    assert res.has_subscriptions is True
    assert res.subscriptions_count == 1
    assert res.has_history is True
    assert res.history_count == 1
    assert res.has_likes is True
    assert res.likes_count == 1
    assert len(res.playlists) == 1
    assert res.playlists[0][0] == "Custom Playlist"
    assert res.total_items == 4
