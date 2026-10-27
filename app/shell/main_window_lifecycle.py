"""Main window shutdown and close-event lifecycle."""

from __future__ import annotations

from typing import Any

from app.qt.QtGui import QCloseEvent

from app.shell import close_while_running_dialog
from app.shell.close_while_running_dialog import CloseRunChoice, build_running_program_summary
from app.shell.document_safety import DocumentScope
from app.shell.python_console_history import save_python_console_history
from app.shell.tab_close_blockers import confirm_tab_close_blockers


class MainWindowLifecycle:
    """Coordinates unsaved-change prompts, teardown, and persistence on close."""

    @staticmethod
    def handle_close_event(window: Any, event: QCloseEvent) -> None:
        run_choice = MainWindowLifecycle.ask_about_active_run(window)
        if run_choice == CloseRunChoice.CANCEL:
            event.ignore()
            return
        registry = getattr(window, "_tab_content_registry", None)
        editor_manager = getattr(window, "_editor_manager", None)
        if registry is not None and editor_manager is not None:
            open_paths = [tab.file_path for tab in editor_manager.all_tabs()]
            if not confirm_tab_close_blockers(window, registry, open_paths):
                event.ignore()
                return
        decision = window._save_workflow.request_unsaved_changes_decision(
            "exiting",
            scope=DocumentScope.APPLICATION,
            allow_keep_for_next_launch=True,
        )
        if not window._save_workflow.apply_unsaved_changes_decision(decision):
            event.ignore()
            return
        window._is_shutting_down = True
        if hasattr(window, "_run_debug_presenter"):
            window._run_debug_presenter.clear_pending_restart()
        MainWindowLifecycle.begin_shutdown_teardown(window)
        MainWindowLifecycle.stop_active_run_before_close(
            window,
            keep_running=run_choice == CloseRunChoice.KEEP,
        )
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
    def ask_about_active_run(window: Any) -> CloseRunChoice | None:
        """Ask what to do with a program still running from CBCS; ``None`` when nothing runs."""
        run_service = window._run_service
        if not run_service.supervisor.is_running():
            return None
        run_log_panel = getattr(window, "_run_log_panel", None)
        summary = build_running_program_summary(
            run_service.current_session,
            loaded_project=getattr(window, "_loaded_project", None),
            process_id=run_service.supervisor.process_id,
            freecad_window_seen=bool(run_log_panel is not None and run_log_panel.saw_freecad_window_start),
        )
        return close_while_running_dialog.prompt_close_while_running(window, summary)

    @staticmethod
    def begin_shutdown_teardown(window: Any) -> None:
        # Form surfaces own parentless canvas timers and the in-place editor.
        # Releasing them here, before Qt destroys the window, closes that
        # editor while its view is still alive.
        MainWindowLifecycle.release_open_surfaces(window)
        window._local_history_workflow.stop_autosave_timer()
        window._pending_project_tree_preview_path = None
        window._pending_realtime_lint_file_path = None
        composition_timers = getattr(window, "_composition_timers", None)
        if composition_timers is not None:
            composition_timers.stop_all()
        else:
            window._auto_save_to_file_timer.stop()
            window._realtime_lint_timer.stop()
            window._project_tree_preview_click_timer.stop()
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
    def release_open_surfaces(window: Any) -> None:
        """Release open tab surfaces. Leaves the editor manager in place."""
        workflow = getattr(window, "_editor_tab_workflow", None)
        manager = getattr(window, "_editor_manager", None)
        release = getattr(workflow, "release_tab_content", None)
        open_paths = getattr(manager, "open_paths", None)
        if not callable(release) or not callable(open_paths):
            return
        for path in list(open_paths()):
            release(path)

    @staticmethod
    def drain_run_event_queue(window: Any) -> None:
        window._run_event_workflow.drain_run_event_queue()

    @staticmethod
    def stop_active_run_before_close(window: Any, *, keep_running: bool = False) -> None:
        if window._run_service.supervisor.is_running():
            if keep_running:
                MainWindowLifecycle._detach_active_run(window)
            else:
                try:
                    window._run_service.stop_run()
                except Exception as exc:
                    window._logger.warning("Failed to stop active run during window close: %s", exc)

        window._repl_manager.shutdown()
        window._plugin_runtime_manager.stop()
        window._run_session_controller.clear_active_session()
        window._run_event_workflow.set_run_status("idle")
        if window._python_console_widget is not None:
            window._python_console_widget.set_session_active(False)

    @staticmethod
    def _detach_active_run(window: Any) -> None:
        try:
            result = window._run_service.detach_run()
        except Exception as exc:
            window._logger.warning("Failed to leave the active run running during window close: %s", exc)
            return
        if result is None:
            return
        window._logger.info(
            "Left run process %s running after close; later output goes to %s",
            result.process_id,
            result.output_path or "(discarded)",
        )
