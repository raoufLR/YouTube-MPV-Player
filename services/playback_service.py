"""Asynchronous playback orchestration.

``PlaybackService`` turns a video ID into playback without blocking the UI:
stream resolution runs on a worker thread, superseded requests are cancelled,
and only the newest request may start MPV.  This removes the previous
synchronous ``resolve → Popen → 300 ms sleep`` path from the Qt main thread.
"""

from __future__ import annotations

import logging
import threading

from core.events import (
    PlaybackErrorEvent,
    StreamResolvedEvent,
    StreamResolveFailedEvent,
    StreamResolvingEvent,
)
from core.playback_errors import StreamCancelledError
from core.quality import normalize_quality, validate_video_id


class PlaybackService:
    """Serialize playback requests and resolve them in the background."""

    def __init__(
        self,
        stream_resolver,
        player_service,
        event_bus=None,
        logger: logging.Logger | None = None,
    ):
        if stream_resolver is None:
            raise ValueError("PlaybackService requires a stream resolver")
        if player_service is None:
            raise ValueError("PlaybackService requires a PlayerService")
        self._resolver = stream_resolver
        self._player_service = player_service
        self._event_bus = event_bus
        self._logger = logger or logging.getLogger(__name__)

        self._lock = threading.RLock()
        self._start_lock = threading.Lock()
        self._request_id = 0
        self._cancel_event: threading.Event | None = None
        self._threads: set[threading.Thread] = set()
        self._current_thread: threading.Thread | None = None
        self._last_request = None
        self._shutdown = False
        self._last_error = ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_resolving(self) -> bool:
        with self._lock:
            thread = self._current_thread
            return thread is not None and thread.is_alive()

    @property
    def last_error(self) -> str:
        with self._lock:
            return self._last_error

    @property
    def last_request(self):
        with self._lock:
            return self._last_request

    def play(
        self,
        video_id: str,
        quality: str = "best",
        video_data=None,
        win_id: int | None = None,
    ) -> int:
        """Request playback and return the request token.

        Any previous request is cancelled.  This method never blocks on
        network or process startup.
        """
        validate_video_id(video_id)
        normalized_quality = normalize_quality(quality)
        vdata = dict(video_data or {})

        with self._lock:
            if self._shutdown:
                raise RuntimeError("PlaybackService has been shut down")
            self._request_id += 1
            token = self._request_id
            previous = self._cancel_event
            cancel_event = threading.Event()
            self._cancel_event = cancel_event
            self._last_request = (video_id, normalized_quality, vdata, win_id)
            self._last_error = ""
            thread = threading.Thread(
                target=self._worker,
                args=(token, video_id, normalized_quality, vdata, win_id, cancel_event),
                name=f"playback-resolve-{token}",
                daemon=True,
            )
            self._threads.add(thread)
            self._current_thread = thread

        if previous is not None:
            previous.set()

        if self._event_bus:
            self._event_bus.publish(
                StreamResolvingEvent(video_id=video_id, quality=normalized_quality)
            )

        thread.start()
        return token

    def replay(self) -> int | None:
        """Replay the most recent request through a fresh resolution."""
        with self._lock:
            last = self._last_request
        if last is None:
            return None
        video_id, quality, video_data, win_id = last
        return self.play(video_id, quality, video_data, win_id)

    def stop(self):
        """Cancel pending resolution and stop current playback."""
        with self._lock:
            self._request_id += 1
            cancel_event, self._cancel_event = self._cancel_event, None
            self._current_thread = None
        if cancel_event is not None:
            cancel_event.set()

        # Serialize commit-vs-stop: if a worker is about to start MPV, wait for
        # it so the stop cannot be lost.
        with self._start_lock:
            self._player_service.stop()

    def wait(self, timeout: float = 5.0) -> bool:
        """Wait for all in-flight resolve workers.  Returns ``True`` if idle."""
        with self._lock:
            threads = list(self._threads)
        for thread in threads:
            if thread.is_alive():
                thread.join(timeout=timeout)
        with self._lock:
            return not any(thread.is_alive() for thread in self._threads)

    def shutdown(self):
        if self._shutdown:
            return
        self.stop()
        with self._lock:
            self._shutdown = True
        self.wait(timeout=2.0)
        with self._lock:
            self._threads.clear()
            self._current_thread = None

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    def _is_current(self, token: int) -> bool:
        with self._lock:
            return token == self._request_id and not self._shutdown

    def _worker(
        self,
        token: int,
        video_id: str,
        quality: str,
        video_data: dict,
        win_id: int | None,
        cancel_event: threading.Event,
    ):
        thread = threading.current_thread()
        try:
            vdata = dict(video_data or {})
            if not vdata.get("title"):
                try:
                    info = self._resolver.resolve_metadata(
                        video_id, cancel_event=cancel_event
                    )
                except StreamCancelledError:
                    return
                except Exception:
                    self._logger.debug(
                        "Metadata enrichment failed for %s", video_id, exc_info=True
                    )
                else:
                    if info and self._is_current(token):
                        vdata = {**info, **{k: v for k, v in vdata.items() if v}}

            try:
                media = self._resolver.resolve_stream(
                    video_id,
                    quality,
                    cancel_event=cancel_event,
                    publish_events=False,
                )
            except StreamCancelledError:
                return
            except Exception as exc:
                if not self._is_current(token):
                    return
                with self._lock:
                    self._last_error = str(exc)
                self._publish(
                    StreamResolveFailedEvent(
                        video_id=video_id,
                        quality=quality,
                        error=str(exc),
                    )
                )
                self._publish(
                    PlaybackErrorEvent(
                        error=str(exc),
                        video_id=video_id,
                        stage="resolve",
                    )
                )
                return

            if cancel_event.is_set() or not self._is_current(token):
                return

            video_url = getattr(media, "video_url", media)
            audio_url = getattr(media, "audio_url", "")

            self._publish(
                StreamResolvedEvent(video_id=video_id, url=video_url, quality=quality)
            )

            with self._start_lock:
                if cancel_event.is_set() or not self._is_current(token):
                    return
                try:
                    self._player_service.play_video(
                        video_url,
                        quality,
                        vdata,
                        win_id=win_id,
                        audio_url=audio_url,
                    )
                except Exception:
                    # PlayerService already published a PlaybackErrorEvent.
                    with self._lock:
                        self._last_error = "Playback failed"
                    return
        except Exception:
            self._logger.exception("Playback worker failed for %s", video_id)
        finally:
            with self._lock:
                self._threads.discard(thread)
                if self._current_thread is thread:
                    self._current_thread = None

    def _publish(self, event):
        if self._event_bus:
            self._event_bus.publish(event)
