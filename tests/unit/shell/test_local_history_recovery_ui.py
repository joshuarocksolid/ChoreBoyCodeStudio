"""Unit tests for draft recovery compare/restore behavior."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication, QDialog  # noqa: E402

from app.editors.editor_manager import EditorManager  # noqa: E402
from app.persistence.autosave_store import DraftEntry  # noqa: E402
from app.persistence.history_models import LocalHistoryCheckpoint  # noqa: E402
from app.persistence.local_history_store import LocalHistoryStore  # noqa: E402
from app.shell.local_history_dialog import LocalHistoryDialog  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _FakeAutosaveStore:
    def __init__(self, draft_entry: Optional[DraftEntry]) -> None:
        self.draft_entry = draft_entry
        self.deleted: list[tuple[str, dict[str, Any]]] = []

    def load_draft(self, file_path: str, **kwargs) -> Optional[DraftEntry]:  # type: ignore[no-untyped-def]
        _ = (file_path, kwargs)
        return self.draft_entry

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


def _build_window(tmp_path: Path, draft_text: str) -> tuple[MainWindow, EditorManager, object, _FakeEditorWidget, _FakeAutosaveStore]:
    file_path = tmp_path / "project" / "main.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("print('original')\n", encoding="utf-8")

    manager = EditorManager()
    opened = manager.open_file(str(file_path))
    autosave_store = _FakeAutosaveStore(
        DraftEntry(
            file_path=str(file_path.resolve()),
            content=draft_text,
            saved_at="2026-03-24T10:00:00",
        )
    )
    editor_widget = _FakeEditorWidget("print('original')\n")

    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = SimpleNamespace(
        project_root=str((tmp_path / "project").resolve()),
        metadata=SimpleNamespace(project_id="proj_demo"),
    )
    window_any._autosave_store = autosave_store
    window_any._editor_manager = manager
    window_any._editor_tabs_widget = None
    window_any._tab_index_for_path = lambda _path: -1
    window_any._refresh_tab_presentation = lambda *_args, **_kwargs: None
    scheduled: list[tuple[str, str]] = []
    window_any._schedule_autosave = lambda file_path, content: scheduled.append((file_path, content))
    return window, manager, opened.tab, editor_widget, autosave_store


def _checkpoint(revision_id: int, created_at: str, *, label: str = "", source: str = "save") -> LocalHistoryCheckpoint:
    return LocalHistoryCheckpoint(
        revision_id=revision_id,
        file_key="file_1",
        project_id="proj_demo",
        file_path="/tmp/project/main.py",
        relative_path="main.py",
        blob_sha256=f"sha-{revision_id}",
        created_at=created_at,
        source=source,
        label=label,
    )


def test_maybe_restore_draft_restores_into_buffer_and_reschedules_autosave(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, manager, tab_state, editor_widget, autosave_store = _build_window(tmp_path, "print('draft')\n")
    scheduled: list[tuple[str, str]] = []
    cast(Any, window)._schedule_autosave = lambda file_path, content: scheduled.append((file_path, content))

    class _AcceptDialog:
        discard_draft = False

        def __init__(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
            self.kwargs = kwargs

        def exec_(self) -> int:
            return QDialog.Accepted

    monkeypatch.setattr("app.shell.main_window.DraftRecoveryDialog", _AcceptDialog)

    MainWindow._maybe_restore_draft(window, tab_state, editor_widget)  # type: ignore[arg-type]

    assert editor_widget.replacements == ["print('draft')\n"]
    assert manager.get_tab(tab_state.file_path).current_content == "print('draft')\n"  # type: ignore[union-attr]
    assert scheduled == [(tab_state.file_path, "print('draft')\n")]
    assert autosave_store.deleted == []


def test_maybe_restore_draft_keep_disk_version_discards_saved_draft(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, _manager, tab_state, editor_widget, autosave_store = _build_window(tmp_path, "print('draft')\n")

    class _RejectDialog:
        discard_draft = True

        def __init__(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
            self.kwargs = kwargs

        def exec_(self) -> int:
            return QDialog.Rejected

    monkeypatch.setattr("app.shell.main_window.DraftRecoveryDialog", _RejectDialog)

    MainWindow._maybe_restore_draft(window, tab_state, editor_widget)  # type: ignore[arg-type]

    assert editor_widget.replacements == []
    assert autosave_store.deleted == [
        (
            tab_state.file_path,
            {
                "project_id": "proj_demo",
                "project_root": str((tmp_path / "project").resolve()),
            },
        )
    ]


def test_local_history_dialog_compares_selected_revision_with_current_and_previous() -> None:
    loader_calls: list[int] = []
    contents = {
        2: "print('second')\n",
        1: "print('first')\n",
    }
    dialog = LocalHistoryDialog(
        file_name="main.py",
        checkpoints=[
            _checkpoint(2, "2026-03-24T10:05:00", label="Second Save"),
            _checkpoint(1, "2026-03-24T10:00:00", label="First Save"),
        ],
        current_text="print('current')\n",
        checkpoint_content_loader=lambda revision_id: loader_calls.append(revision_id) or contents[revision_id],
        restore_to_buffer=lambda _content: None,
    )

    assert "Current Buffer" in dialog._diff_view.toPlainText()
    assert "2026-03-24T10:05:00" in dialog._diff_view.toPlainText()
    assert loader_calls == [2]

    dialog._compare_with_previous()

    diff_text = dialog._diff_view.toPlainText()
    assert "2026-03-24T10:00:00" in diff_text
    assert "2026-03-24T10:05:00" in diff_text
    assert loader_calls == [2, 1]

    dialog._compare_with_current()
    assert loader_calls == [2, 1]


def test_local_history_dialog_restore_to_buffer_uses_selected_revision() -> None:
    restored: list[str] = []
    dialog = LocalHistoryDialog(
        file_name="main.py",
        checkpoints=[_checkpoint(1, "2026-03-24T10:00:00", label="First Save")],
        current_text="print('current')\n",
        checkpoint_content_loader=lambda _revision_id: "print('restored')\n",
        restore_to_buffer=restored.append,
    )

    dialog._handle_restore()

    assert restored == ["print('restored')\n"]
    assert dialog.result() == QDialog.Accepted


def test_show_local_history_for_path_opens_dialog_and_restores_into_live_buffer(
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

    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = SimpleNamespace(
        project_root=str(project_root.resolve()),
        metadata=SimpleNamespace(project_id="proj_demo"),
    )
    window_any._local_history_store = local_history_store
    window_any._editor_manager = manager
    window_any._editor_widgets_by_path = {str(file_path.resolve()): editor_widget}
    window_any._editor_tabs_widget = None
    window_any._tab_index_for_path = lambda _path: -1
    window_any._refresh_tab_presentation = lambda *_args, **_kwargs: None
    scheduled: list[tuple[str, str]] = []
    window_any._schedule_autosave = lambda file_path, content: scheduled.append((file_path, content))

    captured: dict[str, Any] = {}

    class _FakeDialog:
        def __init__(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
            captured.update(kwargs)

        def exec_(self) -> int:
            restore = cast(Any, captured["restore_to_buffer"])
            restore("print('history')\n")
            return QDialog.Accepted

    monkeypatch.setattr("app.shell.main_window.LocalHistoryDialog", _FakeDialog)

    MainWindow._show_local_history_for_path(window, str(file_path.resolve()))

    assert captured["file_name"] == "main.py"
    assert captured["current_text"] == "print('current')\n"
    assert len(cast(Any, captured["checkpoints"])) == 1
    assert editor_widget.replacements == ["print('history')\n"]
    assert manager.get_tab(str(file_path.resolve())).current_content == "print('history')\n"  # type: ignore[union-attr]
    assert scheduled == [(str(file_path.resolve()), "print('history')\n")]
