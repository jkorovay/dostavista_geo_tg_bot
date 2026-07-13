"""
Tests for logging configuration.
"""
import logging
import logging.handlers
import tempfile
import os
from pathlib import Path

import pytest

from logging_config import setup_logging, get_logger


def _clear_logging():
    """Clear all handlers from root logger."""
    root = logging.getLogger()
    for h in root.handlers[:]:
        h.close()
        root.removeHandler(h)
    # Reset level to NOTSET so basicConfig works
    root.setLevel(logging.NOTSET)


class TestLoggingConfig:
    """Tests for logging configuration."""

    def test_setup_logging_creates_file_handler(self):
        """Setup creates rotating file handler."""
        # Clear any existing handlers first
        _clear_logging()

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "bot.log"

            setup_logging(level="DEBUG", log_file=str(log_file), json_format=False)

            root_logger = logging.getLogger()
            file_handlers = [
                h for h in root_logger.handlers
                if isinstance(h, logging.handlers.RotatingFileHandler)
            ]
            assert len(file_handlers) == 1
            assert file_handlers[0].baseFilename == str(log_file)

            # Close handlers to release file lock on Windows
            _clear_logging()

    def test_setup_logging_level(self):
        """Setup applies log level."""
        _clear_logging()

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "bot.log"

            setup_logging(level="WARNING", log_file=str(log_file))

            root_logger = logging.getLogger()
            assert root_logger.level == logging.WARNING

            _clear_logging()

    def test_get_logger_returns_logger(self):
        """get_logger returns Logger instance."""
        logger = get_logger("test.module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"

    def test_json_format_when_available(self):
        """JSON formatter used when python-json-logger available."""
        try:
            from pythonjsonlogger import jsonlogger
            has_json = True
        except ImportError:
            has_json = False

        _clear_logging()

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "bot.log"

            setup_logging(level="INFO", log_file=str(log_file), json_format=has_json)

            root_logger = logging.getLogger()
            file_handlers = [
                h for h in root_logger.handlers
                if isinstance(h, logging.handlers.RotatingFileHandler)
            ]

            if has_json:
                from pythonjsonlogger.jsonlogger import JsonFormatter
                assert isinstance(file_handlers[0].formatter, JsonFormatter)
            else:
                # Falls back to standard formatter
                assert isinstance(file_handlers[0].formatter, logging.Formatter)

            _clear_logging()