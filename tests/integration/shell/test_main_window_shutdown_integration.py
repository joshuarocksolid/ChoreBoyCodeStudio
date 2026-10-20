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
from app.shell import close_while_running_dialog
from app.shell.close_while_running_dialog import CloseRunChoice
from app.shell.main_window import MainWindow
from app.shell.python_console_history import load_python_console_history
from testing.main_window_shutdown import shutdown_main_window_for_test
from testing.main_window_test_helpers import prepare_main_window_for_test
from tests.support.run_group_heartbeat import heartbeat_command, is_beating, kill_group, wait_for_beats
from tests.support.subprocess_guards import skip_unless_can_exec

pytestmark = pytest.mark.integration


def test_close_event_stops_active_run_before_accepting_exit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    shell_qapp,
) -> None:
    app = shell_qapp
    window = MainWindow(state_root=str(tmp_path.resolve()))
    prepare_main_window_for_test(window, app=app)
    try:
        stop_calls: list[str] = []
        clear_mode_calls: list[str] = []
        console_session_updates: list[bool] = []

        monkeypatch.setattr(window._save_workflow, "confirm_proceed_with_unsaved_changes", lambda _action: True)
        monkeypatch.setattr(window._run_service.supervisor, "is_running", lambda: True)
        monkeypatch.setattr(close_while_running_dialog, "prompt_close_while_running", lambda *_a: CloseRunChoice.STOP)
        monkeypatch.setattr(window._run_service, "stop_run", lambda: stop_calls.append("stop"))
        monkeypatch.setattr(
            window._run_session_controller,
            "clear_active_session",
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
    finally:
        shutdown_main_window_for_test(window, app)


def test_close_event_blocks_post_close_run_event_application(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    shell_qapp,
) -> None:
    app = shell_qapp
    window = MainWindow(state_root=str(tmp_path.resolve()))
    prepare_main_window_for_test(window, app=app)
    try:
        applied_events: list[ProcessEvent] = []
        stop_calls: list[str] = []

        monkeypatch.setattr(window._save_workflow, "confirm_proceed_with_unsaved_changes", lambda _action: True)
        monkeypatch.setattr(window._run_service.supervisor, "is_running", lambda: True)
        monkeypatch.setattr(close_while_running_dialog, "prompt_close_while_running", lambda *_a: CloseRunChoice.STOP)
        monkeypatch.setattr(window._run_service, "stop_run", lambda: stop_calls.append("stop"))
        monkeypatch.setattr(window._run_event_workflow, "apply_run_event", lambda event: applied_events.append(event))

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
        window._run_event_workflow.enqueue_run_event(ProcessEvent(event_type="state", state="exited"))
        window._run_event_workflow.process_queued_run_events()
        assert window._run_event_queue.empty() is True
        assert applied_events == []
    finally:
        shutdown_main_window_for_test(window, app)


def test_close_without_active_run_does_not_ask_about_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    shell_qapp,
) -> None:
    app = shell_qapp
    window = MainWindow(state_root=str(tmp_path.resolve()))
    prepare_main_window_for_test(window, app=app)
    try:
        prompts: list[object] = []
        monkeypatch.setattr(window._save_workflow, "confirm_proceed_with_unsaved_changes", lambda _action: True)
        monkeypatch.setattr(window._run_service.supervisor, "is_running", lambda: False)
        monkeypatch.setattr(close_while_running_dialog, "prompt_close_while_running", lambda *a: prompts.append(a))

        close_event = QCloseEvent()
        window.closeEvent(close_event)

        assert close_event.isAccepted() is True
        assert prompts == []
    finally:
        shutdown_main_window_for_test(window, app)


def test_close_cancel_keeps_window_open_and_run_untouched(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    shell_qapp,
) -> None:
    app = shell_qapp
    window = MainWindow(state_root=str(tmp_path.resolve()))
    prepare_main_window_for_test(window, app=app)
    try:
        calls: list[str] = []
        monkeypatch.setattr(window._run_service.supervisor, "is_running", lambda: True)
        monkeypatch.setattr(close_while_running_dialog, "prompt_close_while_running", lambda *_a: CloseRunChoice.CANCEL)
        monkeypatch.setattr(window._run_service, "stop_run", lambda: calls.append("stop"))
        monkeypatch.setattr(window._run_service, "detach_run", lambda: calls.append("detach"))
        monkeypatch.setattr(
            window._save_workflow,
            "request_unsaved_changes_decision",
            lambda *_a, **_k: calls.append("unsaved-prompt"),
        )

        close_event = QCloseEvent()
        window.closeEvent(close_event)

        assert close_event.isAccepted() is False
        assert calls == []
        assert window._is_shutting_down is False
    finally:
        shutdown_main_window_for_test(window, app)


@pytest.mark.slow
@pytest.mark.timeout(120)
@pytest.mark.parametrize(
    ("choice", "expect_alive"),
    [(CloseRunChoice.KEEP, True), (CloseRunChoice.STOP, False)],
)
def test_close_with_running_program_keeps_or_stops_its_process_group(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    shell_qapp,
    choice: CloseRunChoice,
    expect_alive: bool,
) -> None:
    """Keep It Running leaves the program and the child it started alive (and able
    to print); Stop It ends both. Mirrors Clair's FreeCAD window (repro-A issue 4)."""
    skip_unless_can_exec()
    app = shell_qapp
    beats = tmp_path / "beats"
    beats.mkdir()
    window = MainWindow(state_root=str(tmp_path.resolve() / "state"))
    prepare_main_window_for_test(window, app=app)
    runner_pid = None
    try:
        monkeypatch.setattr(window._save_workflow, "confirm_proceed_with_unsaved_changes", lambda _action: True)
        monkeypatch.setattr(close_while_running_dialog, "prompt_close_while_running", lambda *_a: choice)
        runner_pid = window._run_service.supervisor.start(heartbeat_command(beats), cwd=str(tmp_path))
        assert wait_for_beats(beats)

        close_event = QCloseEvent()
        window.closeEvent(close_event)
        assert close_event.isAccepted() is True

        # Let the editor's reader threads drop their copies of the pipes, as on exit.
        app.processEvents()
        is_beating(beats / "parent", window_seconds=0.5)
        assert is_beating(beats / "parent") is expect_alive
        assert is_beating(beats / "child") is expect_alive
    finally:
        kill_group(runner_pid)
        shutdown_main_window_for_test(window, app)


def test_close_event_persists_python_console_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    shell_qapp,
) -> None:
    app = shell_qapp
    state_root = tmp_path.resolve()
    window = MainWindow(state_root=str(state_root))
    prepare_main_window_for_test(window, app=app)
    try:
        assert window._python_console_widget is not None
        window._python_console_widget.set_history(["print('saved')"])

        monkeypatch.setattr(window._save_workflow, "confirm_proceed_with_unsaved_changes", lambda _action: True)
        monkeypatch.setattr(window._run_service.supervisor, "is_running", lambda: False)

        close_event = QCloseEvent()
        window.closeEvent(close_event)

        assert close_event.isAccepted() is True
        history_path = global_python_console_history_path(str(state_root))
        assert load_python_console_history(history_path, max_entries=200) == ["print('saved')"]
    finally:
        shutdown_main_window_for_test(window, app)


def test_close_event_discard_deletes_recovery_draft(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    shell_qapp,
) -> None:
    app = shell_qapp
    state_root = tmp_path / "state"
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "main.py"
    file_path.write_text("print('disk')\n", encoding="utf-8")
    window = MainWindow(state_root=str(state_root.resolve()))
    prepare_main_window_for_test(window, app=app)
    try:
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
    finally:
        shutdown_main_window_for_test(window, app)


def test_close_event_keep_marks_draft_for_silent_restore(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    shell_qapp,
) -> None:
    app = shell_qapp
    state_root = tmp_path / "state"
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "main.py"
    file_path.write_text("print('disk')\n", encoding="utf-8")
    window = MainWindow(state_root=str(state_root.resolve()))
    prepare_main_window_for_test(window, app=app)
    try:
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
    finally:
        shutdown_main_window_for_test(window, app)
