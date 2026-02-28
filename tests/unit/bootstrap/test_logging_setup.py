"""Unit tests for bootstrap logging setup."""

import logging
import re
from pathlib import Path
from typing import Iterator

import pytest

from app.bootstrap import logging_setup
from app.core import constants

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def reset_app_logger() -> Iterator[None]:
    """Ensure each test starts with a clean app logger."""
    app_logger = logging.getLogger(constants.APP_LOGGER_NAMESPACE)
    _clear_handlers(app_logger)
    yield
    _clear_handlers(app_logger)


def test_configure_app_logging_creates_logs_dir_and_file(tmp_path: Path) -> None:
    """Configuring logging should create the expected app log file."""
    state_root = tmp_path / "state"
    log_path = logging_setup.configure_app_logging(state_root=state_root)

    logger = logging_setup.get_subsystem_logger("bootstrap")
    logger.info("log bootstrap ready")
    _flush_app_logger_handlers()

    assert log_path == state_root / constants.GLOBAL_LOGS_DIRNAME / constants.APP_LOG_FILENAME
    assert log_path.parent.exists()
    assert log_path.exists()


def test_configure_app_logging_writes_expected_format_fields(tmp_path: Path) -> None:
    """Log lines should include timestamp, level, subsystem, and message."""
    state_root = tmp_path / "state"
    log_path = logging_setup.configure_app_logging(state_root=state_root)

    logger = logging_setup.get_subsystem_logger("format")
    logger.warning("format check")
    _flush_app_logger_handlers()

    line = log_path.read_text(encoding="utf-8").splitlines()[-1]
    parts = line.split(" | ", 3)

    assert len(parts) == 4
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", parts[0])
    assert parts[1] == "WARNING"
    assert parts[2] == f"{constants.APP_LOGGER_NAMESPACE}.format"
    assert parts[3] == "format check"


def test_get_subsystem_logger_returns_namespaced_logger() -> None:
    """Subsystem logger names should be app-namespace scoped."""
    logger = logging_setup.get_subsystem_logger("runner")
    assert logger.name == f"{constants.APP_LOGGER_NAMESPACE}.runner"


def test_configure_app_logging_is_idempotent(tmp_path: Path) -> None:
    """Repeated configure calls should not duplicate file handlers."""
    state_root = tmp_path / "state"
    log_path = logging_setup.configure_app_logging(state_root=state_root)
    logging_setup.configure_app_logging(state_root=state_root)

    app_logger = logging.getLogger(constants.APP_LOGGER_NAMESPACE)
    file_handlers = [handler for handler in app_logger.handlers if isinstance(handler, logging.FileHandler)]
    assert len(file_handlers) == 1

    logger = logging_setup.get_subsystem_logger("idempotence")
    logger.info("single emission")
    _flush_app_logger_handlers()

    matching_lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if "single emission" in line]
    assert len(matching_lines) == 1


def test_configure_app_logging_respects_state_root_override(tmp_path: Path) -> None:
    """State-root override should control where app logs are written."""
    state_root = tmp_path / "custom-state-root"
    log_path = logging_setup.configure_app_logging(state_root=state_root)

    logger = logging_setup.get_subsystem_logger("override")
    logger.info("override path")
    _flush_app_logger_handlers()

    expected = state_root / constants.GLOBAL_LOGS_DIRNAME / constants.APP_LOG_FILENAME
    assert log_path == expected
    assert expected.exists()


def _flush_app_logger_handlers() -> None:
    app_logger = logging.getLogger(constants.APP_LOGGER_NAMESPACE)
    for handler in app_logger.handlers:
        handler.flush()


def _clear_handlers(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
