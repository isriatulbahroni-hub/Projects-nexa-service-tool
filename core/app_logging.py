"""Centralized logging for Nexa Service Tool.

Keeps application logs outside the source tree and provides a small helper
that can be reused by UI pages and background workers without configuring
logging in every module.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import PROJECT_ROOT

LOG_DIR = PROJECT_ROOT / "data" / "logs"
LOG_FILE = LOG_DIR / "nexa-service.log"


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure and return the root Nexa logger, idempotently."""
    logger = logging.getLogger("nexa_service")
    logger.setLevel(level)
    logger.propagate = False

    if logger.handlers:
        return logger

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    logger.addHandler(handler)
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a configured child logger."""
    root = configure_logging()
    return root if not name else root.getChild(name)
