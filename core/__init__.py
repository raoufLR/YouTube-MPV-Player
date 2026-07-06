"""
Core Module
============

This package provides the application's internal communication system using an event bus pattern.
All inter-component communication flows through this event-driven architecture to eliminate
tight coupling and enable loose coupling between services and UI.
"""

from .event_bus import EventBus
from .events import *

__all__ = ['EventBus']
