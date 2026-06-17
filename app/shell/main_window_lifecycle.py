"""Main window shutdown and close-event lifecycle."""

from __future__ import annotations

from typing import Any

from PySide2.QtGui import QCloseEvent

from app.shell.document_safety import DocumentScope
from app.shell.python_console_history import save_python_console_history


class MainWindowLifecycle:
    """Coordinates unsaved-change prompts, teardown, and persistence on close."""

    @staticmethod
    def handle_close_event(window: Any, event: QCloseEvent) -> None:
        decision = window._save_workflow.request_unsaved_changes_decision(
            "exiting",
            scope=DocumentScope.APPLICATION,
            allow_keep_for_next_launch=True,
        )
        if not window._save_workflow.apply_unsaved_changes_decision(decision):
            event.ignore()
            return
        window._is_shutting_down = True
        MainWindowLifecycle.begin_shutdown_teardown(window)
        MainWindowLifecycle.stop_active_run_before_close(window)
        if window._status_controller is not None:
            window._status_controller.set_editor_status(file_name=None, line=None, column=None, is_dirty=False)
        window._shell_layout_workflow.persist_to_settings()
        window._local_history_workflow.persist_session_state()
        if window._python_console_widget is not None:
            try:
                save_python_console_history(
                    window._python_console_history_path,
                    window._python_console_widget.history_snapshot(),
                    max_entries=200,
                )
            except OSError as exc:
                window._logger.warning("Unable to persist python console history: %s", exc)
        event.accept()

    @staticmethod
    def begin_shutdown_teardown(window: Any) -> None:
        window._local_history_workflow.stop_autosave_timer()
        window._auto_save_to_file_timer.stop()
        window._realtime_lint_timer.stop()
        window._project_tree_preview_click_timer.stop()
        window._pending_project_tree_preview_path = None
        window._pending_realtime_lint_file_path = None
        if hasattr(window, "_run_event_timer"):
            window._run_event_timer.stop()
        if hasattr(window, "_repl_event_timer"):
            window._repl_event_timer.stop()
        if hasattr(window, "_external_change_poll_timer"):
            window._external_change_poll_timer.stop()
        if hasattr(window, "_restore_project_timer"):
            window._restore_project_timer.stop()
        if hasattr(window, "_auto_start_repl_timer"):
            window._auto_start_repl_timer.stop()
        if hasattr(window, "_runtime_probe_timer"):
            window._runtime_probe_timer.stop()
        if hasattr(window, "_startup_probe_refresh_timer"):
            window._startup_probe_refresh_timer.stop()
        window._startup_capability_facade.set_refresh_callback(None)
        MainWindowLifecycle.drain_run_event_queue(window)
        window._background_tasks.cancel_all()
        window._background_tasks.shutdown(wait=False)
        if hasattr(window, "_semantic_session"):
            window._intelligence_controller.cancel_all()
            window._intelligence_controller.shutdown()
        if hasattr(window, "_intelligence_cache_workflow"):
            window._intelligence_cache_workflow.cancel_symbol_indexing()
        if window._search_sidebar is not None:
            window._search_sidebar.cancel_active_search()
        window._debug_inspector_workflow.clear_debug_execution_indicator()
        if window._debug_panel is not None:
            window._debug_panel.set_command_input_enabled(False)

    @staticmethod
    def drain_run_event_queue(window: Any) -> None:
        window._run_event_workflow.drain_run_event_queue()

    @staticmethod
    def stop_active_run_before_close(window: Any) -> None:
        if window._run_service.supervisor.is_running():
            try:
                window._run_service.stop_run()
            except Exception as exc:
                window._logger.warning("Failed to stop active run during window close: %s", exc)

        window._repl_manager.shutdown()
        window._plugin_runtime_manager.stop()
        window._run_session_controller.clear_active_session_mode()
        window._run_event_workflow.set_run_status("idle")
        if window._python_console_widget is not None:
            window._python_console_widget.set_session_active(False)
