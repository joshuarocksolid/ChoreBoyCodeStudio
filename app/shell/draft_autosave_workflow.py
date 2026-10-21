"""Draft autosave scheduling and flush for dirty editor buffers."""

from __future__ import annotations

import logging
from typing import Callable, Optional, Protocol, Sequence

from app.qt.QtCore import QTimer
from app.qt.QtWidgets import QWidget

from app.editors.editor_manager import EditorManager
from app.persistence.autosave_store import AutosaveStore
from app.persistence.history_models import (
    DRAFT_RECOVERY_POLICY_PROMPT,
    DRAFT_RECOVERY_POLICY_RESTORE_SILENTLY,
    DRAFT_SOURCE_KEPT_ON_EXIT,
    DRAFT_SOURCE_LIVE_DIRTY_BACKUP,
)


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


class DraftAutosaveWorkflow:
    """Owns debounced draft autosave timer and pending flush.

    Pending payloads are keyed by buffer id and written to the buffer's path
    at flush time; persisted drafts stay path-keyed in ``AutosaveStore``.
    """

    def __init__(
        self,
        *,
        parent: QWidget | None,
        autosave_store: AutosaveStore,
        editor_manager: EditorManager,
        context_for_path: Callable[[str], tuple[Optional[str], Optional[str]]],
        logger: logging.Logger,
        autosave_timer: _AutosaveTimer | None = None,
    ) -> None:
        self._autosave_store = autosave_store
        self._editor_manager = editor_manager
        self._context_for_path = context_for_path
        self._logger = logger
        self._pending_autosave_payloads: dict[str, str] = {}
        self._autosave_timer = autosave_timer or QTimer(parent)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(500)
        self._autosave_timer.timeout.connect(self.flush_pending_autosaves)

    def set_editor_manager(self, editor_manager: EditorManager) -> None:
        self._editor_manager = editor_manager

    def schedule_autosave(self, file_path: str, content: str) -> None:
        tab_state = self._editor_manager.get_tab(file_path)
        if tab_state is None:
            return
        self._pending_autosave_payloads[tab_state.buffer_id] = content
        self._autosave_timer.start()

    def discard_pending_autosave(self, file_path: str) -> None:
        tab_state = self._editor_manager.get_tab(file_path)
        if tab_state is not None:
            self._pending_autosave_payloads.pop(tab_state.buffer_id, None)

    def migrate_draft_for_move(self, old_path: str, new_path: str) -> None:
        old_project_id, old_project_root = self._context_for_path(old_path)
        draft = self._autosave_store.load_draft(old_path, project_id=old_project_id, project_root=old_project_root)
        if draft is None:
            return
        new_project_id, new_project_root = self._context_for_path(new_path)
        try:
            self._autosave_store.save_draft(
                new_path,
                draft.content,
                project_id=new_project_id,
                project_root=new_project_root,
                recovery_policy=draft.recovery_policy,
                source=draft.source,
                base_blob_sha256=draft.base_blob_sha256,
                last_known_mtime=draft.last_known_mtime,
                session_id=draft.session_id,
            )
        except OSError as exc:
            self._logger.warning("Autosave draft move failed for %s -> %s: %s", old_path, new_path, exc)
            return
        self._autosave_store.delete_draft(old_path, project_id=old_project_id, project_root=old_project_root)

    def discard_drafts_for_paths(self, file_paths: Sequence[str]) -> None:
        for file_path in file_paths:
            self.discard_pending_autosave(file_path)
            self.delete_draft(file_path)

    def keep_drafts_for_paths(self, file_paths: Sequence[str]) -> None:
        for file_path in file_paths:
            tab_state = self._editor_manager.get_tab(file_path)
            if tab_state is None or not tab_state.is_dirty:
                continue
            project_id, project_root = self._context_for_path(tab_state.file_path)
            try:
                self._autosave_store.save_draft(
                    tab_state.file_path,
                    tab_state.current_content,
                    project_id=project_id,
                    project_root=project_root,
                    recovery_policy=DRAFT_RECOVERY_POLICY_RESTORE_SILENTLY,
                    source=DRAFT_SOURCE_KEPT_ON_EXIT,
                    last_known_mtime=tab_state.last_known_mtime,
                )
            except OSError as exc:
                self._logger.warning("Autosave draft write failed for %s: %s", tab_state.file_path, exc)
            self.discard_pending_autosave(tab_state.file_path)

    def clear_pending_autosaves(self) -> None:
        self._pending_autosave_payloads.clear()

    def delete_draft(self, file_path: str) -> None:
        project_id, project_root = self._context_for_path(file_path)
        self._autosave_store.delete_draft(file_path, project_id=project_id, project_root=project_root)

    def flush_pending_autosaves(
        self,
        file_paths: Sequence[str] | None = None,
        *,
        recovery_policy: str = DRAFT_RECOVERY_POLICY_PROMPT,
        source: str = DRAFT_SOURCE_LIVE_DIRTY_BACKUP,
    ) -> None:
        if not self._pending_autosave_payloads:
            return
        selected_ids = None
        if file_paths is not None:
            selected_tabs = (self._editor_manager.get_tab(file_path) for file_path in file_paths)
            selected_ids = {tab.buffer_id for tab in selected_tabs if tab is not None}
        pending_items = [
            (buffer_id, content)
            for buffer_id, content in self._pending_autosave_payloads.items()
            if selected_ids is None or buffer_id in selected_ids
        ]
        for buffer_id, _content in pending_items:
            self._pending_autosave_payloads.pop(buffer_id, None)
        for buffer_id, content in pending_items:
            tab_state = self._editor_manager.get_tab_by_id(buffer_id)
            if tab_state is None:
                continue
            file_path = tab_state.file_path
            try:
                project_id, project_root = self._context_for_path(file_path)
                self._autosave_store.save_draft(
                    file_path,
                    content,
                    project_id=project_id,
                    project_root=project_root,
                    recovery_policy=recovery_policy,
                    source=source,
                    last_known_mtime=tab_state.last_known_mtime,
                )
            except OSError as exc:
                self._logger.warning("Autosave draft write failed for %s: %s", file_path, exc)

    def stop_autosave_timer(self) -> None:
        self._autosave_timer.stop()
