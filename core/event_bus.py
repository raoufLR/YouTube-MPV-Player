"""
Event Bus
=========

Central event dispatcher implementing thread-safe event communication between
components.  The event bus decouples event publishers from subscribers,
enabling an event-driven architecture.

Features:
- Thread-safe event dispatch
- Weak references for bound methods (``weakref.WeakMethod``) and functions
- Subscription tokens with deterministic cancellation
- Exception isolation: a failing subscriber never removes other subscribers
- Qt-friendly integration
- Multiple subscribers per event type
- Automatic cleanup of inactive listeners
"""

from __future__ import annotations

import contextlib
import inspect
import logging
import threading
import weakref
from typing import TYPE_CHECKING, Any

from .events import ApplicationEvent

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)


class Subscription:
    """Opaque token returned by :meth:`EventBus.subscribe`.

    Calling :meth:`cancel` is equivalent to ``bus.unsubscribe(event_type,
    callback)`` and is safe to call more than once.  Keeping the token alive is
    optional for strong subscriptions; weak subscriptions are tracked by the
    bus itself so they also do not need to be stored by callers.
    """

    __slots__ = ("event_type", "_strong", "_weak", "_bus_ref", "_active")

    def __init__(
        self,
        event_type: str,
        bus: EventBus,
        *,
        strong: Callable | None = None,
        weak: weakref.ReferenceType | None = None,
    ):
        self.event_type = event_type
        self._strong = strong
        self._weak = weak
        self._bus_ref = weakref.ref(bus)
        self._active = True

    def resolve(self) -> Callable | None:
        """Return the live callback, or ``None`` if it was garbage collected."""
        if not self._active:
            return None
        if self._strong is not None:
            return self._strong
        if self._weak is not None:
            return self._weak()
        return None

    def matches(self, callback: Callable) -> bool:
        if not self._active:
            return False
        if self._strong is not None:
            return self._strong is callback or self._strong == callback
        if self._weak is not None:
            live = self._weak()
            return live is not None and (live is callback or live == callback)
        return False

    def cancel(self) -> bool:
        """Remove this subscription.  Returns ``True`` if it was active."""
        if not self._active:
            return False
        bus = self._bus_ref()
        if bus is None:
            self._active = False
            return False
        return bus._remove_subscription(self)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Subscription(event_type={self.event_type!r}, active={self._active})"


class EventBus:
    """Thread-safe event dispatcher for loosely coupled component communication."""

    def __init__(self):
        self._subscribers: dict[str, list[Subscription]] = {}
        self._lock = threading.RLock()
        # Per-thread coalescing state used by :meth:`coalesced`.
        self._local = threading.local()

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    def subscribe(
        self,
        event_type: str,
        callback: Callable,
        weak: bool = True,
    ) -> Subscription:
        """Subscribe *callback* to events of *event_type*.

        ``weak=True`` stores a weak reference.  Bound methods are handled with
        :class:`weakref.WeakMethod`, which is essential because a normal
        ``weakref.ref(bound_method)`` dies as soon as the temporary bound
        method object goes out of scope.

        The returned :class:`Subscription` can be used to cancel the
        subscription later.  Exceptions raised by callbacks are logged and
        isolated; failing subscribers are not removed automatically.
        """
        if not isinstance(event_type, str):
            raise TypeError("event_type must be a string")
        if not callable(callback):
            raise TypeError("callback must be callable")

        token = self._make_subscription(event_type, callback, weak)

        with self._lock:
            self._subscribers.setdefault(event_type, []).append(token)

        return token

    def _make_subscription(
        self, event_type: str, callback: Callable, weak: bool
    ) -> Subscription:
        if not weak:
            return Subscription(event_type, self, strong=callback)

        token = Subscription(event_type, self)

        def _on_collected(_ref):
            # The closure captures the token, never the callback itself.
            self._remove_subscription(token)

        # Bound methods must use WeakMethod.  weakref.ref(method) would point
        # at a temporary object and be collected before the next publish.
        try:
            if inspect.ismethod(callback):
                ref: weakref.ReferenceType = weakref.WeakMethod(
                    callback, _on_collected
                )
            else:
                ref = weakref.ref(callback, _on_collected)
        except TypeError:
            # Some callables (for example builtins) cannot be weakly
            # referenced.  Falling back to a strong reference is safer than
            # silently losing the subscription.
            _logger.debug(
                "Callback %r cannot be weakly referenced; using a strong "
                "subscription for %s",
                callback,
                event_type,
            )
            token._strong = callback
            return token

        token._weak = ref
        return token

    def _remove_subscription(self, token: Subscription) -> bool:
        with self._lock:
            token._active = False
            subscribers = self._subscribers.get(token.event_type)
            if not subscribers:
                return False
            try:
                subscribers.remove(token)
            except ValueError:
                return False
            if not subscribers:
                del self._subscribers[token.event_type]
            return True

    def unsubscribe(self, event_type: str, callback: Callable) -> bool:
        """Remove a callback or a :class:`Subscription` token.

        Returns ``True`` if at least one matching subscription was removed.
        """
        if isinstance(callback, Subscription):
            return self._remove_subscription(callback)

        removed = False
        with self._lock:
            subscribers = self._subscribers.get(event_type)
            if not subscribers:
                return False
            keep: list[Subscription] = []
            for token in subscribers:
                if token.matches(callback):
                    token._active = False
                    removed = True
                else:
                    keep.append(token)
            if keep:
                self._subscribers[event_type] = keep
            else:
                self._subscribers.pop(event_type, None)
        return removed

    @contextlib.contextmanager
    def coalesced(self):
        """Coalesce publishes made by the calling thread into one per event type.

        Bulk writers (the Takeout importer) would otherwise publish one event
        per inserted item.  Every UI listener reloads a whole view for each
        event, so thousands of queued refreshes freeze the UI.  While the
        context is active, :meth:`publish` only remembers the newest event of
        each type; they are dispatched when the outermost context exits.
        Nesting is supported and only the outermost context flushes.
        """
        pending = getattr(self._local, "pending", None)
        if pending is not None:
            self._local.depth += 1
            try:
                yield
            finally:
                self._local.depth -= 1
            return

        pending = {}
        self._local.pending = pending
        self._local.depth = 1
        try:
            yield
        finally:
            self._local.pending = None
            self._local.depth = 0
            for event in pending.values():
                self.publish(event)

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def publish(self, event: ApplicationEvent):
        """Publish an event to all currently subscribed listeners.

        Dispatch happens outside the lock so callbacks may safely subscribe,
        unsubscribe, or publish other events.  A subscriber exception is logged
        and does not affect other subscribers.
        """
        if not isinstance(event, ApplicationEvent):
            raise TypeError(
                f"Event must be ApplicationEvent instance, got {type(event)}"
            )

        event_type = event.event_type
        pending = getattr(self._local, "pending", None)
        if pending is not None:
            # Listeners refresh whole views, so only the newest event of each
            # type matters while a bulk operation is running.
            pending[event_type] = event
            return

        with self._lock:
            subscribers = list(self._subscribers.get(event_type, ()))

        for token in subscribers:
            callback = token.resolve()
            if callback is None:
                self._remove_subscription(token)
                continue
            try:
                callback(event)
            except Exception:
                _logger.exception(
                    "Subscriber %r failed while handling event %s",
                    callback,
                    event_type,
                )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_listeners(self, event_type: str) -> list[Callable]:
        """Return live listener callbacks for *event_type*."""
        with self._lock:
            subscribers = list(self._subscribers.get(event_type, ()))
            result: list[Callable] = []
            dead: list[Subscription] = []
            for token in subscribers:
                callback = token.resolve()
                if callback is None:
                    dead.append(token)
                else:
                    result.append(callback)
            for token in dead:
                self._remove_subscription(token)
            return result

    def has_listeners(self, event_type: str) -> bool:
        """Return ``True`` when at least one live listener is subscribed."""
        with self._lock:
            subscribers = self._subscribers.get(event_type)
            if not subscribers:
                return False
            dead = [token for token in subscribers if token.resolve() is None]
            for token in dead:
                self._remove_subscription(token)
            return bool(self._subscribers.get(event_type))

    def clear_subscribers(self, event_type: str | None = None):
        """Clear subscribers for one event type, or all when *event_type* is None."""
        with self._lock:
            if event_type is not None:
                for token in self._subscribers.pop(event_type, ()):
                    token._active = False
            else:
                for subscribers in self._subscribers.values():
                    for token in subscribers:
                        token._active = False
                self._subscribers.clear()

    def get_event_types(self):
        """Return the set of event types that currently have subscribers."""
        with self._lock:
            return set(self._subscribers)

    def _purge_dead_locked(self, event_type: str):
        """Remove dead weak references.  Caller must hold ``self._lock``."""
        subscribers = self._subscribers.get(event_type)
        if not subscribers:
            return
        keep = [token for token in subscribers if token.resolve() is not None]
        if keep:
            self._subscribers[event_type] = keep
        else:
            del self._subscribers[event_type]

    def __repr__(self):
        with self._lock:
            return (
                f"EventBus(subscribers={len(self._subscribers)}, "
                f"types={len(self._subscribers)})"
            )


class ThreadSafeEventBus(EventBus):
    """Event bus with optional Qt-main-thread dispatch for background publishers.

    When a dispatcher is configured, :meth:`publish_to_main_thread` hands each
    callback to it instead of invoking it inline.  Subscriber exceptions and
    dead weak references are handled with the same isolation guarantees as
    :class:`EventBus`.
    """

    def __init__(self):
        super().__init__()
        self._main_thread_dispatcher: Callable[[Any, Callable], None] | None = None

    def set_main_thread_dispatcher(
        self, dispatcher: Callable[[Any, Callable], None] | None
    ):
        """Set ``dispatcher(event, callback)``, or ``None`` to disable it."""
        self._main_thread_dispatcher = dispatcher

    def publish_to_main_thread(self, event: ApplicationEvent):
        """Publish *event*, routing callbacks through the main-thread dispatcher."""
        if self._main_thread_dispatcher is None:
            self.publish(event)
            return

        with self._lock:
            subscribers = list(self._subscribers.get(event.event_type, ()))

        for token in subscribers:
            callback = token.resolve()
            if callback is None:
                self._remove_subscription(token)
                continue
            try:
                self._main_thread_dispatcher(event, callback)
            except Exception:
                _logger.exception(
                    "Main-thread dispatch failed for subscriber %r handling %s",
                    callback,
                    event.event_type,
                )
