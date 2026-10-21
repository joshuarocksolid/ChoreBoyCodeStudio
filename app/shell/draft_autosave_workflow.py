"""Draft autosave scheduling and flush for dirty editor buffers."""

from __future__ import annotations

import logging
from typing import Callable, Optional, Protocol, Sequence

from app.qt.QtCore import QTimer
from app.qt.QtWidgets import QWidget

from app.editors.editor_manager import EditorManager
from app.editors.tab_content_source import TabContentSource
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
    """Owns debounced draft autosave timer and pending flush."""

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
        self._pending_source_paths: set[str] = set()
        self._source_revisions: dict[str, int] = {}
        self._source_unsubs: dict[str, Callable[[], None]] = {}
        self._autosave_timer = autosave_timer or QTimer(parent)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(500)
        self._autosave_timer.timeout.connect(self.flush_pending_autosaves)

    def set_editor_manager(self, editor_manager: EditorManager) -> None:
        self._editor_manager = editor_manager

    def schedule_autosave(self, file_path: str, content: str) -> None:
        self._pending_autosave_payloads[file_path] = content
        self._autosave_timer.start()

    def note_source_changed(self, file_path: str) -> None:
        """Record that a sourced tab changed. The flush reads the text later."""
        self._pending_source_paths.add(file_path)
        self._autosave_timer.start()

    def watch_content_source(self, file_path: str, source: TabContentSource) -> Callable[[], None]:
        """Schedule drafts from ``source`` without serializing until the timer fires."""
        self.unwatch_content_source(file_path)
        self._source_revisions[file_path] = source.revision()

        def on_changed() -> None:
            self._pending_source_paths.add(file_path)
            self._autosave_timer.start()

        unsubscribe = source.subscribe_changed(on_changed)
        self._source_unsubs[file_path] = unsubscribe
        return unsubscribe

    def unwatch_content_source(self, file_path: str) -> None:
        unsubscribe = self._source_unsubs.pop(file_path, None)
        if unsubscribe is not None:
            unsubscribe()
        self._source_revisions.pop(file_path, None)
        self._pending_source_paths.discard(file_path)

    def rekey_content_source(self, old_path: str, new_path: str) -> None:
        unsubscribe = self._source_unsubs.pop(old_path, None)
        if unsubscribe is not None:
            self._source_unsubs[new_path] = unsubscribe
        revision = self._source_revisions.pop(old_path, None)
        if revision is not None:
            self._source_revisions[new_path] = revision
        if old_path in self._pending_source_paths:
            self._pending_source_paths.discard(old_path)
            self._pending_source_paths.add(new_path)

    def discard_pending_autosave(self, file_path: str) -> None:
        self._pending_autosave_payloads.pop(file_path, None)

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
        self._pending_source_paths.clear()

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
        if not self._pending_autosave_payloads and not self._pending_source_paths:
            return
        selected_paths = None if file_paths is None else set(file_paths)
        pending_items = [
            (file_path, content)
            for file_path, content in self._pending_autosave_payloads.items()
            if selected_paths is None or file_path in selected_paths
        ]
        for file_path, _content in pending_items:
            self._pending_autosave_payloads.pop(file_path, None)
        for file_path, content in pending_items:
            try:
                project_id, project_root = self._context_for_path(file_path)
                tab_state = self._editor_manager.get_tab(file_path)
                self._autosave_store.save_draft(
                    file_path,
                    content,
                    project_id=project_id,
                    project_root=project_root,
                    recovery_policy=recovery_policy,
                    source=source,
                    last_known_mtime=None if tab_state is None else tab_state.last_known_mtime,
                )
            except OSError as exc:
                self._logger.warning("Autosave draft write failed for %s: %s", file_path, exc)
        self._flush_sourced_drafts(
            selected_paths=selected_paths,
            recovery_policy=recovery_policy,
            source=source,
        )

    def _flush_sourced_drafts(
        self,
        *,
        selected_paths: Optional[set[str]],
        recovery_policy: str,
        source: str,
    ) -> None:
        pending_paths = [
            file_path
            for file_path in self._pending_source_paths
            if selected_paths is None or file_path in selected_paths
        ]
        for file_path in pending_paths:
            self._pending_source_paths.discard(file_path)
        for file_path in pending_paths:
            tab_state = self._editor_manager.get_tab(file_path)
            content_source = None if tab_state is None else tab_state.content_source
            if content_source is None:
                self._source_revisions.pop(file_path, None)
                continue
            revision = content_source.revision()
            if revision == self._source_revisions.get(file_path):
                continue
            text = content_source.current_text()
            self._source_revisions[file_path] = revision
            try:
                project_id, project_root = self._context_for_path(file_path)
                self._autosave_store.save_draft(
                    file_path,
                    text,
                    project_id=project_id,
                    project_root=project_root,
                    recovery_policy=recovery_policy,
                    source=source,
                    last_known_mtime=None if tab_state is None else tab_state.last_known_mtime,
                )
            except OSError as exc:
                self._logger.warning("Autosave draft write failed for %s: %s", file_path, exc)

    def stop_autosave_timer(self) -> None:
        self._autosave_timer.stop()
