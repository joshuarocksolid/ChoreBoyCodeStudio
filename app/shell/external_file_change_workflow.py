"""External on-disk file change detection and reload decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol, Sequence

from app.editors.editor_manager import EditorManager
from app.shell.document_safety import DocumentCloseIntent, DocumentSafetyDecision, DocumentScope
from app.shell.editor_sync_workflow import EditorDiskSyncSource, EditorSyncWorkflow


class ExternalFileChangeOutcome(str, Enum):
    """Result of handling a stale open file path."""

    SKIPPED = "skipped"
    CONTENT_ALREADY_MATCHES = "content_already_matches"
    DECLINED = "declined"
    CANCELLED = "cancelled"
    RELOADED = "reloaded"


class SaveWorkflowPort(Protocol):
    """Minimal save-workflow surface for external reload prompts."""

    def request_unsaved_changes_decision(
        self,
        action_description: str,
        *,
        scope: DocumentScope,
        allow_keep_for_next_launch: bool,
        dirty_buffers: tuple[object, ...] | None = None,
    ) -> DocumentSafetyDecision:
        ...

    def apply_unsaved_changes_decision(self, decision: DocumentSafetyDecision) -> bool:
        ...


class LocalHistoryPort(Protocol):
    """Minimal local-history surface for external reload checkpoints."""

    def record_checkpoint(
        self,
        file_path: str,
        content: str,
        *,
        source: str,
        label: str = "",
    ) -> None:
        ...

    def discard_drafts_for_paths(self, file_paths: Sequence[str]) -> None:
        ...


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

    def check_and_handle(self, file_path: str) -> ExternalFileChangeOutcome:
        """Prompt when needed and reload ``file_path`` from disk."""
        tab_state = self._editor_manager.get_tab(file_path)
        editor_widget = self._host.editor_widget_for_path(file_path)
        if tab_state is None or editor_widget is None:
            return ExternalFileChangeOutcome.SKIPPED

        current_mtime = self._editor_manager.current_disk_mtime(file_path)
        if current_mtime is None or current_mtime == tab_state.last_known_mtime:
            return ExternalFileChangeOutcome.SKIPPED

        try:
            disk_content = Path(file_path).read_text(encoding="utf-8")
        except OSError:
            self._editor_manager.acknowledge_disk_mtime(file_path, current_mtime)
            return ExternalFileChangeOutcome.SKIPPED

        if disk_content == tab_state.current_content:
            tab_state.mark_saved(last_known_mtime=current_mtime)
            self._host.refresh_save_action_states()
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
                self._editor_manager.acknowledge_disk_mtime(file_path, current_mtime)
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
            self._editor_manager.acknowledge_disk_mtime(file_path, current_mtime)
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

        self._editor_manager.acknowledge_disk_mtime(file_path, current_mtime)
        return None
