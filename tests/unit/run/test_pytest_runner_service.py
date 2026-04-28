"""Unit tests for pytest runner helpers."""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from app.run.pytest_discovery_service import PYTEST_MISSING_MARKER
from app.run.pytest_runner_service import (
    _build_apprun_pytest_payload,
    _build_apprun_pytest_probe_payload,
    parse_pytest_failures,
    run_pytest_args,
    run_pytest_project,
    run_pytest_target,
)

pytestmark = pytest.mark.unit


def _assert_vendor_inserted_before_pytest_import(payload: str, vendor_path: str) -> None:
    insert_pos = payload.find(f"sys.path.insert(0, {vendor_path!r})")
    import_pos = payload.find("import pytest")
    assert insert_pos != -1, "vendor/ path was not inserted into sys.path"
    assert import_pos != -1, "pytest is never imported"
    assert insert_pos < import_pos, "vendor/ must be on sys.path before `import pytest`"


def test_apprun_payload_inserts_editor_vendor_before_pytest_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runner's AppRun -c payload must prepend the editor's vendor/ to
    sys.path before importing pytest, so ChoreBoy can find the bundled copy."""
    monkeypatch.setattr(
        "app.run.pytest_runner_service.resolve_vendor_root",
        lambda: "/opt/cbcs/vendor",
    )

    payload = _build_apprun_pytest_payload(pytest_args=["-q"])

    _assert_vendor_inserted_before_pytest_import(payload, "/opt/cbcs/vendor")
    assert "pytest.main(['-q'])" in payload
    assert PYTEST_MISSING_MARKER in payload


def test_apprun_probe_payload_inserts_editor_vendor_before_pytest_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runtime probe payload must use the same vendor injection so the
    probe doesn't false-fail on ChoreBoy where pytest only lives in vendor/."""
    monkeypatch.setattr(
        "app.run.pytest_runner_service.resolve_vendor_root",
        lambda: "/opt/cbcs/vendor",
    )

    payload = _build_apprun_pytest_probe_payload()

    _assert_vendor_inserted_before_pytest_import(payload, "/opt/cbcs/vendor")
    assert PYTEST_MISSING_MARKER in payload


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
        assert "pytest.main(['-q', '--import-mode=importlib', '-p', 'no:cacheprovider'])" in command[2]
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout="tests/test_sample.py:10: AssertionError",
            stderr="",
        )

    monkeypatch.setattr("app.run.pytest_runner_service._select_pytest_runtime", lambda **_kwargs: "/opt/freecad/AppRun")
    monkeypatch.setattr("app.run.pytest_runner_service.subprocess.run", fake_run)

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

    monkeypatch.setattr("app.run.pytest_runner_service._select_pytest_runtime", lambda **_kwargs: "/usr/bin/python3")
    monkeypatch.setattr("app.run.pytest_runner_service.subprocess.run", fake_run)

    result = run_pytest_target(str(project_root), str(target))

    assert result.return_code == 0
    assert captured_command[:7] == ["/usr/bin/python3", "-m", "pytest", "-q", "--import-mode=importlib", "-p", "no:cacheprovider"]
    assert captured_command[-1] == str(target.resolve())


def test_run_pytest_args_passes_through_explicit_pytest_arguments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()

    captured_command: list[str] = []

    def fake_run(*args, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal captured_command
        captured_command = list(args[0])
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="1 passed",
            stderr="",
        )

    monkeypatch.setattr("app.run.pytest_runner_service._select_pytest_runtime", lambda **_kwargs: "/usr/bin/python3")
    monkeypatch.setattr("app.run.pytest_runner_service.subprocess.run", fake_run)

    result = run_pytest_args(str(project_root), ["-v", "tests/test_sample.py::test_ok"])

    assert result.return_code == 0
    assert captured_command == [
        "/usr/bin/python3",
        "-m",
        "pytest",
        "-v",
        "--import-mode=importlib",
        "-p",
        "no:cacheprovider",
        "tests/test_sample.py::test_ok",
    ]


def test_run_pytest_project_uses_run_tests_py_when_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "run_tests.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    captured_command: list[str] = []

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal captured_command
        captured_command = list(args[0])
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="1 passed", stderr="")

    monkeypatch.setattr("app.run.pytest_runner_service._select_pytest_runtime", lambda **_kwargs: "/opt/freecad/AppRun")
    monkeypatch.setattr("app.run.pytest_runner_service.subprocess.run", fake_run)

    result = run_pytest_project(str(project_root))

    assert result.return_code == 0
    assert captured_command[0] == "/opt/freecad/AppRun"
    assert captured_command[1] == "-c"
    assert "runpy.run_path" in captured_command[2]
    assert str((project_root / "run_tests.py").resolve()) in captured_command[2]
    assert "--import-mode=importlib" in captured_command[2]
    assert "no:cacheprovider" in captured_command[2]


def test_run_pytest_project_includes_import_mode_for_apprun_payload(
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

    monkeypatch.setattr("app.run.pytest_runner_service._select_pytest_runtime", lambda **_kwargs: "/opt/freecad/AppRun")
    monkeypatch.setattr("app.run.pytest_runner_service.subprocess.run", fake_run)

    run_pytest_project(str(project_root))

    assert captured_command[0] == "/opt/freecad/AppRun"
    assert captured_command[1] == "-c"
    assert "pytest.main(['-q', '--import-mode=importlib', '-p', 'no:cacheprovider'])" in captured_command[2]


def test_select_pytest_runtime_prefers_env_override_before_apprun(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    custom_python = tmp_path / "custom_python"
    custom_python.write_text("", encoding="utf-8")

    monkeypatch.setenv("CBCS_PYTEST_EXECUTABLE", str(custom_python.resolve()))
    monkeypatch.setattr("app.run.pytest_runner_service.resolve_runtime_executable", lambda _runtime: "/opt/freecad/AppRun")
    monkeypatch.setattr(
        "app.run.pytest_runner_service._runtime_supports_pytest",
        lambda runtime, **_kwargs: runtime == str(custom_python.resolve()),
    )

    from app.run.pytest_runner_service import _select_pytest_runtime

    selected = _select_pytest_runtime(project_root=str(project_root.resolve()))

    assert selected == str(custom_python.resolve())


def test_select_pytest_runtime_raises_when_no_runtime_supports_pytest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    monkeypatch.delenv("CBCS_PYTEST_EXECUTABLE", raising=False)
    monkeypatch.setattr("app.run.pytest_runner_service.resolve_runtime_executable", lambda _runtime: "/opt/freecad/AppRun")
    monkeypatch.setattr("app.run.pytest_runner_service._runtime_supports_pytest", lambda _runtime, **_kwargs: False)

    from app.run.pytest_runner_service import _select_pytest_runtime

    with pytest.raises(RuntimeError, match="Pytest is not available in detected runtimes"):
        _select_pytest_runtime(project_root=str(project_root.resolve()))


def test_select_pytest_runtime_falls_back_to_apprun(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    monkeypatch.delenv("CBCS_PYTEST_EXECUTABLE", raising=False)
    monkeypatch.setattr("app.run.pytest_runner_service.resolve_runtime_executable", lambda _runtime: "/opt/freecad/AppRun")
    monkeypatch.setattr(
        "app.run.pytest_runner_service._runtime_supports_pytest",
        lambda runtime, **_kwargs: runtime == "/opt/freecad/AppRun",
    )

    from app.run.pytest_runner_service import _select_pytest_runtime

    selected = _select_pytest_runtime(project_root=str(project_root.resolve()))

    assert selected == "/opt/freecad/AppRun"


def test_candidate_pytest_runtimes_do_not_include_venv_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    monkeypatch.delenv("CBCS_PYTEST_EXECUTABLE", raising=False)
    monkeypatch.setattr("app.run.pytest_runner_service.resolve_runtime_executable", lambda _runtime: "/opt/freecad/AppRun")

    from app.run.pytest_runner_service import _candidate_pytest_runtimes

    candidates = _candidate_pytest_runtimes(str(project_root.resolve()))

    assert candidates == ["/opt/freecad/AppRun"]


def test_select_pytest_runtime_preserves_env_override_symlink_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    custom_python = tmp_path / "custom_python"
    custom_python.symlink_to("/usr/bin/python3")

    monkeypatch.setenv("CBCS_PYTEST_EXECUTABLE", str(custom_python))
    monkeypatch.setattr("app.run.pytest_runner_service.resolve_runtime_executable", lambda _runtime: "/opt/freecad/AppRun")
    monkeypatch.setattr(
        "app.run.pytest_runner_service._runtime_supports_pytest",
        lambda runtime, **_kwargs: runtime.endswith("custom_python"),
    )

    from app.run.pytest_runner_service import _select_pytest_runtime

    selected = _select_pytest_runtime(project_root=str(project_root.resolve()))

    assert selected.endswith("custom_python")


# ---------------------------------------------------------------------------
# Cursor-based test identification (R04)
# ---------------------------------------------------------------------------


def test_identify_test_at_cursor_finds_enclosing_test() -> None:
    from app.run.pytest_runner_service import identify_test_at_cursor

    source = """\
def test_hello():
    assert True

def test_goodbye():
    x = 1
    assert x == 1
"""
    # Line 5 is inside test_goodbye (1-based)
    assert identify_test_at_cursor(source, 5) == "test_goodbye"
    # Line 1 is inside test_hello
    assert identify_test_at_cursor(source, 1) == "test_hello"


def test_identify_test_at_cursor_returns_none_outside_tests() -> None:
    from app.run.pytest_runner_service import identify_test_at_cursor

    source = """\
import os

def helper():
    pass

def test_foo():
    pass
"""
    # Line 3 is inside helper, not a test
    assert identify_test_at_cursor(source, 3) is None


def test_identify_test_at_cursor_handles_syntax_error() -> None:
    from app.run.pytest_runner_service import identify_test_at_cursor

    source = "def test_broken(\n"
    assert identify_test_at_cursor(source, 1) is None
