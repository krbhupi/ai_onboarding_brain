"""Logging configuration for the application."""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from config.settings import BASE_DIR, get_settings

settings = get_settings()


def setup_logging() -> logging.Logger:
    """Configure application logging."""
    logger = logging.getLogger("hr_automation")
    logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

    # Prevent duplicate handlers
    if logger.handlers:
        return logger

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler with rotation
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)

    file_handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
    )
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)

    return logger


logger = setup_logging()