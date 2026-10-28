import logging

from core import EventBus
from core.data_bundle import (
    DATA_SCHEMA_VERSION,
    build_bundle,
    bundle_sections,
    validate_bundle,
)
from core.events import ApplicationClosingEvent, ApplicationStartedEvent
from version import APP_NAME, __version__

from .service_container import ServiceContainer

_logger = logging.getLogger(__name__)


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

    # ------------------------------------------------------------------
    # Profile lifecycle
    # ------------------------------------------------------------------

    def load_profile(self, profile_name: str) -> bool:
        """Switch to *profile_name*; return ``False`` when the switch fails.

        Callers use the return value to avoid tearing down UI pages while the
        old profile's services are still active.
        """
        um = self._container.user_manager_service
        if um is None:
            return False
        playback = self._container.playback_service
        if playback is not None:
            # Switching profiles must not leave MPV playing the old profile's
            # video (or a pending resolver) in the background.
            playback.stop()
        if um.switch_profile(profile_name) is None:
            return False
        profile_dir = um.current_profile_dir()
        self._container.reload_profile_services(profile_dir)
        return True

    def switch_profile(self, profile_name: str) -> bool:
        return self.load_profile(profile_name)

    def create_profile(self, name: str):
        um = self._container.user_manager_service
        return um.create_profile(name) if um is not None else None

    def duplicate_profile(self, source_name: str, new_name: str):
        um = self._container.user_manager_service
        return um.duplicate_profile(source_name, new_name) if um is not None else None

    def rename_profile(self, old_name: str, new_name: str) -> bool:
        um = self._container.user_manager_service
        return um.rename_profile(old_name, new_name) if um is not None else False

    def delete_profile(self, name: str) -> bool:
        """Delete a profile, switching away from it first when necessary.

        The active profile cannot be deleted directly because every service
        holds a path into its directory.  Deleting it is still convenient
        through this composition-root wrapper: switch to ``Default`` first,
        then remove the old directory.
        """
        um = self._container.user_manager_service
        if um is None or not isinstance(name, str):
            return False
        if not um.has_profile(name):
            return False

        current = um.current_profile_name()
        if current and current.casefold() == name.strip().casefold():
            if current.casefold() == "default":
                return False
            # Use the normal switch path so playback stops and every
            # profile-scoped service reloads against the Default directory.
            self.load_profile("Default")
            if um.current_profile_name() != "Default":
                return False
        return um.delete_profile(name)

    # ------------------------------------------------------------------
    # Data export / import
    # ------------------------------------------------------------------

    def export_data(self) -> dict:
        """Return a versioned snapshot of the active profile's data."""
        user_manager = self._container.user_manager_service
        profile_name = (
            user_manager.current_profile_name() if user_manager is not None else ""
        ) or ""

        def _export(service_name, method_name, default):
            service = self._container.get(service_name)
            method = getattr(service, method_name, None)
            if not callable(method):
                return default
            try:
                return method()
            except Exception:
                _logger.exception("Failed to export %s", service_name)
                return default

        return build_bundle(
            profile_name=profile_name,
            user_profile=_export("user_profile_service", "export", {}),
            settings=_export("settings_service", "export", {}),
            history=_export("history_service", "export", []),
            likes=_export("likes_service", "export", []),
            playlists=_export("playlist_service", "export_all", {}),
            app_version=f"{APP_NAME} {__version__}",
        )

    def import_data(self, bundle: object) -> bool:
        """Import a bundle produced by :meth:`export_data`.

        Returns ``False`` without changing anything when the bundle envelope
        is invalid.  Individual services sanitize their own sections.
        """
        valid, reason = validate_bundle(bundle)
        if not valid:
            _logger.warning("Rejected data bundle: %s", reason)
            return False

        sections = bundle_sections(bundle)
        results = []

        settings = self._container.get("settings_service")
        if settings is not None and sections["settings"]:
            results.append(settings.import_data(sections["settings"]))

        user_profile = self._container.get("user_profile_service")
        if user_profile is not None and sections["user_profile"]:
            results.append(user_profile.import_data(sections["user_profile"]))

        history = self._container.get("history_service")
        if history is not None:
            history.import_data(sections["history"])
            results.append(True)

        likes = self._container.get("likes_service")
        if likes is not None:
            results.append(likes.import_data(sections["likes"]))

        playlists = self._container.get("playlist_service")
        if playlists is not None and sections["playlists"]:
            imported = playlists.import_all(sections["playlists"])
            results.append(imported > 0)

        player = self._container.get("player_service")
        if player is not None and settings is not None:
            volume = settings.get("volume", 80)
            try:
                player.set_volume(int(volume))
            except (TypeError, ValueError):
                _logger.warning("Ignoring invalid imported volume: %r", volume)

        return all(results) if results else True

    def data_schema_version(self) -> int:
        return DATA_SCHEMA_VERSION

    def shutdown(self):
        """Stop playback, flush data, join threads, and clear subscribers.

        Safe to call repeatedly (including from ``closeEvent`` after an
        explicit shutdown).
        """
        if not self._is_running:
            return
        self._is_running = False

        try:
            self._event_bus.publish(ApplicationClosingEvent())
        except Exception:
            _logger.exception("ApplicationClosingEvent handler failed")

        # Stop playback first so no MPV process outlives the application.
        playback = self._container.playback_service
        if playback is not None:
            try:
                playback.shutdown()
            except Exception:
                _logger.exception("Playback service shutdown failed")

        player = self._container.player_service
        if player is not None:
            try:
                player.shutdown()
            except Exception:
                _logger.exception("Player shutdown failed")

        try:
            self._container.shutdown()
        finally:
            self._event_bus.clear_subscribers()

    def run(self):
        return self._is_running

    def is_running(self):
        return self._is_running
