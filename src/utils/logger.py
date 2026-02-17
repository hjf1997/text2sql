"""Logging utilities for Text-to-SQL Agent."""

import logging
import sys
from pathlib import Path
from typing import Optional
from ..config import settings


def setup_logger(
    name: str,
    level: Optional[str] = None,
    log_file: Optional[str] = None,
) -> logging.Logger:
    """Set up a logger with console and optional file handlers.

    Args:
        name: Logger name (usually __name__)
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Get level from config if not provided
    if level is None:
        level = settings.get("logging.level", "INFO")

    logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Get format from config
    log_format = settings.get(
        "logging.format",
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    formatter = logging.Formatter(log_format)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler if specified
    if log_file is None:
        log_file = settings.get("logging.log_file")

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


def mask_sensitive_data(text: str, patterns: list[str] = None) -> str:
    """Mask sensitive data in text for logging.

    Args:
        text: Text potentially containing sensitive data
        patterns: List of patterns to mask (e.g., API keys, passwords)

    Returns:
        Text with sensitive data masked
    """
    import re

    if not settings.get("logging.sensitive_data_masking", True):
        return text

    # Default patterns to mask
    if patterns is None:
        patterns = [
            r'(api[_-]?key["\s:=]+)([a-zA-Z0-9_\-]+)',
            r'(password["\s:=]+)([^\s"]+)',
            r'(bearer\s+)([a-zA-Z0-9_\-\.]+)',
            r'(authorization["\s:=]+)([^\s"]+)',
        ]

    masked_text = text
    for pattern in patterns:
        masked_text = re.sub(
            pattern,
            r'\1***MASKED***',
            masked_text,
            flags=re.IGNORECASE,
        )

    return masked_text


class LogContext:
    """Context manager for adding context to log messages."""

    def __init__(self, logger: logging.Logger, context: dict):
        """Initialize log context.

        Args:
            logger: Logger instance
            context: Context dictionary to include in logs
        """
        self.logger = logger
        self.context = context
        self.old_factory = None

    def __enter__(self):
        """Enter context and modify log record factory."""
        old_factory = logging.getLogRecordFactory()

        def record_factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            for key, value in self.context.items():
                setattr(record, key, value)
            return record

        logging.setLogRecordFactory(record_factory)
        self.old_factory = old_factory
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context and restore original factory."""
        if self.old_factory:
            logging.setLogRecordFactory(self.old_factory)


# Global logger instance for the package
logger = setup_logger("text2sql")
