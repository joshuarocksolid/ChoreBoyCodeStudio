"""Save and save-time formatting workflow for the shell."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from PySide2.QtWidgets import QMessageBox

from app.core import constants
from app.intelligence.cache_controls import should_refresh_index_after_save
from app.editors.formatting_service import format_text_basic
from app.plugins.workflow_adapters import format_python_with_workflow, organize_imports_with_workflow
from app.python_tools.models import (
    PYTHON_TOOLING_STATUS_CONFIG_ERROR,
    PYTHON_TOOLING_STATUS_FORMATTED,
    PYTHON_TOOLING_STATUS_IMPORTS_ORGANIZED,
    PYTHON_TOOLING_STATUS_SYNTAX_ERROR,
    PYTHON_TOOLING_STATUS_TOOL_UNAVAILABLE,
    PYTHON_TOOLING_STATUS_UNCHANGED,
    PythonTextTransformResult,
)


PYTHON_STYLE_SAVE_GUARDRAIL_CHAR_LIMIT = 250_000


class SaveWorkflow:
    """Owns save, autosave-to-file, and style-on-save coordination."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def confirm_proceed_with_unsaved_changes(self, action_description: str) -> bool:
        window = self._window
        dirty_tabs = [tab for tab in window._editor_manager.all_tabs() if tab.is_dirty]
        if not dirty_tabs:
            return True

        response = QMessageBox.warning(
            window,
            "Unsaved changes",
            (
                f"You have {len(dirty_tabs)} unsaved file(s) before {action_description}.\n"
                "Would you like to save changes first?"
            ),
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )

        if response == QMessageBox.Cancel:
            return False
        if response == QMessageBox.Discard:
            return True

        return self.handle_save_all_action()

    def handle_save_action(self) -> bool:
        window = self._window
        active_tab = window._editor_manager.active_tab()
        if active_tab is None:
            return False
        return self.save_tab(active_tab.file_path)

    def handle_save_all_action(self) -> bool:
        window = self._window
        any_failure = False
        for tab in window._editor_manager.all_tabs():
            if not tab.is_dirty:
                continue
            if not self.save_tab(tab.file_path):
                any_failure = True
        window._refresh_save_action_states()
        return not any_failure

    def handle_toggle_auto_save(self, checked: bool) -> None:
        window = self._window
        window._editor_auto_save = checked
        window._settings_service.update_global(
            lambda payload: _merge_auto_save_setting(payload, checked)
        )
        if not checked:
            window._auto_save_to_file_timer.stop()

    def flush_auto_save_to_file(self) -> None:
        window = self._window
        if not window._editor_auto_save:
            return
        for tab in window._editor_manager.all_tabs():
            if not tab.is_dirty:
                continue
            try:
                self.save_tab(
                    tab.file_path,
                    show_style_warnings=False,
                    checkpoint_source="auto_save_to_file",
                    apply_transforms=False,
                )
            except Exception:
                window._logger.warning("Auto-save to file failed for %s", tab.file_path, exc_info=True)

    def save_tab(
        self,
        file_path: str,
        *,
        show_style_warnings: bool = True,
        checkpoint_source: str = "save",
        apply_transforms: bool = True,
    ) -> bool:
        window = self._window
        path_existed_before_save = Path(file_path).expanduser().resolve().exists()
        if apply_transforms:
            self.apply_save_transforms(file_path, show_style_warnings=show_style_warnings)
        try:
            saved_tab = window._editor_manager.save_tab(file_path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(window, "Save failed", str(exc))
            window._logger.warning("Save failed for %s: %s", file_path, exc)
            return False

        if window._editor_tabs_widget is not None:
            tab_index = window._tab_index_for_path(saved_tab.file_path)
            if tab_index >= 0:
                window._refresh_tab_presentation(saved_tab.file_path)

        window._local_history_workflow.discard_pending_autosave(saved_tab.file_path)
        window._local_history_workflow.record_checkpoint(
            saved_tab.file_path,
            saved_tab.current_content,
            source=checkpoint_source,
        )
        window._local_history_workflow.delete_draft(saved_tab.file_path)
        project_id, _project_root = window._local_history_workflow.local_history_context_for_path(saved_tab.file_path)
        if not path_existed_before_save and project_id is not None:
            window._reload_current_project()
        window._refresh_save_action_states()
        window._update_editor_status_for_path(saved_tab.file_path)
        if should_refresh_index_after_save(
            window._intelligence_runtime_settings,
            has_loaded_project=window._loaded_project is not None,
        ) and window._loaded_project is not None:
            window._start_symbol_indexing(window._loaded_project.project_root)
        if saved_tab.file_path.lower().endswith(".py"):
            window._render_lint_diagnostics_for_file(saved_tab.file_path, trigger="save")
            test_runner_workflow = getattr(window, "_test_runner_workflow", None)
            if test_runner_workflow is not None:
                test_runner_workflow.refresh_discovery()
        window._logger.info("Saved file: %s", saved_tab.file_path)
        return True

    def python_tooling_failure_message(self, action_label: str, result: PythonTextTransformResult) -> str:
        if result.status == PYTHON_TOOLING_STATUS_SYNTAX_ERROR:
            return f"{action_label} skipped because the file contains Python syntax errors."
        if result.status == PYTHON_TOOLING_STATUS_CONFIG_ERROR:
            details = f"\n\n{result.error_message}" if result.error_message else ""
            return f"{action_label} skipped because project-local pyproject settings could not be parsed.{details}"
        if result.status == PYTHON_TOOLING_STATUS_TOOL_UNAVAILABLE:
            details = f"\n\n{result.error_message}" if result.error_message else ""
            return f"{action_label} is unavailable because the vendored Python tooling could not be loaded.{details}"
        details = f"\n\n{result.error_message}" if result.error_message else ""
        return f"{action_label} failed.{details}"

    def should_skip_python_style_on_save(self, source_text: str) -> bool:
        return len(source_text) > PYTHON_STYLE_SAVE_GUARDRAIL_CHAR_LIMIT

    def consume_save_python_tool_result(
        self,
        *,
        action_label: str,
        current_text: str,
        result: PythonTextTransformResult,
        warning_messages: list[str],
    ) -> str:
        if result.status in {PYTHON_TOOLING_STATUS_FORMATTED, PYTHON_TOOLING_STATUS_IMPORTS_ORGANIZED}:
            return result.formatted_text
        if result.status == PYTHON_TOOLING_STATUS_UNCHANGED:
            return current_text
        warning_messages.append(self.python_tooling_failure_message(action_label, result))
        return current_text

    def apply_save_transforms(self, file_path: str, *, show_style_warnings: bool) -> None:
        window = self._window
        tab_state = window._editor_manager.get_tab(file_path)
        if tab_state is None:
            return

        original_text = tab_state.current_content
        transformed_text = format_text_basic(
            original_text,
            trim_trailing_whitespace=window._editor_trim_trailing_whitespace_on_save,
            ensure_final_newline=window._editor_insert_final_newline_on_save,
        ).formatted_text

        warning_messages: list[str] = []
        is_python_file = file_path.lower().endswith(".py")
        should_run_python_style = is_python_file and (
            window._editor_organize_imports_on_save or window._editor_format_on_save
        )
        if should_run_python_style:
            if self.should_skip_python_style_on_save(transformed_text):
                warning_messages.append(
                    "Python style automation was skipped on save because the file exceeds the size guardrail."
                )
            else:
                project_root = window._resolve_python_tooling_project_root(file_path)
                if window._editor_organize_imports_on_save:
                    try:
                        _provider, organize_result = organize_imports_with_workflow(
                            window._workflow_broker,
                            source_text=transformed_text,
                            file_path=file_path,
                            project_root=project_root,
                        )
                    except Exception as exc:
                        warning_messages.append(f"Organize Imports on save failed: {exc}")
                    else:
                        transformed_text = self.consume_save_python_tool_result(
                            action_label="Organize Imports on save",
                            current_text=transformed_text,
                            result=organize_result,
                            warning_messages=warning_messages,
                        )
                if window._editor_format_on_save:
                    try:
                        _provider, format_result = format_python_with_workflow(
                            window._workflow_broker,
                            source_text=transformed_text,
                            file_path=file_path,
                            project_root=project_root,
                        )
                    except Exception as exc:
                        warning_messages.append(f"Formatting on save failed: {exc}")
                    else:
                        transformed_text = self.consume_save_python_tool_result(
                            action_label="Formatting on save",
                            current_text=transformed_text,
                            result=format_result,
                            warning_messages=warning_messages,
                        )

        if transformed_text != original_text:
            window._apply_text_to_open_tab(file_path, transformed_text)
        if show_style_warnings and warning_messages:
            QMessageBox.warning(window, "Save formatting", "\n\n".join(warning_messages))


def _merge_auto_save_setting(payload: Mapping[str, Any], enabled: bool) -> dict[str, Any]:
    merged = dict(payload)
    editor = dict(merged.get(constants.UI_EDITOR_SETTINGS_KEY, {}))
    editor[constants.UI_EDITOR_AUTO_SAVE_KEY] = enabled
    merged[constants.UI_EDITOR_SETTINGS_KEY] = editor
    return merged
