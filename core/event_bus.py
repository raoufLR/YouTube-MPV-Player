"""
Event Bus
=========

Central event dispatcher implementing thread-safe event communication between components.
The event bus decouples event publishers from subscribers, enabling event-driven architecture.

Features:
- Thread-safe event dispatch
- Weak reference management for listeners
- Qt-friendly integration
- Multiple subscribers per event type
- Automatic cleanup of inactive listeners
"""

import threading
import weakref
from typing import Dict, List, Callable, Any
from .events import ApplicationEvent


class EventBus:
    """Thread-safe event dispatcher for loosely coupled component communication"""
    
    def __init__(self):
        self._subscribers: Dict[str, list] = {}
        self._lock = threading.RLock()
    
    def subscribe(self, event_type: str, callback: Callable, weak: bool = True):
        """
        Subscribe to events of a specific type
        
        Args:
            event_type: Type of event to subscribe to
            callback: Function to call when event is published
            weak: Use weak reference to avoid keeping callbacks alive
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            
            if weak:
                ref = weakref.ref(callback, lambda ref, et=event_type: self._callback_removed(ref, et))
                self._subscribers[event_type].append(ref)
            else:
                self._subscribers[event_type].append(callback)
    
    def unsubscribe(self, event_type: str, callback: Callable):
        """
        Unsubscribe from events of a specific type
        
        Args:
            event_type: Type of event to unsubscribe from
            callback: The callback function to remove
        """
        with self._lock:
            if event_type not in self._subscribers:
                return
            
            self._subscribers[event_type] = [
                sub for sub in self._subscribers[event_type]
                if not (isinstance(sub, weakref.ref) and sub() is callback)
                and sub is not callback
            ]
            
            if not self._subscribers[event_type]:
                del self._subscribers[event_type]
    
    def publish(self, event: ApplicationEvent):
        """
        Publish an event to all subscribed listeners
        
        Args:
            event: The event to publish
        """
        if not isinstance(event, ApplicationEvent):
            raise TypeError(f"Event must be ApplicationEvent instance, got {type(event)}")
        
        event_type = event.event_type
        
        with self._lock:
            subscribers_copy = self._subscribers.get(event_type, [])[:]
        
        for subscriber in subscribers_copy:
            try:
                if isinstance(subscriber, weakref.ref):
                    callback = subscriber()
                    if callback:
                        callback(event)
                    else:
                        with self._lock:
                            if event_type in self._subscribers:
                                self._subscribers[event_type] = [
                                    s for s in self._subscribers[event_type]
                                    if s is not subscriber
                                ]
                else:
                    subscriber(event)
            except Exception:
                with self._lock:
                    if event_type in self._subscribers:
                        self._subscribers[event_type] = [
                            sub for sub in self._subscribers[event_type]
                            if sub is not subscriber
                        ]
    
    def get_listeners(self, event_type: str):
        """
        Get all active listeners for a specific event type
        
        Args:
            event_type: Type of event to check
            
        Returns:
            List of active listener callbacks
        """
        with self._lock:
            result = []
            for sub in self._subscribers.get(event_type, []):
                if isinstance(sub, weakref.ref):
                    cb = sub()
                    if cb is not None:
                        result.append(cb)
                else:
                    result.append(sub)
            return result
    
    def clear_subscribers(self, event_type: str = None):
        """
        Clear all subscribers or all subscribers if event_type is None
        
        Args:
            event_type: Specific event type to clear, or None for all
        """
        with self._lock:
            if event_type is not None:
                if event_type in self._subscribers:
                    del self._subscribers[event_type]
            else:
                self._subscribers.clear()
    
    def has_listeners(self, event_type: str):
        """
        Check if there are any active listeners for an event type
        
        Args:
            event_type: Type of event to check
            
        Returns:
            True if there are active listeners, False otherwise
        """
        with self._lock:
            if event_type not in self._subscribers:
                return False
            
            for sub in self._subscribers[event_type]:
                if isinstance(sub, weakref.ref):
                    if sub() is not None:
                        return True
                else:
                    return True
            return False
    
    def _callback_removed(self, callback_ref, event_type=None):
        """
        Callback invoked when a weak reference is garbage collected
        
        Args:
            callback_ref: The garbage collected callback reference
            event_type: Optional event type (passed via closure)
        """
        if event_type is None:
            event_type = getattr(callback_ref, 'event_type', None)
        if event_type and event_type in self._subscribers:
            with self._lock:
                self._subscribers[event_type] = [
                    sub for sub in self._subscribers[event_type]
                    if sub is not callback_ref
                ]
    
    def get_event_types(self):
        """
        Get all event types that have subscribers
        
        Returns:
            Set of event type strings
        """
        with self._lock:
            return set(self._subscribers.keys())
    
    def __repr__(self):
        with self._lock:
            return f"EventBus(subscribers={len(self._subscribers)}, types={len(self._subscribers)})"
