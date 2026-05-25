"""Project-tree delete orchestration for the shell."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping, Optional, Protocol

from PySide2.QtWidgets import QMessageBox, QWidget


class SaveWorkflowPort(Protocol):
    def confirm_proceed_before_tree_delete(
        self,
        target_paths: list[str],
        *,
        action_description: str = "moving items to trash",
    ) -> bool:
        ...


class LocalHistoryWorkflowPort(Protocol):
    def capture_delete_snapshots(self, target_paths: list[str]) -> dict[str, str]:
        ...

    def record_transaction(
        self,
        payloads_by_path: Mapping[str, str],
        *,
        source: str,
        label: str,
    ) -> None:
        ...

    def filter_snapshots_for_paths(
        self,
        snapshots_by_path: Mapping[str, str],
        accepted_paths: list[str],
    ) -> dict[str, str]:
        ...


class ProjectTreeActionCoordinatorPort(Protocol):
    def handle_delete(self, target_path: str) -> Optional[str]:
        ...

    def handle_bulk_delete(self, paths: list[str]) -> tuple[list[str], list[str]]:
        ...


class ProjectTreeActionWorkflow:
    """Owns project-tree delete confirmation, history capture, and coordinator calls."""

    _MOVE_TO_TRASH_TITLE = "Move to Trash"

    def __init__(
        self,
        *,
        save_workflow: SaveWorkflowPort,
        local_history_workflow: LocalHistoryWorkflowPort,
        project_tree_action_coordinator: ProjectTreeActionCoordinatorPort,
        dialog_parent: QWidget,
        ask_yes_no: Callable[[str, str], bool] | None = None,
        show_warning: Callable[[str, str], None] | None = None,
    ) -> None:
        self._save_workflow = save_workflow
        self._local_history_workflow = local_history_workflow
        self._project_tree_action_coordinator = project_tree_action_coordinator
        self._dialog_parent = dialog_parent
        self._ask_yes_no = ask_yes_no or self._default_ask_yes_no
        self._show_warning = show_warning or self._default_show_warning

    def delete_paths(self, target_path: str) -> None:
        if not self._save_workflow.confirm_proceed_before_tree_delete([target_path]):
            return
        if not self._ask_yes_no(
            self._MOVE_TO_TRASH_TITLE,
            f"Move '{Path(target_path).name}' to trash?",
        ):
            return
        delete_snapshots = self._local_history_workflow.capture_delete_snapshots([target_path])
        error_message = self._project_tree_action_coordinator.handle_delete(target_path)
        if error_message is not None:
            self._show_warning(self._MOVE_TO_TRASH_TITLE, error_message)
            return
        self._local_history_workflow.record_transaction(
            delete_snapshots,
            source="delete",
            label=f"Delete '{Path(target_path).name}'",
        )

    def bulk_delete(self, paths: list[str]) -> None:
        if not self._save_workflow.confirm_proceed_before_tree_delete(
            paths,
            action_description=f"moving {len(paths)} items to trash",
        ):
            return
        names = "\n".join(f"  • {Path(path).name}" for path in paths)
        if not self._ask_yes_no(
            self._MOVE_TO_TRASH_TITLE,
            f"Move {len(paths)} items to trash?\n\n{names}",
        ):
            return
        delete_snapshots = self._local_history_workflow.capture_delete_snapshots(paths)
        failed, deleted_paths = self._project_tree_action_coordinator.handle_bulk_delete(paths)
        self._local_history_workflow.record_transaction(
            self._local_history_workflow.filter_snapshots_for_paths(delete_snapshots, deleted_paths),
            source="delete",
            label="Bulk delete from project tree",
        )
        if failed:
            self._show_warning(self._MOVE_TO_TRASH_TITLE, "\n".join(failed))

    def _default_ask_yes_no(self, title: str, text: str) -> bool:
        confirmation = QMessageBox.question(
            self._dialog_parent,
            title,
            text,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return confirmation == QMessageBox.Yes

    def _default_show_warning(self, title: str, text: str) -> None:
        QMessageBox.warning(self._dialog_parent, title, text)
