"""Local-history, draft-autosave, and project-session shell workflow."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from PySide2.QtWidgets import QDialog, QMessageBox, QWidget

from app.shell.theme_tokens import ShellThemeTokens

from app.core.models import LoadedProject
from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.editor_manager import EditorManager
from app.editors.editor_tab import EditorTabState
from app.persistence.history_models import (
    DRAFT_RECOVERY_POLICY_PROMPT,
    DRAFT_RECOVERY_POLICY_RESTORE_SILENTLY,
    DRAFT_SOURCE_LIVE_DIRTY_BACKUP,
)
from app.persistence.autosave_store import AutosaveStore, DraftEntry
from app.persistence.history_models import LocalHistoryFileSummary
from app.persistence.history_retention import LocalHistoryRetentionPolicy
from app.persistence.local_history_store import LocalHistoryStore
from app.persistence.local_history_writer import record_local_history_transaction
from app.shell.background_tasks import GeneralTaskScheduler
from app.shell.draft_autosave_workflow import DraftAutosaveWorkflow, _AutosaveTimer
from app.shell.breakpoint_store import BreakpointStore
from app.shell.editor_session_workflow import EditorSessionWorkflow
from app.shell.session_persistence import SessionTreeState
from app.shell.history_restore_picker import (
    HISTORY_RESTORE_ACTION_OPEN_TIMELINE,
    HISTORY_RESTORE_ACTION_RESTORE_LATEST,
    HistoryRestorePickerDialog,
)
from app.shell.local_history_dialog import DraftRecoveryDialog, LocalHistoryDialog
from app.shell.recovery_center_dialog import (
    RECOVERY_ACTION_OPEN_TIMELINE,
    RECOVERY_ACTION_RESTORE_LATEST,
    RECOVERY_ENTRY_KIND_DRAFT,
    RECOVERY_ENTRY_KIND_HISTORY,
    RecoveryCenterDialog,
    RecoveryCenterEntry,
)


class LocalHistoryWorkflow:
    """Owns editor local-history, draft autosave, and project session state."""

    def __init__(
        self,
        *,
        parent: QWidget | None,
        local_history_store: LocalHistoryStore,
        autosave_store: AutosaveStore,
        loaded_project: Callable[[], LoadedProject | None],
        editor_manager: EditorManager,
        editor_widget_for_path: Callable[[str], CodeEditorWidget | None],
        open_file_in_editor: Callable[[str], bool],
        open_restored_history_buffer: Callable[[str, str], bool],
        apply_text_to_open_tab: Callable[[str, str], None],
        tab_index_for_path: Callable[[str], int],
        refresh_tab_presentation: Callable[[str], None],
        set_current_tab_index: Callable[[int], None],
        show_status_message: Callable[[str, int], None],
        logger: logging.Logger,
        background_tasks: GeneralTaskScheduler | None = None,
        autosave_timer: _AutosaveTimer | None = None,
        retention_policy: LocalHistoryRetentionPolicy | None = None,
        ensure_breakpoint_spec: Callable[[str, int], object] | None = None,
        breakpoint_store: BreakpointStore | None = None,
        refresh_breakpoints_list: Callable[[], None] | None = None,
        capture_tree_state: Callable[[], SessionTreeState | None] | None = None,
        restore_tree_state: Callable[[SessionTreeState], None] | None = None,
        reveal_tree_path: Callable[[str], None] | None = None,
        set_tree_reveal_suppressed: Callable[[bool], None] | None = None,
    ) -> None:
        self._parent = parent
        self._local_history_store = local_history_store
        self._autosave_store = autosave_store
        self._loaded_project = loaded_project
        self._editor_manager = editor_manager
        self._editor_widget_for_path = editor_widget_for_path
        self._open_file_in_editor = open_file_in_editor
        self._open_restored_history_buffer = open_restored_history_buffer
        self._apply_text_to_open_tab = apply_text_to_open_tab
        self._tab_index_for_path = tab_index_for_path
        self._refresh_tab_presentation = refresh_tab_presentation
        self._show_status_message = show_status_message
        self._logger = logger
        self._background_tasks = background_tasks
        self._retention_policy = retention_policy
        self._history_restore_picker_dialog: HistoryRestorePickerDialog | None = None
        self._recovery_center_dialog: RecoveryCenterDialog | None = None
        self._session_workflow = EditorSessionWorkflow(
            loaded_project=loaded_project,
            editor_manager=editor_manager,
            editor_widget_for_path=editor_widget_for_path,
            open_file_in_editor=open_file_in_editor,
            tab_index_for_path=tab_index_for_path,
            set_current_tab_index=set_current_tab_index,
            logger=logger,
            breakpoint_store=breakpoint_store,
            refresh_breakpoints_list=refresh_breakpoints_list,
            capture_tree_state=capture_tree_state,
            restore_tree_state=restore_tree_state,
            reveal_tree_path=reveal_tree_path,
            set_tree_reveal_suppressed=set_tree_reveal_suppressed,
        )
        self._draft_autosave = DraftAutosaveWorkflow(
            parent=parent,
            autosave_store=autosave_store,
            editor_manager=editor_manager,
            context_for_path=self.local_history_context_for_path,
            logger=logger,
            autosave_timer=autosave_timer,
        )

    @property
    def local_history_store(self) -> LocalHistoryStore:
        return self._local_history_store

    @property
    def autosave_store(self) -> AutosaveStore:
        return self._autosave_store

    @property
    def history_restore_picker_dialog(self) -> HistoryRestorePickerDialog | None:
        return self._history_restore_picker_dialog

    def set_editor_manager(self, editor_manager: EditorManager) -> None:
        self._editor_manager = editor_manager
        self._session_workflow.set_editor_manager(editor_manager)
        self._draft_autosave.set_editor_manager(editor_manager)

    def set_retention_policy(self, retention_policy: LocalHistoryRetentionPolicy, *, apply_now: bool) -> None:
        self._retention_policy = retention_policy
        self._local_history_store.set_retention_policy(retention_policy, apply_now=apply_now)

    def persist_session_state(self, project_root: str | None = None) -> None:
        self._session_workflow.persist_session_state(project_root)

    def restore_session_state(self, project_root: str) -> None:
        self._session_workflow.restore_session_state(project_root)

    def local_history_context_for_path(self, file_path: str) -> tuple[Optional[str], Optional[str]]:
        loaded_project = self._loaded_project()
        if loaded_project is None:
            return (None, None)
        metadata = getattr(loaded_project, "metadata", None)
        project_id = None if metadata is None else getattr(metadata, "project_id", None)
        normalized_file_path = Path(file_path).expanduser().resolve()
        project_root = Path(loaded_project.project_root).expanduser().resolve()
        try:
            normalized_file_path.relative_to(project_root)
        except ValueError:
            return (None, None)
        return (project_id, str(project_root))

    def record_checkpoint(
        self,
        file_path: str,
        content: str,
        *,
        source: str,
        label: str = "",
        transaction_id: Optional[str] = None,
    ) -> None:
        project_id, project_root = self.local_history_context_for_path(file_path)
        try:
            checkpoint = self._local_history_store.create_checkpoint(
                file_path,
                content,
                project_id=project_id,
                project_root=project_root,
                source=source,
                label=label,
                transaction_id=transaction_id,
            )
        except Exception:
            self._logger.warning("Local history checkpoint failed for %s", file_path, exc_info=True)
            return
        if checkpoint is not None:
            return

        skip_reason = self._local_history_store.checkpoint_skip_reason(
            file_path,
            content,
            project_root=project_root,
        )
        if skip_reason == "excluded":
            self._show_status_message(
                f"Local history skipped for {Path(file_path).name}: file matches a local-history exclude pattern.",
                5000,
            )
        elif skip_reason == "too_large":
            max_bytes = self._retention_policy.max_tracked_file_bytes if self._retention_policy is not None else 0
            self._show_status_message(
                (
                    f"Local history skipped for {Path(file_path).name}: "
                    f"file exceeds the {max_bytes} byte tracking limit."
                ),
                5000,
            )
        self._logger.info("Local history checkpoint skipped for %s", file_path)

    def record_transaction(
        self,
        payloads_by_path: Mapping[str, str],
        *,
        source: str,
        label: str,
    ) -> None:
        if not any(payload is not None for payload in payloads_by_path.values()):
            return
        loaded_project = self._loaded_project()
        project_id = (
            getattr(loaded_project.metadata, "project_id", None)
            if loaded_project is not None
            else None
        )
        project_root = loaded_project.project_root if loaded_project is not None else None
        record_local_history_transaction(
            self._local_history_store,
            payloads_by_path,
            project_id=project_id,
            project_root=project_root,
            source=source,
            label=label,
            logger=self._logger,
        )

    def capture_text_history_snapshots(self, target_paths: list[str]) -> dict[str, str]:
        snapshots: dict[str, str] = {}
        for target_path in target_paths:
            path = Path(target_path).expanduser().resolve()
            if path.is_file():
                candidate_paths = [path]
            elif path.is_dir():
                candidate_paths = sorted(child for child in path.rglob("*") if child.is_file())
            else:
                continue
            for candidate in candidate_paths:
                try:
                    snapshots[str(candidate.resolve())] = candidate.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
        return snapshots

    def capture_delete_snapshots(self, target_paths: list[str]) -> dict[str, str]:
        """Capture pre-delete history payloads, preferring live editor buffers when open."""
        snapshots = self.capture_text_history_snapshots(target_paths)
        for file_path in list(snapshots.keys()):
            tab_state = self._editor_manager.get_tab(file_path)
            if tab_state is not None:
                snapshots[file_path] = tab_state.current_content
        return snapshots

    def filter_snapshots_for_paths(
        self,
        snapshots_by_path: Mapping[str, str],
        accepted_paths: list[str],
    ) -> dict[str, str]:
        accepted_prefixes = [str(Path(path).expanduser().resolve()) for path in accepted_paths]
        filtered: dict[str, str] = {}
        for file_path, payload in snapshots_by_path.items():
            normalized_path = str(Path(file_path).expanduser().resolve())
            if any(
                normalized_path == prefix or normalized_path.startswith(f"{prefix}/")
                for prefix in accepted_prefixes
            ):
                filtered[normalized_path] = payload
        return filtered

    def record_deleted_path(self, deleted_path: str) -> None:
        project_id, project_root = self.local_history_context_for_path(deleted_path)
        if project_id is None:
            return
        try:
            self._local_history_store.record_deleted_path(
                project_id=project_id,
                project_root=project_root,
                deleted_path=deleted_path,
            )
        except Exception:
            self._logger.warning("Local history delete tracking failed for %s", deleted_path, exc_info=True)

    def remap_file_lineage(self, path_mapping: dict[str, str]) -> None:
        if not path_mapping:
            return
        first_path = next(iter(path_mapping.values()))
        project_id, project_root = self.local_history_context_for_path(first_path)
        if project_id is None:
            return
        try:
            self._local_history_store.remap_file_lineage(
                project_id=project_id,
                project_root=project_root,
                path_mapping=path_mapping,
            )
        except Exception:
            self._logger.warning("Local history path remap failed for %s", path_mapping, exc_info=True)

    def current_text_for_history_path(self, file_path: str) -> str:
        tab_state = self._editor_manager.get_tab(file_path)
        if tab_state is not None:
            return tab_state.current_content
        try:
            return Path(file_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""

    def restore_local_history_content_to_buffer(self, file_path: str, content: str) -> None:
        tab_state = self._editor_manager.get_tab(file_path)
        if tab_state is None:
            target_path = Path(file_path).expanduser().resolve()
            if target_path.exists():
                self._open_file_in_editor(file_path)
            else:
                self._open_restored_history_buffer(file_path, content)
            tab_state = self._editor_manager.get_tab(file_path)
        if tab_state is None:
            QMessageBox.warning(self._parent, "Local History", f"Could not open {Path(file_path).name} for restore.")
            return
        self._apply_content_to_open_tab(file_path, content)

    def show_local_history_for_entry(self, summary: LocalHistoryFileSummary) -> None:
        self.show_local_history_for_path(
            summary.file_path,
            project_id=summary.project_id,
            project_root=summary.project_root,
            file_name=Path(summary.display_path or summary.file_path).name,
        )

    def show_local_history_for_path(
        self,
        file_path: str,
        *,
        project_id: Optional[str] = None,
        project_root: Optional[str] = None,
        file_name: Optional[str] = None,
    ) -> None:
        if project_id is None and project_root is None:
            project_id, project_root = self.local_history_context_for_path(file_path)
        checkpoints = self._local_history_store.list_checkpoints(
            file_path,
            project_id=project_id,
            project_root=project_root,
            include_deleted=True,
        )
        if not checkpoints:
            QMessageBox.information(
                self._parent,
                "Local History",
                "No local-history entries are available for this file yet.",
            )
            return
        dialog = LocalHistoryDialog(
            file_name=file_name or Path(file_path).name,
            checkpoints=checkpoints,
            current_text=self.current_text_for_history_path(file_path),
            checkpoint_content_loader=self._local_history_store.load_checkpoint_content,
            restore_to_buffer=lambda content: self.restore_local_history_content_to_buffer(file_path, content),
            tokens=self._resolve_parent_tokens(),
            parent=self._parent,
        )
        dialog.exec_()

    def open_global_history(self) -> None:
        if self._background_tasks is None:
            summaries = self._local_history_store.list_global_history_files()
            self._open_global_history_picker(summaries)
            return

        def task(cancel_event):  # type: ignore[no-untyped-def]
            summaries = self._local_history_store.list_global_history_files()
            if cancel_event.is_set():
                return None
            return summaries

        def on_success(payload: object) -> None:
            if not isinstance(payload, list):
                return
            self._open_global_history_picker(payload)

        def on_error(exc: Exception) -> None:
            self._logger.warning("Failed to load global history entries: %s", exc)
            QMessageBox.warning(self._parent, "Global History", f"Could not load global history:\n{exc}")

        self._background_tasks.run(
            key="global_history_list",
            task=task,
            on_success=on_success,
            on_error=on_error,
        )

    def maybe_restore_draft(self, tab_state: EditorTabState, editor_widget: CodeEditorWidget) -> None:
        project_id, project_root = self.local_history_context_for_path(tab_state.file_path)
        draft_entry = self._autosave_store.load_draft(
            tab_state.file_path,
            project_id=project_id,
            project_root=project_root,
        )
        if draft_entry is None:
            return
        if draft_entry.recovery_policy == DRAFT_RECOVERY_POLICY_RESTORE_SILENTLY:
            if draft_entry.content == tab_state.current_content:
                return
            self._apply_content_to_open_tab(tab_state.file_path, draft_entry.content, editor_widget=editor_widget)
            self._show_status_message(
                f"Restored unsaved changes for {tab_state.display_name}. Save to update the file on disk.",
                6000,
            )
            return

        self._offer_draft_recovery(
            draft_entry,
            file_name=tab_state.display_name,
            disk_text=tab_state.original_content or tab_state.current_content,
            buffer_text=tab_state.current_content,
            editor_widget=editor_widget,
            project_id=project_id,
            project_root=project_root,
        )

    def schedule_autosave(self, file_path: str, content: str) -> None:
        self._draft_autosave.schedule_autosave(file_path, content)

    def discard_pending_autosave(self, file_path: str) -> None:
        self._draft_autosave.discard_pending_autosave(file_path)

    def discard_drafts_for_paths(self, file_paths: Sequence[str]) -> None:
        self._draft_autosave.discard_drafts_for_paths(file_paths)

    def keep_drafts_for_paths(self, file_paths: Sequence[str]) -> None:
        self._draft_autosave.keep_drafts_for_paths(file_paths)

    def clear_pending_autosaves(self) -> None:
        self._draft_autosave.clear_pending_autosaves()

    def delete_draft(self, file_path: str) -> None:
        self._draft_autosave.delete_draft(file_path)

    def flush_pending_autosaves(
        self,
        file_paths: Sequence[str] | None = None,
        *,
        recovery_policy: str = DRAFT_RECOVERY_POLICY_PROMPT,
        source: str = DRAFT_SOURCE_LIVE_DIRTY_BACKUP,
    ) -> None:
        self._draft_autosave.flush_pending_autosaves(
            file_paths,
            recovery_policy=recovery_policy,
            source=source,
        )

    def stop_autosave_timer(self) -> None:
        self._draft_autosave.stop_autosave_timer()

    def _resolve_parent_tokens(self) -> ShellThemeTokens | None:
        accessor = getattr(self._parent, "current_theme_tokens", None)
        if not callable(accessor):
            return None
        try:
            resolved = accessor()
        except Exception:  # pragma: no cover - defensive: parent in shutdown
            return None
        if isinstance(resolved, ShellThemeTokens):
            return resolved
        return None

    def _apply_content_to_open_tab(
        self,
        file_path: str,
        content: str,
        *,
        editor_widget: CodeEditorWidget | None = None,
    ) -> None:
        if editor_widget is not None:
            editor_widget.replace_document_text(content)
        else:
            self._apply_text_to_open_tab(file_path, content)
        updated_tab = self._editor_manager.update_tab_content(file_path, content)
        tab_index = self._tab_index_for_path(file_path)
        if tab_index >= 0:
            self._refresh_tab_presentation(updated_tab.file_path)
        self.schedule_autosave(updated_tab.file_path, updated_tab.current_content)

    def _open_global_history_picker(self, summaries: Sequence[object]) -> None:
        if not summaries:
            QMessageBox.information(
                self._parent,
                "Global History",
                "No saved local-history entries are available yet.",
            )
            return

        if self._history_restore_picker_dialog is None:
            self._history_restore_picker_dialog = HistoryRestorePickerDialog(self._parent)

        entries = [entry for entry in summaries if isinstance(entry, LocalHistoryFileSummary)]
        self._history_restore_picker_dialog.set_entries(entries)
        result = self._history_restore_picker_dialog.open_dialog()
        if result != QDialog.Accepted:
            return

        selected_entry = self._history_restore_picker_dialog.selected_entry()
        if selected_entry is None:
            return

        if self._history_restore_picker_dialog.requested_action == HISTORY_RESTORE_ACTION_RESTORE_LATEST:
            latest_content = self._local_history_store.load_checkpoint_content(selected_entry.latest_revision_id)
            if latest_content is None:
                QMessageBox.warning(self._parent, "Global History", "Could not load the latest saved revision.")
                return
            self.restore_local_history_content_to_buffer(selected_entry.file_path, latest_content)
            return

        if self._history_restore_picker_dialog.requested_action == HISTORY_RESTORE_ACTION_OPEN_TIMELINE:
            self.show_local_history_for_entry(selected_entry)

    def open_recovery_center(self) -> None:
        history_summaries = self._local_history_store.list_global_history_files()
        draft_entries = self._autosave_store.list_drafts()
        entries = self._recovery_center_entries(history_summaries, draft_entries)
        if not entries:
            QMessageBox.information(
                self._parent,
                "Recovery Center",
                "No recovery drafts or saved local-history entries are available yet.",
            )
            return
        if self._recovery_center_dialog is None:
            self._recovery_center_dialog = RecoveryCenterDialog(self._parent)
        self._recovery_center_dialog.set_entries(entries)
        result = self._recovery_center_dialog.open_dialog()
        if result != QDialog.Accepted:
            return
        selected_entry = self._recovery_center_dialog.selected_entry()
        if selected_entry is None:
            return
        if selected_entry.kind == RECOVERY_ENTRY_KIND_DRAFT:
            draft_entry = next(
                (draft for draft in draft_entries if draft.file_path == selected_entry.file_path),
                None,
            )
            if draft_entry is not None:
                self._review_draft_entry(draft_entry)
            return
        selected_summary = next(
            (summary for summary in history_summaries if summary.file_key == selected_entry.file_key),
            None,
        )
        if selected_summary is None:
            return
        if self._recovery_center_dialog.requested_action == RECOVERY_ACTION_RESTORE_LATEST:
            latest_content = self._local_history_store.load_checkpoint_content(selected_summary.latest_revision_id)
            if latest_content is None:
                QMessageBox.warning(self._parent, "Recovery Center", "Could not load the latest saved revision.")
                return
            self.restore_local_history_content_to_buffer(selected_summary.file_path, latest_content)
        elif self._recovery_center_dialog.requested_action == RECOVERY_ACTION_OPEN_TIMELINE:
            self.show_local_history_for_entry(selected_summary)

    def _review_draft_entry(self, draft_entry: DraftEntry) -> None:
        tab_state = self._editor_manager.get_tab(draft_entry.file_path)
        project_id, project_root = self.local_history_context_for_path(draft_entry.file_path)
        if tab_state is not None:
            file_name = tab_state.display_name
            disk_text = tab_state.original_content or tab_state.current_content
            buffer_text = tab_state.current_content
            editor_widget = self._editor_widget_for_path(draft_entry.file_path)
        else:
            file_name = Path(draft_entry.file_path).name
            try:
                disk_text = Path(draft_entry.file_path).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                disk_text = ""
            buffer_text = disk_text
            editor_widget = None
        self._offer_draft_recovery(
            draft_entry,
            file_name=file_name,
            disk_text=disk_text,
            buffer_text=buffer_text,
            editor_widget=editor_widget,
            project_id=project_id,
            project_root=project_root,
            restore_closed_file=True,
        )

    def _offer_draft_recovery(
        self,
        draft_entry: DraftEntry,
        *,
        file_name: str,
        disk_text: str,
        buffer_text: str,
        editor_widget: CodeEditorWidget | None,
        project_id: str | None,
        project_root: str | None,
        restore_closed_file: bool = False,
    ) -> None:
        if draft_entry.content == buffer_text:
            return
        dialog = DraftRecoveryDialog(
            file_name=file_name,
            disk_text=disk_text,
            draft_text=draft_entry.content,
            tokens=self._resolve_parent_tokens(),
            disk_saved_at=_resolve_disk_saved_at_iso(draft_entry.file_path),
            draft_saved_at=draft_entry.saved_at,
            parent=self._parent,
        )
        response = dialog.exec_()
        if response == QDialog.Accepted:
            if restore_closed_file or editor_widget is None:
                self.restore_local_history_content_to_buffer(draft_entry.file_path, draft_entry.content)
            else:
                self._apply_content_to_open_tab(
                    draft_entry.file_path,
                    draft_entry.content,
                    editor_widget=editor_widget,
                )
        elif dialog.discard_draft:
            self._autosave_store.delete_draft(
                draft_entry.file_path,
                project_id=project_id,
                project_root=project_root,
            )

    def _recovery_center_entries(
        self,
        history_summaries: Sequence[LocalHistoryFileSummary],
        draft_entries: Sequence[DraftEntry],
    ) -> list[RecoveryCenterEntry]:
        entries: list[RecoveryCenterEntry] = []
        for draft in draft_entries:
            entries.append(
                RecoveryCenterEntry(
                    kind=RECOVERY_ENTRY_KIND_DRAFT,
                    file_key=draft.file_path,
                    file_path=draft.file_path,
                    display_path=Path(draft.file_path).name,
                    timestamp=draft.saved_at,
                    label=draft.source.replace("_", " "),
                    status="Unsaved Draft",
                )
            )
        for summary in history_summaries:
            entries.append(
                RecoveryCenterEntry(
                    kind=RECOVERY_ENTRY_KIND_HISTORY,
                    file_key=summary.file_key,
                    file_path=summary.file_path,
                    display_path=summary.display_path,
                    timestamp=summary.latest_checkpoint_at,
                    label=summary.latest_label or summary.latest_source.replace("_", " "),
                    status="Deleted" if summary.is_deleted else "Saved History",
                )
            )
        return sorted(entries, key=lambda entry: (entry.timestamp, entry.display_path), reverse=True)

def _resolve_disk_saved_at_iso(file_path: str) -> Optional[str]:
    """Return ``file_path``'s mtime as an ISO timestamp, or ``None`` on failure."""
    try:
        stat = Path(file_path).stat()
    except OSError:
        return None
    return datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).astimezone().isoformat()
