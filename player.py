"""MPV subprocess wrapper with a robust, asynchronous IPC channel.

The player launches one MPV process per video.  Commands are sent through a
single background IPC worker so UI threads never perform blocking pipe I/O.
Each player instance uses a unique named pipe, which prevents one instance
from accidentally sending commands to a stale MPV process.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import Future
from typing import TYPE_CHECKING, Any

from core.quality import QUALITY_MAP, format_selector, validate_stream_url

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["MpvPlayer", "MpvIPC", "MpvIPCError", "QUALITY_MAP"]


class MpvIPCError(RuntimeError):
    """Raised when an IPC command cannot be delivered or returns an error."""


class MpvPropertyUnavailableError(MpvIPCError):
    """Raised when MPV has not loaded a requested property yet.

    MPV answers ``property unavailable`` while a file is still loading or
    after playback has ended.  Callers polling state (for example the
    position monitor) treat this as "not ready yet" rather than a failure.
    """


def _resource_path(relative_path: str) -> str:
    base_path = getattr(sys, "_MEIPASS", None)
    if base_path is None:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


class MpvIPC:
    """Thread-safe MPV JSON IPC client backed by a single worker thread."""

    def __init__(self, path: str, logger: logging.Logger | None = None):
        if not path:
            raise ValueError("IPC path must not be empty")
        self._path = path
        self._logger = logger or logging.getLogger(__name__)
        self._queue: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._request_id = 0
        self._closed = False
        self._worker = threading.Thread(
            target=self._worker_loop,
            name="mpv-ipc",
            daemon=True,
        )
        self._worker.start()

    @property
    def path(self) -> str:
        return self._path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send(self, command, timeout: float = 1.0) -> None:
        """Queue a fire-and-forget command."""
        self._submit(command, wait=False, timeout=timeout)

    def request(self, command, timeout: float = 0.75) -> Any:
        """Send a command and wait up to *timeout* seconds for its result."""
        future = Future()
        self._submit(command, wait=True, timeout=timeout, future=future)
        try:
            return future.result(timeout=timeout)
        except TimeoutError as exc:
            raise MpvIPCError(f"Timed out waiting for MPV command {command!r}") from exc

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._queue.put(None)
        if self._worker.is_alive():
            self._worker.join(timeout=0.5)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _submit(self, command, *, wait: bool, timeout: float, future: Future | None = None):
        if not command:
            raise ValueError("IPC command must not be empty")
        with self._lock:
            if self._closed:
                raise MpvIPCError("IPC channel is closed")
        self._queue.put((list(command), wait, timeout, future))

    def _worker_loop(self):
        while True:
            item = self._queue.get()
            if item is None:
                return
            command, wait, timeout, future = item
            try:
                result = self._execute(command, wait=wait, timeout=timeout)
            except Exception as exc:
                if future is not None:
                    future.set_exception(exc)
                else:
                    self._logger.debug("MPV IPC command %r failed: %s", command, exc)
            else:
                if future is not None:
                    future.set_result(result)

    def _execute(self, command, *, wait: bool, timeout: float):
        deadline = time.monotonic() + max(0.05, timeout)
        with self._lock:
            self._request_id += 1
            request_id = self._request_id if wait else None

        payload: dict[str, Any] = {"command": command}
        if request_id is not None:
            payload["request_id"] = request_id
        data = (json.dumps(payload) + "\n").encode("utf-8")

        last_error: BaseException | None = None
        while True:
            try:
                with open(self._path, "r+b", buffering=0) as pipe:
                    pipe.write(data)
                    pipe.flush()
                    if not wait:
                        return None
                    return self._read_response(pipe, request_id)
            except (FileNotFoundError, ConnectionError, BrokenPipeError) as exc:
                last_error = exc
            except OSError as exc:
                last_error = exc
                if getattr(exc, "winerror", None) not in (2, 5, 109, 231, 232, 233) and exc.errno not in (
                    2,
                    5,
                    11,
                    22,
                    32,
                    109,
                    231,
                    232,
                ):
                    raise MpvIPCError(f"MPV IPC failed: {exc}") from exc

            if time.monotonic() >= deadline:
                raise MpvIPCError(
                    f"MPV IPC pipe {self._path!r} is unavailable: {last_error}"
                )
            time.sleep(0.02)

    @staticmethod
    def _read_response(pipe, request_id: int):
        while True:
            line = pipe.readline()
            if not line:
                raise MpvIPCError("MPV closed the IPC pipe")
            try:
                message = json.loads(line.decode("utf-8") if isinstance(line, bytes) else line)
            except (ValueError, UnicodeDecodeError):
                continue
            if message.get("request_id") != request_id:
                continue
            error = message.get("error", "success")
            if error != "success":
                if error == "property unavailable":
                    raise MpvPropertyUnavailableError(
                        "MPV property is not available yet"
                    )
                raise MpvIPCError(f"MPV command failed: {error}")
            return message.get("data")


class MpvPlayer:
    """MPV player with optional embedded mode (``--wid``) for in-app playback."""

    def __init__(
        self,
        logger: logging.Logger | None = None,
        embed_win_id: int | None = None,
        *,
        mpv_executable: str | None = None,
        popen_factory: Callable | None = None,
        ipc_factory: Callable[[str], MpvIPC] | None = None,
        startup_timeout: float = 0.25,
    ):
        self.process = None
        self.ipc_path = r"\\.\pipe\mpv_ipc"
        self._logger = logger or logging.getLogger(__name__)
        self.embed_win_id = embed_win_id
        self.current_url: str | None = None
        self.current_audio_url: str | None = None
        self._cached_volume = 80
        self._volume = 80
        self._mpv_executable = mpv_executable
        self._popen_factory = popen_factory or subprocess.Popen
        self._ipc_factory = ipc_factory or (lambda path: MpvIPC(path, self._logger))
        self._startup_timeout = startup_timeout
        self._ipc: MpvIPC | None = None
        self.mpv_cmd: str | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def ipc(self) -> MpvIPC | None:
        return self._ipc

    @property
    def is_running(self) -> bool:
        process = self.process
        return process is not None and process.poll() is None

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------

    def play(
        self,
        video_url,
        quality="best",
        win_id: int | None = None,
        audio_url: str = "",
    ):
        stream_url = validate_stream_url(video_url)
        audio_stream = validate_stream_url(audio_url) if audio_url else ""
        self.stop()

        self.mpv_cmd = self._resolve_executable()
        self.ipc_path = self._make_ipc_path()
        self.current_url = stream_url
        self.current_audio_url = audio_stream or None

        cmd = [
            self.mpv_cmd,
            stream_url,
            f"--input-ipc-server={self.ipc_path}",
            f"--ytdl-format={format_selector(quality)}",
            "--no-terminal",
        ]
        if audio_stream:
            cmd.append(f"--audio-file={audio_stream}")

        target_win_id = win_id or self.embed_win_id
        if target_win_id is not None:
            cmd.extend(
                [
                    f"--wid={target_win_id}",
                    "--no-border",
                    "--no-window-dragging",
                    "--force-window=immediate",
                    "--keep-open=yes",
                    "--idle=no",
                ]
            )
        else:
            cmd.extend(["--force-window=immediate", "--keep-open=yes"])

        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            self.process = self._popen_factory(cmd, creationflags=creationflags)
        except FileNotFoundError as exc:
            self.process = None
            self.current_url = None
            raise FileNotFoundError(
                "mpv executable not found.\nPlease download 'mpv.exe' and place it in this folder."
            ) from exc

        try:
            self._ipc = self._ipc_factory(self.ipc_path)
            self._verify_started()
            self.set_volume(self._volume)
        except Exception:
            self.stop()
            raise

    def _verify_started(self):
        """Fail fast when MPV exits immediately and return once IPC is ready."""
        process = self.process
        if process is None:
            return
        deadline = time.monotonic() + max(0.0, self._startup_timeout)
        while time.monotonic() < deadline:
            if process.poll() is not None:
                code = process.returncode
                self._cleanup_process()
                raise RuntimeError(f"MPV exited immediately with code {code}")
            try:
                with open(self.ipc_path, "r+b", buffering=0):
                    return
            except OSError:
                time.sleep(0.02)

    def wait_until_started(self, timeout: float = 2.0) -> bool:
        """Wait until the IPC pipe answers; used by tests and diagnostics."""
        deadline = time.monotonic() + max(0.0, timeout)
        while time.monotonic() < deadline:
            if not self.is_running:
                return False
            try:
                if self.get_property("pid", timeout=0.2) is not None:
                    return True
            except Exception:
                pass
            time.sleep(0.02)
        return False

    def _resolve_executable(self) -> str:
        if self._mpv_executable:
            return self._mpv_executable
        bundled = _resource_path("mpv.exe")
        if os.path.exists(bundled):
            return bundled
        found = shutil.which("mpv")
        if found:
            return found
        raise FileNotFoundError(
            "MPV executable not found.\nPlease download 'mpv.exe' and place it in this folder."
        )

    @staticmethod
    def _make_ipc_path() -> str:
        token = uuid.uuid4().hex[:10]
        return rf"\\.\pipe\ytmpv-{os.getpid()}-{token}"

    # ------------------------------------------------------------------
    # IPC API
    # ------------------------------------------------------------------

    def send_command(self, command, timeout: float = 0.75):
        """Send a command without waiting for a response."""
        if not self.is_running or self._ipc is None:
            return False
        try:
            self._ipc.send(command, timeout=timeout)
            return True
        except Exception as exc:
            self._logger.warning("IPC error (%s): %s", command, exc)
            return False

    def request(self, command, timeout: float = 0.5):
        """Send a command and return MPV's response data."""
        if not self.is_running or self._ipc is None:
            return None
        return self._ipc.request(command, timeout=timeout)

    def pause_resume(self) -> bool | None:
        if self.is_running:
            self.send_command(["cycle", "pause"])
            return None
        return None

    def set_paused(self, paused: bool):
        self.set_property("pause", bool(paused))

    def set_property(self, name: str, value):
        self.send_command(["set_property", name, value])

    def get_property(self, name: str, timeout: float = 0.5):
        return self.request(["get_property", name], timeout=timeout)

    def seek(self, seconds: float, mode: str = "absolute"):
        self.send_command(["seek", str(max(0.0, float(seconds))), mode])

    def set_volume(self, volume):
        try:
            value = int(volume)
        except (TypeError, ValueError):
            value = 80
        value = max(0, min(100, value))
        self._volume = value
        self._cached_volume = value
        self.set_property("volume", value)

    def get_volume(self) -> int:
        return self._volume

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------

    def stop(self):
        """Stop MPV, escalating from IPC quit to terminate to kill."""
        process = self.process
        if process is None:
            self._cleanup_process()
            return

        if self._ipc is not None and process.poll() is None:
            try:
                self._ipc.send(["quit"], timeout=0.4)
            except Exception as exc:
                self._logger.debug("Unable to send quit command: %s", exc)

        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    try:
                        process.wait(timeout=1.0)
                    except subprocess.TimeoutExpired:
                        self._logger.warning("MPV process did not exit after kill")
        except OSError as exc:
            self._logger.debug("Process already terminated: %s", exc)
        finally:
            self._cleanup_process()

    def _cleanup_process(self):
        ipc, self._ipc = self._ipc, None
        if ipc is not None:
            with contextlib.suppress(Exception):
                ipc.close()
        self.process = None
        self.current_url = None
        self.current_audio_url = None
