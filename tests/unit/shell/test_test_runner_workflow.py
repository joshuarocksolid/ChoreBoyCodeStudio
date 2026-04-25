from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.core.models import LoadedProject, ProjectMetadata
from app.run.problem_parser import ProblemEntry
from app.run.pytest_discovery_service import DiscoveredTestNode, DiscoveryResult
from app.run.pytest_runner_service import PytestRunResult
from app.shell.test_runner_workflow import ActiveTestEditor, TestRunnerWorkflow

pytestmark = pytest.mark.unit


@dataclass
class FakeProvider:
    title: str = "Fake Pytest"


class FakeScheduler:
    def __init__(self) -> None:
        self.keys: list[str] = []

    def run(self, *, key, task, on_success, on_error):  # type: ignore[no-untyped-def]
        self.keys.append(key)
        try:
            on_success(task(None))
        except Exception as exc:
            on_error(exc)


class FakeExplorer:
    def __init__(self) -> None:
        self.running_states: list[bool] = []
        self.discovery: DiscoveryResult | None = None
        self.outcomes: dict[str, str] = {}

    def set_running(self, running: bool) -> None:
        self.running_states.append(running)

    def update_discovery(self, result: DiscoveryResult) -> None:
        self.discovery = result

    def set_outcomes(self, outcomes: dict[str, str]) -> None:
        self.outcomes = dict(outcomes)

    def failed_node_ids(self) -> list[str]:
        return [node_id for node_id, outcome in self.outcomes.items() if outcome == "failed"]


class WorkflowHarness:
    def __init__(self, tmp_path: Path) -> None:
        self.project_root = tmp_path / "project"
        self.project_root.mkdir()
        self.run_tests_path = self.project_root / "run_tests.py"
        self.run_tests_path.write_text("raise SystemExit(0)\n", encoding="utf-8")
        self.test_file = self.project_root / "tests" / "test_sample.py"
        self.test_file.parent.mkdir()
        self.test_file.write_text("def test_alpha():\n    assert True\n", encoding="utf-8")
        self.scheduler = FakeScheduler()
        self.explorer = FakeExplorer()
        self.console: list[tuple[str, str]] = []
        self.problems: list[list[ProblemEntry]] = []
        self.warnings: list[tuple[str, str]] = []
        self.infos: list[tuple[str, str]] = []
        self.debug_sessions: list[dict[str, Any]] = []
        self.debug_targets: list[dict[str, object]] = []
        self.workflow_calls: list[dict[str, Any]] = []
        self.discovery = DiscoveryResult(nodes=[
            DiscoveredTestNode(
                node_id="tests/test_sample.py",
                name="test_sample.py",
                file_path=str(self.test_file),
                line_number=0,
                kind="file",
            ),
            DiscoveredTestNode(
                node_id="tests/test_sample.py::test_alpha",
                name="test_alpha",
                file_path=str(self.test_file),
                line_number=1,
                kind="function",
                parent_id="tests/test_sample.py",
            ),
        ])
        self.result = PytestRunResult(
            command=["pytest"],
            project_root=str(self.project_root),
            return_code=0,
            stdout="tests/test_sample.py::test_alpha PASSED\n",
            stderr="",
            elapsed_ms=1.0,
            failures=[],
        )
        self.loaded_project: LoadedProject | None = LoadedProject(
            project_root=str(self.project_root),
            manifest_path=str(self.project_root / "cbcs" / "project.json"),
            metadata=ProjectMetadata(schema_version=1, project_id="proj", name="Project"),
        )
        self.active_editor = ActiveTestEditor(
            file_path=str(self.test_file),
            source_text=self.test_file.read_text(encoding="utf-8"),
            cursor_line=1,
        )
        self.workflow = self._make_workflow()

    def _make_workflow(self) -> TestRunnerWorkflow:
        return TestRunnerWorkflow(
            loaded_project_provider=lambda: self.loaded_project,
            active_editor_provider=lambda: self.active_editor,
            workflow_broker=SimpleNamespace(),
            background_tasks=self.scheduler,
            test_explorer_panel=self.explorer,
            run_pytest_with_workflow=self._run_pytest_with_workflow,
            discover_tests=lambda project_root: self.discovery,
            start_debug_session=self._start_debug_session,
            build_debug_breakpoints=lambda: [{"file_path": str(self.test_file), "line_number": 1}],
            debug_exception_policy_provider=lambda: object(),
            append_console_line=lambda text, stream: self.console.append((text, stream)),
            set_problems=lambda problems: self.problems.append(list(problems)),
            focus_run_log_tab=lambda: None,
            focus_problems_tab=lambda: None,
            show_warning=lambda title, message: self.warnings.append((title, message)),
            show_information=lambda title, message: self.infos.append((title, message)),
            record_debug_target=lambda target: self.debug_targets.append(dict(target)),
            auto_open_console_on_output=lambda: True,
            auto_open_problems_on_failure=lambda: True,
            logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
        )

    def _run_pytest_with_workflow(self, _broker, **kwargs):  # type: ignore[no-untyped-def]
        self.workflow_calls.append(dict(kwargs))
        return FakeProvider(), self.result

    def _start_debug_session(self, **kwargs):  # type: ignore[no-untyped-def]
        self.debug_sessions.append(dict(kwargs))
        return True


def test_run_all_tests_uses_project_scope(tmp_path: Path) -> None:
    harness = WorkflowHarness(tmp_path)

    harness.workflow.run_all_tests()

    assert harness.workflow_calls[-1]["project_root"] == str(harness.project_root)
    assert harness.workflow_calls[-1].get("target_path") is None
    assert harness.explorer.running_states == [True, False]


def test_run_file_tests_targets_active_file(tmp_path: Path) -> None:
    harness = WorkflowHarness(tmp_path)

    harness.workflow.run_file_tests()

    assert harness.workflow_calls[-1]["target_path"] == str(harness.test_file.resolve())


def test_run_test_at_cursor_uses_discovered_node_id(tmp_path: Path) -> None:
    harness = WorkflowHarness(tmp_path)
    harness.workflow.refresh_discovery()

    harness.workflow.run_test_at_cursor()

    assert harness.workflow_calls[-1]["target_node_id"] == "tests/test_sample.py::test_alpha"


def test_rerun_failed_tests_passes_failed_node_args(tmp_path: Path) -> None:
    harness = WorkflowHarness(tmp_path)
    harness.explorer.set_outcomes({
        "tests/test_sample.py::test_alpha": "failed",
        "tests/test_sample.py::test_beta": "passed",
    })

    harness.workflow.rerun_failed_tests()

    assert harness.workflow_calls[-1]["pytest_args"] == ["-v", "tests/test_sample.py::test_alpha"]


def test_debug_failed_test_starts_debug_session_for_first_failed_node(tmp_path: Path) -> None:
    harness = WorkflowHarness(tmp_path)
    harness.explorer.set_outcomes({"tests/test_sample.py::test_alpha": "failed"})

    harness.workflow.debug_failed_test()

    assert harness.debug_sessions[-1]["entry_file"] == str(harness.run_tests_path)
    assert harness.debug_sessions[-1]["argv"] == ["-q", "--import-mode=importlib", "tests/test_sample.py::test_alpha"]
    assert harness.debug_targets[-1] == {"kind": "test_node", "node_id": "tests/test_sample.py::test_alpha"}


def test_refresh_discovery_pushes_result_to_explorer(tmp_path: Path) -> None:
    harness = WorkflowHarness(tmp_path)

    harness.workflow.refresh_discovery()

    assert harness.explorer.discovery == harness.discovery
    assert harness.explorer.outcomes == {}


def test_handle_pytest_result_updates_outcomes_and_problems(tmp_path: Path) -> None:
    harness = WorkflowHarness(tmp_path)
    harness.workflow.refresh_discovery()
    harness.result = PytestRunResult(
        command=["pytest"],
        project_root=str(harness.project_root),
        return_code=1,
        stdout="tests/test_sample.py::test_alpha FAILED\n",
        stderr="",
        elapsed_ms=1.0,
        failures=[
            ProblemEntry(
                file_path=str(harness.test_file),
                line_number=1,
                context="pytest",
                message="AssertionError",
            )
        ],
    )

    harness.workflow.run_all_tests()

    assert harness.explorer.outcomes == {"tests/test_sample.py::test_alpha": "failed"}
    assert harness.problems[-1][0].message == "AssertionError"
