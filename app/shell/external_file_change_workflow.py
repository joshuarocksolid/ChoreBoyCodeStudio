"""External on-disk file change detection and reload decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, cast

from PySide2.QtWidgets import QFileDialog, QMessageBox, QWidget

from app.editors.editor_manager import EditorManager
from app.editors.editor_tab import DISK_CONFLICT_CHANGED, DISK_CONFLICT_MISSING
from app.shell.document_safety import DocumentCloseIntent, DocumentSafetyDecision, DocumentScope
from app.shell.editor_sync_workflow import EditorDiskSyncSource, EditorSyncWorkflow
from app.shell.save_workflow import LocalHistoryPort, SaveWorkflowPort
from app.shell.shell_composition_context import MainWindowCompositionSurface


class ExternalFileChangeOutcome(str, Enum):
    """Result of handling a stale open file path."""

    SKIPPED = "skipped"
    CONTENT_ALREADY_MATCHES = "content_already_matches"
    DECLINED = "declined"
    CANCELLED = "cancelled"
    RELOADED = "reloaded"


class MissingFileChoice(str, Enum):
    """User choice when an open buffer's file is gone from disk."""

    KEEP = "keep"
    SAVE_AS = "save_as"
    CLOSE = "close"


@dataclass(frozen=True)
class MissingFileAction:
    """Result of the missing-file presentation."""

    choice: MissingFileChoice
    destination_path: str | None = None


def present_missing_file_dialog(parent: QWidget, file_path: str) -> MissingFileAction:
    """Isolated presentation for a buffer whose file disappeared."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle("File missing")
    box.setText(f"{Path(file_path).name} is no longer on disk.")
    box.setInformativeText("Keep editing, save the buffer somewhere else, or close the tab.")
    box.addButton("Keep editing", QMessageBox.AcceptRole)
    save_as_button = box.addButton("Save As…", QMessageBox.ActionRole)
    close_button = box.addButton("Close tab", QMessageBox.RejectRole)
    box.exec_()
    clicked = box.clickedButton()
    if clicked is save_as_button:
        destination, _selected_filter = QFileDialog.getSaveFileName(parent, "Save As", file_path)
        if not destination:
            return MissingFileAction(MissingFileChoice.KEEP)
        return MissingFileAction(MissingFileChoice.SAVE_AS, destination_path=destination)
    if clicked is close_button:
        return MissingFileAction(MissingFileChoice.CLOSE)
    return MissingFileAction(MissingFileChoice.KEEP)


class ExternalFileChangeHostPorts(Protocol):
    """Host callbacks for external file reload orchestration."""

    def editor_widget_for_path(self, file_path: str) -> object | None:
        ...

    def confirm_clean_tab_reload(self) -> bool:
        ...

    def refresh_save_action_states(self) -> None:
        ...

    def update_editor_status_for_path(self, file_path: str) -> None:
        ...

    def render_lint_diagnostics_for_file(self, file_path: str, *, trigger: str) -> None:
        ...

    def present_missing_file(self, file_path: str) -> MissingFileAction:
        ...

    def save_missing_buffer_as(self, file_path: str, destination_path: str) -> bool:
        ...

    def close_missing_tab(self, file_path: str) -> None:
        ...

    def refresh_conflict_presentation(self, file_path: str) -> None:
        ...


class MainWindowExternalFileChangeHost:
    """Host ports for ``ExternalFileChangeWorkflow`` backed by a MainWindow instance."""

    def __init__(self, window: MainWindowCompositionSurface) -> None:
        self._window = cast(Any, window)

    def editor_widget_for_path(self, file_path: str) -> object | None:
        return self._window._workspace_controller.widget_for_path(file_path)

    def confirm_clean_tab_reload(self) -> bool:
        choice = QMessageBox.question(
            self._window,
            "External file change detected",
            "This file changed on disk. Reload the file from disk?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        return choice == QMessageBox.Yes

    def refresh_save_action_states(self) -> None:
        self._window._refresh_save_action_states()

    def update_editor_status_for_path(self, file_path: str) -> None:
        self._window._editor_tab_workflow.update_editor_status_for_path(file_path)

    def render_lint_diagnostics_for_file(self, file_path: str, *, trigger: str) -> None:
        self._window._lint_workflow.render_diagnostics_for_file(file_path, trigger=trigger)

    def present_missing_file(self, file_path: str) -> MissingFileAction:
        return present_missing_file_dialog(self._window, file_path)

    def save_missing_buffer_as(self, file_path: str, destination_path: str) -> bool:
        manager = self._window._editor_manager
        source = str(Path(file_path).expanduser().resolve())
        destination = str(Path(destination_path).expanduser().resolve())
        source_tab = manager.get_tab(source)
        existing = manager.get_tab(destination)
        if (
            source_tab is not None
            and existing is not None
            and existing.buffer_id != source_tab.buffer_id
        ):
            return False
        self._window._project_tree_action_coordinator.apply_path_move_updates(
            source,
            destination,
            rewrite_imports=False,
        )
        return bool(self._window._save_workflow.save_tab(destination, check_stale_disk=False))

    def close_missing_tab(self, file_path: str) -> None:
        self._window._editor_tab_workflow.close_tab_discarding_edits(file_path)

    def refresh_conflict_presentation(self, file_path: str) -> None:
        self._window._editor_tab_workflow.refresh_tab_presentation(file_path)


@dataclass(frozen=True)
class _DirtyReloadPlan:
    """Resolved reload intent for a dirty tab blocking external reload."""

    apply_reload: bool
    disk_content: str
    current_mtime: float


class ExternalFileChangeWorkflow:
    """Owns stale-file detection prompts and disk reload application."""

    _RELOAD_ACTION_DESCRIPTION = "reloading this file from disk after an external change"

    def __init__(
        self,
        *,
        editor_manager: EditorManager,
        editor_sync: EditorSyncWorkflow,
        save_workflow: SaveWorkflowPort,
        local_history: LocalHistoryPort,
        host: ExternalFileChangeHostPorts,
    ) -> None:
        self._editor_manager = editor_manager
        self._editor_sync = editor_sync
        self._save_workflow = save_workflow
        self._local_history = local_history
        self._host = host

    def set_editor_manager(self, editor_manager: EditorManager) -> None:
        self._editor_manager = editor_manager
        self._editor_sync.set_editor_manager(editor_manager)

    def check_and_handle(self, file_path: str, *, force: bool = False) -> ExternalFileChangeOutcome:
        """Prompt when needed and reload ``file_path`` from disk.

        ``force`` is set by Save and Run so a remembered conflict prompts again.
        The poller leaves it false and does not repeat a prompt for the same mtime.
        """
        tab_state = self._editor_manager.get_tab(file_path)
        editor_widget = self._host.editor_widget_for_path(file_path)
        if tab_state is None or editor_widget is None:
            return ExternalFileChangeOutcome.SKIPPED

        current_mtime = self._editor_manager.current_disk_mtime(file_path)
        if current_mtime is None:
            return self._handle_missing_file(file_path, force=force)
        if self._same_changed_conflict(tab_state, current_mtime) and not force:
            return ExternalFileChangeOutcome.SKIPPED
        if current_mtime == tab_state.last_known_mtime:
            return ExternalFileChangeOutcome.SKIPPED

        try:
            disk_content = Path(file_path).read_text(encoding="utf-8")
        except OSError:
            return ExternalFileChangeOutcome.SKIPPED

        if disk_content == tab_state.current_content:
            tab_state.mark_saved(last_known_mtime=current_mtime)
            self._host.refresh_save_action_states()
            self._host.refresh_conflict_presentation(file_path)
            return ExternalFileChangeOutcome.CONTENT_ALREADY_MATCHES

        should_reload = False
        reload_disk_content = disk_content
        reload_mtime = current_mtime
        if tab_state.is_dirty:
            dirty_plan = self._resolve_dirty_reload(
                file_path,
                tab_state=tab_state,
                current_mtime=current_mtime,
                disk_content=disk_content,
            )
            if dirty_plan is None:
                return ExternalFileChangeOutcome.CANCELLED
            if not dirty_plan.apply_reload:
                return ExternalFileChangeOutcome.CONTENT_ALREADY_MATCHES
            should_reload = True
            reload_disk_content = dirty_plan.disk_content
            reload_mtime = dirty_plan.current_mtime
        else:
            if not self._host.confirm_clean_tab_reload():
                self._remember_conflict(file_path, DISK_CONFLICT_CHANGED, current_mtime)
                return ExternalFileChangeOutcome.DECLINED
            should_reload = True

        if not should_reload:
            return ExternalFileChangeOutcome.DECLINED

        if not self._editor_sync.apply_disk_content(
            file_path,
            reload_disk_content,
            source=EditorDiskSyncSource.EXTERNAL_RELOAD,
            last_known_mtime=reload_mtime,
        ):
            return ExternalFileChangeOutcome.SKIPPED

        self._local_history.record_checkpoint(
            file_path,
            reload_disk_content,
            source="external_reload",
            label="Reloaded from disk after external change",
        )
        self._local_history.discard_drafts_for_paths([file_path])
        self._host.refresh_save_action_states()
        self._host.update_editor_status_for_path(file_path)
        if file_path.lower().endswith(".py"):
            self._host.render_lint_diagnostics_for_file(file_path, trigger="tab_change")
        return ExternalFileChangeOutcome.RELOADED

    def _resolve_dirty_reload(
        self,
        file_path: str,
        *,
        tab_state: object,
        current_mtime: float,
        disk_content: str,
    ) -> _DirtyReloadPlan | None:
        decision = self._save_workflow.request_unsaved_changes_decision(
            self._RELOAD_ACTION_DESCRIPTION,
            scope=DocumentScope.EXTERNAL_RELOAD,
            allow_keep_for_next_launch=False,
            dirty_buffers=(tab_state,),
        )
        if decision.intent is DocumentCloseIntent.CANCEL:
            self._remember_conflict(file_path, DISK_CONFLICT_CHANGED, current_mtime)
            return None

        if decision.intent is DocumentCloseIntent.SAVE:
            if not self._save_workflow.apply_unsaved_changes_decision(decision):
                return None
            try:
                saved_disk_content = Path(file_path).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                return None
            saved_mtime = Path(file_path).stat().st_mtime
            refreshed_tab = self._editor_manager.get_tab(file_path)
            if refreshed_tab is not None and saved_disk_content == refreshed_tab.current_content:
                refreshed_tab.mark_saved(last_known_mtime=saved_mtime)
                self._host.refresh_save_action_states()
                return _DirtyReloadPlan(
                    apply_reload=False,
                    disk_content=saved_disk_content,
                    current_mtime=saved_mtime,
                )
            return _DirtyReloadPlan(
                apply_reload=True,
                disk_content=saved_disk_content,
                current_mtime=saved_mtime,
            )

        if decision.intent is DocumentCloseIntent.DISCARD:
            buffer_content = str(getattr(tab_state, "current_content", ""))
            self._local_history.record_checkpoint(
                file_path,
                buffer_content,
                source="external_reload_discarded_buffer",
                label="Discarded buffer during disk reload",
            )
            return _DirtyReloadPlan(
                apply_reload=True,
                disk_content=disk_content,
                current_mtime=current_mtime,
            )

        if decision.intent is DocumentCloseIntent.PROCEED:
            return _DirtyReloadPlan(
                apply_reload=True,
                disk_content=disk_content,
                current_mtime=current_mtime,
            )

        self._remember_conflict(file_path, DISK_CONFLICT_CHANGED, current_mtime)
        return None

    def _handle_missing_file(self, file_path: str, *, force: bool) -> ExternalFileChangeOutcome:
        tab_state = self._editor_manager.get_tab(file_path)
        if tab_state is None:
            return ExternalFileChangeOutcome.SKIPPED
        conflict = tab_state.disk_conflict
        if not force and conflict is not None and conflict.kind == DISK_CONFLICT_MISSING:
            return ExternalFileChangeOutcome.SKIPPED

        action = self._host.present_missing_file(file_path)
        if action.choice is MissingFileChoice.SAVE_AS and action.destination_path:
            if self._host.save_missing_buffer_as(file_path, action.destination_path):
                self._clear_conflict(file_path, action.destination_path)
                return ExternalFileChangeOutcome.CONTENT_ALREADY_MATCHES
            self._remember_conflict(file_path, DISK_CONFLICT_MISSING, None)
            return ExternalFileChangeOutcome.CANCELLED
        if action.choice is MissingFileChoice.CLOSE:
            self._host.close_missing_tab(file_path)
            return ExternalFileChangeOutcome.CANCELLED
        self._remember_conflict(file_path, DISK_CONFLICT_MISSING, None)
        return ExternalFileChangeOutcome.DECLINED

    def _remember_conflict(self, file_path: str, kind: str, conflict_mtime: float | None) -> None:
        tab_state = self._editor_manager.get_tab(file_path)
        if tab_state is None:
            return
        tab_state.set_disk_conflict(kind, conflict_mtime)
        self._host.refresh_conflict_presentation(file_path)

    def _clear_conflict(self, file_path: str, destination_path: str) -> None:
        tab_state = self._editor_manager.get_tab(destination_path)
        if tab_state is None:
            tab_state = self._editor_manager.get_tab(file_path)
        if tab_state is None:
            return
        tab_state.clear_disk_conflict()
        self._host.refresh_conflict_presentation(tab_state.file_path)

    @staticmethod
    def _same_changed_conflict(tab_state: object, current_mtime: float) -> bool:
        conflict = getattr(tab_state, "disk_conflict", None)
        if conflict is None or getattr(conflict, "kind", None) != DISK_CONFLICT_CHANGED:
            return False
        return getattr(conflict, "conflict_mtime", None) == current_mtime
