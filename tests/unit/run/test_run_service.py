"""Unit tests for run service helper contracts."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

import pytest

from app.core import constants
from app.core.errors import RunLifecycleError
from app.core.models import LoadedProject, ProjectMetadata
from app.debug.debug_models import DebugExceptionPolicy, DebugSourceMap
from app.run.launch_context import plan_launch
from app.run.process_supervisor import ProcessEvent
from app.run.run_manifest import load_run_manifest
from app.run.run_service import (
    RunService,
    RunSession,
    build_run_log_path,
    build_run_manifest_path,
    generate_run_id,
)

pytestmark = pytest.mark.unit


def test_generate_run_id_includes_timestamp_and_random_suffix() -> None:
    """Run IDs should include deterministic timestamp prefix and unique suffix."""
    now = datetime(2026, 3, 1, 5, 6, 7)
    first = generate_run_id(now=now)
    second = generate_run_id(now=now)

    assert first.startswith("20260301_050607_")
    assert second.startswith("20260301_050607_")
    assert first != second


def test_build_run_manifest_path_uses_project_contract(tmp_path: Path) -> None:
    """Run manifest should target cbcs/runs directory."""
    project_root = tmp_path / "project_alpha"
    run_id = "20260301_050607_abcd12"

    manifest_path = build_run_manifest_path(project_root, run_id)

    assert manifest_path == project_root / "cbcs" / "runs" / f"run_manifest_{run_id}.json"


def test_build_run_log_path_uses_project_logs_contract(tmp_path: Path) -> None:
    """Run log should target cbcs/logs inside the project."""
    project_root = tmp_path / "project_alpha"
    run_id = "20260301_050607_abcd12"

    log_path = build_run_log_path(project_root, run_id)

    assert log_path == project_root / "cbcs" / "logs" / f"run_{run_id}.log"


def test_plan_launch_resolves_loaded_project_overrides(tmp_path: Path) -> None:
    """Loaded-project planning should merge metadata and explicit overrides."""
    project_root = tmp_path / "project"
    (project_root / "app").mkdir(parents=True)
    (project_root / "run.py").write_text("print('run')\n", encoding="utf-8")
    loaded_project = LoadedProject(
        project_root=str(project_root.resolve()),
        manifest_path=str((project_root / "cbcs" / "project.json").resolve()),
        metadata=ProjectMetadata(
            schema_version=1,
            name="demo",
            default_entry="run.py",
            working_directory=".",
            env_overrides={"BASE_ENV": "1"},
        ),
        entries=[],
    )
    run_id = "20260301_050607_abcd12"

    launch = plan_launch(
        run_id=run_id,
        loaded_project=loaded_project,
        entry_file="app/main.py",
        mode="python_script",
        argv=["--flag"],
        working_directory="app",
        env_overrides={"EXTRA_ENV": "2"},
    )

    assert launch.mode == "python_script"
    assert launch.entry_file == "app/main.py"
    assert launch.working_directory == str((project_root / "app").resolve())
    assert launch.launch_cwd == str(project_root.resolve())
    assert launch.argv == ["--flag"]
    assert launch.env == {"BASE_ENV": "1", "EXTRA_ENV": "2"}
    assert launch.manifest_path == project_root / "cbcs" / "runs" / f"run_manifest_{run_id}.json"
    assert launch.log_path == project_root / "cbcs" / "logs" / f"run_{run_id}.log"


def test_plan_launch_defaults_projectless_repl_to_home_cwd(tmp_path: Path) -> None:
    """Projectless REPL planning should default working directory to home."""
    state_root = tmp_path / "state"
    run_id = "20260301_050607_abcd12"
    expected_home = str(Path.home().expanduser().resolve())

    launch = plan_launch(
        run_id=run_id,
        loaded_project=None,
        mode="python_repl",
        state_root=str(state_root.resolve()),
    )

    assert launch.mode == "python_repl"
    assert launch.entry_file == "__repl__.py"
    assert launch.working_directory == expected_home
    assert launch.launch_cwd == expected_home
    assert "/repl/runs/" in str(launch.manifest_path)
    assert "/repl/logs/" in str(launch.log_path)


def test_plan_launch_resolves_projectless_script_entry(tmp_path: Path) -> None:
    """Projectless script planning should resolve entry file and parent cwd."""
    state_root = tmp_path / "state"
    script_path = tmp_path / "snippet.py"
    script_path.write_text("print('snippet')\n", encoding="utf-8")
    run_id = "20260301_050607_abcd12"

    launch = plan_launch(
        run_id=run_id,
        loaded_project=None,
        mode=constants.RUN_MODE_PYTHON_SCRIPT,
        entry_file=str(script_path),
        state_root=str(state_root.resolve()),
    )

    assert launch.mode == constants.RUN_MODE_PYTHON_SCRIPT
    assert launch.entry_file == str(script_path.resolve())
    assert launch.project_root == str(script_path.parent.resolve())
    assert launch.working_directory == str(script_path.parent.resolve())
    assert launch.launch_cwd == str(script_path.parent.resolve())


def test_plan_launch_requires_entry_for_projectless_script() -> None:
    """Projectless non-REPL runs should fail fast without an entry file."""
    with pytest.raises(RunLifecycleError, match="Provide a file entry"):
        plan_launch(
            run_id="20260301_050607_abcd12",
            loaded_project=None,
            mode=constants.RUN_MODE_PYTHON_SCRIPT,
        )


def test_plan_launch_rejects_missing_projectless_entry_file(tmp_path: Path) -> None:
    """Projectless script planning should reject missing entry paths."""
    missing_entry = tmp_path / "missing.py"
    with pytest.raises(RunLifecycleError, match="Entry file not found"):
        plan_launch(
            run_id="20260301_050607_abcd12",
            loaded_project=None,
            mode=constants.RUN_MODE_PYTHON_SCRIPT,
            entry_file=str(missing_entry),
        )


def test_start_run_is_thin_coordinator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CC-12: start_run coordinates plan_launch then _start_manifest without inline planning."""
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    (project_root / "run.py").write_text("print('run')\n", encoding="utf-8")
    loaded_project = LoadedProject(
        project_root=str(project_root.resolve()),
        manifest_path=str((project_root / "cbcs" / "project.json").resolve()),
        metadata=ProjectMetadata(
            schema_version=1,
            name="demo",
            default_entry="run.py",
        ),
        entries=[],
    )
    service = RunService(runtime_executable=sys.executable, runner_boot_path=str(tmp_path / "run_runner.py"))
    delegation: list[str] = []
    original_plan_launch = plan_launch

    def _tracking_plan_launch(**kwargs):  # type: ignore[no-untyped-def]
        delegation.append("plan_launch")
        return original_plan_launch(**kwargs)

    def _tracking_start_manifest(self, manifest_path: str, *, cwd: str) -> None:  # type: ignore[no-untyped-def]
        delegation.append("_start_manifest")

    monkeypatch.setattr("app.run.run_service.plan_launch", _tracking_plan_launch)
    monkeypatch.setattr(RunService, "_start_manifest", _tracking_start_manifest)

    session = service.start_run(loaded_project)

    assert delegation == ["plan_launch", "_start_manifest"]
    assert session.run_id


def test_start_run_applies_explicit_run_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit run overrides should flow into generated run manifest fields."""
    project_root = tmp_path / "project"
    (project_root / "app").mkdir(parents=True)
    (project_root / "run.py").write_text("print('run')\n", encoding="utf-8")
    (project_root / "app" / "main.py").write_text("print('main')\n", encoding="utf-8")
    loaded_project = LoadedProject(
        project_root=str(project_root.resolve()),
        manifest_path=str((project_root / "cbcs" / "project.json").resolve()),
        metadata=ProjectMetadata(
            schema_version=1,
            name="demo",
            default_entry="run.py",
            working_directory=".",
            env_overrides={"BASE_ENV": "1"},
        ),
        entries=[],
    )
    service = RunService(runtime_executable=sys.executable, runner_boot_path=str(tmp_path / "run_runner.py"))
    monkeypatch.setattr(service.supervisor, "start", lambda *args, **kwargs: None)

    session = service.start_run(
        loaded_project,
        entry_file="app/main.py",
        mode="python_script",
        argv=["--flag"],
        working_directory="app",
        env_overrides={"EXTRA_ENV": "2"},
    )
    manifest = load_run_manifest(session.manifest_path)

    assert manifest.entry_file == "app/main.py"
    assert manifest.mode == "python_script"
    assert manifest.working_directory == str((project_root / "app").resolve())
    assert manifest.argv == ("--flag",)
    assert dict(manifest.env)["BASE_ENV"] == "1"
    assert dict(manifest.env)["EXTRA_ENV"] == "2"
    assert manifest.log_file == session.log_file_path
    assert Path(manifest.log_file).name.endswith(".log")


def test_start_run_uses_project_default_argv_when_not_overridden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When argv is omitted, metadata default_argv should populate run manifest."""
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    (project_root / "run.py").write_text("print('run')\n", encoding="utf-8")
    loaded_project = LoadedProject(
        project_root=str(project_root.resolve()),
        manifest_path=str((project_root / "cbcs" / "project.json").resolve()),
        metadata=ProjectMetadata(
            schema_version=1,
            name="demo",
            default_entry="run.py",
            default_argv=["--from-default"],
        ),
        entries=[],
    )
    service = RunService(runtime_executable=sys.executable, runner_boot_path=str(tmp_path / "run_runner.py"))
    monkeypatch.setattr(service.supervisor, "start", lambda *args, **kwargs: None)

    session = service.start_run(loaded_project)
    manifest = load_run_manifest(session.manifest_path)

    assert manifest.argv == ("--from-default",)


def test_start_run_supports_projectless_repl_with_home_working_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Projectless REPL runs should default to home cwd."""
    state_root = tmp_path / "state"
    service = RunService(
        runtime_executable=sys.executable,
        runner_boot_path=str(tmp_path / "run_runner.py"),
        state_root=str(state_root.resolve()),
    )
    launch_context: dict[str, str] = {}

    def _capture_start(_command: list[str], *, cwd: str, env) -> None:  # type: ignore[no-untyped-def]
        launch_context["cwd"] = cwd

    monkeypatch.setattr(service.supervisor, "start", _capture_start)

    session = service.start_run(None, mode="python_repl")
    manifest = load_run_manifest(session.manifest_path)
    expected_home = str(Path.home().expanduser().resolve())

    assert manifest.mode == "python_repl"
    assert manifest.repl_control is not None
    assert manifest.working_directory == expected_home
    assert manifest.log_file == session.log_file_path
    assert launch_context["cwd"] == expected_home
    assert "/repl/runs/" in session.manifest_path
    assert "/repl/logs/" in session.log_file_path


def test_start_run_supports_projectless_script_with_explicit_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = tmp_path / "state"
    script_path = tmp_path / "snippet.py"
    script_path.write_text("print('snippet')\n", encoding="utf-8")
    service = RunService(
        runtime_executable=sys.executable,
        runner_boot_path=str(tmp_path / "run_runner.py"),
        state_root=str(state_root.resolve()),
    )
    launch_context: dict[str, str] = {}

    def _capture_start(_command: list[str], *, cwd: str, env) -> None:  # type: ignore[no-untyped-def]
        launch_context["cwd"] = cwd

    monkeypatch.setattr(service.supervisor, "start", _capture_start)

    session = service.start_run(None, mode=constants.RUN_MODE_PYTHON_SCRIPT, entry_file=str(script_path))
    manifest = load_run_manifest(session.manifest_path)

    assert manifest.mode == constants.RUN_MODE_PYTHON_SCRIPT
    assert manifest.entry_file == str(script_path.resolve())
    assert manifest.project_root == str(script_path.parent.resolve())
    assert manifest.working_directory == str(script_path.parent.resolve())
    assert launch_context["cwd"] == str(script_path.parent.resolve())


def test_start_run_python_debug_writes_transport_policy_and_source_maps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    (project_root / "run.py").write_text("print('run')\n", encoding="utf-8")
    loaded_project = LoadedProject(
        project_root=str(project_root.resolve()),
        manifest_path=str((project_root / "cbcs" / "project.json").resolve()),
        metadata=ProjectMetadata(
            schema_version=1,
            name="demo",
            default_entry="run.py",
        ),
        entries=[],
    )
    service = RunService(runtime_executable=sys.executable, runner_boot_path=str(tmp_path / "run_runner.py"))
    monkeypatch.setattr(service.supervisor, "start", lambda *args, **kwargs: None)

    session = service.start_run(
        loaded_project,
        mode=constants.RUN_MODE_PYTHON_DEBUG,
        debug_exception_policy=DebugExceptionPolicy(
            stop_on_uncaught_exceptions=False,
            stop_on_raised_exceptions=True,
        ),
        source_maps=[
            DebugSourceMap(
                runtime_path=str((project_root / "cbcs" / "temp.py").resolve()),
                source_path=str((project_root / "run.py").resolve()),
            )
        ],
    )
    manifest = load_run_manifest(session.manifest_path)

    assert manifest.mode == constants.RUN_MODE_PYTHON_DEBUG
    assert manifest.debug_transport is not None
    assert manifest.debug_transport.protocol
    assert manifest.debug_transport.host == "127.0.0.1"
    assert manifest.debug_transport.port > 0
    assert manifest.debug_exception_policy == DebugExceptionPolicy(
        stop_on_uncaught_exceptions=False,
        stop_on_raised_exceptions=True,
    )
    assert manifest.source_maps == (
        DebugSourceMap(
            runtime_path=str((project_root / "cbcs" / "temp.py").resolve()),
            source_path=str((project_root / "run.py").resolve()),
        ),
    )
    service._close_debug_transport_server()  # noqa: SLF001 - avoid leaking a listener in unit tests


def test_forward_debug_message_forwards_events_without_pause_tracking(tmp_path: Path) -> None:
    """Structured debug events should be forwarded to observers unchanged."""
    captured_events: list[ProcessEvent] = []
    service = RunService(
        on_event=captured_events.append,
        runtime_executable=sys.executable,
        runner_boot_path=str(tmp_path / "run_runner.py"),
    )

    service._forward_debug_message(  # noqa: SLF001 - characterization test for private coordination logic
        {"kind": "event", "event": "stopped", "body": {"message": "Paused at breakpoint."}}
    )
    service._forward_debug_message(  # noqa: SLF001 - characterization test for private coordination logic
        {"kind": "event", "event": "continued", "body": {"message": "Debug execution running."}}
    )
    assert [event.event_type for event in captured_events] == ["debug", "debug"]


def test_forward_event_exit_clears_active_session_state(tmp_path: Path) -> None:
    """Exit events should clear current session metadata."""
    service = RunService(
        runtime_executable=sys.executable,
        runner_boot_path=str(tmp_path / "run_runner.py"),
    )
    service._current_session = RunSession(  # noqa: SLF001 - characterization test for private state
        run_id="run123",
        manifest_path="/tmp/run_manifest.json",
        log_file_path="/tmp/run.log",
        project_root="/tmp/project",
        entry_file="main.py",
        mode=constants.RUN_MODE_PYTHON_DEBUG,
    )

    service._forward_event(  # noqa: SLF001 - characterization test for private coordination logic
        ProcessEvent(event_type="exit", return_code=0, terminated_by_user=False)
    )

    assert service.current_session is None


def test_second_start_run_raises_and_preserves_debug_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CC-03: re-entrant start_run must fail before tearing down active debug transport."""
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    (project_root / "run.py").write_text("print('run')\n", encoding="utf-8")
    loaded_project = LoadedProject(
        project_root=str(project_root.resolve()),
        manifest_path=str((project_root / "cbcs" / "project.json").resolve()),
        metadata=ProjectMetadata(
            schema_version=1,
            name="demo",
            default_entry="run.py",
        ),
        entries=[],
    )
    service = RunService(runtime_executable=sys.executable, runner_boot_path=str(tmp_path / "run_runner.py"))
    supervisor_running = {"value": False}

    def _start_and_mark_running(*_args, **_kwargs) -> int:  # type: ignore[no-untyped-def]
        supervisor_running["value"] = True
        return 4242

    monkeypatch.setattr(service.supervisor, "start", _start_and_mark_running)
    monkeypatch.setattr(service.supervisor, "is_running", lambda: supervisor_running["value"])

    session = service.start_run(loaded_project, mode=constants.RUN_MODE_PYTHON_DEBUG)
    first_transport = service._debug_transport_server  # noqa: SLF001
    assert first_transport is not None
    assert session.mode == constants.RUN_MODE_PYTHON_DEBUG

    with pytest.raises(RunLifecycleError, match="already active"):
        service.start_run(loaded_project, mode=constants.RUN_MODE_PYTHON_DEBUG)

    assert service._debug_transport_server is first_transport  # noqa: SLF001
    assert first_transport._server_socket is not None  # noqa: SLF001
    service._close_debug_transport_server()  # noqa: SLF001 - avoid leaking a listener in unit tests


@pytest.mark.parametrize("failure", [RunLifecycleError("Runner process is already active."), RuntimeError("boom")])
def test_start_run_rolls_back_manifest_when_supervisor_start_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
) -> None:
    """CC-08: failed supervisor launch must remove manifest and clear debug transport."""
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    (project_root / "run.py").write_text("print('run')\n", encoding="utf-8")
    loaded_project = LoadedProject(
        project_root=str(project_root.resolve()),
        manifest_path=str((project_root / "cbcs" / "project.json").resolve()),
        metadata=ProjectMetadata(
            schema_version=1,
            name="demo",
            default_entry="run.py",
        ),
        entries=[],
    )
    service = RunService(runtime_executable=sys.executable, runner_boot_path=str(tmp_path / "run_runner.py"))
    manifest_dir = project_root / "cbcs" / "runs"

    def _raise_on_start(*_args, **_kwargs) -> None:  # type: ignore[no-untyped-def]
        raise failure

    monkeypatch.setattr(service.supervisor, "start", _raise_on_start)

    with pytest.raises(type(failure), match=str(failure) if str(failure) else None):
        service.start_run(loaded_project, mode=constants.RUN_MODE_PYTHON_DEBUG)

    assert service.current_session is None
    assert list(manifest_dir.glob("run_manifest_*.json")) == []
    assert service._debug_transport_server is None  # noqa: SLF001


def test_forward_debug_transport_error_closes_server_and_emits_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CC-06: transport errors must close the editor-side server and notify observers."""
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    (project_root / "run.py").write_text("print('run')\n", encoding="utf-8")
    loaded_project = LoadedProject(
        project_root=str(project_root.resolve()),
        manifest_path=str((project_root / "cbcs" / "project.json").resolve()),
        metadata=ProjectMetadata(
            schema_version=1,
            name="demo",
            default_entry="run.py",
        ),
        entries=[],
    )
    captured_events: list[ProcessEvent] = []
    service = RunService(
        on_event=captured_events.append,
        runtime_executable=sys.executable,
        runner_boot_path=str(tmp_path / "run_runner.py"),
    )
    monkeypatch.setattr(service.supervisor, "start", lambda *args, **kwargs: None)

    service.start_run(loaded_project, mode=constants.RUN_MODE_PYTHON_DEBUG)
    assert service._debug_transport_server is not None  # noqa: SLF001

    service._forward_debug_transport_error("Debug transport disconnected.")  # noqa: SLF001

    assert service._debug_transport_server is None  # noqa: SLF001
    debug_payloads = [
        event.payload
        for event in captured_events
        if event.event_type == "debug" and isinstance(event.payload, dict)
    ]
    assert any(payload.get("event") == "session_ended" for payload in debug_payloads)
    assert any(
        event.event_type == "output" and "[debug]" in (event.text or "")
        for event in captured_events
    )

