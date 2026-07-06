from .service_container import ServiceContainer
from core import EventBus
from core.events import ApplicationStartedEvent, ApplicationClosingEvent


class Application:
    def __init__(self):
        self._event_bus = EventBus()
        self._container = ServiceContainer(self._event_bus)
        self._is_running = False

    @property
    def services(self):
        return self._container

    @property
    def event_bus(self):
        return self._event_bus

    def startup(self):
        if self._is_running:
            return

        self._container.create_services()
        self._is_running = True
        self._event_bus.publish(ApplicationStartedEvent())

    def load_profile(self, profile_name: str):
        um = self._container.user_manager_service
        um.switch_profile(profile_name)
        profile_dir = um.current_profile_dir()
        self._container.reload_profile_services(profile_dir)

    def switch_profile(self, profile_name: str):
        um = self._container.user_manager_service
        um.switch_profile(profile_name)
        profile_dir = um.current_profile_dir()
        self._container.reload_profile_services(profile_dir)

    def shutdown(self):
        self._event_bus.publish(ApplicationClosingEvent())
        self._container.shutdown()
        self._is_running = False

    def run(self):
        return self._is_running

    def is_running(self):
        return self._is_running
