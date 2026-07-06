"""
Application Core
================

This package contains the application bootstrap layer and service management.

The application follows a dependency injection pattern where services are
centrally managed and injected into the UI layer without UI creating services.
"""

from .application import Application
from .service_container import ServiceContainer

__all__ = ['Application', 'ServiceContainer']
