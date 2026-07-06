import logging
import shutil
import subprocess
import os
import json
import time
import sys
from typing import Optional

QUALITY_MAP = {
    "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
    "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]",
    "best": "bestvideo+bestaudio/best",
}


def _resource_path(relative_path: str) -> str:
    """Get absolute path to a bundled resource, works for dev and PyInstaller EXE."""
    try:
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except AttributeError:
        base_path = os.getcwd()
    return os.path.join(base_path, relative_path)


class MpvPlayer:
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.process = None
        self.ipc_path = r'\\.\pipe\mpv_ipc'
        self._logger = logger or logging.getLogger(__name__)
    
    def play(self, video_url, quality="best"):
        if not video_url or not isinstance(video_url, str):
            raise ValueError("video_url must be a non-empty string")
        if not video_url.startswith(("http://", "https://", "ytdl://")):
            raise ValueError(f"Invalid video URL scheme: {video_url[:20]!r}")

        self.stop()

        bundled_mpv = _resource_path("mpv.exe")
        if os.path.exists(bundled_mpv):
            self.mpv_cmd = bundled_mpv
        elif shutil.which("mpv"):
            self.mpv_cmd = "mpv"
        else:
             raise FileNotFoundError("MPV executable not found.\nPlease download 'mpv.exe' and place it in this folder,\nor install it to your system PATH.")

        ytdl_format = QUALITY_MAP.get(quality)
        if ytdl_format is None:
            self._logger.warning("Unknown quality '%s', falling back to 'best'", quality)
            ytdl_format = QUALITY_MAP["best"]

        cmd = [
            self.mpv_cmd,
            video_url,
            f'--input-ipc-server={self.ipc_path}',
            f'--ytdl-format={ytdl_format}',
            '--force-window=immediate',
            '--keep-open=yes'
        ]

        try:
            creationflags = 0
            if sys.platform == 'win32':
                creationflags = subprocess.CREATE_NO_WINDOW

            self.process = subprocess.Popen(
                cmd,
                creationflags=creationflags
            )
        except FileNotFoundError:
            raise FileNotFoundError("mpv executable not found via PATH.")

    def send_command(self, command):
        """
        Sends a JSON IPC command to the running mpv instance.
        """
        if not self.process or self.process.poll() is not None:
            return

        try:
            # Wait a bit for pipe to be ready if we just started
            time.sleep(0.1) 
            with open(self.ipc_path, 'w+b') as f:
                 cmd_str = json.dumps({"command": command}) + '\n'
                 f.write(cmd_str.encode('utf-8'))
                 f.flush()
        except Exception as e:
            self._logger.warning("IPC Error (%s): %s", command, e)

    def pause_resume(self):
        self.send_command(["cycle", "pause"])

    def set_volume(self, volume):
        self.send_command(["set", "volume", str(volume)])

    def stop(self):
        if self.process:
            try:
                self.send_command(["quit"])
                self.process.terminate()
            except OSError:
                self._logger.debug("Process already terminated")
            self.process = None
