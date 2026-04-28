"""Integration tests for main-window shutdown behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtGui import QCloseEvent
from app.bootstrap.paths import global_python_console_history_path
from app.run.process_supervisor import ProcessEvent
from app.persistence.history_models import DRAFT_RECOVERY_POLICY_RESTORE_SILENTLY
from app.shell.document_safety import (
    DirtyBufferSnapshot,
    DocumentCloseIntent,
    DocumentSafetyDecision,
    DocumentScope,
)
from app.shell.main_window import MainWindow
from app.shell.python_console_history import load_python_console_history

pytestmark = pytest.mark.integration


def _ensure_qapplication(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide2.QtWidgets import QApplication
    import PySide2.QtGui as qt_gui
    import PySide2.QtWidgets as qt_widgets

    if not hasattr(qt_widgets, "QActionGroup"):
        qt_widgets.QActionGroup = qt_gui.QActionGroup  # type: ignore[attr-defined]

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_close_event_stops_active_run_before_accepting_exit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = _ensure_qapplication(monkeypatch)
    window = MainWindow(state_root=str(tmp_path.resolve()))

    stop_calls: list[str] = []
    clear_mode_calls: list[str] = []
    console_session_updates: list[bool] = []

    monkeypatch.setattr(window._save_workflow, "confirm_proceed_with_unsaved_changes", lambda _action: True)
    monkeypatch.setattr(window._run_service.supervisor, "is_running", lambda: True)
    monkeypatch.setattr(window._run_service, "stop_run", lambda: stop_calls.append("stop"))
    monkeypatch.setattr(
        window._run_session_controller,
        "clear_active_session_mode",
        lambda: clear_mode_calls.append("cleared"),
    )
    assert window._python_console_widget is not None
    monkeypatch.setattr(
        window._python_console_widget,
        "set_session_active",
        lambda active: console_session_updates.append(active),
    )

    close_event = QCloseEvent()
    window.closeEvent(close_event)

    assert close_event.isAccepted() is True
    assert stop_calls == ["stop"]
    assert clear_mode_calls == ["cleared"]
    assert console_session_updates == [False]


def test_close_event_blocks_post_close_run_event_application(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = _ensure_qapplication(monkeypatch)
    window = MainWindow(state_root=str(tmp_path.resolve()))

    applied_events: list[ProcessEvent] = []
    stop_calls: list[str] = []

    monkeypatch.setattr(window._save_workflow, "confirm_proceed_with_unsaved_changes", lambda _action: True)
    monkeypatch.setattr(window._run_service.supervisor, "is_running", lambda: True)
    monkeypatch.setattr(window._run_service, "stop_run", lambda: stop_calls.append("stop"))
    monkeypatch.setattr(window, "_apply_run_event", lambda event: applied_events.append(event))

    # Seed a queued event to verify shutdown drains it rather than applying.
    window._run_event_queue.put(ProcessEvent(event_type="state", state="running"))
    close_event = QCloseEvent()
    window.closeEvent(close_event)

    assert close_event.isAccepted() is True
    assert stop_calls == ["stop"]
    assert window._is_shutting_down is True
    assert window._run_event_queue.empty() is True
    assert applied_events == []

    # New events arriving from background threads are ignored once shutdown begins.
    window._enqueue_run_event(ProcessEvent(event_type="state", state="exited"))
    window._process_queued_run_events()
    assert window._run_event_queue.empty() is True
    assert applied_events == []


def test_close_event_persists_python_console_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = _ensure_qapplication(monkeypatch)
    state_root = tmp_path.resolve()
    window = MainWindow(state_root=str(state_root))
    assert window._python_console_widget is not None
    window._python_console_widget.set_history(["print('saved')"])

    monkeypatch.setattr(window._save_workflow, "confirm_proceed_with_unsaved_changes", lambda _action: True)
    monkeypatch.setattr(window._run_service.supervisor, "is_running", lambda: False)

    close_event = QCloseEvent()
    window.closeEvent(close_event)

    assert close_event.isAccepted() is True
    history_path = global_python_console_history_path(str(state_root))
    assert load_python_console_history(history_path, max_entries=200) == ["print('saved')"]


def test_close_event_discard_deletes_recovery_draft(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = _ensure_qapplication(monkeypatch)
    state_root = tmp_path / "state"
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "main.py"
    file_path.write_text("print('disk')\n", encoding="utf-8")
    window = MainWindow(state_root=str(state_root.resolve()))
    window._editor_manager.open_file(str(file_path.resolve()))
    window._editor_manager.update_tab_content(str(file_path.resolve()), "print('draft')\n")
    project_id, project_context_root = window._local_history_workflow.local_history_context_for_path(
        str(file_path.resolve())
    )
    window._local_history_workflow.autosave_store.save_draft(
        str(file_path.resolve()),
        "print('draft')\n",
        project_id=project_id,
        project_root=project_context_root,
    )
    monkeypatch.setattr(window._run_service.supervisor, "is_running", lambda: False)
    monkeypatch.setattr(
        window._save_workflow,
        "request_unsaved_changes_decision",
        lambda *_args, **_kwargs: DocumentSafetyDecision(
            intent=DocumentCloseIntent.DISCARD,
            scope=DocumentScope.APPLICATION,
            dirty_buffers=(
                DirtyBufferSnapshot(
                    file_path=str(file_path.resolve()),
                    display_name="main.py",
                    current_content="print('draft')\n",
                    original_content="print('disk')\n",
                ),
            ),
        ),
    )

    close_event = QCloseEvent()
    window.closeEvent(close_event)

    assert close_event.isAccepted() is True
    assert (
        window._local_history_workflow.autosave_store.load_draft(
            str(file_path.resolve()),
            project_id=project_id,
            project_root=project_context_root,
        )
        is None
    )


def test_close_event_keep_marks_draft_for_silent_restore(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = _ensure_qapplication(monkeypatch)
    state_root = tmp_path / "state"
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "main.py"
    file_path.write_text("print('disk')\n", encoding="utf-8")
    window = MainWindow(state_root=str(state_root.resolve()))
    window._editor_manager.open_file(str(file_path.resolve()))
    window._editor_manager.update_tab_content(str(file_path.resolve()), "print('draft')\n")
    project_id, project_context_root = window._local_history_workflow.local_history_context_for_path(
        str(file_path.resolve())
    )
    monkeypatch.setattr(window._run_service.supervisor, "is_running", lambda: False)
    monkeypatch.setattr(
        window._save_workflow,
        "request_unsaved_changes_decision",
        lambda *_args, **_kwargs: DocumentSafetyDecision(
            intent=DocumentCloseIntent.KEEP_FOR_NEXT_LAUNCH,
            scope=DocumentScope.APPLICATION,
            dirty_buffers=(
                DirtyBufferSnapshot(
                    file_path=str(file_path.resolve()),
                    display_name="main.py",
                    current_content="print('draft')\n",
                    original_content="print('disk')\n",
                ),
            ),
        ),
    )

    close_event = QCloseEvent()
    window.closeEvent(close_event)

    draft = window._local_history_workflow.autosave_store.load_draft(
        str(file_path.resolve()),
        project_id=project_id,
        project_root=project_context_root,
    )
    assert close_event.isAccepted() is True
    assert draft is not None
    assert draft.content == "print('draft')\n"
    assert draft.recovery_policy == DRAFT_RECOVERY_POLICY_RESTORE_SILENTLY
