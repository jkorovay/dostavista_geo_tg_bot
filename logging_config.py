"""
Конфигурация логирования: консоль + файл с ротацией.
Опционально JSON формат (python-json-logger).
"""
import logging
import logging.handlers
import os
from pathlib import Path

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "logs/bot.log")
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", "5_000_000"))
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "3"))

# Создаём директорию для логов
Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)


def setup_logging(level: str = LOG_LEVEL, log_file: str = LOG_FILE, json_format: bool = False):
    """
    Настраивает логирование.

    Args:
        level: Уровень логирования (DEBUG, INFO, WARNING, ERROR)
        log_file: Путь к файлу логов
        json_format: Использовать JSON форматтер (требует python-json-logger)
    """

    handlers = [
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        ),
    ]

    if json_format:
        try:
            from pythonjsonlogger.jsonlogger import JsonFormatter
            formatter = JsonFormatter(
                "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        except ImportError:
            logging.warning("python-json-logger not installed, falling back to standard formatter")
            formatter = logging.Formatter(
                "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
    else:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    for h in handlers:
        h.setFormatter(formatter)

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        handlers=handlers,
    )


def get_logger(name: str) -> logging.Logger:
    """Возвращает logger с заданным именем."""
    return logging.getLogger(name)