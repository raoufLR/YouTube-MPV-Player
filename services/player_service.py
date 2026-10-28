"""Playback state and MPV lifecycle management.

``PlayerService`` owns the high-level playback state (playing/paused,
position/duration, volume) and supervises the MPV process.  A lightweight
monitor thread polls MPV's IPC for position and end-of-file, so UI code only
reads cached values and never performs blocking IPC itself.
"""

from __future__ import annotations

import logging
import threading

from core.events import (
    PlaybackErrorEvent,
    VideoPausedEvent,
    VideoStartedEvent,
    VideoStoppedEvent,
)
from core.quality import normalize_quality, validate_stream_url
from player import MpvPlayer, MpvPropertyUnavailableError

DEFAULT_VOLUME = 80
MONITOR_INTERVAL = 0.5


class PlayerService:
    """Service for managing embedded MPV playback (no external window).

    Stream URL resolution is handled by ``StreamResolverService`` /
    ``PlaybackService``; this service only receives playable URLs.
    """

    def __init__(
        self,
        mpv_player: MpvPlayer,
        event_bus=None,
        logger=None,
        *,
        volume: int = DEFAULT_VOLUME,
        monitor_interval: float = MONITOR_INTERVAL,
    ):
        if mpv_player is None:
            raise ValueError("PlayerService requires an MpvPlayer instance (Dependency Injection).")
        self.event_bus = event_bus
        self._logger = logger or logging.getLogger(__name__)
        self.player = mpv_player
        self._lock = threading.RLock()
        self._shutdown = False
        self._has_media = False
        self._paused = False
        self._position = 0.0
        self._duration = 0.0
        self._volume = max(0, min(100, int(volume)))
        self._current_video_id = ""
        self._monitor_interval = max(0.0, float(monitor_interval))
        self._monitor_stop = threading.Event()
        self._monitor_thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def is_playing(self) -> bool:
        with self._lock:
            if self._shutdown or not self._has_media or self._paused:
                return False
            return self._player_is_running()

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    @property
    def has_media(self) -> bool:
        with self._lock:
            return self._has_media

    @property
    def current_video_id(self) -> str:
        with self._lock:
            return self._current_video_id

    def get_position(self) -> float:
        with self._lock:
            return self._position

    def get_duration(self) -> float:
        with self._lock:
            return self._duration

    def get_volume(self) -> int:
        with self._lock:
            return self._volume

    def _player_is_running(self) -> bool:
        running = getattr(self.player, "is_running", None)
        if isinstance(running, bool):
            return running
        process = getattr(self.player, "process", None)
        if process is None:
            return False
        poll = getattr(process, "poll", None)
        if not callable(poll):
            return True
        return poll() is None

    # ------------------------------------------------------------------
    # Playback commands
    # ------------------------------------------------------------------

    def play_video(
        self,
        stream_url,
        quality="best",
        video_data=None,
        win_id: int | None = None,
        *,
        audio_url: str = "",
    ):
        if self._shutdown:
            raise RuntimeError("PlayerService has been shut down")
        url = validate_stream_url(stream_url)
        audio = validate_stream_url(audio_url) if audio_url else ""
        quality = normalize_quality(quality)
        vdata = dict(video_data or {})
        video_id = str(vdata.get("videoId", vdata.get("video_id", "")))

        if self.has_media:
            self.stop()

        try:
            self.player.play(url, quality, win_id=win_id, audio_url=audio)
        except Exception as exc:
            if self.event_bus:
                self.event_bus.publish(
                    PlaybackErrorEvent(
                        error=str(exc),
                        video_id=video_id,
                        stage="playback",
                    )
                )
            raise

        with self._lock:
            self._has_media = True
            self._paused = False
            self._position = 0.0
            self._duration = 0.0
            self._current_video_id = video_id

        try:
            self.player.set_volume(self._volume)
        except Exception:
            self._logger.debug("Unable to apply volume after playback start", exc_info=True)

        self._ensure_monitor()

        if self.event_bus:
            self.event_bus.publish(
                VideoStartedEvent(
                    url=url,
                    quality=quality,
                    video_data=vdata or None,
                    video_id=video_id,
                    title=vdata.get("title", ""),
                    channel=vdata.get("channel", ""),
                    thumbnail=vdata.get("thumbnail", ""),
                )
            )

    def pause_resume(self):
        """Toggle pause and return the new paused state (or ``None``)."""
        with self._lock:
            if self._shutdown or not self._has_media:
                return None
            target = not self._paused
            self._paused = target

        try:
            set_paused = getattr(self.player, "set_paused", None)
            if callable(set_paused):
                set_paused(target)
            else:
                self.player.pause_resume()
        except Exception:
            self._logger.exception("Unable to toggle pause")

        if self.event_bus:
            self.event_bus.publish(VideoPausedEvent(is_paused=target))
        return target

    def set_paused(self, paused: bool):
        with self._lock:
            if self._shutdown or not self._has_media:
                return None
            target = bool(paused)
            if target == self._paused:
                return target
            self._paused = target

        try:
            set_paused = getattr(self.player, "set_paused", None)
            if callable(set_paused):
                set_paused(target)
        except Exception:
            self._logger.exception("Unable to set pause state")

        if self.event_bus:
            self.event_bus.publish(VideoPausedEvent(is_paused=target))
        return target

    def seek_absolute(self, seconds: float):
        with self._lock:
            if self._shutdown or not self._has_media:
                return None
            duration = self._duration
            target = max(0.0, float(seconds))
            if duration > 0:
                target = min(target, duration)
            self._position = target

        try:
            self.player.seek(target, "absolute")
        except Exception:
            self._logger.exception("Unable to seek")
        return target

    def seek_relative(self, delta: float):
        with self._lock:
            position = self._position
        return self.seek_absolute(position + float(delta))

    def set_volume(self, volume):
        try:
            value = int(volume)
        except (TypeError, ValueError):
            return self.get_volume()
        value = max(0, min(100, value))
        with self._lock:
            self._volume = value
        if self._shutdown:
            return value
        try:
            self.player.set_volume(value)
        except Exception:
            self._logger.exception("Unable to set volume")
        return value

    def stop(self):
        """Stop playback; publishes at most one ``VideoStoppedEvent``."""
        with self._lock:
            had_media = self._has_media
            position = self._position
            duration = self._duration
            video_id = self._current_video_id
            self._has_media = False
            self._paused = False
            self._position = 0.0
            self._duration = 0.0
            self._current_video_id = ""

        try:
            self.player.stop()
        except Exception:
            self._logger.exception("Failed to stop MPV")
        finally:
            if had_media and self.event_bus:
                self.event_bus.publish(
                    VideoStoppedEvent(
                        reason="stopped",
                        video_id=video_id,
                        position=position,
                        duration=duration,
                    )
                )

    # ------------------------------------------------------------------
    # Process monitor
    # ------------------------------------------------------------------

    def _ensure_monitor(self):
        if self._monitor_interval <= 0:
            return
        if self._monitor_thread is not None and self._monitor_thread.is_alive():
            return
        self._monitor_stop.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            name="player-monitor",
            daemon=True,
        )
        self._monitor_thread.start()

    def _monitor_loop(self):
        while not self._monitor_stop.wait(self._monitor_interval):
            if self._shutdown:
                continue
            with self._lock:
                has_media = self._has_media
            if not has_media:
                continue
            if not self._player_is_running():
                self._handle_end("exited")
                continue

            try:
                position = self.player.request(
                    ["get_property", "time-pos"], timeout=0.4
                )
                duration = self.player.request(
                    ["get_property", "duration"], timeout=0.4
                )
                paused = self.player.request(
                    ["get_property", "pause"], timeout=0.4
                )
                eof = self.player.request(
                    ["get_property", "eof-reached"], timeout=0.4
                )
            except MpvPropertyUnavailableError:
                # Normal while the file is loading or just after EOF: MPV has
                # not published time-pos/duration yet.  Poll again next tick.
                continue
            except Exception:
                self._logger.debug("MPV state poll failed", exc_info=True)
                continue

            with self._lock:
                if not self._has_media:
                    continue
                if isinstance(position, (int, float)):
                    self._position = max(0.0, float(position))
                if isinstance(duration, (int, float)) and duration > 0:
                    self._duration = float(duration)
                if isinstance(paused, bool):
                    self._paused = paused

            if eof is True:
                self._handle_end("ended")

    def _handle_end(self, reason: str):
        with self._lock:
            if not self._has_media:
                return
            position = self._position
            duration = self._duration
            video_id = self._current_video_id
            self._has_media = False
            self._paused = False
            self._position = 0.0
            self._duration = 0.0
            self._current_video_id = ""

        try:
            self.player.stop()
        except Exception:
            self._logger.exception("Failed to stop MPV after %s", reason)

        if reason == "exited" and self.event_bus:
            self.event_bus.publish(
                PlaybackErrorEvent(
                    error="MPV exited unexpectedly",
                    stage="playback",
                )
            )

        if self.event_bus:
            self.event_bus.publish(
                VideoStoppedEvent(
                    reason=reason,
                    video_id=video_id,
                    position=position,
                    duration=duration,
                )
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def shutdown(self):
        """Stop playback, join the monitor, and make the service inert."""
        with self._lock:
            if self._shutdown:
                return
            self._shutdown = True

        self.stop()
        self._monitor_stop.set()
        thread = self._monitor_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        self._monitor_thread = None
