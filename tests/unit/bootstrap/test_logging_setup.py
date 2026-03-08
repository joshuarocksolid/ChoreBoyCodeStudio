"""Unit tests for bootstrap logging setup."""

import logging
import re
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

import pytest

from app.bootstrap import logging_setup
from app.core import constants

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def reset_app_logger() -> Iterator[None]:
    """Ensure each test starts with a clean app logger."""
    app_logger = logging.getLogger(constants.APP_LOGGER_NAMESPACE)
    _clear_handlers(app_logger)
    logging_setup._set_active_log_path(None)
    yield
    logging_setup._set_active_log_path(None)
    _clear_handlers(app_logger)


# --- Primary tier (existing behavior) ---


def test_configure_app_logging_creates_logs_dir_and_file(tmp_path: Path) -> None:
    """Configuring logging should create the expected app log file."""
    state_root = tmp_path / "state"
    result = logging_setup.configure_app_logging(state_root=state_root)

    logger = logging_setup.get_subsystem_logger("bootstrap")
    logger.info("log bootstrap ready")
    _flush_app_logger_handlers()

    assert result.log_path == state_root / constants.GLOBAL_LOGS_DIRNAME / constants.APP_LOG_FILENAME
    assert result.tier == logging_setup.TIER_PRIMARY
    assert result.warnings == []
    assert result.log_path.parent.exists()
    assert result.log_path.exists()


def test_configure_app_logging_writes_expected_format_fields(tmp_path: Path) -> None:
    """Log lines should include timestamp, level, subsystem, and message."""
    state_root = tmp_path / "state"
    result = logging_setup.configure_app_logging(state_root=state_root)

    logger = logging_setup.get_subsystem_logger("format")
    logger.warning("format check")
    _flush_app_logger_handlers()

    line = result.log_path.read_text(encoding="utf-8").splitlines()[-1]
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
    result = logging_setup.configure_app_logging(state_root=state_root)
    logging_setup.configure_app_logging(state_root=state_root)

    app_logger = logging.getLogger(constants.APP_LOGGER_NAMESPACE)
    file_handlers = [handler for handler in app_logger.handlers if isinstance(handler, logging.FileHandler)]
    assert len(file_handlers) == 1

    logger = logging_setup.get_subsystem_logger("idempotence")
    logger.info("single emission")
    _flush_app_logger_handlers()

    matching_lines = [line for line in result.log_path.read_text(encoding="utf-8").splitlines() if "single emission" in line]
    assert len(matching_lines) == 1


def test_configure_app_logging_respects_state_root_override(tmp_path: Path) -> None:
    """State-root override should control where app logs are written."""
    state_root = tmp_path / "custom-state-root"
    result = logging_setup.configure_app_logging(state_root=state_root)

    logger = logging_setup.get_subsystem_logger("override")
    logger.info("override path")
    _flush_app_logger_handlers()

    expected = state_root / constants.GLOBAL_LOGS_DIRNAME / constants.APP_LOG_FILENAME
    assert result.log_path == expected
    assert expected.exists()


# --- Fallback tier ---


def test_fallback_tier_when_primary_not_writable(tmp_path: Path) -> None:
    """When primary log dir cannot be created, fall back to temp."""
    blocker = tmp_path / "state" / constants.GLOBAL_LOGS_DIRNAME
    blocker.parent.mkdir(parents=True)
    blocker.write_text("I am a file blocking mkdir")

    result = logging_setup.configure_app_logging(state_root=tmp_path / "state")

    assert result.tier == logging_setup.TIER_FALLBACK
    assert result.log_path is not None
    assert constants.GLOBAL_LOGS_DIRNAME in str(result.log_path)
    assert len(result.warnings) >= 1
    assert "Primary log directory not writable" in result.warnings[0]

    logger = logging_setup.get_subsystem_logger("fallback_test")
    logger.info("fallback works")
    _flush_app_logger_handlers()
    assert result.log_path.exists()


# --- Stderr tier ---


def test_stderr_tier_when_all_paths_fail(tmp_path: Path) -> None:
    """When both primary and fallback fail, use stderr handler without crashing."""
    blocker = tmp_path / "state" / constants.GLOBAL_LOGS_DIRNAME
    blocker.parent.mkdir(parents=True)
    blocker.write_text("I am a file blocking mkdir")

    def _fail_try_ensure(path):  # type: ignore[no-untyped-def]
        return None, OSError(f"Simulated failure for {path}")

    with patch.object(logging_setup, "try_ensure_directory", side_effect=_fail_try_ensure):
        result = logging_setup.configure_app_logging(state_root=tmp_path / "state")

    assert result.tier == logging_setup.TIER_STDERR
    assert result.log_path is None
    assert len(result.warnings) >= 2
    assert "Primary log directory not writable" in result.warnings[0]
    assert "stderr" in result.warnings[-1].lower()

    app_logger = logging.getLogger(constants.APP_LOGGER_NAMESPACE)
    stream_handlers = [h for h in app_logger.handlers if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)]
    assert len(stream_handlers) == 1


def test_warnings_contain_actionable_paths(tmp_path: Path) -> None:
    """Fallback warnings should include the failed path for diagnostics."""
    blocker = tmp_path / "state" / constants.GLOBAL_LOGS_DIRNAME
    blocker.parent.mkdir(parents=True)
    blocker.write_text("I am a file blocking mkdir")

    result = logging_setup.configure_app_logging(state_root=tmp_path / "state")

    assert any(str(blocker) in w for w in result.warnings)


def test_get_active_log_path_returns_fallback_when_primary_unwritable(tmp_path: Path) -> None:
    blocker = tmp_path / "state" / constants.GLOBAL_LOGS_DIRNAME
    blocker.parent.mkdir(parents=True)
    blocker.write_text("I am a file blocking mkdir")

    result = logging_setup.configure_app_logging(state_root=tmp_path / "state")

    assert result.tier == logging_setup.TIER_FALLBACK
    active_log_path = logging_setup.get_active_log_path(state_root=tmp_path / "state")
    assert active_log_path == result.log_path


def test_get_active_log_path_ignores_active_log_from_different_state_root(tmp_path: Path) -> None:
    first_state_root = tmp_path / "state_one"
    second_state_root = tmp_path / "state_two"

    first_result = logging_setup.configure_app_logging(state_root=first_state_root)
    assert first_result.log_path is not None
    first_result.log_path.write_text("state one log\n", encoding="utf-8")

    second_expected = logging_setup.global_app_log_path(second_state_root)
    second_expected.parent.mkdir(parents=True, exist_ok=True)
    second_expected.write_text("state two log\n", encoding="utf-8")

    active_for_second = logging_setup.get_active_log_path(state_root=second_state_root)

    assert active_for_second == second_expected


# --- Helpers ---


def _flush_app_logger_handlers() -> None:
    app_logger = logging.getLogger(constants.APP_LOGGER_NAMESPACE)
    for handler in app_logger.handlers:
        handler.flush()


def _clear_handlers(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
