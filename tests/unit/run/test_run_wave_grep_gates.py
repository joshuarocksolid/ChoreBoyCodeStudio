"""Static contract gates for Run Wave 1 remediation (@ HEAD).

Guards structural wins and P0 prerequisites documented in
docs/code review/run-wave-1/run_wave_1_implementation_plan.md §15.
"""

from __future__ import annotations

from pathlib import Path
import re

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_APP_RUN = _REPO_ROOT / "app" / "run"
_APP_RUNNER = _REPO_ROOT / "app" / "runner"
_APP_DEBUG = _REPO_ROOT / "app" / "debug"
_APP_PYTEST = _REPO_ROOT / "app" / "pytest"


def _read(relative_path: str) -> str:
    return (_REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _py_files_under(*roots: Path) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        files.extend(path for path in root.rglob("*.py") if path.is_file())
    return files


def test_no_pytest_modules_under_app_run() -> None:
    pytest_modules = list(_APP_RUN.glob("pytest*.py"))
    assert pytest_modules == []


def test_app_pytest_package_exists() -> None:
    assert (_APP_PYTEST / "launch_plan.py").is_file()
    assert (_APP_PYTEST / "discovery_service.py").is_file()
    assert (_APP_PYTEST / "runner_service.py").is_file()


def test_pytest_launch_plan_shared_by_discovery_and_runner() -> None:
    discovery = _read("app/pytest/discovery_service.py")
    runner = _read("app/pytest/runner_service.py")
    assert "build_pytest_launch_plan" in discovery
    assert "build_pytest_launch_plan" in runner


def test_debug_runner_is_thin_facade() -> None:
    line_count = len(_read("app/runner/debug_runner.py").splitlines())
    assert line_count <= 30


def test_debug_runner_modules_decomposed() -> None:
    debug_pkg = _APP_RUNNER / "debug"
    assert debug_pkg.is_dir()
    module_names = {path.stem for path in debug_pkg.glob("*.py") if path.name != "__init__.py"}
    assert {"command_loop", "engine", "inspector", "breakpoints", "session"}.issubset(module_names)


def test_run_service_has_no_is_debug_paused() -> None:
    run_service = _read("app/run/run_service.py")
    assert "_is_debug_paused" not in run_service
    assert "is_debug_paused" not in run_service


def test_run_service_asserts_idle_before_launch() -> None:
    run_service = _read("app/run/run_service.py")
    start_run_index = run_service.index("def start_run(")
    assert_idle_index = run_service.index("self._assert_idle()", start_run_index)
    plan_launch_index = run_service.index("plan_launch(", start_run_index)
    assert assert_idle_index < plan_launch_index


def test_no_host_process_manager_under_app_run() -> None:
    for path in _py_files_under(_APP_RUN):
        assert "HostProcessManager" not in path.read_text(encoding="utf-8")


def test_start_run_is_thin_coordinator() -> None:
    """CC-12: start_run delegates to plan_launch and _start_manifest within LOC budget."""
    run_service = _read("app/run/run_service.py")
    start_index = run_service.index("    def start_run(")
    next_def_index = run_service.index("\n    def ", start_index + 1)
    start_run_block = run_service[start_index:next_def_index]
    line_count = len(start_run_block.splitlines())
    assert line_count <= 50, f"start_run is {line_count} LOC; CC-12 budget is ≤50"
    assert "plan_launch(" in start_run_block
    assert "_start_manifest(" in start_run_block


def test_run_service_forwards_transport_errors_and_closes_server() -> None:
    run_service = _read("app/run/run_service.py")
    assert "on_error=self._forward_debug_transport_error" in run_service
    forward_block = run_service.split("def _forward_debug_transport_error", 1)[1]
    assert "_close_debug_transport_server()" in forward_block


def test_runner_pause_loop_bounded_and_transport_aware() -> None:
    command_loop = _read("app/runner/debug/command_loop.py")
    assert "_PAUSE_COMMAND_TIMEOUT_SEC" in command_loop
    assert "_transport_failed" in command_loop
    assert "on_error=self._handle_transport_error" in command_loop


def test_pytest_runner_uses_q_with_ra_summary() -> None:
    runner = _read("app/pytest/runner_service.py")
    assert '"-q"' in runner or "'-q'" in runner
    assert '"-rA"' in runner or "'-rA'" in runner


def test_breakpoint_store_has_no_mutable_dict_property_exports() -> None:
    """CC-18: BreakpointStore exposes methods only — no live dict aliases."""
    store_source = _read("app/shell/breakpoint_store.py")
    assert "@property" not in store_source
    assert "def breakpoints_by_file" not in store_source
    assert "def breakpoint_specs_by_key" not in store_source


def test_shell_workflows_use_breakpoint_store_not_dict_aliases() -> None:
    """CC-18: shell workflows must not inject or mutate breakpoint dict aliases."""
    shell_root = _REPO_ROOT / "app" / "shell"
    forbidden = ("breakpoints_by_file=", "breakpoint_specs_by_key=")
    for path in shell_root.rglob("*.py"):
        if path.name == "breakpoint_store.py":
            continue
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{path.relative_to(_REPO_ROOT)} contains {token!r}"


def test_repl_session_manager_delegates_launch_to_run_service() -> None:
    """CC-19: ReplSessionManager must not duplicate run-layer manifest/command assembly."""
    repl_mgr = _read("app/shell/repl_session_manager.py")
    assert "start_repl_sidecar" in repl_mgr
    assert "build_repl_sidecar_launch" not in repl_mgr
    assert "build_runner_command" not in repl_mgr
    assert "resolve_runtime_executable" not in repl_mgr
    assert "generate_run_id" not in repl_mgr


def test_presentation_modules_not_under_app_run() -> None:
    """CC-20: shell presentation buffers must not live in the run layer."""
    assert not (_APP_RUN / "console_model.py").is_file()
    assert not (_APP_RUN / "exit_status.py").is_file()


def test_presentation_modules_live_in_shell_package() -> None:
    """CC-20: ConsoleModel and describe_exit_code belong under app/shell/."""
    shell_root = _REPO_ROOT / "app" / "shell"
    assert (shell_root / "console_model.py").is_file()
    assert (shell_root / "exit_status.py").is_file()


def test_no_imports_from_app_run_presentation_modules() -> None:
    """CC-20: import graph has no edges to app.run.console_model or app.run.exit_status."""
    import_pattern = re.compile(
        r"from app\.run\.(console_model|exit_status)\b|"
        r"import app\.run\.(console_model|exit_status)\b"
    )
    app_root = _REPO_ROOT / "app"
    for path in app_root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        match = import_pattern.search(source)
        assert match is None, (
            f"{path.relative_to(_REPO_ROOT)} imports misplaced run presentation: {match.group(0)!r}"
        )


def test_app_run_has_no_shell_presentation_references() -> None:
    """CC-20: run layer must not reference shell-only presentation modules."""
    forbidden = ("console_model", "exit_status", "ConsoleModel", "describe_exit_code")
    for path in _py_files_under(_APP_RUN):
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{path.relative_to(_REPO_ROOT)} references {token!r}"


def test_bare_except_exception_count_documented_ceiling() -> None:
    """CC-22: bare ``except Exception:`` reserved for observer/bootstrap paths only."""
    pattern = re.compile(r"^\s*except\s+Exception\s*:\s*$", re.MULTILINE)
    allowed_sites = {
        "app/run/process_supervisor.py",
        "app/runner/debug/session.py",
        "app/runner/repl_control.py",
        "app/runner/runner_main.py",
    }
    count = 0
    for path in _py_files_under(_APP_RUN, _APP_RUNNER, _APP_DEBUG):
        source = path.read_text(encoding="utf-8")
        matches = pattern.findall(source)
        if not matches:
            continue
        rel = path.relative_to(_REPO_ROOT).as_posix()
        assert rel in allowed_sites, f"unexpected bare except Exception in {rel}"
        count += len(matches)
    assert count <= 8, f"bare except Exception count {count} exceeds CC-22 ceiling 8"


def test_no_legacy_debug_reducer_paths() -> None:
    """CC-21: legacy DebugEvent/stdout-marker reducers stay removed; protocol path only."""
    forbidden = (
        "class DebugEvent",
        "def apply_event(",
        "ingest_output_line",
        "debug_event_protocol",
        "__CB_DEBUG_",
    )
    for path in _py_files_under(_APP_DEBUG):
        source = path.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in source, f"{needle!r} found in {path.relative_to(_REPO_ROOT)}"


_APP_SHELL = _REPO_ROOT / "app" / "shell"
_RUN_LAUNCH_WORKFLOW = _APP_SHELL / "run_launch_workflow.py"
_RUN_LAUNCH_PKG = _APP_SHELL / "run_launch"


def test_run_launch_workflow_facade_loc_budget() -> None:
    """CC-16: run_launch_workflow.py stays a thin orchestrator (≤500 LOC)."""
    line_count = len(_read("app/shell/run_launch_workflow.py").splitlines())
    assert line_count <= 500, f"run_launch_workflow.py is {line_count} LOC; CC-16 budget is ≤500"


def test_run_launch_split_modules_loc_budget() -> None:
    """CC-16: each run_launch submodule stays below 400 LOC."""
    module_paths = [
        _RUN_LAUNCH_WORKFLOW,
        *_RUN_LAUNCH_PKG.glob("*.py"),
    ]
    for path in module_paths:
        if path.name == "__init__.py":
            continue
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        assert line_count <= 400, (
            f"{path.relative_to(_REPO_ROOT)} is {line_count} LOC; CC-16 budget is ≤400 per module"
        )


def test_run_launch_workflow_has_no_public_reexport_surface() -> None:
    """CC-16: facade keeps no __all__ re-export surface for moved symbols."""
    facade = _read("app/shell/run_launch_workflow.py")
    assert "__all__" not in facade
    for symbol in (
        "RunDebugPresenterPort",
        "CurrentTestTarget",
        "TestNodeTarget",
        "MainWindowRunLaunchHost",
    ):
        assert symbol not in facade, f"run_launch_workflow.py must not re-export {symbol!r}"
