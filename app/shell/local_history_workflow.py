"""Local-history, draft-autosave, and project-session shell workflow."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence

from PySide2.QtCore import QTimer
from PySide2.QtWidgets import QDialog, QMessageBox, QWidget

from app.core.models import LoadedProject
from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.editor_manager import EditorManager
from app.editors.editor_tab import EditorTabState
from app.persistence.autosave_store import AutosaveStore
from app.persistence.history_models import LocalHistoryFileSummary
from app.persistence.history_retention import LocalHistoryRetentionPolicy
from app.persistence.local_history_store import LocalHistoryStore
from app.persistence.local_history_writer import record_local_history_transaction
from app.shell.background_tasks import GeneralTaskScheduler
from app.shell.history_restore_picker import (
    HISTORY_RESTORE_ACTION_OPEN_TIMELINE,
    HISTORY_RESTORE_ACTION_RESTORE_LATEST,
    HistoryRestorePickerDialog,
)
from app.shell.local_history_dialog import DraftRecoveryDialog, LocalHistoryDialog
from app.shell.session_persistence import SessionFileState, SessionState, load_session_file, save_session_file


class _ConnectableTimeout(Protocol):
    def connect(self, slot: Callable[..., object]) -> object:
        ...


class _AutosaveTimer(Protocol):
    timeout: _ConnectableTimeout

    def setSingleShot(self, value: bool) -> None:
        ...

    def setInterval(self, value: int) -> None:
        ...

    def start(self) -> None:
        ...

    def stop(self) -> None:
        ...


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
        breakpoints_by_file: dict[str, set[int]] | None = None,
        breakpoint_specs_by_key: dict[tuple[str, int], Any] | None = None,
        refresh_breakpoints_list: Callable[[], None] | None = None,
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
        self._set_current_tab_index = set_current_tab_index
        self._show_status_message = show_status_message
        self._logger = logger
        self._background_tasks = background_tasks
        self._retention_policy = retention_policy
        self._ensure_breakpoint_spec = ensure_breakpoint_spec
        self._breakpoints_by_file = breakpoints_by_file
        self._breakpoint_specs_by_key = breakpoint_specs_by_key
        self._refresh_breakpoints_list = refresh_breakpoints_list
        self._history_restore_picker_dialog: HistoryRestorePickerDialog | None = None
        self._pending_autosave_payloads: dict[str, str] = {}
        self._autosave_timer = autosave_timer or QTimer(parent)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(500)
        self._autosave_timer.timeout.connect(self.flush_pending_autosaves)

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

    def set_retention_policy(self, retention_policy: LocalHistoryRetentionPolicy, *, apply_now: bool) -> None:
        self._retention_policy = retention_policy
        self._local_history_store.set_retention_policy(retention_policy, apply_now=apply_now)

    def persist_session_state(self, project_root: str | None = None) -> None:
        target_project_root = project_root
        if target_project_root is None:
            loaded_project = self._loaded_project()
            if loaded_project is None:
                return
            target_project_root = loaded_project.project_root

        open_files: list[SessionFileState] = []
        for file_path in self._editor_manager.open_paths():
            cursor_line = 1
            cursor_column = 1
            scroll_position = 0
            editor_widget = self._editor_widget_for_path(file_path)
            if editor_widget is not None:
                cursor = editor_widget.textCursor()
                cursor_line = cursor.blockNumber() + 1
                cursor_column = cursor.positionInBlock() + 1
                scroll_position = editor_widget.verticalScrollBar().value()
            breakpoints = set()
            if self._breakpoints_by_file is not None:
                breakpoints = self._breakpoints_by_file.get(file_path, set())
            open_files.append(
                SessionFileState(
                    file_path=file_path,
                    cursor_line=cursor_line,
                    cursor_column=cursor_column,
                    scroll_position=scroll_position,
                    breakpoints=tuple(sorted(breakpoints)),
                )
            )

        active_tab = self._editor_manager.active_tab()
        active_file_path = None if active_tab is None else active_tab.file_path
        session_state = SessionState(open_files=tuple(open_files), active_file_path=active_file_path)
        try:
            save_session_file(target_project_root, session_state)
        except Exception as exc:
            self._logger.warning("Failed to persist project session state for %s: %s", target_project_root, exc)

    def restore_session_state(self, project_root: str) -> None:
        try:
            session_state = load_session_file(project_root)
        except Exception as exc:
            self._logger.warning("Failed to load project session state for %s: %s", project_root, exc)
            return
        if session_state is None:
            return

        if self._breakpoints_by_file is not None:
            self._breakpoints_by_file.clear()
        if self._breakpoint_specs_by_key is not None:
            self._breakpoint_specs_by_key.clear()
        for file_state in session_state.open_files:
            if not file_state.breakpoints or self._breakpoints_by_file is None:
                continue
            self._breakpoints_by_file[file_state.file_path] = set(file_state.breakpoints)
            if self._ensure_breakpoint_spec is not None:
                for line_number in file_state.breakpoints:
                    self._ensure_breakpoint_spec(file_state.file_path, line_number)

        for file_state in session_state.open_files:
            if not self._open_file_in_editor(file_state.file_path):
                if self._breakpoints_by_file is not None:
                    self._breakpoints_by_file.pop(file_state.file_path, None)
                continue
            editor_widget = self._editor_widget_for_path(file_state.file_path)
            if editor_widget is None:
                continue
            self._restore_editor_cursor_and_scroll(editor_widget, file_state)

        if session_state.active_file_path is not None:
            active_index = self._tab_index_for_path(session_state.active_file_path)
            if active_index >= 0:
                self._set_current_tab_index(active_index)
        if self._refresh_breakpoints_list is not None:
            self._refresh_breakpoints_list()

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
        if draft_entry is None or draft_entry.content == tab_state.current_content:
            return

        dialog = DraftRecoveryDialog(
            file_name=tab_state.display_name,
            disk_text=tab_state.current_content,
            draft_text=draft_entry.content,
            parent=self._parent,
        )
        response = dialog.exec_()
        if response != QDialog.Accepted:
            if dialog.discard_draft:
                self._autosave_store.delete_draft(
                    tab_state.file_path,
                    project_id=project_id,
                    project_root=project_root,
                )
            return

        self._apply_content_to_open_tab(tab_state.file_path, draft_entry.content, editor_widget=editor_widget)

    def schedule_autosave(self, file_path: str, content: str) -> None:
        self._pending_autosave_payloads[file_path] = content
        self._autosave_timer.start()

    def discard_pending_autosave(self, file_path: str) -> None:
        self._pending_autosave_payloads.pop(file_path, None)

    def clear_pending_autosaves(self) -> None:
        self._pending_autosave_payloads.clear()

    def delete_draft(self, file_path: str) -> None:
        project_id, project_root = self.local_history_context_for_path(file_path)
        self._autosave_store.delete_draft(file_path, project_id=project_id, project_root=project_root)

    def flush_pending_autosaves(self) -> None:
        if not self._pending_autosave_payloads:
            return
        pending_items = list(self._pending_autosave_payloads.items())
        self._pending_autosave_payloads.clear()
        for file_path, content in pending_items:
            try:
                project_id, project_root = self.local_history_context_for_path(file_path)
                self._autosave_store.save_draft(
                    file_path,
                    content,
                    project_id=project_id,
                    project_root=project_root,
                )
            except OSError as exc:
                self._logger.warning("Autosave draft write failed for %s: %s", file_path, exc)

    def stop_autosave_timer(self) -> None:
        self._autosave_timer.stop()

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

    def _restore_editor_cursor_and_scroll(self, editor_widget: CodeEditorWidget, file_state: SessionFileState) -> None:
        target_line = max(1, file_state.cursor_line)
        target_column = max(1, file_state.cursor_column)
        document = editor_widget.document()
        block = document.findBlockByNumber(target_line - 1)
        if block.isValid():
            max_column_offset = max(0, block.length() - 1)
            column_offset = min(target_column - 1, max_column_offset)
            target_position = block.position() + column_offset
        else:
            target_position = max(0, document.characterCount() - 1)
        cursor = editor_widget.textCursor()
        cursor.setPosition(target_position)
        editor_widget.setTextCursor(cursor)
        scroll_position = max(0, file_state.scroll_position)
        QTimer.singleShot(0, lambda widget=editor_widget, value=scroll_position: widget.verticalScrollBar().setValue(value))
