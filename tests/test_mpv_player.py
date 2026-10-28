"""MPV process wrapper tests. No real MPV binary is launched."""

import pytest

from player import MpvIPCError, MpvPlayer
from tests.fakes import FakeProcess


class FakeIPC:
    def __init__(self, path):
        self.path = path
        self.sent = []
        self.requests = []
        self.closed = False
        self.response = 123

    def send(self, command, timeout=1.0):
        self.sent.append(list(command))

    def request(self, command, timeout=0.5):
        self.requests.append(list(command))
        return self.response

    def close(self):
        self.closed = True


class Popener:
    def __init__(self, process=None):
        self.fixed_process = process
        self.commands = []
        self.processes = []
        self.error = None

    def __call__(self, cmd, creationflags=0):
        self.commands.append(list(cmd))
        if self.error is not None:
            raise self.error
        process = self.fixed_process if self.fixed_process is not None else FakeProcess()
        self.processes.append(process)
        return process


STREAM = "https://example.com/video"
AUDIO = "https://example.com/audio"


def _make_player(popener, ipcs):
    def ipc_factory(path):
        ipc = FakeIPC(path)
        ipcs.append(ipc)
        return ipc

    return MpvPlayer(
        mpv_executable="mpv.exe",
        popen_factory=popener,
        ipc_factory=ipc_factory,
        startup_timeout=0.02,
    )


class TestMpvPlayer:
    def test_play_builds_command_and_starts_ipc(self):
        popener = Popener()
        ipcs = []
        player = _make_player(popener, ipcs)

        player.play(STREAM, "720p", win_id=42)

        cmd = popener.commands[0]
        assert cmd[0] == "mpv.exe"
        assert cmd[1] == STREAM
        assert any(arg.startswith("--input-ipc-server=") for arg in cmd)
        assert "--ytdl-format=bestvideo[height<=720]+bestaudio/best[height<=720]" in cmd
        assert "--wid=42" in cmd
        assert "--no-terminal" in cmd

        assert player.current_url == STREAM
        assert player.is_running is True
        assert len(ipcs) == 1
        assert ipcs[0].sent == [["set_property", "volume", 80]]

    def test_play_adds_external_audio_track(self):
        popener = Popener()
        player = _make_player(popener, [])

        player.play(STREAM, "1080p", audio_url=AUDIO)

        assert f"--audio-file={AUDIO}" in popener.commands[0]
        assert player.current_audio_url == AUDIO

    def test_progressive_stream_has_no_audio_flag(self):
        popener = Popener()
        player = _make_player(popener, [])

        player.play(STREAM)

        assert not any(arg.startswith("--audio-file=") for arg in popener.commands[0])
        assert player.current_audio_url is None

    def test_each_playback_gets_a_unique_ipc_pipe(self):
        first = _make_player(Popener(), [])
        second = _make_player(Popener(), [])
        first.play(STREAM)
        second.play(STREAM)

        assert first.ipc_path != second.ipc_path
        assert first.ipc_path.startswith(r"\\.\pipe\ytmpv-")
        assert second.ipc_path.startswith(r"\\.\pipe\ytmpv-")

    def test_invalid_urls_rejected_before_launch(self):
        popener = Popener()
        player = _make_player(popener, [])

        with pytest.raises(ValueError):
            player.play("file:///etc/passwd")
        assert popener.commands == []

        with pytest.raises(ValueError):
            player.play(STREAM, audio_url="file:///etc/audio")
        assert popener.commands == []

    def test_immediate_exit_surfaces_as_error(self):
        popener = Popener(FakeProcess(returncode=1))
        player = _make_player(popener, [])

        with pytest.raises(RuntimeError, match="exited immediately"):
            player.play(STREAM)

        assert player.process is None
        assert player.current_url is None

    def test_missing_executable_is_reported(self):
        popener = Popener()
        popener.error = FileNotFoundError()
        player = _make_player(popener, [])

        with pytest.raises(FileNotFoundError, match="mpv executable not found"):
            player.play(STREAM)

        assert player.current_url is None

    def test_stop_sends_quit_and_releases_process(self):
        popener = Popener()
        ipcs = []
        player = _make_player(popener, ipcs)
        player.play(STREAM)
        process = player.process

        player.stop()

        assert ["quit"] in ipcs[0].sent
        assert process.terminated is True
        assert ipcs[0].closed is True
        assert player.process is None
        assert player.is_running is False

    def test_stop_without_playback_is_safe(self):
        player = _make_player(Popener(), [])
        player.stop()
        assert player.process is None

    def test_second_play_stops_the_previous_process(self):
        popener = Popener()
        ipcs = []
        player = _make_player(popener, ipcs)
        player.play(STREAM)
        first_process = player.process

        player.play("https://example.com/second")
        assert first_process.terminated is True
        assert len(popener.commands) == 2

    def test_commands_are_ignored_when_not_running(self):
        player = _make_player(Popener(), [])
        assert player.send_command(["quit"]) is False
        assert player.request(["get_property", "time-pos"]) is None

    def test_pause_seek_and_volume_use_explicit_properties(self):
        ipcs = []
        player = _make_player(Popener(), ipcs)
        player.play(STREAM)

        player.set_paused(True)
        player.seek(15.5)
        player.seek(-10)
        player.set_volume(150)

        sent = ipcs[0].sent
        assert ["set_property", "pause", True] in sent
        assert ["seek", "15.5", "absolute"] in sent
        assert ["seek", "0.0", "absolute"] in sent
        assert ["set_property", "volume", 100] in sent
        assert player.get_volume() == 100

    def test_volume_falls_back_to_default_on_invalid_input(self):
        player = _make_player(Popener(), [])
        player.set_volume("loud")
        assert player.get_volume() == 80

    def test_request_forwards_to_ipc(self):
        ipcs = []
        player = _make_player(Popener(), ipcs)
        player.play(STREAM)

        assert player.get_property("duration") == 123
        assert ipcs[0].requests == [["get_property", "duration"]]

    def test_wait_until_started_detects_unresponsive_process(self):
        player = _make_player(Popener(), [])
        player.play(STREAM)
        # The fake process never exits and the fake IPC always answers.
        assert player.wait_until_started(timeout=0.2) is True


class TestMpvIPC:
    def test_closed_channel_rejects_commands(self, tmp_path):
        from player import MpvIPC

        ipc = MpvIPC(str(tmp_path / "pipe"))
        ipc.close()
        with pytest.raises(MpvIPCError):
            ipc.send(["quit"])

    def test_request_timeout_is_reported(self, monkeypatch, tmp_path):
        from player import MpvIPC

        ipc = MpvIPC(str(tmp_path / "pipe"))
        monkeypatch.setattr(
            ipc, "_execute", lambda command, wait, timeout: __import__("time").sleep(0.3)
        )
        try:
            with pytest.raises(MpvIPCError):
                ipc.request(["get_property", "duration"], timeout=0.05)
        finally:
            ipc.close()

    def test_worker_survives_command_failure(self, monkeypatch, tmp_path):
        from player import MpvIPC

        ipc = MpvIPC(str(tmp_path / "pipe"))
        calls = []

        def execute(command, wait, timeout):
            calls.append(command)
            if len(calls) == 1:
                raise RuntimeError("boom")
            return "ok"

        monkeypatch.setattr(ipc, "_execute", execute)
        try:
            ipc.send(["first"])

            assert ipc.request(["second"], timeout=1) == "ok"
            assert calls == [["first"], ["second"]]
        finally:
            ipc.close()

    def test_read_response_skips_events_and_matches_request_id(self):
        from player import MpvIPC

        class Pipe:
            def __init__(self, lines):
                self.lines = list(lines)

            def readline(self):
                return self.lines.pop(0) if self.lines else b""

        pipe = Pipe(
            [
                b'{"event": "start-file"}\n',
                b'{"request_id": 7, "error": "success", "data": 12.5}\n',
            ]
        )
        assert MpvIPC._read_response(pipe, 7) == 12.5

    def test_read_response_reports_mpv_errors(self):
        from player import MpvIPC

        class Pipe:
            def readline(self):
                return b'{"request_id": 3, "error": "loading failed"}\n'

        with pytest.raises(MpvIPCError, match="loading failed"):
            MpvIPC._read_response(Pipe(), 3)

    def test_read_response_marks_unavailable_property(self):
        from player import MpvIPC, MpvPropertyUnavailableError

        class Pipe:
            def readline(self):
                return b'{"request_id": 4, "error": "property unavailable"}\n'

        with pytest.raises(MpvPropertyUnavailableError, match="not available"):
            MpvIPC._read_response(Pipe(), 4)

        # It must remain catchable as the generic IPC error for callers that
        # only care that the command failed.
        assert issubclass(MpvPropertyUnavailableError, MpvIPCError)
