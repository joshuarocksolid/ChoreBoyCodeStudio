"""Runtime-parity tests for debugger engine under AppRun."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core import constants
from app.debug.debug_runtime_probe import probe_debug_runtime

pytestmark = pytest.mark.runtime_parity


def _require_apprun() -> None:
    app_run = Path(constants.APP_RUN_PATH)
    if not app_run.exists():
        pytest.skip(f"AppRun not available at {app_run}; skipping debug runtime parity tests.")


def test_debug_engine_decision_runs_under_apprun() -> None:
    """Probe produces a valid engine decision under AppRun runtime."""
    _require_apprun()
    decision = probe_debug_runtime()

    assert decision.chosen_engine in ("bdb", "debugpy")
    assert isinstance(decision.debugpy_available, bool)
    assert isinstance(decision.supports_python_threads, bool)
    if decision.chosen_engine == "bdb":
        assert decision.debugpy_rejection_reason  # must explain why not debugpy


def test_bdb_engine_is_always_available_under_apprun() -> None:
    """bdb is a stdlib module and must always be importable."""
    _require_apprun()
    import bdb

    assert hasattr(bdb, "Bdb")
    assert hasattr(bdb, "BdbQuit")


def test_debug_models_are_importable_under_apprun() -> None:
    """Core debug models import cleanly under AppRun without circular dependencies."""
    _require_apprun()
    from app.debug.debug_models import (
        DebugBreakpoint,
        DebugExceptionPolicy,
        DebugExecutionState,
        DebugTransportConfig,
    )

    bp = DebugBreakpoint(breakpoint_id="bp_1", file_path="/tmp/test.py", line_number=10)
    assert bp.enabled is True
    policy = DebugExceptionPolicy()
    assert policy.stop_on_uncaught_exceptions is True
    config = DebugTransportConfig(protocol="cbcs_debug_v1", host="127.0.0.1", port=12345, session_token="tok")
    assert config.port == 12345
