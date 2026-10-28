import contextlib
import logging
import os
from logging.handlers import RotatingFileHandler

from core.security import ensure_private_dir, ensure_private_file, install_redaction

LOG_DIR = "Logs"
LOG_FILE = "app.log"
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 3


class LoggingService:
    """Configure console + rotating file logging with secret redaction.

    Every handler receives :class:`core.security.RedactionFilter`, so signed
    media URLs (which carry short-lived tokens in the query string) and other
    ``key=value`` secrets are scrubbed before they reach disk or the console.
    Log files are owner-only on POSIX; on Windows the file inherits the ACL of
    the per-user application directory.
    """

    def __init__(self, log_dir: str = LOG_DIR,
                 console_level: int = logging.INFO,
                 file_level: int = logging.DEBUG):
        self._log_dir = log_dir
        self._handlers: list[logging.Handler] = []

        root = logging.getLogger()
        root.setLevel(logging.DEBUG)

        if not root.handlers:
            console = logging.StreamHandler()
            console.setLevel(console_level)
            console.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            ))
            root.addHandler(console)
            self._handlers.append(console)

            file_handler = self._install_file_handler(log_dir, file_level)
            if file_handler is not None:
                self._handlers.append(file_handler)

        # Also covers handlers installed by an embedding host before startup.
        install_redaction(root)

    def _install_file_handler(
        self, log_dir: str, file_level: int
    ) -> logging.Handler | None:
        """Attach the rotating file handler, staying usable when it is not.

        The working directory of a launched shortcut is not guaranteed to be
        writable; failing to create ``Logs/`` must not prevent the UI from
        starting, so the app falls back to console logging.
        """
        try:
            os.makedirs(log_dir, exist_ok=True)
            ensure_private_dir(log_dir)
            file_path = os.path.join(log_dir, LOG_FILE)
            file_handler = RotatingFileHandler(
                file_path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT
            )
            ensure_private_file(file_path)
        except OSError as exc:
            logging.getLogger(__name__).warning(
                "File logging disabled (%s): %s", log_dir, exc
            )
            return None

        file_handler.setLevel(file_level)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"
        ))
        logging.getLogger().addHandler(file_handler)
        return file_handler

    def get_logger(self, name: str) -> logging.Logger:
        return logging.getLogger(name)

    def shutdown(self):
        """Detach and close only the handlers this service installed.

        A global ``logging.shutdown()`` would also close handlers owned by an
        embedding host (or pytest) and leaves our file handler attached to a
        deleted directory between application instances.
        """
        root = logging.getLogger()
        for handler in self._handlers:
            with contextlib.suppress(Exception):
                handler.flush()
                handler.close()
            root.removeHandler(handler)
        self._handlers.clear()
