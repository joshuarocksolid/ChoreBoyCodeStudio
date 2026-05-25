"""Unit tests for shell run-session metadata store."""

from __future__ import annotations

import pytest

from app.core import constants
from app.run.run_service import RunSession
from app.shell.run_session_store import RunSessionStore

pytestmark = pytest.mark.unit


def _run_session(*, mode: str = constants.RUN_MODE_PYTHON_SCRIPT) -> RunSession:
    return RunSession(
        run_id="run123",
        manifest_path="/tmp/project/cbcs/runs/run.json",
        log_file_path="/tmp/project/logs/run_run123.log",
        project_root="/tmp/project",
        entry_file="main.py",
        mode=mode,
    )


def test_start_from_session_records_mode_run_id_and_log_path() -> None:
    store = RunSessionStore()
    session = _run_session(mode=constants.RUN_MODE_PYTHON_DEBUG)

    store.start_from_session(session)

    active = store.active_session
    assert active is not None
    assert store.active_session_mode == constants.RUN_MODE_PYTHON_DEBUG
    assert active.run_id == "run123"
    assert store.log_path == "/tmp/project/logs/run_run123.log"
    assert active.entry_file == "main.py"


def test_clear_resets_active_session_metadata() -> None:
    store = RunSessionStore()
    store.start_from_session(_run_session())

    store.clear()

    assert store.active_session is None
    assert store.active_session_mode is None
    assert store.log_path is None


def test_start_clear_start_keeps_metadata_consistent() -> None:
    store = RunSessionStore()
    first = _run_session(mode=constants.RUN_MODE_PYTHON_SCRIPT)
    second = RunSession(
        run_id="run456",
        manifest_path="/tmp/project/cbcs/runs/run456.json",
        log_file_path="/tmp/project/logs/run_run456.log",
        project_root="/tmp/project",
        entry_file="other.py",
        mode=constants.RUN_MODE_PYTHON_DEBUG,
    )

    store.start_from_session(first)
    assert store.active_session_mode == constants.RUN_MODE_PYTHON_SCRIPT
    assert store.active_session is not None
    assert store.active_session.run_id == "run123"

    store.clear()
    assert store.active_session is None

    store.start_from_session(second)
    assert store.active_session_mode == constants.RUN_MODE_PYTHON_DEBUG
    assert store.active_session is not None
    assert store.active_session.run_id == "run456"
    assert store.log_path == "/tmp/project/logs/run_run456.log"
