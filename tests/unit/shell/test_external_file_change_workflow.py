"""Unit tests for external file change reload workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.editors.editor_manager import EditorManager  # noqa: E402
from app.editors.editor_tab import EditorTabState  # noqa: E402
from app.shell.document_safety import (  # noqa: E402
    DocumentCloseIntent,
    DocumentSafetyDecision,
    DocumentScope,
)
from app.shell.editor_sync_workflow import EditorDiskSyncSource, EditorSyncWorkflow, EditorWidgetPort  # noqa: E402
from app.shell.external_file_change_workflow import (  # noqa: E402
    ExternalFileChangeOutcome,
    ExternalFileChangeWorkflow,
)

pytestmark = pytest.mark.unit


class _FakeEditorWidget:
    def __init__(self, text: str) -> None:
        self.text = text

    def blockSignals(self, blocked: bool) -> bool:  # noqa: N802
        return False

    def setPlainText(self, text: str) -> None:
        self.text = text


@dataclass
class _RecordingSyncHost:
    widgets: dict[str, _FakeEditorWidget] = field(default_factory=dict)
    revision_bumps: list[str] = field(default_factory=list)
    indent_calls: list[tuple[str, str]] = field(default_factory=list)
    refreshed_paths: list[str] = field(default_factory=list)
    tab_indices: dict[str, int] = field(default_factory=dict)

    def editor_widget_for_path(self, file_path: str) -> _FakeEditorWidget | None:
        return self.widgets.get(file_path)

    def advance_buffer_revision(self, file_path: str) -> int:
        self.revision_bumps.append(file_path)
        return len(self.revision_bumps)

    def apply_detected_indentation(
        self,
        file_path: str,
        editor_widget: EditorWidgetPort,
        source_text: str,
    ) -> None:
        del editor_widget
        self.indent_calls.append((file_path, source_text))

    def tab_index_for_path(self, file_path: str) -> int:
        return self.tab_indices.get(file_path, -1)

    def refresh_tab_presentation(self, file_path: str) -> None:
        self.refreshed_paths.append(file_path)

    def has_editor_tabs_widget(self) -> bool:
        return True


@dataclass
class _RecordingExternalHost:
    widgets: dict[str, _FakeEditorWidget] = field(default_factory=dict)
    confirm_reload: bool = True
    save_refreshes: int = 0
    status_updates: list[str] = field(default_factory=list)

    def editor_widget_for_path(self, file_path: str) -> _FakeEditorWidget | None:
        return self.widgets.get(file_path)

    def confirm_clean_tab_reload(self) -> bool:
        return self.confirm_reload

    def refresh_save_action_states(self) -> None:
        self.save_refreshes += 1

    def update_editor_status_for_path(self, file_path: str) -> None:
        self.status_updates.append(file_path)


@dataclass
class _RecordingLocalHistory:
    checkpoints: list[tuple[str, str, str, str]] = field(default_factory=list)
    discarded: list[list[str]] = field(default_factory=list)

    def record_checkpoint(
        self,
        file_path: str,
        content: str,
        *,
        source: str,
        label: str = "",
    ) -> None:
        self.checkpoints.append((file_path, content, source, label))

    def discard_drafts_for_paths(self, file_paths) -> None:  # type: ignore[no-untyped-def]
        self.discarded.append(list(file_paths))


@dataclass
class _RecordingSaveWorkflow:
    decision: DocumentSafetyDecision
    apply_result: bool = True
    requests: list[tuple[str, DocumentScope]] = field(default_factory=list)
    applied: list[DocumentSafetyDecision] = field(default_factory=list)

    def request_unsaved_changes_decision(
        self,
        action_description: str,
        *,
        scope: DocumentScope,
        allow_keep_for_next_launch: bool,
        dirty_buffers: tuple[object, ...] | None = None,
    ) -> DocumentSafetyDecision:
        del action_description, allow_keep_for_next_launch, dirty_buffers
        self.requests.append(("request", scope))
        return self.decision

    def apply_unsaved_changes_decision(self, decision: DocumentSafetyDecision) -> bool:
        self.applied.append(decision)
        return self.apply_result


def _build_workflows(
    manager: EditorManager,
    *,
    sync_host: _RecordingSyncHost,
    external_host: _RecordingExternalHost,
    save_workflow: _RecordingSaveWorkflow,
    local_history: _RecordingLocalHistory,
) -> ExternalFileChangeWorkflow:
    editor_sync = EditorSyncWorkflow(editor_manager=manager, host=sync_host)
    return ExternalFileChangeWorkflow(
        editor_manager=manager,
        editor_sync=editor_sync,
        save_workflow=save_workflow,
        local_history=local_history,
        host=external_host,
    )


def _open_tab_with_widget(
    manager: EditorManager,
    file_path: Path,
    *,
    content: str,
    mtime: float | None = None,
    sync_host: _RecordingSyncHost,
    external_host: _RecordingExternalHost,
) -> EditorTabState:
    file_path.write_text(content, encoding="utf-8")
    result = manager.open_file(str(file_path))
    tab = result.tab
    resolved_mtime = manager.current_disk_mtime(tab.file_path) if mtime is None else mtime
    tab.mark_saved(last_known_mtime=resolved_mtime)
    widget = _FakeEditorWidget(tab.current_content)
    sync_host.widgets[tab.file_path] = widget
    external_host.widgets[tab.file_path] = widget
    sync_host.tab_indices[tab.file_path] = 0
    return tab


def test_check_and_handle_skips_when_mtime_unchanged(tmp_path: Path) -> None:
    file_path = tmp_path / "main.py"
    manager = EditorManager()
    sync_host = _RecordingSyncHost()
    external_host = _RecordingExternalHost()
    tab = _open_tab_with_widget(
        manager,
        file_path,
        content="print('disk')\n",
        sync_host=sync_host,
        external_host=external_host,
    )
    workflow = _build_workflows(
        manager,
        sync_host=sync_host,
        external_host=external_host,
        save_workflow=_RecordingSaveWorkflow(
            decision=DocumentSafetyDecision(intent=DocumentCloseIntent.PROCEED, scope=DocumentScope.EXTERNAL_RELOAD)
        ),
        local_history=_RecordingLocalHistory(),
    )

    outcome = workflow.check_and_handle(tab.file_path)

    assert outcome is ExternalFileChangeOutcome.SKIPPED
    assert sync_host.revision_bumps == []


def test_check_and_handle_marks_saved_when_buffer_matches_disk(tmp_path: Path) -> None:
    file_path = tmp_path / "main.py"
    manager = EditorManager()
    sync_host = _RecordingSyncHost()
    external_host = _RecordingExternalHost()
    tab = _open_tab_with_widget(
        manager,
        file_path,
        content="print('disk')\n",
        mtime=1.0,
        sync_host=sync_host,
        external_host=external_host,
    )
    file_path.write_text("print('disk')\n", encoding="utf-8")
    new_mtime = file_path.stat().st_mtime
    workflow = _build_workflows(
        manager,
        sync_host=sync_host,
        external_host=external_host,
        save_workflow=_RecordingSaveWorkflow(
            decision=DocumentSafetyDecision(intent=DocumentCloseIntent.PROCEED, scope=DocumentScope.EXTERNAL_RELOAD)
        ),
        local_history=_RecordingLocalHistory(),
    )

    outcome = workflow.check_and_handle(tab.file_path)

    assert outcome is ExternalFileChangeOutcome.CONTENT_ALREADY_MATCHES
    assert tab.last_known_mtime == new_mtime
    assert external_host.save_refreshes == 1


def test_check_and_handle_reloads_clean_tab_when_confirmed(tmp_path: Path) -> None:
    file_path = tmp_path / "main.py"
    manager = EditorManager()
    sync_host = _RecordingSyncHost()
    external_host = _RecordingExternalHost(confirm_reload=True)
    tab = _open_tab_with_widget(
        manager,
        file_path,
        content="print('old')\n",
        mtime=1.0,
        sync_host=sync_host,
        external_host=external_host,
    )
    file_path.write_text("print('new')\n", encoding="utf-8")
    local_history = _RecordingLocalHistory()
    workflow = _build_workflows(
        manager,
        sync_host=sync_host,
        external_host=external_host,
        save_workflow=_RecordingSaveWorkflow(
            decision=DocumentSafetyDecision(intent=DocumentCloseIntent.PROCEED, scope=DocumentScope.EXTERNAL_RELOAD)
        ),
        local_history=local_history,
    )

    outcome = workflow.check_and_handle(tab.file_path)

    assert outcome is ExternalFileChangeOutcome.RELOADED
    assert tab.current_content == "print('new')\n"
    assert sync_host.revision_bumps == [tab.file_path]
    assert local_history.checkpoints == [
        (
            tab.file_path,
            "print('new')\n",
            "external_reload",
            "Reloaded from disk after external change",
        )
    ]
    assert local_history.discarded == [[tab.file_path]]
    assert external_host.status_updates == [tab.file_path]


def test_check_and_handle_declines_clean_tab_and_acknowledges_mtime(tmp_path: Path) -> None:
    file_path = tmp_path / "main.py"
    manager = EditorManager()
    sync_host = _RecordingSyncHost()
    external_host = _RecordingExternalHost(confirm_reload=False)
    tab = _open_tab_with_widget(
        manager,
        file_path,
        content="print('old')\n",
        mtime=1.0,
        sync_host=sync_host,
        external_host=external_host,
    )
    file_path.write_text("print('new')\n", encoding="utf-8")
    new_mtime = file_path.stat().st_mtime
    workflow = _build_workflows(
        manager,
        sync_host=sync_host,
        external_host=external_host,
        save_workflow=_RecordingSaveWorkflow(
            decision=DocumentSafetyDecision(intent=DocumentCloseIntent.PROCEED, scope=DocumentScope.EXTERNAL_RELOAD)
        ),
        local_history=_RecordingLocalHistory(),
    )

    outcome = workflow.check_and_handle(tab.file_path)

    assert outcome is ExternalFileChangeOutcome.DECLINED
    assert tab.current_content == "print('old')\n"
    assert tab.last_known_mtime == new_mtime
    assert tab.is_dirty is False


def test_check_and_handle_dirty_cancel_acknowledges_mtime(tmp_path: Path) -> None:
    file_path = tmp_path / "main.py"
    manager = EditorManager()
    sync_host = _RecordingSyncHost()
    external_host = _RecordingExternalHost()
    tab = _open_tab_with_widget(
        manager,
        file_path,
        content="print('disk')\n",
        mtime=1.0,
        sync_host=sync_host,
        external_host=external_host,
    )
    tab.update_content("print('draft')\n")
    file_path.write_text("print('new')\n", encoding="utf-8")
    new_mtime = file_path.stat().st_mtime
    save_workflow = _RecordingSaveWorkflow(
        decision=DocumentSafetyDecision(
            intent=DocumentCloseIntent.CANCEL,
            scope=DocumentScope.EXTERNAL_RELOAD,
            dirty_buffers=(SimpleNamespace(file_path=tab.file_path),),  # type: ignore[arg-type]
        )
    )
    workflow = _build_workflows(
        manager,
        sync_host=sync_host,
        external_host=external_host,
        save_workflow=save_workflow,
        local_history=_RecordingLocalHistory(),
    )

    outcome = workflow.check_and_handle(tab.file_path)

    assert outcome is ExternalFileChangeOutcome.CANCELLED
    assert save_workflow.requests == [("request", DocumentScope.EXTERNAL_RELOAD)]
    assert tab.current_content == "print('draft')\n"
    assert tab.last_known_mtime == new_mtime


def test_check_and_handle_dirty_discard_records_buffer_checkpoint_and_reloads(tmp_path: Path) -> None:
    file_path = tmp_path / "main.py"
    manager = EditorManager()
    sync_host = _RecordingSyncHost()
    external_host = _RecordingExternalHost()
    tab = _open_tab_with_widget(
        manager,
        file_path,
        content="print('disk')\n",
        mtime=1.0,
        sync_host=sync_host,
        external_host=external_host,
    )
    tab.update_content("print('draft')\n")
    file_path.write_text("print('new')\n", encoding="utf-8")
    local_history = _RecordingLocalHistory()
    save_workflow = _RecordingSaveWorkflow(
        decision=DocumentSafetyDecision(
            intent=DocumentCloseIntent.DISCARD,
            scope=DocumentScope.EXTERNAL_RELOAD,
            dirty_buffers=(SimpleNamespace(file_path=tab.file_path),),  # type: ignore[arg-type]
        )
    )
    workflow = _build_workflows(
        manager,
        sync_host=sync_host,
        external_host=external_host,
        save_workflow=save_workflow,
        local_history=local_history,
    )

    outcome = workflow.check_and_handle(tab.file_path)

    assert outcome is ExternalFileChangeOutcome.RELOADED
    assert local_history.checkpoints[0] == (
        tab.file_path,
        "print('draft')\n",
        "external_reload_discarded_buffer",
        "Discarded buffer during disk reload",
    )
    assert tab.current_content == "print('new')\n"


def test_check_and_handle_dirty_save_skips_reload_when_buffer_matches_disk(tmp_path: Path) -> None:
    file_path = tmp_path / "main.py"
    manager = EditorManager()
    sync_host = _RecordingSyncHost()
    external_host = _RecordingExternalHost()
    tab = _open_tab_with_widget(
        manager,
        file_path,
        content="print('disk')\n",
        mtime=1.0,
        sync_host=sync_host,
        external_host=external_host,
    )
    tab.update_content("print('saved')\n")
    file_path.write_text("print('other')\n", encoding="utf-8")
    save_workflow = _RecordingSaveWorkflow(
        decision=DocumentSafetyDecision(
            intent=DocumentCloseIntent.SAVE,
            scope=DocumentScope.EXTERNAL_RELOAD,
            dirty_buffers=(SimpleNamespace(file_path=tab.file_path),),  # type: ignore[arg-type]
        )
    )

    def _apply_save(_decision: DocumentSafetyDecision) -> bool:
        file_path.write_text("print('saved')\n", encoding="utf-8")
        tab.update_content("print('saved')\n")
        return True

    save_workflow.apply_unsaved_changes_decision = _apply_save  # type: ignore[method-assign]
    workflow = _build_workflows(
        manager,
        sync_host=sync_host,
        external_host=external_host,
        save_workflow=save_workflow,
        local_history=_RecordingLocalHistory(),
    )

    outcome = workflow.check_and_handle(tab.file_path)

    assert outcome is ExternalFileChangeOutcome.CONTENT_ALREADY_MATCHES
    assert tab.is_dirty is False
    assert sync_host.revision_bumps == []


def test_check_and_handle_dirty_proceed_reloads_without_save_prompt_side_effects(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "main.py"
    manager = EditorManager()
    sync_host = _RecordingSyncHost()
    external_host = _RecordingExternalHost()
    tab = _open_tab_with_widget(
        manager,
        file_path,
        content="print('disk')\n",
        mtime=1.0,
        sync_host=sync_host,
        external_host=external_host,
    )
    tab.update_content("print('draft')\n")
    file_path.write_text("print('new')\n", encoding="utf-8")
    save_workflow = _RecordingSaveWorkflow(
        decision=DocumentSafetyDecision(
            intent=DocumentCloseIntent.PROCEED,
            scope=DocumentScope.EXTERNAL_RELOAD,
            dirty_buffers=(SimpleNamespace(file_path=tab.file_path),),  # type: ignore[arg-type]
        )
    )
    workflow = _build_workflows(
        manager,
        sync_host=sync_host,
        external_host=external_host,
        save_workflow=save_workflow,
        local_history=_RecordingLocalHistory(),
    )

    outcome = workflow.check_and_handle(tab.file_path)

    assert outcome is ExternalFileChangeOutcome.RELOADED
    assert save_workflow.applied == []
    assert tab.current_content == "print('new')\n"
