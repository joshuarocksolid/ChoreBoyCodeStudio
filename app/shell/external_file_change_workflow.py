"""External on-disk file change detection and reload decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, cast

from app.qt.QtWidgets import QDialog, QFileDialog, QMessageBox, QWidget

from app.editors.editor_manager import EditorManager
from app.editors.generated_file import generated_banner
from app.editors.editor_tab import DISK_CONFLICT_CHANGED, DISK_CONFLICT_MISSING
from app.shell.document_safety import DocumentCloseIntent, DocumentScope
from app.shell.disk_conflict_dialogs import (
    DiskChangedChoice,
    DiskChangedDialog,
    DiskCompareDialog,
    MissingFileDialog,
    MissingFileDialogChoice,
    StaleSaveChoice,
    StaleSaveDialog,
)
from app.shell.editor_sync_workflow import EditorDiskSyncSource, EditorSyncWorkflow
from app.shell.save_workflow import LocalHistoryPort, SaveWorkflowPort
from app.shell.shell_composition_context import MainWindowCompositionSurface
from app.qt.qt_compat import exec_qt


def _clean_generated_readonly(editor_widget: object, file_path: str, content: str) -> bool:
    """A clean tab still showing the generated banner reloads without a prompt."""
    probe = getattr(editor_widget, "isReadOnly", None)
    if not callable(probe) or not probe():
        return False
    return generated_banner(file_path, content) is not None


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
    """Ask what to do with a buffer whose file disappeared (Save As... is the default)."""
    dialog = MissingFileDialog(file_path, parent)
    exec_qt(dialog)
    choice = dialog.choice()
    if choice is MissingFileDialogChoice.SAVE_AS:
        destination = ask_save_as_path(parent, file_path)
        if not destination:
            return MissingFileAction(MissingFileChoice.KEEP)
        return MissingFileAction(MissingFileChoice.SAVE_AS, destination_path=destination)
    if choice is MissingFileDialogChoice.CLOSE_TAB:
        return MissingFileAction(MissingFileChoice.CLOSE)
    return MissingFileAction(MissingFileChoice.KEEP)


def present_stale_save_dialog(
    parent: QWidget,
    file_path: str,
    *,
    disk_mtime: float | None,
    buffer_is_dirty: bool,
) -> StaleSaveChoice:
    """Ask before a save replaces a file that changed on disk (Save My Version is the default)."""
    dialog = StaleSaveDialog(
        file_path,
        disk_changed_text=_describe_mtime(disk_mtime),
        buffer_is_dirty=buffer_is_dirty,
        parent=parent,
    )
    if exec_qt(dialog) != QDialog.Accepted:
        return StaleSaveChoice.CANCEL
    return dialog.choice()


def present_disk_changed_dialog(parent: QWidget, file_path: str, *, disk_mtime: float | None) -> DiskChangedChoice:
    """Ask what to do when a dirty buffer's file changed on disk (Keep My Version is the default)."""
    dialog = DiskChangedDialog(file_path, disk_changed_text=_describe_mtime(disk_mtime), parent=parent)
    exec_qt(dialog)
    return dialog.choice()


def ask_save_as_path(parent: QWidget, file_path: str) -> str | None:
    destination, _selected_filter = QFileDialog.getSaveFileName(parent, "Save As", file_path)
    return destination or None


def _describe_mtime(mtime: float | None) -> str:
    if mtime is None:
        return ""
    changed = datetime.fromtimestamp(mtime)
    clock = changed.strftime("%I:%M %p").lstrip("0")
    if changed.date() == datetime.now().date():
        return f"changed today {clock}"
    return f"changed {changed.strftime('%d %b %Y')} {clock}"


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

    def present_stale_save(self, file_path: str, *, disk_mtime: float | None, buffer_is_dirty: bool) -> StaleSaveChoice:
        ...

    def present_disk_changed(self, file_path: str, *, disk_mtime: float | None) -> DiskChangedChoice:
        ...

    def show_disk_compare(self, file_path: str, *, disk_text: str, buffer_text: str) -> None:
        ...

    def ask_save_as_path(self, file_path: str) -> str | None:
        ...


class MainWindowExternalFileChangeHost:
    """Host ports for ``ExternalFileChangeWorkflow`` backed by a MainWindow instance."""

    def __init__(self, window: MainWindowCompositionSurface) -> None:
        self._window = cast(Any, window)

    def editor_widget_for_path(self, file_path: str) -> object | None:
        return self._window._workspace_controller.widget_for_path(file_path)

    def surface_for_path(self, file_path: str) -> object | None:
        registry = getattr(self._window, "_tab_content_registry", None)
        if registry is None:
            return None
        return registry.surface_for_path(file_path)

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
        self._window._refresh_save_action_states()

    def present_stale_save(self, file_path: str, *, disk_mtime: float | None, buffer_is_dirty: bool) -> StaleSaveChoice:
        return present_stale_save_dialog(
            self._window,
            file_path,
            disk_mtime=disk_mtime,
            buffer_is_dirty=buffer_is_dirty,
        )

    def present_disk_changed(self, file_path: str, *, disk_mtime: float | None) -> DiskChangedChoice:
        return present_disk_changed_dialog(self._window, file_path, disk_mtime=disk_mtime)

    def show_disk_compare(self, file_path: str, *, disk_text: str, buffer_text: str) -> None:
        exec_qt(DiskCompareDialog(file_path, disk_text=disk_text, buffer_text=buffer_text, parent=self._window))

    def ask_save_as_path(self, file_path: str) -> str | None:
        return ask_save_as_path(self._window, file_path)


@dataclass(frozen=True)
class _DirtyReloadPlan:
    """Resolved reload intent for a dirty sourced tab with no text buffer."""

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
        # Paths with a conflict prompt open. The poller runs while a modal
        # prompt spins its event loop; it must not stack a second prompt.
        self._prompting: set[str] = set()

    def set_editor_manager(self, editor_manager: EditorManager) -> None:
        self._editor_manager = editor_manager
        self._editor_sync.set_editor_manager(editor_manager)

    def check_and_handle(self, file_path: str, *, force: bool = False) -> ExternalFileChangeOutcome:
        if file_path in self._prompting:
            return ExternalFileChangeOutcome.SKIPPED
        self._prompting.add(file_path)
        try:
            return self._check_and_handle(file_path, force=force)
        finally:
            self._prompting.discard(file_path)

    def _check_and_handle(self, file_path: str, *, force: bool) -> ExternalFileChangeOutcome:
        """Prompt when needed and reload ``file_path`` from disk.

        ``force`` is set by Save and Run so a remembered conflict prompts again.
        The poller leaves it false and does not repeat a prompt for the same mtime.
        """
        tab_state = self._editor_manager.get_tab(file_path)
        editor_widget = self._host.editor_widget_for_path(file_path)
        # A lazy sourced surface has no source editor in the widget dict; it is
        # reached through the provider registry instead (CONTRACTS.md §11.4).
        surface = getattr(self._host, "surface_for_path", lambda _p: None)(file_path)
        if tab_state is None or (editor_widget is None and surface is None):
            return ExternalFileChangeOutcome.SKIPPED
        # The New form tab is not a file. A missing-file prompt would offer to
        # save the sentinel path under cbcs/.
        if tab_state.virtual_tab:
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
            tab_state.mark_saved(last_known_mtime=current_mtime, saved_text=disk_content)
            self._host.refresh_save_action_states()
            self._host.refresh_conflict_presentation(file_path)
            return ExternalFileChangeOutcome.CONTENT_ALREADY_MATCHES

        needs_bar = getattr(surface, "external_change_needs_bar", None)
        offer_bar = getattr(surface, "offer_external_change", None)
        if surface is not None and callable(needs_bar) and callable(offer_bar) and needs_bar(disk_content):
            self._remember_conflict(file_path, DISK_CONFLICT_CHANGED, current_mtime)
            offer_bar(
                Path(file_path).name,
                lambda: self.reload_from_disk(file_path),
                lambda: None,
                lambda: self.compare_with_disk(file_path),
            )
            return ExternalFileChangeOutcome.DECLINED

        should_reload = False
        reload_disk_content = disk_content
        reload_mtime = current_mtime
        if tab_state.is_dirty and editor_widget is None and tab_state.content_source is not None:
            dirty_plan = self._resolve_sourced_dirty_reload(
                file_path,
                tab_state=tab_state,
                current_mtime=current_mtime,
                disk_content=disk_content,
            )
            if dirty_plan is None:
                return ExternalFileChangeOutcome.DECLINED
            if not dirty_plan.apply_reload:
                return ExternalFileChangeOutcome.CONTENT_ALREADY_MATCHES
            should_reload = True
            reload_disk_content = dirty_plan.disk_content
            reload_mtime = dirty_plan.current_mtime
        elif tab_state.is_dirty:
            if not self._dirty_buffer_takes_disk_version(file_path, current_mtime=current_mtime):
                self._remember_conflict(file_path, DISK_CONFLICT_CHANGED, current_mtime)
                return ExternalFileChangeOutcome.DECLINED
            self._local_history.record_checkpoint(
                file_path,
                tab_state.current_content,
                source="external_reload_discarded_buffer",
                label="Discarded buffer during disk reload",
            )
            should_reload = True
            # Compare... may have let the file change again; reload what is on disk now.
            refreshed_mtime = self._editor_manager.current_disk_mtime(file_path)
            refreshed_content = None if refreshed_mtime is None else self._read_disk_text(file_path)
            if refreshed_mtime is not None and refreshed_content is not None:
                reload_disk_content = refreshed_content
                reload_mtime = refreshed_mtime
        else:
            content = tab_state.current_content if isinstance(tab_state.current_content, str) else ""
            if _clean_generated_readonly(editor_widget, file_path, content):
                should_reload = True
            elif not self._host.confirm_clean_tab_reload():
                self._remember_conflict(file_path, DISK_CONFLICT_CHANGED, current_mtime)
                return ExternalFileChangeOutcome.DECLINED
            else:
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

    def _resolve_sourced_dirty_reload(
        self,
        file_path: str,
        *,
        tab_state: object,
        current_mtime: float,
        disk_content: str,
    ) -> _DirtyReloadPlan | None:
        """Three-way prompt for a provider tab that has no text editor to compare."""
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

    def _dirty_buffer_takes_disk_version(self, file_path: str, *, current_mtime: float) -> bool:
        """Ask about a dirty buffer whose file changed; True means Reload from Disk."""
        while True:
            choice = self._host.present_disk_changed(file_path, disk_mtime=current_mtime)
            if choice is DiskChangedChoice.COMPARE:
                self.compare_with_disk(file_path)
                continue
            return choice is DiskChangedChoice.RELOAD_FROM_DISK

    def resolve_before_save(self, file_path: str) -> str:
        if file_path in self._prompting:
            return "abort"
        self._prompting.add(file_path)
        try:
            return self._resolve_before_save(file_path)
        finally:
            self._prompting.discard(file_path)

    def _resolve_before_save(self, file_path: str) -> str:
        """Settle a disk conflict before Save writes ``file_path``.

        Returns ``"proceed"`` to write the buffer, ``"already_synced"`` when
        nothing is left to write, and ``"abort"`` to stop the save.
        """
        tab_state = self._editor_manager.get_tab(file_path)
        if tab_state is None:
            return "proceed"
        if tab_state.virtual_tab:
            return "abort"
        current_mtime = self._editor_manager.current_disk_mtime(file_path)
        if current_mtime is None:
            conflict = tab_state.disk_conflict
            if conflict is not None and conflict.kind == DISK_CONFLICT_MISSING:
                # The user already chose Keep Editing: saving puts the file back where it was.
                return "proceed"
            outcome = self._handle_missing_file(file_path, force=True)
            if outcome is ExternalFileChangeOutcome.CONTENT_ALREADY_MATCHES:
                return "already_synced"
            return "abort"
        disk_content = self._read_disk_text(file_path)
        if disk_content is None:
            return "abort"
        if disk_content == tab_state.current_content:
            tab_state.mark_saved(last_known_mtime=current_mtime)
            self._host.refresh_save_action_states()
            self._host.refresh_conflict_presentation(file_path)
            return "already_synced"
        while True:
            choice = self._host.present_stale_save(
                file_path,
                disk_mtime=current_mtime,
                buffer_is_dirty=tab_state.is_dirty,
            )
            if choice is StaleSaveChoice.COMPARE:
                self.compare_with_disk(file_path)
                continue
            if choice is StaleSaveChoice.SAVE_MY_VERSION:
                return "proceed"
            if choice is StaleSaveChoice.RELOAD_FROM_DISK:
                return "already_synced" if self.reload_from_disk(file_path) else "abort"
            self._remember_conflict(file_path, DISK_CONFLICT_CHANGED, current_mtime)
            return "abort"

    def reload_from_disk(self, file_path: str) -> bool:
        """Replace the buffer with the file on disk; the buffer goes to local history."""
        tab_state = self._editor_manager.get_tab(file_path)
        current_mtime = self._editor_manager.current_disk_mtime(file_path)
        disk_content = None if current_mtime is None else self._read_disk_text(file_path)
        if tab_state is None or disk_content is None:
            return False
        if tab_state.is_dirty:
            self._local_history.record_checkpoint(
                file_path,
                tab_state.current_content,
                source="external_reload_discarded_buffer",
                label="Discarded buffer during disk reload",
            )
        if not self._editor_sync.apply_disk_content(
            file_path,
            disk_content,
            source=EditorDiskSyncSource.EXTERNAL_RELOAD,
            last_known_mtime=current_mtime,
        ):
            return False
        self._local_history.record_checkpoint(
            file_path,
            disk_content,
            source="external_reload",
            label="Reloaded from disk after external change",
        )
        self._local_history.discard_drafts_for_paths([file_path])
        self._host.refresh_conflict_presentation(file_path)
        self._host.refresh_save_action_states()
        self._host.update_editor_status_for_path(file_path)
        if file_path.lower().endswith(".py"):
            self._host.render_lint_diagnostics_for_file(file_path, trigger="tab_change")
        return True

    def compare_with_disk(self, file_path: str) -> None:
        """Show the file on disk next to the buffer."""
        tab_state = self._editor_manager.get_tab(file_path)
        if tab_state is None:
            return
        disk_content = self._read_disk_text(file_path) or ""
        self._host.show_disk_compare(file_path, disk_text=disk_content, buffer_text=tab_state.current_content)

    def save_buffer_as(self, file_path: str) -> bool:
        """Save a buffer (usually one whose file went missing) under a new path."""
        if self._editor_manager.get_tab(file_path) is None:
            return False
        destination = self._host.ask_save_as_path(file_path)
        if not destination:
            return False
        if not self._host.save_missing_buffer_as(file_path, destination):
            return False
        self._clear_conflict(file_path, destination)
        return True

    @staticmethod
    def _read_disk_text(file_path: str) -> str | None:
        try:
            return Path(file_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
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
