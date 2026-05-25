"""Unit tests for project-tree delete orchestration workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping

import pytest

from app.shell.project_tree_action_workflow import ProjectTreeActionWorkflow

pytestmark = pytest.mark.unit


@dataclass
class RecordingSaveWorkflow:
    proceed: bool = True
    calls: list[tuple[list[str], str | None]] = field(default_factory=list)

    def confirm_proceed_before_tree_delete(
        self,
        target_paths: list[str],
        *,
        action_description: str = "moving items to trash",
    ) -> bool:
        self.calls.append((list(target_paths), action_description))
        return self.proceed


@dataclass
class RecordingLocalHistoryWorkflow:
    snapshots: dict[str, str] = field(default_factory=dict)
    captured_paths: list[list[str]] = field(default_factory=list)
    recorded_transactions: list[tuple[dict[str, str], str, str]] = field(default_factory=list)
    filtered_snapshots: dict[str, str] | None = None

    def capture_delete_snapshots(self, target_paths: list[str]) -> dict[str, str]:
        self.captured_paths.append(list(target_paths))
        return dict(self.snapshots)

    def record_transaction(
        self,
        payloads_by_path: Mapping[str, str],
        *,
        source: str,
        label: str,
    ) -> None:
        self.recorded_transactions.append((dict(payloads_by_path), source, label))

    def filter_snapshots_for_paths(
        self,
        snapshots_by_path: Mapping[str, str],
        accepted_paths: list[str],
    ) -> dict[str, str]:
        if self.filtered_snapshots is not None:
            return dict(self.filtered_snapshots)
        return dict(snapshots_by_path)


@dataclass
class RecordingCoordinator:
    delete_error: str | None = None
    bulk_result: tuple[list[str], list[str]] = field(default_factory=lambda: ([], []))
    deleted_paths: list[str] = field(default_factory=list)
    bulk_paths: list[list[str]] = field(default_factory=list)

    def handle_delete(self, target_path: str) -> str | None:
        self.deleted_paths.append(target_path)
        return self.delete_error

    def handle_bulk_delete(self, paths: list[str]) -> tuple[list[str], list[str]]:
        self.bulk_paths.append(list(paths))
        return self.bulk_result


@dataclass
class WorkflowHarness:
    workflow: ProjectTreeActionWorkflow
    save_workflow: RecordingSaveWorkflow
    local_history_workflow: RecordingLocalHistoryWorkflow
    coordinator: RecordingCoordinator
    prompts: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[tuple[str, str]] = field(default_factory=list)


def _workflow(
    *,
    save_workflow: RecordingSaveWorkflow | None = None,
    local_history_workflow: RecordingLocalHistoryWorkflow | None = None,
    coordinator: RecordingCoordinator | None = None,
    ask_yes_no: Callable[[str, str], bool] | None = None,
    show_warning: Callable[[str, str], None] | None = None,
) -> WorkflowHarness:
    save = save_workflow or RecordingSaveWorkflow()
    history = local_history_workflow or RecordingLocalHistoryWorkflow()
    tree_coordinator = coordinator or RecordingCoordinator()
    prompts: list[tuple[str, str]] = []
    warnings: list[tuple[str, str]] = []

    def _ask_yes_no(title: str, text: str) -> bool:
        prompts.append((title, text))
        return True

    def _show_warning(title: str, text: str) -> None:
        warnings.append((title, text))

    workflow = ProjectTreeActionWorkflow(
        save_workflow=save,
        local_history_workflow=history,
        project_tree_action_coordinator=tree_coordinator,
        dialog_parent=object(),  # type: ignore[arg-type]
        ask_yes_no=ask_yes_no or _ask_yes_no,
        show_warning=show_warning or _show_warning,
    )
    return WorkflowHarness(
        workflow=workflow,
        save_workflow=save,
        local_history_workflow=history,
        coordinator=tree_coordinator,
        prompts=prompts,
        warnings=warnings,
    )


def test_delete_paths_confirmation_uses_move_to_trash_copy() -> None:
    harness = _workflow()

    harness.workflow.delete_paths("/tmp/example.txt")

    assert harness.coordinator.deleted_paths == ["/tmp/example.txt"]
    assert harness.prompts == [("Move to Trash", "Move 'example.txt' to trash?")]
    assert harness.local_history_workflow.captured_paths == [["/tmp/example.txt"]]
    assert harness.local_history_workflow.recorded_transactions == [({}, "delete", "Delete 'example.txt'")]


def test_delete_paths_blocks_when_save_workflow_declines() -> None:
    harness = _workflow(
        save_workflow=RecordingSaveWorkflow(proceed=False),
    )

    harness.workflow.delete_paths("/tmp/example.txt")

    assert harness.coordinator.deleted_paths == []
    assert harness.prompts == []
    assert harness.local_history_workflow.captured_paths == []


def test_delete_paths_skips_coordinator_when_trash_confirm_declined() -> None:
    harness = _workflow(ask_yes_no=lambda _title, _text: False)

    harness.workflow.delete_paths("/tmp/example.txt")

    assert harness.coordinator.deleted_paths == []
    assert harness.local_history_workflow.captured_paths == []


def test_delete_paths_shows_warning_and_skips_history_on_coordinator_error() -> None:
    harness = _workflow(
        coordinator=RecordingCoordinator(delete_error="permission denied"),
    )

    harness.workflow.delete_paths("/tmp/example.txt")

    assert harness.coordinator.deleted_paths == ["/tmp/example.txt"]
    assert harness.warnings == [("Move to Trash", "permission denied")]
    assert harness.local_history_workflow.recorded_transactions == []


def test_bulk_delete_failure_warning_uses_move_to_trash_title() -> None:
    harness = _workflow(
        coordinator=RecordingCoordinator(
            bulk_result=(["one.py: permission denied"], ["/tmp/one.py"]),
        ),
    )

    harness.workflow.bulk_delete(["/tmp/one.py", "/tmp/two.py"])

    assert harness.save_workflow.calls == [
        (["/tmp/one.py", "/tmp/two.py"], "moving 2 items to trash"),
    ]
    assert harness.coordinator.bulk_paths == [["/tmp/one.py", "/tmp/two.py"]]
    assert harness.local_history_workflow.captured_paths == [["/tmp/one.py", "/tmp/two.py"]]
    assert harness.local_history_workflow.recorded_transactions == [({}, "delete", "Bulk delete from project tree")]
    assert harness.prompts[0][0] == "Move to Trash"
    assert "cannot be undone" not in harness.prompts[0][1].lower()
    assert harness.warnings == [("Move to Trash", "one.py: permission denied")]


def test_bulk_delete_records_filtered_snapshots() -> None:
    history = RecordingLocalHistoryWorkflow(
        snapshots={"/tmp/one.py": "alpha", "/tmp/two.py": "beta"},
        filtered_snapshots={"/tmp/one.py": "alpha"},
    )
    harness = _workflow(
        local_history_workflow=history,
        coordinator=RecordingCoordinator(
            bulk_result=([], ["/tmp/one.py"]),
        ),
    )

    harness.workflow.bulk_delete(["/tmp/one.py", "/tmp/two.py"])

    assert harness.local_history_workflow.recorded_transactions == [
        ({"/tmp/one.py": "alpha"}, "delete", "Bulk delete from project tree"),
    ]


def test_bulk_delete_blocks_when_save_workflow_declines() -> None:
    harness = _workflow(
        save_workflow=RecordingSaveWorkflow(proceed=False),
    )

    harness.workflow.bulk_delete(["/tmp/one.py", "/tmp/two.py"])

    assert harness.coordinator.bulk_paths == []
    assert harness.local_history_workflow.captured_paths == []
