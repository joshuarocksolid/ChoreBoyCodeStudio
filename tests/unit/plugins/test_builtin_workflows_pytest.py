"""Unit tests for built-in pytest workflow request routing."""

from __future__ import annotations

import pytest

from app.plugins import builtin_workflows
from app.run.test_runner_service import PytestRunResult

pytestmark = pytest.mark.unit


def _fake_result() -> PytestRunResult:
    return PytestRunResult(
        command=["/opt/freecad/AppRun", "-c", "pytest"],
        project_root="/tmp/project",
        return_code=0,
        stdout="",
        stderr="",
        elapsed_ms=1.0,
        failures=[],
    )


def test_builtin_pytest_job_prefers_explicit_pytest_args(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[tuple[str, object]] = []

    monkeypatch.setattr(
        builtin_workflows,
        "run_pytest_args",
        lambda project_root, args, timeout_seconds=300: called.append(("args", list(args))) or _fake_result(),  # type: ignore[no-untyped-def]
    )
    monkeypatch.setattr(
        builtin_workflows,
        "run_pytest_target",
        lambda *_args, **_kwargs: called.append(("target", None)) or _fake_result(),  # type: ignore[no-untyped-def]
    )
    monkeypatch.setattr(
        builtin_workflows,
        "run_pytest_project",
        lambda *_args, **_kwargs: called.append(("project", None)) or _fake_result(),  # type: ignore[no-untyped-def]
    )

    builtin_workflows._run_builtin_pytest_job(  # type: ignore[attr-defined]
        {
            "project_root": "/tmp/project",
            "target_path": "tests/test_sample.py",
            "target_node_id": "tests/test_sample.py::test_case",
            "pytest_args": ["-k", "targeted"],
            "timeout_seconds": 123,
        },
        emit_event=lambda *_args, **_kwargs: None,
        is_cancelled=lambda: False,
    )

    assert called == [("args", ["-k", "targeted"])]


def test_builtin_pytest_job_routes_target_node_to_args(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[tuple[str, object]] = []

    monkeypatch.setattr(
        builtin_workflows,
        "run_pytest_args",
        lambda _project_root, args, timeout_seconds=300: called.append(("args", list(args))) or _fake_result(),  # type: ignore[no-untyped-def]
    )
    monkeypatch.setattr(
        builtin_workflows,
        "run_pytest_target",
        lambda *_args, **_kwargs: called.append(("target", None)) or _fake_result(),  # type: ignore[no-untyped-def]
    )
    monkeypatch.setattr(
        builtin_workflows,
        "run_pytest_project",
        lambda *_args, **_kwargs: called.append(("project", None)) or _fake_result(),  # type: ignore[no-untyped-def]
    )

    builtin_workflows._run_builtin_pytest_job(  # type: ignore[attr-defined]
        {
            "project_root": "/tmp/project",
            "target_node_id": "tests/test_sample.py::test_case",
        },
        emit_event=lambda *_args, **_kwargs: None,
        is_cancelled=lambda: False,
    )

    assert called == [("args", ["-v", "tests/test_sample.py::test_case"])]


def test_builtin_pytest_job_routes_target_path_when_no_node_or_explicit_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[tuple[str, object]] = []

    monkeypatch.setattr(
        builtin_workflows,
        "run_pytest_args",
        lambda *_args, **_kwargs: called.append(("args", None)) or _fake_result(),  # type: ignore[no-untyped-def]
    )
    monkeypatch.setattr(
        builtin_workflows,
        "run_pytest_target",
        lambda _project_root, target_path, timeout_seconds=300: called.append(("target", target_path)) or _fake_result(),  # type: ignore[no-untyped-def]
    )
    monkeypatch.setattr(
        builtin_workflows,
        "run_pytest_project",
        lambda *_args, **_kwargs: called.append(("project", None)) or _fake_result(),  # type: ignore[no-untyped-def]
    )

    builtin_workflows._run_builtin_pytest_job(  # type: ignore[attr-defined]
        {
            "project_root": "/tmp/project",
            "target_path": "tests/test_sample.py",
        },
        emit_event=lambda *_args, **_kwargs: None,
        is_cancelled=lambda: False,
    )

    assert called == [("target", "tests/test_sample.py")]


def test_builtin_pytest_job_routes_project_when_no_specific_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[tuple[str, object]] = []

    monkeypatch.setattr(
        builtin_workflows,
        "run_pytest_args",
        lambda *_args, **_kwargs: called.append(("args", None)) or _fake_result(),  # type: ignore[no-untyped-def]
    )
    monkeypatch.setattr(
        builtin_workflows,
        "run_pytest_target",
        lambda *_args, **_kwargs: called.append(("target", None)) or _fake_result(),  # type: ignore[no-untyped-def]
    )
    monkeypatch.setattr(
        builtin_workflows,
        "run_pytest_project",
        lambda _project_root, timeout_seconds=300: called.append(("project", timeout_seconds)) or _fake_result(),  # type: ignore[no-untyped-def]
    )

    builtin_workflows._run_builtin_pytest_job(  # type: ignore[attr-defined]
        {
            "project_root": "/tmp/project",
            "timeout_seconds": 77,
        },
        emit_event=lambda *_args, **_kwargs: None,
        is_cancelled=lambda: False,
    )

    assert called == [("project", 77)]

