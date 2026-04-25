"""Pytest workflow orchestration for the shell."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from app.core import constants
from app.core.models import LoadedProject
from app.debug.debug_models import DebugBreakpoint, DebugExceptionPolicy
from app.run.problem_parser import ProblemEntry
from app.run.pytest_discovery_service import DiscoveryResult, discover_tests as default_discover_tests, parse_test_results
from app.run.pytest_runner_service import PytestRunResult, identify_test_at_cursor


@dataclass(frozen=True)
class ActiveTestEditor:
    """Active editor data needed for pytest targeting."""

    file_path: str
    source_text: str
    cursor_line: int


class TestExplorerView(Protocol):
    def set_running(self, running: bool) -> None:
        ...

    def update_discovery(self, result: DiscoveryResult) -> None:
        ...

    def set_outcomes(self, outcomes: dict[str, str]) -> None:
        ...

    def failed_node_ids(self) -> list[str]:
        ...


class BackgroundTaskRunner(Protocol):
    def run(
        self,
        *,
        key: str,
        task: Callable[[Any], object],
        on_success: Callable[[Any], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        ...


class TestRunnerWorkflow:
    """Owns in-app pytest discovery, execution, and debug targeting."""

    def __init__(
        self,
        *,
        loaded_project_provider: Callable[[], LoadedProject | None],
        active_editor_provider: Callable[[], ActiveTestEditor | None],
        workflow_broker: Any,
        background_tasks: BackgroundTaskRunner,
        test_explorer_panel: TestExplorerView | None,
        run_pytest_with_workflow: Callable[..., tuple[Any, PytestRunResult]],
        start_debug_session: Callable[..., bool],
        build_debug_breakpoints: Callable[[], list[DebugBreakpoint] | list[dict[str, object]]],
        debug_exception_policy_provider: Callable[[], DebugExceptionPolicy | object | None],
        append_console_line: Callable[[str, str], None],
        set_problems: Callable[[list[ProblemEntry]], None],
        focus_run_log_tab: Callable[[], None],
        focus_problems_tab: Callable[[], None],
        show_warning: Callable[[str, str], None],
        show_information: Callable[[str, str], None],
        record_debug_target: Callable[[dict[str, object]], None],
        auto_open_console_on_output: Callable[[], bool],
        auto_open_problems_on_failure: Callable[[], bool],
        logger: Any,
        discover_tests: Callable[[str], DiscoveryResult] = default_discover_tests,
    ) -> None:
        self._loaded_project_provider = loaded_project_provider
        self._active_editor_provider = active_editor_provider
        self._workflow_broker = workflow_broker
        self._background_tasks = background_tasks
        self._test_explorer_panel = test_explorer_panel
        self._run_pytest_with_workflow = run_pytest_with_workflow
        self._discover_tests = discover_tests
        self._start_debug_session = start_debug_session
        self._build_debug_breakpoints = build_debug_breakpoints
        self._debug_exception_policy_provider = debug_exception_policy_provider
        self._append_console_line = append_console_line
        self._set_problems = set_problems
        self._focus_run_log_tab = focus_run_log_tab
        self._focus_problems_tab = focus_problems_tab
        self._show_warning = show_warning
        self._show_information = show_information
        self._record_debug_target = record_debug_target
        self._auto_open_console_on_output = auto_open_console_on_output
        self._auto_open_problems_on_failure = auto_open_problems_on_failure
        self._logger = logger
        self._test_discovery_result = DiscoveryResult()
        self._test_outcomes_by_node_id: dict[str, str] = {}

    def run_all_tests(self) -> None:
        loaded_project = self._require_project("Run Project Tests")
        if loaded_project is None:
            return
        project_root = loaded_project.project_root
        self._append_console_line(f"Running pytest in {project_root}", "system")
        self._run_pytest_background(
            key="run_pytest_project",
            title="Run Project Tests",
            start_error_prefix="Pytest run failed to start",
            success_message_prefix="Pytest completed",
            project_root=project_root,
        )

    def run_file_tests(self) -> None:
        loaded_project = self._require_project("Run Current File Tests")
        if loaded_project is None:
            return
        active_editor = self._active_editor_provider()
        if active_editor is None:
            self._show_warning("Run Current File Tests", "Open a file tab first.")
            return
        target_path = self._project_relative_target(
            loaded_project,
            active_editor.file_path,
            title="Run Current File Tests",
            outside_message="Current file is outside project root and cannot be run as a test target.",
        )
        if target_path is None:
            return
        self._append_console_line(f"Running pytest for {target_path}", "system")
        self._run_pytest_background(
            key="run_pytest_target",
            title="Run Current File Tests",
            start_error_prefix="Pytest target run failed to start",
            success_message_prefix="Pytest completed",
            project_root=loaded_project.project_root,
            target_path=str(target_path),
        )

    def run_test_at_cursor(self) -> None:
        loaded_project = self._require_project("Run Test at Cursor")
        if loaded_project is None:
            return
        active_editor = self._active_editor_provider()
        if active_editor is None:
            self._show_warning("Run Test at Cursor", "Open a file tab first.")
            return
        target_path = self._project_relative_target(
            loaded_project,
            active_editor.file_path,
            title="Run Test at Cursor",
            outside_message="Current file is outside project root and cannot be run as a test target.",
        )
        if target_path is None:
            return
        test_name = identify_test_at_cursor(active_editor.source_text, active_editor.cursor_line)
        if not test_name:
            self._show_information("Run Test at Cursor", "Place the cursor inside a test function first.")
            return
        node_id = self._node_id_for_cursor_test(target_path, test_name, loaded_project)
        self.run_test_node(node_id)

    def rerun_failed_tests(self) -> None:
        loaded_project = self._require_project("Rerun Failed")
        if loaded_project is None:
            return
        failed_node_ids = self._failed_node_ids()
        if not failed_node_ids:
            self._show_information("Rerun Failed", "No failed tests recorded yet.")
            return
        self._append_console_line(f"Rerunning failed pytest nodes ({len(failed_node_ids)})", "system")
        self._run_pytest_background(
            key="run_pytest_failed",
            title="Rerun Failed",
            start_error_prefix="Rerun failed failed to start",
            success_message_prefix="Rerun failed completed",
            project_root=loaded_project.project_root,
            pytest_args=["-v"] + failed_node_ids,
        )

    def debug_failed_test(self) -> None:
        failed_node_ids = self._failed_node_ids()
        if not failed_node_ids:
            self._show_information("Debug Failed Test", "No failed tests recorded yet.")
            return
        self.debug_test_node(failed_node_ids[0])

    def has_failed_tests(self) -> bool:
        return bool(self._failed_node_ids())

    def run_test_node(self, node_id: str) -> None:
        loaded_project = self._require_project("Run Test")
        if loaded_project is None:
            return
        normalized_node = node_id.strip()
        if not normalized_node:
            return
        self._append_console_line(f"Running pytest node {normalized_node}", "system")
        self._run_pytest_background(
            key="run_pytest_node",
            title="Run Test",
            start_error_prefix="Pytest node run failed to start",
            success_message_prefix="Pytest node run completed",
            project_root=loaded_project.project_root,
            target_node_id=normalized_node,
        )

    def debug_current_file_tests(self) -> None:
        loaded_project = self._require_project("Debug Current Test")
        if loaded_project is None:
            return
        active_editor = self._active_editor_provider()
        if active_editor is None:
            self._show_warning("Debug Current Test", "Open a file tab first.")
            return
        target_path = self._project_relative_target(
            loaded_project,
            active_editor.file_path,
            title="Debug Current Test",
            outside_message="Current file is outside project root and cannot be debugged as a pytest target.",
        )
        if target_path is None:
            return
        if self._start_debug_target(
            title="Debug Current Test",
            loaded_project=loaded_project,
            argv=["-q", "--import-mode=importlib", str(target_path)],
        ):
            self._record_debug_target({"kind": "current_test", "target_path": str(target_path)})

    def debug_test_node(self, node_id: str) -> None:
        loaded_project = self._require_project("Debug Test")
        if loaded_project is None:
            return
        normalized_node = node_id.strip()
        if not normalized_node:
            return
        if self._start_debug_target(
            title="Debug Test",
            loaded_project=loaded_project,
            argv=["-q", "--import-mode=importlib", normalized_node],
        ):
            self._record_debug_target({"kind": "test_node", "node_id": normalized_node})

    def refresh_discovery(self) -> None:
        loaded_project = self._loaded_project_provider()
        if loaded_project is None:
            self._test_discovery_result = DiscoveryResult()
            self._test_outcomes_by_node_id.clear()
            if self._test_explorer_panel is not None:
                self._test_explorer_panel.update_discovery(self._test_discovery_result)
                self._test_explorer_panel.set_outcomes({})
            return

        def task(_cancel_event: Any) -> object:
            return self._discover_tests(loaded_project.project_root)

        def on_success(result: Any) -> None:
            self._test_discovery_result = result
            if self._test_explorer_panel is not None:
                self._test_explorer_panel.update_discovery(result)
                self._test_explorer_panel.set_outcomes(self._test_outcomes_by_node_id)

        def on_error(exc: Exception) -> None:
            self._logger.warning("Test discovery failed: %s", exc)
            self._test_discovery_result = DiscoveryResult(error_message=str(exc))
            if self._test_explorer_panel is not None:
                self._test_explorer_panel.update_discovery(self._test_discovery_result)
                self._test_explorer_panel.set_outcomes(self._test_outcomes_by_node_id)

        self._background_tasks.run(
            key="test_discovery",
            task=task,
            on_success=on_success,
            on_error=on_error,
        )

    def _run_pytest_background(
        self,
        *,
        key: str,
        title: str,
        start_error_prefix: str,
        success_message_prefix: str,
        project_root: str,
        target_path: str | None = None,
        target_node_id: str | None = None,
        pytest_args: list[str] | None = None,
    ) -> None:
        if self._test_explorer_panel is not None:
            self._test_explorer_panel.set_running(True)

        def task(_cancel_event: Any) -> object:
            return self._run_pytest_with_workflow(
                self._workflow_broker,
                project_root=project_root,
                target_path=target_path,
                target_node_id=target_node_id,
                pytest_args=pytest_args,
            )

        def on_success(payload: Any) -> None:
            if self._test_explorer_panel is not None:
                self._test_explorer_panel.set_running(False)
            provider, result = payload
            self._append_console_line(f"{success_message_prefix} via {provider.title}", "system")
            self._handle_pytest_run_result(result)

        def on_error(exc: Exception) -> None:
            if self._test_explorer_panel is not None:
                self._test_explorer_panel.set_running(False)
            self._append_console_line(f"{start_error_prefix}: {exc}", "stderr")
            self._show_warning(title, f"Pytest run failed: {exc}")

        self._background_tasks.run(
            key=key,
            task=task,
            on_success=on_success,
            on_error=on_error,
        )

    def _handle_pytest_run_result(self, result: PytestRunResult) -> None:
        if result.stdout.strip():
            for line in result.stdout.splitlines():
                self._append_console_line(line, "stdout")
        if result.stderr.strip():
            for line in result.stderr.splitlines():
                self._append_console_line(line, "stderr")
        if self._auto_open_console_on_output() and (result.stdout.strip() or result.stderr.strip()):
            self._focus_run_log_tab()
        if result.failures:
            self._set_problems(result.failures)
            if self._auto_open_problems_on_failure():
                self._focus_problems_tab()
        else:
            self._set_problems([])
        status = "passed" if result.succeeded else "failed"
        self._append_console_line(
            f"Pytest run {status} (code={result.return_code}, elapsed_ms={result.elapsed_ms:.2f}).",
            "system",
        )
        self._update_test_outcomes_from_pytest(result)

    def _update_test_outcomes_from_pytest(self, result: PytestRunResult) -> None:
        if not self._test_discovery_result.nodes:
            return
        parsed = parse_test_results(result.stdout)
        if not parsed:
            return
        outcome_map = {item.node_id: item.outcome for item in parsed}
        for node in self._test_discovery_result.function_nodes():
            outcome = outcome_map.get(node.node_id)
            if outcome is not None:
                self._test_outcomes_by_node_id[node.node_id] = outcome
        if self._test_explorer_panel is not None:
            self._test_explorer_panel.set_outcomes(self._test_outcomes_by_node_id)

    def _start_debug_target(
        self,
        *,
        title: str,
        loaded_project: LoadedProject,
        argv: list[str],
    ) -> bool:
        project_root_path = Path(loaded_project.project_root).expanduser().resolve()
        run_tests_path = project_root_path / "run_tests.py"
        if not run_tests_path.is_file():
            self._show_warning(
                title,
                "This project does not contain `run_tests.py`, so the pytest debug flow is unavailable.",
            )
            return False
        return self._start_debug_session(
            mode=constants.RUN_MODE_PYTHON_DEBUG,
            entry_file=str(run_tests_path),
            argv=argv,
            breakpoints=self._build_debug_breakpoints(),
            debug_exception_policy=self._debug_exception_policy_provider(),
        )

    def _require_project(self, title: str) -> LoadedProject | None:
        loaded_project = self._loaded_project_provider()
        if loaded_project is None:
            self._show_warning(title, "Open a project first.")
            return None
        return loaded_project

    def _project_relative_target(
        self,
        loaded_project: LoadedProject,
        file_path: str,
        *,
        title: str,
        outside_message: str,
    ) -> Path | None:
        target_path = Path(file_path).expanduser().resolve()
        project_root_path = Path(loaded_project.project_root).expanduser().resolve()
        try:
            target_path.relative_to(project_root_path)
        except ValueError:
            self._show_warning(title, outside_message)
            return None
        return target_path

    def _node_id_for_cursor_test(
        self,
        target_path: Path,
        test_name: str,
        loaded_project: LoadedProject,
    ) -> str:
        for node in self._test_discovery_result.function_nodes():
            if Path(node.file_path).expanduser().resolve() == target_path and node.name == test_name:
                return node.node_id
        relative_path = target_path.relative_to(Path(loaded_project.project_root).expanduser().resolve())
        return f"{relative_path.as_posix()}::{test_name}"

    def _failed_node_ids(self) -> list[str]:
        if self._test_explorer_panel is not None:
            failed_node_ids = self._test_explorer_panel.failed_node_ids()
            if failed_node_ids:
                return failed_node_ids
        return [
            node_id
            for node_id, outcome in self._test_outcomes_by_node_id.items()
            if outcome == "failed"
        ]
