"""Shared logging bootstrap helpers for the editor process."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from app.bootstrap.paths import PathInput, ensure_directory, global_app_log_path
from app.core import constants


def configure_app_logging(state_root: Optional[PathInput] = None, level: int = logging.INFO) -> Path:
    """Configure deterministic file-based app logging and return the log path."""
    log_path = global_app_log_path(state_root)
    ensure_directory(log_path.parent)

    app_logger = logging.getLogger(constants.APP_LOGGER_NAMESPACE)
    app_logger.setLevel(level)
    app_logger.propagate = False

    formatter = logging.Formatter(constants.APP_LOG_FORMAT, constants.APP_LOG_DATE_FORMAT)
    _configure_file_handler(app_logger, log_path, formatter, level)
    return log_path


def get_subsystem_logger(subsystem: str) -> logging.Logger:
    """Return an app-namespaced logger for a subsystem."""
    normalized = subsystem.strip()
    if not normalized:
        raise ValueError("subsystem must be a non-empty string")
    return logging.getLogger(f"{constants.APP_LOGGER_NAMESPACE}.{normalized}")


def _configure_file_handler(
    app_logger: logging.Logger,
    log_path: Path,
    formatter: logging.Formatter,
    level: int,
) -> None:
    target_path = log_path.resolve()
    active_handler: Optional[logging.FileHandler] = None

    for handler in list(app_logger.handlers):
        if not isinstance(handler, logging.FileHandler):
            continue

        handler_path = Path(handler.baseFilename).resolve()
        if handler_path == target_path:
            active_handler = handler
            continue

        app_logger.removeHandler(handler)
        handler.close()

    if active_handler is None:
        active_handler = logging.FileHandler(target_path, encoding="utf-8")
        app_logger.addHandler(active_handler)

    active_handler.setLevel(level)
    active_handler.setFormatter(formatter)
