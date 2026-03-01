"""Unit tests for runner debug helper module."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import constants
from app.run.run_manifest import RunManifest
from app.runner.debug_runner import run_debug_session

pytestmark = pytest.mark.unit


def test_run_debug_session_returns_success_for_clean_script(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script_path = tmp_path / "run.py"
    script_path.write_text("value = 1\n", encoding="utf-8")
    manifest = RunManifest(
        manifest_version=constants.RUN_MANIFEST_VERSION,
        run_id="run_debug_test",
        project_root=str(tmp_path.resolve()),
        entry_file="run.py",
        working_directory=str(tmp_path.resolve()),
        mode=constants.RUN_MODE_PYTHON_DEBUG,
        argv=[],
        env={},
        safe_mode=True,
        log_file=str((tmp_path / "run.log").resolve()),
        timestamp="2026-03-01T00:00:00",
        breakpoints=[],
    )

    def _entry_callable(_path: str) -> None:
        return None

    monkeypatch.setattr("builtins.input", lambda _prompt="": "continue")
    exit_code = run_debug_session(manifest, _entry_callable, str(script_path.resolve()))
    assert exit_code == constants.RUN_EXIT_SUCCESS
