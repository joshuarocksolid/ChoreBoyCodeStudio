"""Unit tests for pytest runner helpers."""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from app.run.test_runner_service import parse_pytest_failures, run_pytest_project

pytestmark = pytest.mark.unit


def test_parse_pytest_failures_extracts_relative_paths(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    output = "tests/test_sample.py:14: AssertionError: boom"

    failures = parse_pytest_failures(output, str(project_root))

    assert len(failures) == 1
    failure = failures[0]
    assert failure.file_path.endswith("tests/test_sample.py")
    assert failure.line_number == 14
    assert "AssertionError" in failure.message


def test_run_pytest_project_invokes_subprocess_and_parses_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        assert kwargs["cwd"] == str(project_root.resolve())
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout="tests/test_sample.py:10: AssertionError",
            stderr="",
        )

    monkeypatch.setattr("app.run.test_runner_service.subprocess.run", fake_run)

    result = run_pytest_project(str(project_root))

    assert result.return_code == 1
    assert result.succeeded is False
    assert len(result.failures) == 1
    assert result.failures[0].line_number == 10
