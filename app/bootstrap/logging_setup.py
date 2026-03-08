"""Shared logging bootstrap helpers for the editor process."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import List, NamedTuple, Optional

from app.bootstrap.paths import (
    PathInput,
    global_app_log_path,
    resolve_temp_root,
    try_ensure_directory,
)
from app.core import constants

TIER_PRIMARY = "primary"
TIER_FALLBACK = "fallback"
TIER_STDERR = "stderr"
_ACTIVE_LOG_PATH: Optional[Path] = None


class LoggingResult(NamedTuple):
    log_path: Optional[Path]
    tier: str
    warnings: List[str]


def configure_app_logging(
    state_root: Optional[PathInput] = None, level: int = logging.INFO
) -> LoggingResult:
    """Configure app logging with fallback chain: primary -> temp -> stderr.

    Never raises due to directory/file creation failures.
    """
    warnings: List[str] = []

    app_logger = logging.getLogger(constants.APP_LOGGER_NAMESPACE)
    app_logger.setLevel(level)
    app_logger.propagate = False
    formatter = logging.Formatter(constants.APP_LOG_FORMAT, constants.APP_LOG_DATE_FORMAT)

    log_path, tier = _resolve_log_path_with_fallback(state_root, warnings)

    if log_path is not None:
        _configure_file_handler(app_logger, log_path, formatter, level)
    else:
        _configure_stderr_handler(app_logger, formatter, level)
    _set_active_log_path(log_path)

    return LoggingResult(log_path=log_path, tier=tier, warnings=warnings)


def get_subsystem_logger(subsystem: str) -> logging.Logger:
    """Return an app-namespaced logger for a subsystem."""
    normalized = subsystem.strip()
    if not normalized:
        raise ValueError("subsystem must be a non-empty string")
    return logging.getLogger(f"{constants.APP_LOGGER_NAMESPACE}.{normalized}")


def get_active_log_path(state_root: Optional[PathInput] = None) -> Optional[Path]:
    """Return currently configured app log path, falling back to canonical path if present."""
    if _ACTIVE_LOG_PATH is not None:
        resolved = _ACTIVE_LOG_PATH.resolve()
        if resolved.exists():
            return resolved
    fallback = global_app_log_path(state_root)
    if fallback.exists():
        return fallback.resolve()
    return None


def _resolve_log_path_with_fallback(
    state_root: Optional[PathInput],
    warnings: List[str],
) -> tuple[Optional[Path], str]:
    """Try primary then temp log path; return (path, tier) or (None, "stderr")."""
    primary_path = global_app_log_path(state_root)
    created, error = try_ensure_directory(primary_path.parent)
    if created is not None:
        return primary_path, TIER_PRIMARY

    warnings.append(
        f"Primary log directory not writable: {primary_path.parent} ({error})"
    )

    fallback_path = (
        resolve_temp_root()
        / constants.GLOBAL_LOGS_DIRNAME
        / constants.APP_LOG_FILENAME
    )
    created, error = try_ensure_directory(fallback_path.parent)
    if created is not None:
        warnings.append(f"Using fallback log path: {fallback_path}")
        return fallback_path, TIER_FALLBACK

    warnings.append(
        f"Fallback log directory not writable: {fallback_path.parent} ({error}). "
        "Logging to stderr only."
    )
    return None, TIER_STDERR


def _configure_file_handler(
    app_logger: logging.Logger,
    log_path: Path,
    formatter: logging.Formatter,
    level: int,
) -> None:
    target_path = log_path.resolve()
    active_handler: Optional[logging.FileHandler] = None

    for handler in list(app_logger.handlers):
        if isinstance(handler, logging.FileHandler):
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


def _configure_stderr_handler(
    app_logger: logging.Logger,
    formatter: logging.Formatter,
    level: int,
) -> None:
    for handler in list(app_logger.handlers):
        app_logger.removeHandler(handler)
        handler.close()

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    handler.setFormatter(formatter)
    app_logger.addHandler(handler)


def _set_active_log_path(log_path: Optional[Path]) -> None:
    global _ACTIVE_LOG_PATH
    _ACTIVE_LOG_PATH = None if log_path is None else log_path.resolve()
