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
        os.makedirs(log_dir, exist_ok=True)
        ensure_private_dir(log_dir)

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

            file_path = os.path.join(log_dir, LOG_FILE)
            file_handler = RotatingFileHandler(
                file_path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT
            )
            file_handler.setLevel(file_level)
            file_handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"
            ))
            root.addHandler(file_handler)
            ensure_private_file(file_path)

        # Also covers handlers installed by an embedding host before startup.
        install_redaction(root)

    def get_logger(self, name: str) -> logging.Logger:
        return logging.getLogger(name)

    def shutdown(self):
        logging.shutdown()
