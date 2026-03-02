"""Unit tests for runner debug helper module."""

from __future__ import annotations

from pathlib import Path
import runpy

import pytest

from app.core import constants
from app.debug.debug_event_protocol import parse_debug_output_line
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


def test_run_debug_session_first_pause_targets_user_breakpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script_path = tmp_path / "run.py"
    script_path.write_text("value = 41\nvalue = value + 1\nprint(value)\n", encoding="utf-8")
    manifest = RunManifest(
        manifest_version=constants.RUN_MANIFEST_VERSION,
        run_id="run_debug_breakpoint_test",
        project_root=str(tmp_path.resolve()),
        entry_file="run.py",
        working_directory=str(tmp_path.resolve()),
        mode=constants.RUN_MODE_PYTHON_DEBUG,
        argv=[],
        env={},
        safe_mode=True,
        log_file=str((tmp_path / "run.log").resolve()),
        timestamp="2026-03-01T00:00:00",
        breakpoints=[{"file_path": str(script_path.resolve()), "line_number": 2}],
    )

    def _entry_callable(path: str) -> None:
        runpy.run_path(path, run_name="__main__")

    monkeypatch.setattr("builtins.input", lambda _prompt="": "continue")
    exit_code = run_debug_session(manifest, _entry_callable, str(script_path.resolve()))
    assert exit_code == constants.RUN_EXIT_SUCCESS

    paused_events = []
    for line in capsys.readouterr().out.splitlines():
        parsed_event = parse_debug_output_line(line)
        if parsed_event is None or parsed_event.event_type != "paused" or not parsed_event.frames:
            continue
        paused_events.append(parsed_event)

    assert paused_events
    first_frame = paused_events[0].frames[0]
    assert Path(first_frame.file_path).resolve() == script_path.resolve()
    assert first_frame.line_number == 2
