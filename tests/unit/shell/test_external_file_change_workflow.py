"""Unit tests for external file change reload workflow."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.editors.editor_manager import EditorManager  # noqa: E402
from app.editors.editor_tab import DISK_CONFLICT_CHANGED, DISK_CONFLICT_MISSING, EditorTabState  # noqa: E402
from app.shell.document_safety import (  # noqa: E402
    DocumentCloseIntent,
    DocumentSafetyDecision,
    DocumentScope,
)
from app.shell.disk_conflict_dialogs import DiskChangedChoice, StaleSaveChoice  # noqa: E402
from app.shell.editor_sync_workflow import EditorDiskSyncSource, EditorSyncWorkflow, EditorWidgetPort  # noqa: E402
from app.shell.editor_tabs_coordinator import tab_presentation_data  # noqa: E402
from app.shell.external_file_change_workflow import (  # noqa: E402
    ExternalFileChangeOutcome,
    ExternalFileChangeWorkflow,
    MissingFileAction,
    MissingFileChoice,
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

    def lock_generated(self, tab: EditorTabState, text: str) -> None:
        del tab, text


@dataclass
class _RecordingExternalHost:
    widgets: dict[str, _FakeEditorWidget] = field(default_factory=dict)
    confirm_reload: bool = True
    save_refreshes: int = 0
    confirm_calls: int = 0
    status_updates: list[str] = field(default_factory=list)
    conflict_refreshes: list[str] = field(default_factory=list)
    missing_presentations: list[str] = field(default_factory=list)
    missing_action: MissingFileAction = field(
        default_factory=lambda: MissingFileAction(MissingFileChoice.KEEP)
    )
    saved_as: list[tuple[str, str]] = field(default_factory=list)
    save_as_result: bool = True
    closed_missing: list[str] = field(default_factory=list)
    disk_changed_choices: list[DiskChangedChoice] = field(default_factory=list)
    disk_changed_prompts: list[str] = field(default_factory=list)
    compares: list[tuple[str, str]] = field(default_factory=list)

    def editor_widget_for_path(self, file_path: str) -> _FakeEditorWidget | None:
        return self.widgets.get(file_path)

    def confirm_clean_tab_reload(self) -> bool:
        self.confirm_calls += 1
        return self.confirm_reload

    def refresh_save_action_states(self) -> None:
        self.save_refreshes += 1

    def update_editor_status_for_path(self, file_path: str) -> None:
        self.status_updates.append(file_path)

    def render_lint_diagnostics_for_file(self, file_path: str, *, trigger: str) -> None:
        del file_path, trigger

    def present_missing_file(self, file_path: str) -> MissingFileAction:
        self.missing_presentations.append(file_path)
        return self.missing_action

    def save_missing_buffer_as(self, file_path: str, destination_path: str) -> bool:
        self.saved_as.append((file_path, destination_path))
        return self.save_as_result

    def close_missing_tab(self, file_path: str) -> None:
        self.closed_missing.append(file_path)

    def refresh_conflict_presentation(self, file_path: str) -> None:
        self.conflict_refreshes.append(file_path)

    def present_disk_changed(self, file_path: str, *, disk_mtime: float | None) -> DiskChangedChoice:
        del disk_mtime
        self.disk_changed_prompts.append(file_path)
        return self.disk_changed_choices.pop(0)

    def show_disk_compare(self, file_path: str, *, disk_text: str, buffer_text: str) -> None:
        del file_path
        self.compares.append((disk_text, buffer_text))


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


def test_check_and_handle_declines_clean_tab_and_keeps_the_conflict(tmp_path: Path) -> None:
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
    assert tab.last_known_mtime == 1.0
    assert tab.disk_conflict is not None
    assert tab.disk_conflict.kind == DISK_CONFLICT_CHANGED
    assert tab.disk_conflict.conflict_mtime == new_mtime
    assert tab_presentation_data(tab)["is_stale"] is True
    assert tab.is_dirty is False


def _dirty_changed_on_disk(tmp_path: Path, choices: list[DiskChangedChoice]):  # type: ignore[no-untyped-def]
    file_path = tmp_path / "main.py"
    manager = EditorManager()
    sync_host = _RecordingSyncHost()
    external_host = _RecordingExternalHost(disk_changed_choices=list(choices))
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
        decision=DocumentSafetyDecision(intent=DocumentCloseIntent.PROCEED, scope=DocumentScope.EXTERNAL_RELOAD)
    )
    local_history = _RecordingLocalHistory()
    workflow = _build_workflows(
        manager,
        sync_host=sync_host,
        external_host=external_host,
        save_workflow=save_workflow,
        local_history=local_history,
    )
    return workflow, tab, external_host, save_workflow, local_history, file_path.stat().st_mtime


def test_poll_on_a_dirty_buffer_keep_my_version_keeps_the_buffer_as_stale(tmp_path: Path) -> None:
    workflow, tab, host, save_workflow, local_history, new_mtime = _dirty_changed_on_disk(
        tmp_path, [DiskChangedChoice.KEEP_MY_VERSION]
    )

    outcome = workflow.check_and_handle(tab.file_path)

    assert outcome is ExternalFileChangeOutcome.DECLINED
    assert host.disk_changed_prompts == [tab.file_path]
    assert save_workflow.requests == [], "the generic Unsaved Changes dialog is not used at poll time"
    assert tab.current_content == "print('draft')\n" and tab.is_dirty
    assert tab.disk_conflict is not None and tab.disk_conflict.conflict_mtime == new_mtime
    assert tab_presentation_data(tab)["is_stale"] is True
    assert local_history.checkpoints == []
    assert workflow.check_and_handle(tab.file_path) is ExternalFileChangeOutcome.SKIPPED
    assert host.disk_changed_prompts == [tab.file_path], "the same change is not asked about twice"


def test_poll_on_a_dirty_buffer_reload_after_compare_saves_the_buffer_to_history(tmp_path: Path) -> None:
    workflow, tab, host, _save_workflow, local_history, _new_mtime = _dirty_changed_on_disk(
        tmp_path, [DiskChangedChoice.COMPARE, DiskChangedChoice.RELOAD_FROM_DISK]
    )

    outcome = workflow.check_and_handle(tab.file_path)

    assert outcome is ExternalFileChangeOutcome.RELOADED
    assert host.compares == [("print('new')\n", "print('draft')\n")]
    assert local_history.checkpoints[0] == (
        tab.file_path,
        "print('draft')\n",
        "external_reload_discarded_buffer",
        "Discarded buffer during disk reload",
    )
    assert tab.current_content == "print('new')\n" and not tab.is_dirty
    assert tab.disk_conflict is None


def test_check_and_handle_follows_replaced_editor_manager(tmp_path: Path) -> None:
    file_path = tmp_path / "main.py"
    compose_time_manager = EditorManager()
    live_manager = EditorManager()
    sync_host = _RecordingSyncHost()
    external_host = _RecordingExternalHost(confirm_reload=True)
    tab = _open_tab_with_widget(
        live_manager,
        file_path,
        content="print('old')\n",
        mtime=1.0,
        sync_host=sync_host,
        external_host=external_host,
    )
    file_path.write_text("print('new')\n", encoding="utf-8")
    workflow = _build_workflows(
        compose_time_manager,
        sync_host=sync_host,
        external_host=external_host,
        save_workflow=_RecordingSaveWorkflow(
            decision=DocumentSafetyDecision(intent=DocumentCloseIntent.PROCEED, scope=DocumentScope.EXTERNAL_RELOAD)
        ),
        local_history=_RecordingLocalHistory(),
    )

    assert workflow.check_and_handle(tab.file_path) is ExternalFileChangeOutcome.SKIPPED

    workflow.set_editor_manager(live_manager)
    outcome = workflow.check_and_handle(tab.file_path)

    assert outcome is ExternalFileChangeOutcome.RELOADED
    assert tab.current_content == "print('new')\n"


class _FakeContentSource:
    """Sourced buffer whose text only changes through the surface."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.saved_text = text
        self.mark_saved_calls: list[str] = []
        # When set, every current_text() call after the first one returns this
        # instead: a re-serialization that differs from what was read from disk.
        self.drift_text: "str | None" = None
        self._calls_since_drift = 0

    def current_text(self) -> str:
        if self.drift_text is not None:
            self._calls_since_drift += 1
            if self._calls_since_drift > 1:
                return self.drift_text
        return self.text

    def is_dirty(self) -> bool:
        return self.text != self.saved_text

    def mark_saved(self, saved_text: str) -> None:
        self.mark_saved_calls.append(saved_text)
        self.saved_text = saved_text

    def revision(self) -> int:
        return 0

    def subscribe_changed(self, listener):  # type: ignore[no-untyped-def]
        del listener
        return lambda: None


class _FakeSurface:
    def __init__(self, source: _FakeContentSource) -> None:
        self._source = source
        self.restored: list[tuple[str, str]] = []

    def restore_text(self, text: str, reason: str) -> None:
        self.restored.append((text, reason))
        self._source.text = text


@dataclass
class _SurfaceSyncHost(_RecordingSyncHost):
    surfaces: dict[str, _FakeSurface] = field(default_factory=dict)

    def surface_for_path(self, file_path: str) -> _FakeSurface | None:
        return self.surfaces.get(file_path)


@dataclass
class _SurfaceExternalHost(_RecordingExternalHost):
    surfaces: dict[str, _FakeSurface] = field(default_factory=dict)
    confirm_calls: int = 0

    def surface_for_path(self, file_path: str) -> _FakeSurface | None:
        return self.surfaces.get(file_path)

    def confirm_clean_tab_reload(self) -> bool:
        self.confirm_calls += 1
        return self.confirm_reload


def _open_lazy_sourced_tab(
    manager: EditorManager,
    file_path: Path,
    *,
    content: str,
    sync_host: _SurfaceSyncHost,
    external_host: _SurfaceExternalHost,
) -> tuple[EditorTabState, _FakeContentSource, _FakeSurface]:
    """A provider-owned tab with a surface and no source editor widget."""
    file_path.write_text(content, encoding="utf-8")
    tab = manager.open_file(str(file_path)).tab
    source = _FakeContentSource(content)
    tab.content_source = source  # type: ignore[assignment]
    tab.mark_saved(last_known_mtime=1.0)
    surface = _FakeSurface(source)
    sync_host.surfaces[tab.file_path] = surface
    external_host.surfaces[tab.file_path] = surface
    sync_host.tab_indices[tab.file_path] = 0
    return tab, source, surface


def test_lazy_sourced_clean_tab_prompts_and_reloads_through_surface(tmp_path: Path) -> None:
    file_path = tmp_path / "form.ui"
    manager = EditorManager()
    sync_host = _SurfaceSyncHost()
    external_host = _SurfaceExternalHost(confirm_reload=True)
    tab, source, surface = _open_lazy_sourced_tab(
        manager, file_path, content="<ui old/>\n", sync_host=sync_host, external_host=external_host
    )
    file_path.write_text("<ui new/>\n", encoding="utf-8")
    new_mtime = file_path.stat().st_mtime
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
    assert external_host.confirm_calls == 1
    assert sync_host.widgets == {}
    assert surface.restored == [("<ui new/>\n", "external_reload")]
    assert source.saved_text == "<ui new/>\n"
    assert tab.is_dirty is False
    assert tab.last_known_mtime == new_mtime
    assert local_history.checkpoints[-1][2] == "external_reload"


def test_sourced_dirty_cancel_marks_the_conflict_and_the_next_save_prompts(tmp_path: Path) -> None:
    file_path = tmp_path / "form.ui"
    manager = EditorManager()
    sync_host = _SurfaceSyncHost()
    external_host = _SourcedStaleHost()
    tab, source, _surface = _open_lazy_sourced_tab(
        manager, file_path, content="<ui old/>\n", sync_host=sync_host, external_host=external_host
    )
    source.text = "<ui draft/>\n"
    file_path.write_text("<ui new/>\n", encoding="utf-8")
    workflow = _build_workflows(
        manager,
        sync_host=sync_host,
        external_host=external_host,
        save_workflow=_RecordingSaveWorkflow(
            decision=DocumentSafetyDecision(intent=DocumentCloseIntent.CANCEL, scope=DocumentScope.EXTERNAL_RELOAD)
        ),
        local_history=_RecordingLocalHistory(),
    )

    outcome = workflow.check_and_handle(tab.file_path)

    assert outcome is ExternalFileChangeOutcome.DECLINED
    assert tab.disk_conflict is not None and tab.disk_conflict.kind == DISK_CONFLICT_CHANGED
    assert external_host.stale_prompts == []
    assert workflow.resolve_before_save(tab.file_path) == "abort"
    assert external_host.stale_prompts == [tab.file_path]
    assert source.text == "<ui draft/>\n"


def test_lazy_sourced_dirty_tab_gets_three_way_prompt_then_reloads(tmp_path: Path) -> None:
    file_path = tmp_path / "form.ui"
    manager = EditorManager()
    sync_host = _SurfaceSyncHost()
    external_host = _SurfaceExternalHost()
    tab, source, surface = _open_lazy_sourced_tab(
        manager, file_path, content="<ui old/>\n", sync_host=sync_host, external_host=external_host
    )
    source.text = "<ui draft/>\n"
    file_path.write_text("<ui new/>\n", encoding="utf-8")
    save_workflow = _RecordingSaveWorkflow(
        decision=DocumentSafetyDecision(intent=DocumentCloseIntent.DISCARD, scope=DocumentScope.EXTERNAL_RELOAD)
    )
    local_history = _RecordingLocalHistory()
    workflow = _build_workflows(
        manager,
        sync_host=sync_host,
        external_host=external_host,
        save_workflow=save_workflow,
        local_history=local_history,
    )

    outcome = workflow.check_and_handle(tab.file_path)

    assert outcome is ExternalFileChangeOutcome.RELOADED
    assert save_workflow.requests == [("request", DocumentScope.EXTERNAL_RELOAD)]
    assert external_host.confirm_calls == 0
    assert local_history.checkpoints[0][1:3] == ("<ui draft/>\n", "external_reload_discarded_buffer")
    assert surface.restored == [("<ui new/>\n", "external_reload")]
    assert tab.is_dirty is False


def test_sourced_tab_matching_disk_marks_saved_with_disk_text(tmp_path: Path) -> None:
    file_path = tmp_path / "form.ui"
    manager = EditorManager()
    sync_host = _SurfaceSyncHost()
    external_host = _SurfaceExternalHost()
    tab, source, surface = _open_lazy_sourced_tab(
        manager, file_path, content="<ui old/>\n", sync_host=sync_host, external_host=external_host
    )
    source.text = "<ui same/>\n"
    # After the content comparison, a re-read of the source would yield a different
    # serialization. The baseline must be the exact disk text, not a fresh read.
    source.drift_text = "<ui same />\n"
    file_path.write_text("<ui same/>\n", encoding="utf-8")
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
    assert source.mark_saved_calls[-1] == "<ui same/>\n"
    assert tab.original_content == "<ui same/>\n"
    assert surface.restored == []


def test_markdown_style_tab_with_widget_and_surface_reloads_through_surface(tmp_path: Path) -> None:
    file_path = tmp_path / "README.md"
    manager = EditorManager()
    sync_host = _SurfaceSyncHost()
    external_host = _SurfaceExternalHost(confirm_reload=True)
    tab, _source, surface = _open_lazy_sourced_tab(
        manager, file_path, content="# old\n", sync_host=sync_host, external_host=external_host
    )
    widget = _FakeEditorWidget("# old\n")
    sync_host.widgets[tab.file_path] = widget
    external_host.widgets[tab.file_path] = widget
    file_path.write_text("# new\n", encoding="utf-8")
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

    assert outcome is ExternalFileChangeOutcome.RELOADED
    assert external_host.confirm_calls == 1
    assert surface.restored == [("# new\n", "external_reload")]
    assert widget.text == "# old\n"
    assert sync_host.indent_calls == [(tab.file_path, "# new\n")]


def test_tab_without_widget_or_surface_is_skipped(tmp_path: Path) -> None:
    file_path = tmp_path / "main.py"
    file_path.write_text("old\n", encoding="utf-8")
    manager = EditorManager()
    tab = manager.open_file(str(file_path)).tab
    tab.mark_saved(last_known_mtime=1.0)
    external_host = _SurfaceExternalHost()
    workflow = _build_workflows(
        manager,
        sync_host=_SurfaceSyncHost(),
        external_host=external_host,
        save_workflow=_RecordingSaveWorkflow(
            decision=DocumentSafetyDecision(intent=DocumentCloseIntent.PROCEED, scope=DocumentScope.EXTERNAL_RELOAD)
        ),
        local_history=_RecordingLocalHistory(),
    )

    assert workflow.check_and_handle(tab.file_path) is ExternalFileChangeOutcome.SKIPPED
    assert external_host.confirm_calls == 0


def test_declined_conflict_does_not_prompt_again_until_mtime_changes(tmp_path: Path) -> None:
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
    workflow = _build_workflows(
        manager,
        sync_host=sync_host,
        external_host=external_host,
        save_workflow=_RecordingSaveWorkflow(
            decision=DocumentSafetyDecision(intent=DocumentCloseIntent.PROCEED, scope=DocumentScope.EXTERNAL_RELOAD)
        ),
        local_history=_RecordingLocalHistory(),
    )

    assert workflow.check_and_handle(tab.file_path) is ExternalFileChangeOutcome.DECLINED
    assert workflow.check_and_handle(tab.file_path) is ExternalFileChangeOutcome.SKIPPED
    assert external_host.confirm_calls == 1

    later = file_path.stat().st_mtime + 5
    file_path.write_text("print('newer')\n", encoding="utf-8")
    os.utime(file_path, (later, later))
    assert workflow.check_and_handle(tab.file_path) is ExternalFileChangeOutcome.DECLINED
    assert external_host.confirm_calls == 2
    assert tab.disk_conflict is not None
    assert tab.disk_conflict.conflict_mtime == manager.current_disk_mtime(tab.file_path)


def test_save_forces_a_prompt_for_the_same_conflict_mtime(tmp_path: Path) -> None:
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
    workflow = _build_workflows(
        manager,
        sync_host=sync_host,
        external_host=external_host,
        save_workflow=_RecordingSaveWorkflow(
            decision=DocumentSafetyDecision(intent=DocumentCloseIntent.PROCEED, scope=DocumentScope.EXTERNAL_RELOAD)
        ),
        local_history=_RecordingLocalHistory(),
    )

    workflow.check_and_handle(tab.file_path)
    outcome = workflow.check_and_handle(tab.file_path, force=True)

    assert outcome is ExternalFileChangeOutcome.DECLINED
    assert external_host.confirm_calls == 2


def test_missing_file_sets_missing_conflict_once(tmp_path: Path) -> None:
    file_path = tmp_path / "main.py"
    manager = EditorManager()
    sync_host = _RecordingSyncHost()
    external_host = _RecordingExternalHost()
    tab = _open_tab_with_widget(
        manager,
        file_path,
        content="print('old')\n",
        sync_host=sync_host,
        external_host=external_host,
    )
    file_path.unlink()
    workflow = _build_workflows(
        manager,
        sync_host=sync_host,
        external_host=external_host,
        save_workflow=_RecordingSaveWorkflow(
            decision=DocumentSafetyDecision(intent=DocumentCloseIntent.PROCEED, scope=DocumentScope.EXTERNAL_RELOAD)
        ),
        local_history=_RecordingLocalHistory(),
    )

    assert workflow.check_and_handle(tab.file_path) is ExternalFileChangeOutcome.DECLINED
    assert tab.disk_conflict is not None
    assert tab.disk_conflict.kind == DISK_CONFLICT_MISSING
    assert tab_presentation_data(tab)["is_missing"] is True
    assert workflow.check_and_handle(tab.file_path) is ExternalFileChangeOutcome.SKIPPED
    assert external_host.missing_presentations == [tab.file_path]


def test_save_as_clears_missing_conflict(tmp_path: Path) -> None:
    file_path = tmp_path / "main.py"
    manager = EditorManager()
    sync_host = _RecordingSyncHost()
    destination = str(tmp_path / "kept.py")
    external_host = _RecordingExternalHost(
        missing_action=MissingFileAction(MissingFileChoice.SAVE_AS, destination_path=destination)
    )
    tab = _open_tab_with_widget(
        manager,
        file_path,
        content="print('old')\n",
        sync_host=sync_host,
        external_host=external_host,
    )
    file_path.unlink()
    tab.set_disk_conflict(DISK_CONFLICT_MISSING, None)
    workflow = _build_workflows(
        manager,
        sync_host=sync_host,
        external_host=external_host,
        save_workflow=_RecordingSaveWorkflow(
            decision=DocumentSafetyDecision(intent=DocumentCloseIntent.PROCEED, scope=DocumentScope.EXTERNAL_RELOAD)
        ),
        local_history=_RecordingLocalHistory(),
    )

    assert workflow.check_and_handle(tab.file_path, force=True) is ExternalFileChangeOutcome.CONTENT_ALREADY_MATCHES
    assert tab.disk_conflict is None
    assert external_host.saved_as == [(tab.file_path, destination)]


@dataclass
class _SourcedStaleHost(_SurfaceExternalHost):
    stale_prompts: list[str] = field(default_factory=list)

    def present_stale_save(self, file_path: str, *, disk_mtime: float | None, buffer_is_dirty: bool) -> StaleSaveChoice:
        del disk_mtime, buffer_is_dirty
        self.stale_prompts.append(file_path)
        return StaleSaveChoice.CANCEL


@dataclass
class _StaleSaveHost(_RecordingExternalHost):
    stale_choices: list[StaleSaveChoice] = field(default_factory=list)

    def present_stale_save(self, file_path: str, *, disk_mtime: float | None, buffer_is_dirty: bool) -> StaleSaveChoice:
        del file_path, disk_mtime, buffer_is_dirty
        return self.stale_choices.pop(0)


def _stale_dirty_tab(tmp_path: Path, choices: list[StaleSaveChoice]):  # type: ignore[no-untyped-def]
    file_path = tmp_path / "report.py"
    manager = EditorManager()
    sync_host = _RecordingSyncHost()
    external_host = _StaleSaveHost(stale_choices=list(choices))
    tab = _open_tab_with_widget(
        manager,
        file_path,
        content="disk v1\n",
        mtime=1.0,
        sync_host=sync_host,
        external_host=external_host,
    )
    manager.update_tab_content(tab.file_path, "mine\n")
    file_path.write_text("disk v2\n", encoding="utf-8")
    history = _RecordingLocalHistory()
    workflow = _build_workflows(
        manager,
        sync_host=sync_host,
        external_host=external_host,
        save_workflow=_RecordingSaveWorkflow(
            decision=DocumentSafetyDecision(intent=DocumentCloseIntent.CANCEL, scope=DocumentScope.EXTERNAL_RELOAD)
        ),
        local_history=history,
    )
    return workflow, tab, external_host, sync_host, history


def test_stale_save_compare_then_save_my_version_writes_the_buffer(tmp_path: Path) -> None:
    workflow, tab, host, _sync_host, _history = _stale_dirty_tab(
        tmp_path, [StaleSaveChoice.COMPARE, StaleSaveChoice.SAVE_MY_VERSION]
    )

    assert workflow.resolve_before_save(tab.file_path) == "proceed"
    assert host.compares == [("disk v2\n", "mine\n")]


def test_stale_save_reload_from_disk_keeps_the_buffer_in_history(tmp_path: Path) -> None:
    workflow, tab, _host, sync_host, history = _stale_dirty_tab(tmp_path, [StaleSaveChoice.RELOAD_FROM_DISK])

    assert workflow.resolve_before_save(tab.file_path) == "already_synced"
    assert sync_host.widgets[tab.file_path].text == "disk v2\n"
    assert not tab.is_dirty and tab.disk_conflict is None
    assert (tab.file_path, "mine\n", "external_reload_discarded_buffer") in [entry[:3] for entry in history.checkpoints]


def test_stale_save_cancel_keeps_the_conflict_and_does_not_save(tmp_path: Path) -> None:
    workflow, tab, _host, _sync_host, _history = _stale_dirty_tab(tmp_path, [StaleSaveChoice.CANCEL])

    assert workflow.resolve_before_save(tab.file_path) == "abort"
    assert tab.disk_conflict is not None and tab.disk_conflict.kind == DISK_CONFLICT_CHANGED
    assert tab.current_content == "mine\n"


def test_poll_while_the_stale_save_prompt_is_open_does_not_prompt_again(tmp_path: Path) -> None:
    workflow, tab, host, _sync_host, _history = _stale_dirty_tab(tmp_path, [StaleSaveChoice.CANCEL])
    nested: list[ExternalFileChangeOutcome] = []
    present = host.present_stale_save

    def present_and_poll(file_path: str, **kwargs):  # type: ignore[no-untyped-def]
        nested.append(workflow.check_and_handle(file_path))
        return present(file_path, **kwargs)

    host.present_stale_save = present_and_poll  # type: ignore[method-assign]

    assert workflow.resolve_before_save(tab.file_path) == "abort"
    assert nested == [ExternalFileChangeOutcome.SKIPPED]


def test_form_bar_handles_a_dirty_external_change_without_the_modal(tmp_path: Path) -> None:
    file_path = tmp_path / "form.ui"
    manager = EditorManager()
    sync_host = _SurfaceSyncHost()
    external_host = _SurfaceExternalHost()
    tab, source, surface = _open_lazy_sourced_tab(
        manager, file_path, content="<ui old/>\n", sync_host=sync_host, external_host=external_host
    )
    source.text = "<ui draft/>\n"

    class _Bar(_FakeSurface):
        def __init__(self, content: _FakeContentSource) -> None:
            super().__init__(content)
            self.offered: list[str] = []
            self.compare = lambda: None
            self.reload = lambda: None

        def external_change_needs_bar(self, disk_text: str) -> bool:
            del disk_text
            return True

        def offer_external_change(self, file_name: str, on_reload, on_keep, on_compare) -> None:  # type: ignore[no-untyped-def]
            del on_keep
            self.offered.append(file_name)
            self.reload = on_reload
            self.compare = on_compare

    bar = _Bar(source)
    sync_host.surfaces[tab.file_path] = bar
    external_host.surfaces[tab.file_path] = bar
    del surface
    file_path.write_text("<ui new/>\n", encoding="utf-8")
    save_workflow = _RecordingSaveWorkflow(
        decision=DocumentSafetyDecision(intent=DocumentCloseIntent.DISCARD, scope=DocumentScope.EXTERNAL_RELOAD)
    )
    workflow = _build_workflows(
        manager,
        sync_host=sync_host,
        external_host=external_host,
        save_workflow=save_workflow,
        local_history=_RecordingLocalHistory(),
    )

    outcome = workflow.check_and_handle(tab.file_path)

    assert outcome is ExternalFileChangeOutcome.DECLINED
    assert save_workflow.requests == []
    assert bar.offered == ["form.ui"]
    bar.compare()
    assert external_host.compares
    bar.reload()
    assert bar.restored[-1][0] == "<ui new/>\n"
