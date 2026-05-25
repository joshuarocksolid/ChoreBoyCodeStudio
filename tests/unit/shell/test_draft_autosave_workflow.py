"""Unit tests for draft autosave scheduling and flush."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.editors.editor_manager import EditorManager  # noqa: E402
from app.persistence.autosave_store import DraftEntry  # noqa: E402
from app.persistence.history_models import (  # noqa: E402
    DRAFT_RECOVERY_POLICY_RESTORE_SILENTLY,
    DRAFT_SOURCE_KEPT_ON_EXIT,
)
from app.shell.draft_autosave_workflow import DraftAutosaveWorkflow  # noqa: E402

pytestmark = pytest.mark.unit


class _FakeTimer:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0
        self.interval: int | None = None
        self.single_shot = False
        self.timeout_callback = None
        self.timeout = SimpleNamespace(connect=self._connect)

    def _connect(self, callback) -> None:  # type: ignore[no-untyped-def]
        self.timeout_callback = callback

    def setSingleShot(self, value: bool) -> None:
        self.single_shot = value

    def setInterval(self, value: int) -> None:
        self.interval = value

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1


class _FakeAutosaveStore:
    def __init__(self) -> None:
        self.saved: list[tuple[str, str, dict[str, Any]]] = []
        self.deleted: list[tuple[str, dict[str, Any]]] = []

    def save_draft(self, file_path: str, content: str, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.saved.append((file_path, content, kwargs))

    def delete_draft(self, file_path: str, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.deleted.append((file_path, kwargs))


def _context_for_path(project_root: Path):
    def _resolve(_file_path: str) -> tuple[Optional[str], Optional[str]]:
        return ("proj_demo", str(project_root.resolve()))

    return _resolve


def test_schedule_autosave_starts_timer_and_flush_persists_draft(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "main.py"
    file_path.write_text("print('disk')\n", encoding="utf-8")
    manager = EditorManager()
    tab = manager.open_file(str(file_path.resolve())).tab
    autosave_store = _FakeAutosaveStore()
    timer = _FakeTimer()
    workflow = DraftAutosaveWorkflow(
        parent=None,
        autosave_store=autosave_store,  # type: ignore[arg-type]
        editor_manager=manager,
        context_for_path=_context_for_path(project_root),
        logger=logging.getLogger("test.draft_autosave_workflow"),
        autosave_timer=timer,  # type: ignore[arg-type]
    )

    workflow.schedule_autosave(tab.file_path, "print('draft')\n")
    assert timer.started == 1
    workflow.flush_pending_autosaves()

    assert len(autosave_store.saved) == 1
    saved_path, saved_content, saved_kwargs = autosave_store.saved[0]
    assert saved_path == tab.file_path
    assert saved_content == "print('draft')\n"
    assert saved_kwargs["project_id"] == "proj_demo"
    assert saved_kwargs["project_root"] == str(project_root.resolve())


def test_discard_drafts_for_paths_clears_pending_and_persisted_draft(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "main.py"
    file_path.write_text("print('disk')\n", encoding="utf-8")
    manager = EditorManager()
    tab = manager.open_file(str(file_path.resolve())).tab
    autosave_store = _FakeAutosaveStore()
    workflow = DraftAutosaveWorkflow(
        parent=None,
        autosave_store=autosave_store,  # type: ignore[arg-type]
        editor_manager=manager,
        context_for_path=_context_for_path(project_root),
        logger=logging.getLogger("test.draft_autosave_workflow"),
        autosave_timer=_FakeTimer(),  # type: ignore[arg-type]
    )

    workflow.schedule_autosave(tab.file_path, "print('draft')\n")
    workflow.discard_drafts_for_paths([tab.file_path])
    workflow.flush_pending_autosaves()

    assert autosave_store.saved == []
    assert (
        tab.file_path,
        {"project_id": "proj_demo", "project_root": str(project_root.resolve())},
    ) in autosave_store.deleted


def test_keep_drafts_for_paths_persists_restore_policy_and_clears_pending(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "main.py"
    file_path.write_text("print('disk')\n", encoding="utf-8")
    manager = EditorManager()
    tab = manager.open_file(str(file_path.resolve())).tab
    manager.update_tab_content(tab.file_path, "print('draft')\n")
    autosave_store = _FakeAutosaveStore()
    workflow = DraftAutosaveWorkflow(
        parent=None,
        autosave_store=autosave_store,  # type: ignore[arg-type]
        editor_manager=manager,
        context_for_path=_context_for_path(project_root),
        logger=logging.getLogger("test.draft_autosave_workflow"),
        autosave_timer=_FakeTimer(),  # type: ignore[arg-type]
    )

    workflow.schedule_autosave(tab.file_path, "older draft")
    workflow.keep_drafts_for_paths([tab.file_path])
    workflow.flush_pending_autosaves()

    assert autosave_store.saved == [
        (
            tab.file_path,
            "print('draft')\n",
            {
                "project_id": "proj_demo",
                "project_root": str(project_root.resolve()),
                "recovery_policy": DRAFT_RECOVERY_POLICY_RESTORE_SILENTLY,
                "source": DRAFT_SOURCE_KEPT_ON_EXIT,
                "last_known_mtime": tab.last_known_mtime,
            },
        )
    ]


def test_local_history_workflow_delegates_autosave_to_draft_module(tmp_path: Path) -> None:
    from app.persistence.local_history_store import LocalHistoryStore  # noqa: E402
    from app.shell.local_history_workflow import LocalHistoryWorkflow  # noqa: E402

    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "main.py"
    file_path.write_text("print('disk')\n", encoding="utf-8")
    manager = EditorManager()
    tab = manager.open_file(str(file_path.resolve())).tab
    autosave_store = _FakeAutosaveStore()
    timer = _FakeTimer()
    workflow = LocalHistoryWorkflow(
        parent=None,
        local_history_store=LocalHistoryStore(state_root=tmp_path / "state"),
        autosave_store=autosave_store,  # type: ignore[arg-type]
        autosave_timer=timer,  # type: ignore[arg-type]
        loaded_project=lambda: SimpleNamespace(
            project_root=str(project_root.resolve()),
            metadata=SimpleNamespace(project_id="proj_demo"),
        ),
        editor_manager=manager,
        editor_widget_for_path=lambda _path: None,
        open_file_in_editor=lambda _path: True,
        open_restored_history_buffer=lambda _path, _content: True,
        apply_text_to_open_tab=lambda _path, _content: None,
        tab_index_for_path=lambda _path: -1,
        refresh_tab_presentation=lambda _path: None,
        set_current_tab_index=lambda _index: None,
        show_status_message=lambda _message, _timeout: None,
        logger=logging.getLogger("test.draft_autosave_workflow"),
    )

    workflow.schedule_autosave(tab.file_path, "delegated draft")
    assert timer.started == 1
    workflow.flush_pending_autosaves()
    assert autosave_store.saved[0][1] == "delegated draft"
