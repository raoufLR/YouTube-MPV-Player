"""
EventBus Thread Safety Tests — v2.0
Tests that publish from non-Qt threads does not corrupt subscribers.
"""
import gc
import threading
import weakref

from core.event_bus import EventBus, Subscription, ThreadSafeEventBus
from core.events import LikeChangedEvent, SearchStartedEvent


class TestEventBusThreadSafety:
    def test_publish_from_background_thread(self):
        bus = EventBus()
        results = []
        bus.subscribe("search_started", lambda e: results.append(e.query), weak=False)

        def bg_publish():
            bus.publish(SearchStartedEvent(query="test_bg"))

        t = threading.Thread(target=bg_publish)
        t.start()
        t.join(timeout=5)
        assert t.is_alive() is False
        assert len(results) == 1
        assert results[0] == "test_bg"

    def test_weak_ref_cleanup(self):
        bus = EventBus()
        results = []

        def listener(event):
            results.append(event.event_type)

        bus.subscribe("search_started", listener, weak=True)
        bus.publish(SearchStartedEvent(query="x"))
        assert len(results) == 1
        assert bus.has_listeners("search_started")
        # After listener goes out of scope, weak ref should clean up
        del listener
        import gc
        gc.collect()
        # Subscriber list should be cleaned automatically by weakref callback
        assert not bus.has_listeners("search_started")

    def test_thread_safe_event_bus_dispatcher(self):
        bus = ThreadSafeEventBus()
        results = []

        def dispatcher(event, callback):
            # Simulate main-thread dispatch
            callback(event)

        bus.set_main_thread_dispatcher(dispatcher)
        bus.subscribe("search_started", lambda e: results.append(e.event_type), weak=False)
        bus.publish_to_main_thread(SearchStartedEvent(query="main_thread"))
        assert len(results) == 1


class Listener:
    def __init__(self):
        self.calls = 0

    def on_event(self, event):
        self.calls += 1


class TestEventBusSubscriptions:
    def test_bound_method_weak_subscription_survives(self):
        bus = EventBus()
        listener = Listener()

        bus.subscribe("search_started", listener.on_event)
        assert bus.has_listeners("search_started")

        bus.publish(SearchStartedEvent(query="bound"))
        assert listener.calls == 1

        del listener
        gc.collect()
        assert not bus.has_listeners("search_started")

    def test_strong_subscription_keeps_callback_alive_until_cancelled(self):
        bus = EventBus()
        listener = Listener()
        ref = weakref.ref(listener)
        token = bus.subscribe("search_started", listener.on_event, weak=False)

        del listener
        gc.collect()
        assert ref() is not None

        bus.publish(SearchStartedEvent(query="strong"))
        assert ref().calls == 1

        assert isinstance(token, Subscription)
        assert token.cancel() is True
        assert not bus.has_listeners("search_started")
        assert token.cancel() is False

    def test_unsubscribe_by_callback_and_token(self):
        bus = EventBus()

        def first(event):
            pass

        def second(event):
            pass

        token = bus.subscribe("search_started", first, weak=False)
        bus.subscribe("search_started", second, weak=False)

        assert bus.unsubscribe("search_started", first) is True
        assert bus.get_listeners("search_started") == [second]

        assert bus.unsubscribe("search_started", token) is False
        assert bus.unsubscribe("search_started", second) is True
        assert not bus.has_listeners("search_started")

    def test_subscriber_exception_is_isolated_and_retained(self):
        bus = EventBus()
        calls = []

        def broken(event):
            calls.append("broken")
            raise RuntimeError("subscriber failed")

        def healthy(event):
            calls.append("healthy")

        bus.subscribe("search_started", broken, weak=False)
        bus.subscribe("search_started", healthy, weak=False)

        bus.publish(SearchStartedEvent(query="first"))
        bus.publish(SearchStartedEvent(query="second"))

        assert calls.count("broken") == 2
        assert calls.count("healthy") == 2
        assert bus.has_listeners("search_started")

    def test_publish_uses_snapshot_and_allows_mutation(self):
        bus = EventBus()
        calls = []

        def second(event):
            calls.append("second")

        def first(event):
            calls.append("first")
            bus.unsubscribe("search_started", second)

        bus.subscribe("search_started", first, weak=False)
        bus.subscribe("search_started", second, weak=False)

        bus.publish(SearchStartedEvent(query="snapshot"))
        # The snapshot is safe to mutate; an explicitly cancelled callback is
        # skipped for the rest of this dispatch.
        assert calls == ["first"]

        bus.publish(SearchStartedEvent(query="after"))
        assert calls == ["first", "first"]

    def test_thread_safe_dispatcher_failure_does_not_evict(self):
        bus = ThreadSafeEventBus()
        calls = []

        def dispatcher(event, callback):
            calls.append(callback)
            raise RuntimeError("dispatch failed")

        bus.subscribe("search_started", lambda e: None, weak=False)
        bus.set_main_thread_dispatcher(dispatcher)

        bus.publish_to_main_thread(SearchStartedEvent(query="x"))
        bus.publish_to_main_thread(SearchStartedEvent(query="y"))

        assert len(calls) == 2
        assert bus.has_listeners("search_started")


class TestCoalescedPublish:
    def test_only_the_newest_event_of_each_type_is_delivered(self):
        bus = EventBus()
        searches = []
        likes = []
        bus.subscribe("search_started", searches.append, weak=False)
        bus.subscribe("like_changed", likes.append, weak=False)

        with bus.coalesced():
            bus.publish(SearchStartedEvent(query="first"))
            bus.publish(LikeChangedEvent(video_id="abc", is_liked=True))
            bus.publish(SearchStartedEvent(query="second"))
            assert searches == []
            assert likes == []

        assert [event.query for event in searches] == ["second"]
        assert len(likes) == 1

    def test_nested_contexts_flush_only_on_the_outermost_exit(self):
        bus = EventBus()
        seen = []
        bus.subscribe("search_started", seen.append, weak=False)

        with bus.coalesced():
            with bus.coalesced():
                bus.publish(SearchStartedEvent(query="inner"))
            assert seen == []
            bus.publish(SearchStartedEvent(query="outer"))

        assert [event.query for event in seen] == ["outer"]

    def test_publish_after_the_context_is_not_buffered(self):
        bus = EventBus()
        seen = []
        bus.subscribe("search_started", seen.append, weak=False)

        with bus.coalesced():
            bus.publish(SearchStartedEvent(query="buffered"))
        bus.publish(SearchStartedEvent(query="direct"))

        assert [event.query for event in seen] == ["buffered", "direct"]
