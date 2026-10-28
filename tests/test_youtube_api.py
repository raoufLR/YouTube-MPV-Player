"""yt-dlp wrapper tests. No subprocess or network access is used."""

import subprocess
import threading

import pytest

import youtube_api
from core.playback_errors import StreamCancelledError, StreamResolutionError
from core.quality import ResolvedStream


class _FakePopen:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.terminated = False
        self.killed = False

    def communicate(self, timeout=None):
        return self.stdout, self.stderr

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9


class _TimeoutPopen(_FakePopen):
    def __init__(self):
        super().__init__(returncode=None)

    def communicate(self, timeout=None):
        raise subprocess.TimeoutExpired("yt-dlp", timeout)


@pytest.fixture
def api(monkeypatch, tmp_path):
    monkeypatch.setattr(youtube_api, "_RETRY_DELAYS", [0.0, 0.0])
    service = youtube_api.YouTubeAPI()
    service.ytdlp_path = str(tmp_path / "yt-dlp.exe")
    return service


class TestStreamExtraction:
    def test_dash_formats_return_video_and_audio(self, api, monkeypatch):
        captured = {}

        def run(cmd, timeout, cancel_event=None):
            captured["cmd"] = cmd
            return "https://example.com/video\nhttps://example.com/audio\n"

        monkeypatch.setattr(api, "_run_ytdlp", run)
        media = api.extract_streams("abc123def45", "720p")

        assert media == ResolvedStream(
            "https://example.com/video", "https://example.com/audio", "720p"
        )
        assert "-g" in captured["cmd"]
        assert "-f" in captured["cmd"]
        assert "bestvideo[height<=720]+bestaudio/best[height<=720]" in captured["cmd"]

    def test_progressive_format_returns_single_url(self, api, monkeypatch):
        monkeypatch.setattr(api, "_run_ytdlp", lambda *a, **k: "https://example.com/v\n")
        media = api.extract_streams("abc123def45", "360p")
        assert media.video_url == "https://example.com/v"
        assert media.audio_url == ""

    def test_unknown_quality_normalizes_to_best(self, api, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            api,
            "_run_ytdlp",
            lambda cmd, timeout, cancel_event=None: captured.update(cmd=cmd)
            or "https://example.com/v\n",
        )
        media = api.extract_streams("abc123def45", "4k")
        assert media.quality == "best"
        assert "bestvideo+bestaudio/best" in captured["cmd"]

    def test_empty_output_is_an_error(self, api, monkeypatch):
        monkeypatch.setattr(api, "_run_ytdlp", lambda *a, **k: "\n\n")
        with pytest.raises(StreamResolutionError):
            api.extract_streams("abc123def45")

    def test_invalid_url_output_is_an_error(self, api, monkeypatch):
        monkeypatch.setattr(api, "_run_ytdlp", lambda *a, **k: "not-a-url\n")
        with pytest.raises(StreamResolutionError):
            api.extract_streams("abc123def45")

    def test_invalid_video_id_is_rejected_before_running(self, api):
        with pytest.raises(ValueError):
            api.extract_streams("../../etc/passwd")

    def test_cancellation_propagates(self, api, monkeypatch):
        def run(*args, **kwargs):
            raise StreamCancelledError("cancelled")

        monkeypatch.setattr(api, "_run_ytdlp", run)
        with pytest.raises(StreamCancelledError):
            api.extract_streams("abc123def45")

    def test_timeout_is_wrapped(self, api, monkeypatch):
        def run(*args, **kwargs):
            raise subprocess.TimeoutExpired("yt-dlp", 60)

        monkeypatch.setattr(api, "_run_ytdlp", run)
        with pytest.raises(StreamResolutionError):
            api.extract_streams("abc123def45")

    def test_cancel_event_is_forwarded(self, api, monkeypatch):
        seen = {}

        def run(cmd, timeout, cancel_event=None):
            seen["event"] = cancel_event
            return "https://example.com/v\n"

        monkeypatch.setattr(api, "_run_ytdlp", run)
        event = threading.Event()
        api.extract_streams("abc123def45", cancel_event=event)
        assert seen["event"] is event


class TestMetadata:
    def test_fetch_video_info(self, api, monkeypatch):
        payload = (
            '{"title": "T", "channel": "C", "duration": 10,'
            ' "thumbnails": [{"url": "https://example.com/t.jpg"}]}'
        )
        monkeypatch.setattr(api, "_run_ytdlp", lambda *a, **k: payload + "\n")

        info = api.fetch_video_info("abc123def45")
        assert info == {
            "videoId": "abc123def45",
            "title": "T",
            "channel": "C",
            "thumbnail": "https://example.com/t.jpg",
            "duration": 10,
        }

    def test_invalid_metadata_json_raises(self, api, monkeypatch):
        monkeypatch.setattr(api, "_run_ytdlp", lambda *a, **k: "not json\n")
        with pytest.raises(StreamResolutionError):
            api.fetch_video_info("abc123def45")


class TestSearch:
    def test_search_parses_results(self, api, monkeypatch):
        payload = (
            '{"id": "abc123def45", "title": "T",'
            ' "channel": "C", "thumbnails": [{"url": "u"}]}'
        )
        monkeypatch.setattr(api, "_run_ytdlp", lambda *a, **k: payload + "\n")

        results = api.search_videos("query")
        assert results == [
            {
                "title": "T",
                "videoId": "abc123def45",
                "thumbnail": "u",
                "channel": "C",
            }
        ]

    def test_search_failure_returns_empty_list(self, api, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("offline")

        monkeypatch.setattr(api, "_run_ytdlp", boom)
        assert api.search_videos("query") == []


class TestRunYtdlp:
    def test_success_returns_stdout(self, api, monkeypatch):
        monkeypatch.setattr(
            youtube_api.subprocess,
            "Popen",
            lambda *a, **k: _FakePopen(stdout="result"),
        )
        assert api._run_ytdlp(["yt-dlp"], timeout=1) == "result"

    def test_nonzero_exit_retries_then_raises(self, api, monkeypatch):
        calls = []

        def popen(*args, **kwargs):
            calls.append(1)
            return _FakePopen(stderr="bad", returncode=2)

        monkeypatch.setattr(youtube_api.subprocess, "Popen", popen)
        with pytest.raises(RuntimeError):
            api._run_ytdlp(["yt-dlp"], timeout=1)
        assert len(calls) == 3

    def test_timeout_terminates_process(self, api, monkeypatch):
        process = _TimeoutPopen()
        monkeypatch.setattr(
            youtube_api.subprocess, "Popen", lambda *a, **k: process
        )
        with pytest.raises(subprocess.TimeoutExpired):
            api._run_ytdlp(["yt-dlp"], timeout=0)
        assert process.terminated is True

    def test_pre_cancelled_request_never_spawns_process(self, api, monkeypatch):
        monkeypatch.setattr(
            youtube_api.subprocess,
            "Popen",
            lambda *a, **k: pytest.fail("process must not start"),
        )
        event = threading.Event()
        event.set()
        with pytest.raises(StreamCancelledError):
            api._run_ytdlp(["yt-dlp"], timeout=1, cancel_event=event)


class TestCommandHardening:
    def test_search_command_ignores_config(self, api, monkeypatch):
        captured = {}

        def run(cmd, timeout, cancel_event=None):
            captured["cmd"] = cmd
            return ""

        monkeypatch.setattr(api, "_run_ytdlp", run)
        api.search_videos("query")
        assert "--ignore-config" in captured["cmd"]

    def test_extract_command_ignores_config_and_playlist(self, api, monkeypatch):
        captured = {}

        def run(cmd, timeout, cancel_event=None):
            captured["cmd"] = cmd
            return "https://example.com/v\n"

        monkeypatch.setattr(api, "_run_ytdlp", run)
        api.extract_streams("abc123def45")
        assert "--ignore-config" in captured["cmd"]
        assert "--no-playlist" in captured["cmd"]

    def test_info_command_ignores_config(self, api, monkeypatch):
        captured = {}

        def run(cmd, timeout, cancel_event=None):
            captured["cmd"] = cmd
            return '{"title": "T"}'

        monkeypatch.setattr(api, "_run_ytdlp", run)
        api.fetch_video_info("abc123def45")
        assert "--ignore-config" in captured["cmd"]

    def test_search_result_limit_is_clamped(self, api, monkeypatch):
        captured = {}

        def run(cmd, timeout, cancel_event=None):
            captured["cmd"] = cmd
            return ""

        monkeypatch.setattr(api, "_run_ytdlp", run)
        api.search_videos("query", max_results=10_000)
        assert f"ytsearch{100}:query" in captured["cmd"]

    @pytest.mark.parametrize(
        "query",
        ["", "   ", "x" * 201, "bad\x00query", "line\nbreak", None, 42],
    )
    def test_invalid_queries_are_rejected(self, api, query):
        with pytest.raises(ValueError):
            api.search_videos(query)


class TestSearchResultSanitising:
    def test_results_with_invalid_ids_are_dropped(self, api, monkeypatch):
        payload = "\n".join(
            [
                '{"id": "not-an-id", "title": "Bad"}',
                '{"id": "abc123def45", "title": "Good"}',
                '{"id": "../../etc", "title": "Traversal"}',
            ]
        )
        monkeypatch.setattr(api, "_run_ytdlp", lambda *a, **k: payload + "\n")

        results = api.search_videos("query")

        assert [item["videoId"] for item in results] == ["abc123def45"]

    def test_control_characters_are_stripped_from_metadata(self, api, monkeypatch):
        payload = (
            '{"id": "abc123def45", "title": "T\\r\\nitle",'
            ' "channel": "C\\u0000hannel"}'
        )
        monkeypatch.setattr(api, "_run_ytdlp", lambda *a, **k: payload + "\n")

        result = api.search_videos("query")[0]

        assert result["title"] == "Title"
        assert result["channel"] == "Channel"


class TestExecutableResolution:
    def test_working_directory_is_not_searched(self, monkeypatch, tmp_path):
        planted = tmp_path / "yt-dlp.exe"
        planted.write_bytes(b"MZ")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(youtube_api, "_resource_path", lambda name: str(tmp_path / "missing"))
        monkeypatch.setattr(youtube_api.shutil, "which", lambda name: None)

        api = youtube_api.YouTubeAPI()

        assert api.ytdlp_path == "yt-dlp"
        assert str(planted) != api.ytdlp_path

    def test_child_process_gets_no_stdin(self, api, monkeypatch):
        captured = {}

        def popen(*args, **kwargs):
            captured.update(kwargs)
            return _FakePopen(stdout="ok")

        monkeypatch.setattr(youtube_api.subprocess, "Popen", popen)
        api._run_ytdlp(["yt-dlp"], timeout=1)

        assert captured["stdin"] is subprocess.DEVNULL
