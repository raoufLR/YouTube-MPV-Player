"""Application entry point and command-line argument handling."""

from __future__ import annotations

import argparse
import os
import sys
from typing import TYPE_CHECKING

from version import APP_NAME, __version__

if TYPE_CHECKING:
    from collections.abc import Sequence

SELF_TEST_SERVICES = (
    "logging_service",
    "user_manager_service",
    "settings_service",
    "player_service",
    "stream_resolver_service",
    "playback_service",
    "search_service",
    "thumbnail_service",
    "user_profile_service",
    "history_service",
    "likes_service",
    "playlist_service",
    "recommendation_service",
)


def _emit(message: str, *, error: bool = False) -> None:
    """Write a status line when a console stream exists (windowed builds have none)."""
    stream = sys.stderr if error else sys.stdout
    if stream is None:
        return
    try:
        stream.write(message + "\n")
        stream.flush()
    except Exception:
        pass


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser without creating a Qt application."""
    parser = argparse.ArgumentParser(
        prog="youtube-mpv-player",
        description=f"{APP_NAME} — a lightweight desktop YouTube player.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Start and stop core services without showing the UI, then exit.",
    )
    return parser


def parse_args(argv: Sequence[str] | None = None):
    """Parse known app arguments and return Qt arguments separately."""
    parser = build_parser()
    return parser.parse_known_args(list(argv) if argv is not None else None)


def _run_self_test(application) -> int:
    """Verify that the service graph starts cleanly without showing a window."""
    missing = [
        name
        for name in SELF_TEST_SERVICES
        if getattr(application.services, name, None) is None
    ]
    if missing:
        _emit(
            f"{APP_NAME} self-test FAILED: missing services: {', '.join(missing)}",
            error=True,
        )
        return 1

    user_manager = application.services.user_manager_service
    if user_manager.profile_count() < 1:
        _emit(
            f"{APP_NAME} self-test FAILED: no profiles available",
            error=True,
        )
        return 1

    _emit(f"{APP_NAME} {__version__} self-test OK")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the GUI application, or a headless self-test when requested."""
    args, qt_args = parse_args(argv)

    if args.self_test:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PyQt6.QtWidgets import QApplication

    from app import Application

    qt_app = QApplication.instance() or QApplication([sys.argv[0], *qt_args])

    from core.paths import data_root
    from core.single_instance import LOCK_FILENAME, SingleInstanceGuard
    from ui.app_icon import app_icon
    from ui.i18n import install_translations, tr

    qt_app.setWindowIcon(app_icon())
    install_translations(qt_app)

    # One copy per data directory: a second window would race the JSON stores.
    guard = SingleInstanceGuard(os.path.join(data_root(), "User", LOCK_FILENAME))
    if not guard.acquire():
        if args.self_test:
            _emit(
                f"{APP_NAME} self-test FAILED: another instance is running",
                error=True,
            )
            return 1

        from ui.window_activation import focus_existing_instance

        if focus_existing_instance(guard.owner_pid()):
            return 0

        from PyQt6.QtWidgets import QMessageBox

        QMessageBox.information(
            None,
            tr("Already running"),
            tr(
                "YouTube MPV Player is already running. "
                "Close the other window before starting a new copy."
            ),
        )
        return 0

    application = Application()
    exit_code = 0

    try:
        application.startup()

        if args.self_test:
            return _run_self_test(application)

        from ui.main_window import MainWindow
        from ui.pages.profile_selector import ProfileSelectorWindow

        um = application.services.user_manager_service
        if um.profile_count() > 1:
            chosen = ProfileSelectorWindow.select_profile(um)
            if chosen:
                application.load_profile(chosen)
        else:
            profiles = um.list_profiles()
            if profiles:
                application.load_profile(profiles[0].name)

        window = MainWindow(application)
        window.show()
        exit_code = qt_app.exec()

    except Exception as exc:
        if args.self_test:
            _emit(f"{APP_NAME} self-test FAILED: {exc}", error=True)
            return 1
        raise

    finally:
        if application.is_running():
            application.shutdown()
        guard.release()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
