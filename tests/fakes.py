"""Small deterministic fakes for tests that must not launch real binaries."""

from __future__ import annotations

from typing import Any


class FakeProcess:
    """Minimal subprocess.Popen-compatible object used by player tests."""

    def __init__(self, returncode: int | None = None):
        self.returncode = returncode
        self.terminated = False
        self.killed = False
        self.waited = False
        self.creationflags = 0

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        self.waited = True
        return self.returncode if self.returncode is not None else 0

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def communicate(self, timeout: float | None = None):
        return b"", b""


class FakeMpvPlayer:
    """In-memory implementation of the MpvPlayer interface used by PlayerService."""

    def __init__(self):
        self.process: FakeProcess | None = None
        self.current_url: str | None = None
        self.current_audio_url: str | None = None
        self.embed_win_id: int | None = None
        self.ipc_path = r"\\.\pipe\fake-mpv"
        self.play_calls: list[tuple[str, str, int | None]] = []
        self.audio_urls: list[str] = []
        self.commands: list[list[Any]] = []
        self.request_calls: list[list[Any]] = []
        self.seeks: list[tuple[float, str]] = []
        self.volume = 80
        self.paused = False
        self.stopped = 0
        self._cached_volume = 80
        self.properties: dict[str, Any] = {
            "time-pos": 0.0,
            "duration": 0.0,
            "pause": False,
            "eof-reached": False,
        }

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def play(
        self,
        video_url: str,
        quality: str = "best",
        win_id: int | None = None,
        audio_url: str = "",
    ):
        self.current_url = video_url
        self.current_audio_url = audio_url or None
        self.play_calls.append((video_url, quality, win_id))
        self.audio_urls.append(audio_url)
        self.process = FakeProcess()
        self.paused = False
        self.properties["pause"] = False
        self.properties["eof-reached"] = False
        self.properties["time-pos"] = 0.0

    def stop(self):
        had_playback = self.process is not None or self.current_url is not None
        if had_playback:
            self.stopped += 1
        if self.process is not None:
            self.process.terminate()
        self.process = None
        self.current_url = None
        self.current_audio_url = None

    def send_command(self, command):
        self.commands.append(list(command))

    def request(self, command, timeout: float = 0.5):
        self.request_calls.append(list(command))
        if command and command[0] == "get_property":
            return self.properties.get(command[1])
        return None

    def get_property(self, name: str, timeout: float = 0.5):
        return self.properties.get(name)

    def pause_resume(self):
        self.paused = not self.paused
        self.properties["pause"] = self.paused

    def set_paused(self, paused: bool):
        self.paused = bool(paused)
        self.properties["pause"] = self.paused
        self.commands.append(["set_property", "pause", self.paused])

    def seek(self, seconds: float, mode: str = "absolute"):
        self.seeks.append((seconds, mode))
        self.properties["time-pos"] = seconds

    def set_volume(self, volume: int):
        self.volume = volume
        self._cached_volume = volume
        self.commands.append(["set_property", "volume", volume])

    def get_volume(self) -> int:
        return self.volume
