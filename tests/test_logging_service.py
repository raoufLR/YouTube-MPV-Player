"""Logging setup degrades gracefully when the log directory is unusable."""

import logging
import os
from logging.handlers import RotatingFileHandler

import pytest

from services.logging_service import LoggingService


@pytest.fixture
def clean_root_logger():
    root = logging.getLogger()
    saved = list(root.handlers)
    root.handlers.clear()
    try:
        yield root
    finally:
        for handler in list(root.handlers):
            handler.close()
            root.removeHandler(handler)
        for handler in saved:
            root.addHandler(handler)


def test_valid_directory_gets_a_rotating_file_handler(tmp_path, clean_root_logger):
    # Pytest's logging plugin attaches capture handlers after fixtures run.
    clean_root_logger.handlers.clear()

    LoggingService(log_dir=str(tmp_path / "Logs"))

    handlers = [
        handler
        for handler in clean_root_logger.handlers
        if isinstance(handler, RotatingFileHandler)
    ]
    assert len(handlers) == 1
    assert (tmp_path / "Logs" / "app.log").is_file()


def test_unusable_directory_does_not_prevent_startup(tmp_path, clean_root_logger):
    clean_root_logger.handlers.clear()

    blocker = tmp_path / "Logs"
    blocker.write_text("not a directory", encoding="utf-8")

    LoggingService(log_dir=str(blocker))

    assert not any(
        isinstance(handler, RotatingFileHandler)
        for handler in clean_root_logger.handlers
    )
    assert any(
        isinstance(handler, logging.StreamHandler)
        for handler in clean_root_logger.handlers
    )


def test_shutdown_detaches_and_closes_its_handlers(tmp_path, clean_root_logger):
    clean_root_logger.handlers.clear()
    service = LoggingService(log_dir=str(tmp_path / "Logs"))
    log_file = tmp_path / "Logs" / "app.log"
    assert log_file.is_file()

    service.shutdown()

    assert clean_root_logger.handlers == []
    # Closed on Windows too: a stale handler would lock the file.
    os.unlink(log_file)
