import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional

LOG_DIR = "Logs"
LOG_FILE = "app.log"
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 3


class LoggingService:
    def __init__(self, log_dir: str = LOG_DIR,
                 console_level: int = logging.INFO,
                 file_level: int = logging.DEBUG):
        self._log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)

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

    def get_logger(self, name: str) -> logging.Logger:
        return logging.getLogger(name)

    def shutdown(self):
        logging.shutdown()
