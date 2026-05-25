"""Unit tests for the shell local-history workflow controller."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QDialog  # noqa: E402

from app.editors.editor_manager import EditorManager  # noqa: E402
from app.persistence.autosave_store import DraftEntry  # noqa: E402
from app.persistence.history_models import LocalHistoryCheckpoint  # noqa: E402
from app.persistence.local_history_store import LocalHistoryStore  # noqa: E402
from app.shell.local_history_workflow import LocalHistoryWorkflow  # noqa: E402

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
    def __init__(self, draft_entry: Optional[DraftEntry] = None) -> None:
        self.draft_entry = draft_entry
        self.saved: list[tuple[str, str, dict[str, Any]]] = []
        self.deleted: list[tuple[str, dict[str, Any]]] = []

    def load_draft(self, file_path: str, **kwargs) -> Optional[DraftEntry]:  # type: ignore[no-untyped-def]
        self.deleted.append(("load", {"file_path": file_path, **kwargs}))
        return self.draft_entry

    def save_draft(self, file_path: str, content: str, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.saved.append((file_path, content, kwargs))

    def delete_draft(self, file_path: str, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.deleted.append((file_path, kwargs))


class _FakeEditorWidget:
    def __init__(self, text: str) -> None:
        self.text = text
        self.replacements: list[str] = []

    def toPlainText(self) -> str:
        return self.text

    def replace_document_text(self, replacement_text: str) -> bool:
        self.replacements.append(replacement_text)
        self.text = replacement_text
        return True


def _loaded_project(project_root: Path) -> object:
    return SimpleNamespace(
        project_root=str(project_root.resolve()),
        metadata=SimpleNamespace(project_id="proj_demo"),
    )


def _checkpoint(revision_id: int, *, file_path: str = "/tmp/project/main.py") -> LocalHistoryCheckpoint:
    return LocalHistoryCheckpoint(
        revision_id=revision_id,
        file_key="file_1",
        project_id="proj_demo",
        file_path=file_path,
        relative_path="main.py",
        blob_sha256=f"sha-{revision_id}",
        created_at="2026-03-24T10:00:00",
        source="save",
        label="Saved Revision",
    )


def test_maybe_restore_draft_restores_into_buffer_and_reschedules_autosave(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "main.py"
    file_path.write_text("print('disk')\n", encoding="utf-8")
    manager = EditorManager()
    tab = manager.open_file(str(file_path.resolve())).tab
    editor_widget = _FakeEditorWidget("print('disk')\n")
    autosave_store = _FakeAutosaveStore(
        DraftEntry(
            file_path=str(file_path.resolve()),
            content="print('draft')\n",
            saved_at="2026-03-24T10:00:00",
        )
    )
    timer = _FakeTimer()

    class _AcceptDialog:
        discard_draft = False

        def __init__(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
            self.kwargs = kwargs

        def exec_(self) -> int:
            return QDialog.Accepted

    monkeypatch.setattr("app.shell.local_history_workflow.DraftRecoveryDialog", _AcceptDialog)

    workflow = LocalHistoryWorkflow(
        parent=None,
        local_history_store=LocalHistoryStore(state_root=tmp_path / "state"),
        autosave_store=autosave_store,  # type: ignore[arg-type]
        autosave_timer=timer,  # type: ignore[arg-type]
        loaded_project=lambda: _loaded_project(project_root),
        editor_manager=manager,
        editor_widget_for_path=lambda _path: editor_widget,  # type: ignore[return-value]
        open_file_in_editor=lambda _path: True,
        open_restored_history_buffer=lambda _path, _content: True,
        apply_text_to_open_tab=lambda path, content: editor_widget.replace_document_text(content),
        tab_index_for_path=lambda _path: -1,
        refresh_tab_presentation=lambda _path: None,
        set_current_tab_index=lambda _index: None,
        show_status_message=lambda _message, _timeout: None,
        logger=logging.getLogger("test.local_history_workflow"),
    )

    workflow.maybe_restore_draft(tab, editor_widget)  # type: ignore[arg-type]

    assert editor_widget.replacements == ["print('draft')\n"]
    assert manager.get_tab(tab.file_path).current_content == "print('draft')\n"  # type: ignore[union-attr]
    assert timer.started == 1
    workflow.flush_pending_autosaves()
    assert len(autosave_store.saved) == 1
    saved_path, saved_content, saved_kwargs = autosave_store.saved[0]
    assert saved_path == tab.file_path
    assert saved_content == "print('draft')\n"
    assert saved_kwargs["project_id"] == "proj_demo"
    assert saved_kwargs["project_root"] == str(project_root.resolve())


def test_review_draft_entry_shows_dialog_when_draft_matches_disk_but_not_buffer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "main.py"
    file_path.write_text("print('disk')\n", encoding="utf-8")
    manager = EditorManager()
    tab = manager.open_file(str(file_path.resolve())).tab
    manager.update_tab_content(tab.file_path, "print('dirty')\n")
    editor_widget = _FakeEditorWidget("print('dirty')\n")
    autosave_store = _FakeAutosaveStore(
        DraftEntry(
            file_path=str(file_path.resolve()),
            content="print('disk')\n",
            saved_at="2026-03-24T10:00:00",
        )
    )
    captured: list[dict[str, object]] = []

    class _RecordingDialog:
        discard_draft = False

        def __init__(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
            captured.append(kwargs)

        def exec_(self) -> int:
            return QDialog.Rejected

    monkeypatch.setattr("app.shell.local_history_workflow.DraftRecoveryDialog", _RecordingDialog)

    workflow = LocalHistoryWorkflow(
        parent=None,
        local_history_store=LocalHistoryStore(state_root=tmp_path / "state"),
        autosave_store=autosave_store,  # type: ignore[arg-type]
        autosave_timer=_FakeTimer(),  # type: ignore[arg-type]
        loaded_project=lambda: _loaded_project(project_root),
        editor_manager=manager,
        editor_widget_for_path=lambda _path: editor_widget,  # type: ignore[return-value]
        open_file_in_editor=lambda _path: True,
        open_restored_history_buffer=lambda _path, _content: True,
        apply_text_to_open_tab=lambda _path, _content: None,
        tab_index_for_path=lambda _path: -1,
        refresh_tab_presentation=lambda _path: None,
        set_current_tab_index=lambda _index: None,
        show_status_message=lambda _message, _timeout: None,
        logger=logging.getLogger("test.local_history_workflow"),
    )

    draft_entry = DraftEntry(
        file_path=str(file_path.resolve()),
        content="print('disk')\n",
        saved_at="2026-03-24T10:00:00",
    )
    workflow._review_draft_entry(draft_entry)

    assert len(captured) == 1
    assert captured[0]["disk_text"] == "print('disk')\n"
    assert captured[0]["draft_text"] == "print('disk')\n"
    assert captured[0]["tokens"] is None or captured[0]["disk_saved_at"] is not None
    assert autosave_store.deleted == []


def test_maybe_restore_draft_keep_disk_version_discards_saved_draft(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "main.py"
    file_path.write_text("print('disk')\n", encoding="utf-8")
    manager = EditorManager()
    tab = manager.open_file(str(file_path.resolve())).tab
    editor_widget = _FakeEditorWidget("print('disk')\n")
    autosave_store = _FakeAutosaveStore(
        DraftEntry(
            file_path=str(file_path.resolve()),
            content="print('draft')\n",
            saved_at="2026-03-24T10:00:00",
        )
    )

    class _RejectDialog:
        discard_draft = True

        def __init__(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
            self.kwargs = kwargs

        def exec_(self) -> int:
            return QDialog.Rejected

    monkeypatch.setattr("app.shell.local_history_workflow.DraftRecoveryDialog", _RejectDialog)

    workflow = LocalHistoryWorkflow(
        parent=None,
        local_history_store=LocalHistoryStore(state_root=tmp_path / "state"),
        autosave_store=autosave_store,  # type: ignore[arg-type]
        autosave_timer=_FakeTimer(),  # type: ignore[arg-type]
        loaded_project=lambda: _loaded_project(project_root),
        editor_manager=manager,
        editor_widget_for_path=lambda _path: editor_widget,  # type: ignore[return-value]
        open_file_in_editor=lambda _path: True,
        open_restored_history_buffer=lambda _path, _content: True,
        apply_text_to_open_tab=lambda _path, _content: None,
        tab_index_for_path=lambda _path: -1,
        refresh_tab_presentation=lambda _path: None,
        set_current_tab_index=lambda _index: None,
        show_status_message=lambda _message, _timeout: None,
        logger=logging.getLogger("test.local_history_workflow"),
    )

    workflow.maybe_restore_draft(tab, editor_widget)  # type: ignore[arg-type]

    assert editor_widget.replacements == []
    assert (
        tab.file_path,
        {"project_id": "proj_demo", "project_root": str(project_root.resolve())},
    ) in autosave_store.deleted


def test_show_local_history_for_path_opens_dialog_and_restores_live_buffer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = tmp_path / "state"
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "main.py"
    file_path.write_text("print('disk')\n", encoding="utf-8")
    manager = EditorManager()
    manager.open_file(str(file_path.resolve()))
    manager.update_tab_content(str(file_path.resolve()), "print('current')\n")
    editor_widget = _FakeEditorWidget("print('current')\n")
    local_history_store = LocalHistoryStore(state_root=state_root)
    local_history_store.create_checkpoint(
        str(file_path.resolve()),
        "print('history')\n",
        source="save",
        label="Saved Revision",
        project_id="proj_demo",
        project_root=str(project_root.resolve()),
    )
    captured: dict[str, Any] = {}

    class _FakeDialog:
        def __init__(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
            captured.update(kwargs)

        def exec_(self) -> int:
            restore = captured["restore_to_buffer"]
            restore("print('history')\n")
            return QDialog.Accepted

    monkeypatch.setattr("app.shell.local_history_workflow.LocalHistoryDialog", _FakeDialog)
    timer = _FakeTimer()
    workflow = LocalHistoryWorkflow(
        parent=None,
        local_history_store=local_history_store,
        autosave_store=_FakeAutosaveStore(),  # type: ignore[arg-type]
        autosave_timer=timer,  # type: ignore[arg-type]
        loaded_project=lambda: _loaded_project(project_root),
        editor_manager=manager,
        editor_widget_for_path=lambda _path: editor_widget,  # type: ignore[return-value]
        open_file_in_editor=lambda _path: True,
        open_restored_history_buffer=lambda _path, _content: True,
        apply_text_to_open_tab=lambda path, content: editor_widget.replace_document_text(content),
        tab_index_for_path=lambda _path: -1,
        refresh_tab_presentation=lambda _path: None,
        set_current_tab_index=lambda _index: None,
        show_status_message=lambda _message, _timeout: None,
        logger=logging.getLogger("test.local_history_workflow"),
    )

    workflow.show_local_history_for_path(str(file_path.resolve()))

    assert captured["file_name"] == "main.py"
    assert captured["current_text"] == "print('current')\n"
    assert len(captured["checkpoints"]) == 1
    assert editor_widget.replacements == ["print('history')\n"]
    assert manager.get_tab(str(file_path.resolve())).current_content == "print('history')\n"  # type: ignore[union-attr]
    assert timer.started == 1


def test_restore_deleted_history_path_opens_dirty_buffer_without_disk_write(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "deleted.py"
    manager = EditorManager()
    opened_buffers: list[tuple[str, str]] = []
    applied: list[tuple[str, str]] = []

    def open_restored(path: str, content: str) -> bool:
        opened_buffers.append((path, content))
        manager.open_file_with_content(path, content, original_content="", preview=False, last_known_mtime=None)
        return True

    workflow = LocalHistoryWorkflow(
        parent=None,
        local_history_store=LocalHistoryStore(state_root=tmp_path / "state"),
        autosave_store=_FakeAutosaveStore(),  # type: ignore[arg-type]
        autosave_timer=_FakeTimer(),  # type: ignore[arg-type]
        loaded_project=lambda: _loaded_project(project_root),
        editor_manager=manager,
        editor_widget_for_path=lambda _path: None,
        open_file_in_editor=lambda _path: False,
        open_restored_history_buffer=open_restored,
        apply_text_to_open_tab=lambda path, content: applied.append((path, content)),
        tab_index_for_path=lambda _path: -1,
        refresh_tab_presentation=lambda _path: None,
        set_current_tab_index=lambda _index: None,
        show_status_message=lambda _message, _timeout: None,
        logger=logging.getLogger("test.local_history_workflow"),
    )

    workflow.restore_local_history_content_to_buffer(str(file_path.resolve()), "print('history')\n")

    assert not file_path.exists()
    assert opened_buffers == [(str(file_path.resolve()), "print('history')\n")]
    assert applied == [(str(file_path.resolve()), "print('history')\n")]
    restored_tab = manager.get_tab(str(file_path.resolve()))
    assert restored_tab is not None
    assert restored_tab.current_content == "print('history')\n"
    assert restored_tab.is_dirty


def test_checkpoint_skip_uses_current_retention_policy_for_status(tmp_path: Path) -> None:
    class _SkippingStore:
        def create_checkpoint(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            return None

        def checkpoint_skip_reason(self, *_args, **_kwargs) -> str:  # type: ignore[no-untyped-def]
            return "too_large"

    messages: list[str] = []
    workflow = LocalHistoryWorkflow(
        parent=None,
        local_history_store=_SkippingStore(),  # type: ignore[arg-type]
        autosave_store=_FakeAutosaveStore(),  # type: ignore[arg-type]
        autosave_timer=_FakeTimer(),  # type: ignore[arg-type]
        loaded_project=lambda: None,
        editor_manager=EditorManager(),
        editor_widget_for_path=lambda _path: None,
        open_file_in_editor=lambda _path: False,
        open_restored_history_buffer=lambda _path, _content: False,
        apply_text_to_open_tab=lambda _path, _content: None,
        tab_index_for_path=lambda _path: -1,
        refresh_tab_presentation=lambda _path: None,
        set_current_tab_index=lambda _index: None,
        show_status_message=lambda message, _timeout: messages.append(message),
        logger=logging.getLogger("test.local_history_workflow"),
    )

    workflow.record_checkpoint(str(tmp_path / "large.py"), "x", source="save")

    assert messages
    assert "tracking limit" in messages[0]


