"""Unit tests for pytest runner helpers."""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from app.run.test_runner_service import parse_pytest_failures, run_pytest_project, run_pytest_target

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
        command = list(args[0])
        assert command[0] == "/opt/freecad/AppRun"
        assert command[1] == "-c"
        assert "pytest.main(['-q'])" in command[2]
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout="tests/test_sample.py:10: AssertionError",
            stderr="",
        )

    monkeypatch.setattr("app.run.test_runner_service._select_pytest_runtime", lambda **_kwargs: "/opt/freecad/AppRun")
    monkeypatch.setattr("app.run.test_runner_service._candidate_pytest_site_packages", lambda **_kwargs: [])
    monkeypatch.setattr("app.run.test_runner_service.subprocess.run", fake_run)

    result = run_pytest_project(str(project_root))

    assert result.return_code == 1
    assert result.succeeded is False
    assert len(result.failures) == 1
    assert result.failures[0].line_number == 10


def test_run_pytest_target_includes_target_argument(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    target = project_root / "tests" / "test_sample.py"
    target.parent.mkdir(parents=True)
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    captured_command: list[str] = []

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal captured_command
        captured_command = list(args[0])
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="1 passed",
            stderr="",
        )

    monkeypatch.setattr("app.run.test_runner_service._select_pytest_runtime", lambda **_kwargs: "/usr/bin/python3")
    monkeypatch.setattr("app.run.test_runner_service.subprocess.run", fake_run)

    result = run_pytest_target(str(project_root), str(target))

    assert result.return_code == 0
    assert captured_command[:4] == ["/usr/bin/python3", "-m", "pytest", "-q"]
    assert captured_command[-1] == str(target.resolve())


def test_run_pytest_project_includes_site_packages_for_apprun_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    captured_command: list[str] = []

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal captured_command
        captured_command = list(args[0])
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr("app.run.test_runner_service._select_pytest_runtime", lambda **_kwargs: "/opt/freecad/AppRun")
    monkeypatch.setattr(
        "app.run.test_runner_service._candidate_pytest_site_packages",
        lambda **_kwargs: ["/workspace/.venv/lib/python3.12/site-packages"],
    )
    monkeypatch.setattr("app.run.test_runner_service.subprocess.run", fake_run)

    run_pytest_project(str(project_root))

    assert captured_command[0] == "/opt/freecad/AppRun"
    assert captured_command[1] == "-c"
    assert "/workspace/.venv/lib/python3.12/site-packages" in captured_command[2]
    assert "pytest.main(['-q'])" in captured_command[2]


def test_select_pytest_runtime_prefers_project_venv_when_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    project_python = project_root / ".venv" / "bin" / "python"
    project_python.parent.mkdir(parents=True)
    project_python.write_text("", encoding="utf-8")
    app_python = tmp_path / "app" / ".venv" / "bin" / "python"
    app_python.parent.mkdir(parents=True)
    app_python.write_text("", encoding="utf-8")

    monkeypatch.setattr("app.run.test_runner_service.resolve_app_root", lambda: tmp_path / "app")
    monkeypatch.setattr("app.run.test_runner_service.resolve_runtime_executable", lambda _runtime: "/opt/freecad/AppRun")
    monkeypatch.setattr(
        "app.run.test_runner_service._runtime_supports_pytest",
        lambda runtime, **_kwargs: runtime == str(project_python.resolve()),
    )

    from app.run.test_runner_service import _select_pytest_runtime

    selected = _select_pytest_runtime(project_root=str(project_root.resolve()))

    assert selected == str(project_python.resolve())


def test_select_pytest_runtime_raises_when_no_runtime_supports_pytest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    monkeypatch.setattr("app.run.test_runner_service.resolve_app_root", lambda: tmp_path / "app")
    monkeypatch.setattr("app.run.test_runner_service.resolve_runtime_executable", lambda _runtime: "/opt/freecad/AppRun")
    monkeypatch.setattr("app.run.test_runner_service._runtime_supports_pytest", lambda _runtime, **_kwargs: False)

    from app.run.test_runner_service import _select_pytest_runtime

    with pytest.raises(RuntimeError, match="Pytest is not available in detected runtimes"):
        _select_pytest_runtime(project_root=str(project_root.resolve()))


def test_select_pytest_runtime_preserves_venv_symlink_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    project_python = project_root / ".venv" / "bin" / "python"
    project_python.parent.mkdir(parents=True)
    project_python.symlink_to("/usr/bin/python3")

    monkeypatch.setattr("app.run.test_runner_service.resolve_app_root", lambda: tmp_path / "app")
    monkeypatch.setattr("app.run.test_runner_service.resolve_runtime_executable", lambda _runtime: "/opt/freecad/AppRun")
    monkeypatch.setattr(
        "app.run.test_runner_service._runtime_supports_pytest",
        lambda runtime, **_kwargs: runtime.endswith("/.venv/bin/python"),
    )

    from app.run.test_runner_service import _select_pytest_runtime

    selected = _select_pytest_runtime(project_root=str(project_root.resolve()))

    assert selected.endswith("/.venv/bin/python")
