"""Save and save-time formatting workflow for the shell."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence, cast

from PySide2.QtWidgets import QMessageBox, QWidget

from app.core import constants
from app.editors.editor_manager import EditorManager
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
from app.shell.document_safety import (
    DocumentCloseIntent,
    DocumentSafetyDecision,
    DocumentScope,
    dirty_buffer_snapshots,
)
from app.shell.shell_composition_context import MainWindowCompositionSurface
from app.shell.unsaved_changes_dialog import prompt_for_unsaved_changes


PYTHON_STYLE_SAVE_GUARDRAIL_CHAR_LIMIT = 250_000


class SaveWorkflowPort(Protocol):
    """Minimal save-workflow surface for external reload prompts."""

    def request_unsaved_changes_decision(
        self,
        action_description: str,
        *,
        scope: DocumentScope,
        allow_keep_for_next_launch: bool,
        dirty_buffers: tuple[object, ...] | None = None,
    ) -> DocumentSafetyDecision:
        ...

    def apply_unsaved_changes_decision(self, decision: DocumentSafetyDecision) -> bool:
        ...


class SaveWorkflowTreeDeletePort(Protocol):
    """Minimal save-workflow surface for project-tree delete prompts."""

    def confirm_proceed_before_tree_delete(
        self,
        target_paths: list[str],
        *,
        action_description: str = "moving items to trash",
    ) -> bool:
        ...


class SaveDocumentLocalHistoryPort(Protocol):
    """Local-history callbacks used during save and unsaved-change handling."""

    def discard_drafts_for_paths(self, file_paths: Sequence[str]) -> None:
        ...

    def keep_drafts_for_paths(self, file_paths: Sequence[str]) -> None:
        ...

    def discard_pending_autosave(self, file_path: str) -> None:
        ...

    def record_checkpoint(
        self,
        file_path: str,
        content: str,
        *,
        source: str,
        label: str = "",
    ) -> None:
        ...

    def delete_draft(self, file_path: str) -> None:
        ...

    def local_history_context_for_path(self, file_path: str) -> tuple[object | None, object | None]:
        ...


class SaveDocumentIntelligenceCachePort(Protocol):
    """Intelligence cache refresh callbacks invoked after save."""

    def start_symbol_indexing(self, project_root: str, *, inventory_snapshot: object) -> None:
        ...


class SaveDocumentSettingsPort(Protocol):
    """Settings persistence for save-related editor preferences."""

    def update_global(self, updater: Callable[[Mapping[str, Any]], Mapping[str, Any]]) -> Mapping[str, Any]:
        ...


class SaveDocumentHost(Protocol):
    """Host callbacks and editor settings for save orchestration."""

    def editor_manager(self) -> EditorManager:
        ...

    def dialog_parent(self) -> QWidget:
        ...

    def editor_exit_behavior(self) -> str:
        ...

    def refresh_save_action_states(self) -> None:
        ...

    def editor_auto_save(self) -> bool:
        ...

    def set_editor_auto_save(self, enabled: bool) -> None:
        ...

    def stop_auto_save_timer(self) -> None:
        ...

    def logger(self) -> object:
        ...

    def has_editor_tabs_widget(self) -> bool:
        ...

    def editor_trim_trailing_whitespace_on_save(self) -> bool:
        ...

    def editor_insert_final_newline_on_save(self) -> bool:
        ...

    def editor_organize_imports_on_save(self) -> bool:
        ...

    def editor_format_on_save(self) -> bool:
        ...

    def resolve_python_tooling_project_root(self, file_path: str) -> str:
        ...

    def apply_text_to_open_tab(self, file_path: str, transformed_text: str) -> None:
        ...

    def intelligence_runtime_settings(self) -> object:
        ...

    def loaded_project(self) -> object | None:
        ...

    def project_inventory_snapshot(self) -> object:
        ...

    def workflow_broker(self) -> object:
        ...

    def tab_index_for_path(self, file_path: str) -> int:
        ...

    def refresh_tab_presentation(self, file_path: str) -> None:
        ...

    def update_editor_status_for_path(self, file_path: str) -> None:
        ...

    def rescan_project_from_disk(self, *, reload_plugins: bool, reindex: bool) -> None:
        ...

    def render_lint_for_file(self, file_path: str, *, trigger: str) -> None:
        ...

    def refresh_test_discovery(self) -> None:
        ...


# Narrow aliases consumed by sibling shell workflows.
LocalHistoryPort = SaveDocumentLocalHistoryPort


class MainWindowSaveDocumentHost:
    """Host ports for ``SaveWorkflow`` backed by a MainWindow instance."""

    def __init__(self, window: MainWindowCompositionSurface) -> None:
        self._window = cast(Any, window)

    def dialog_parent(self) -> QWidget:
        return self._window

    def editor_manager(self) -> EditorManager:
        return self._window._editor_manager

    def editor_exit_behavior(self) -> str:
        return self._window._editor_exit_behavior

    def refresh_save_action_states(self) -> None:
        self._window._refresh_save_action_states()

    def editor_auto_save(self) -> bool:
        return self._window._editor_auto_save

    def set_editor_auto_save(self, enabled: bool) -> None:
        self._window._editor_auto_save = enabled

    def stop_auto_save_timer(self) -> None:
        self._window._auto_save_to_file_timer.stop()

    def logger(self) -> Any:
        return self._window._logger

    def has_editor_tabs_widget(self) -> bool:
        return self._window._editor_tabs_widget is not None

    def editor_trim_trailing_whitespace_on_save(self) -> bool:
        return self._window._editor_trim_trailing_whitespace_on_save

    def editor_insert_final_newline_on_save(self) -> bool:
        return self._window._editor_insert_final_newline_on_save

    def editor_organize_imports_on_save(self) -> bool:
        return self._window._editor_organize_imports_on_save

    def editor_format_on_save(self) -> bool:
        return self._window._editor_format_on_save

    def resolve_python_tooling_project_root(self, file_path: str) -> str:
        return self._window._resolve_python_tooling_project_root(file_path)

    def apply_text_to_open_tab(self, file_path: str, transformed_text: str) -> None:
        self._window._apply_text_to_open_tab(file_path, transformed_text)

    def intelligence_runtime_settings(self) -> Any:
        return self._window._intelligence_runtime_settings

    def loaded_project(self) -> Any | None:
        return self._window._loaded_project

    def project_inventory_snapshot(self) -> Any:
        return self._window._project_inventory_orchestrator.snapshot

    def workflow_broker(self) -> Any:
        return self._window._workflow_broker

    def tab_index_for_path(self, file_path: str) -> int:
        return self._window._editor_tab_workflow.tab_index_for_path(file_path)

    def refresh_tab_presentation(self, file_path: str) -> None:
        self._window._editor_tab_workflow.refresh_tab_presentation(file_path)

    def update_editor_status_for_path(self, file_path: str) -> None:
        self._window._editor_tab_workflow.update_editor_status_for_path(file_path)

    def rescan_project_from_disk(self, *, reload_plugins: bool, reindex: bool) -> None:
        self._window._project_rescan_workflow.rescan_from_disk(
            reload_plugins=reload_plugins,
            reindex=reindex,
        )

    def render_lint_for_file(self, file_path: str, *, trigger: str) -> None:
        self._window._lint_workflow.render_diagnostics_for_file(file_path, trigger=trigger)

    def refresh_test_discovery(self) -> None:
        test_runner_workflow = getattr(self._window, "_test_runner_workflow", None)
        if test_runner_workflow is not None:
            test_runner_workflow.refresh_discovery()


class SaveWorkflow:
    """Owns save, autosave-to-file, and style-on-save coordination."""

    def __init__(
        self,
        *,
        local_history: SaveDocumentLocalHistoryPort,
        intelligence_cache: SaveDocumentIntelligenceCachePort,
        host: SaveDocumentHost,
        settings_service: SaveDocumentSettingsPort,
    ) -> None:
        self._local_history = local_history
        self._intelligence_cache = intelligence_cache
        self._host = host
        self._settings_service = settings_service

    def _editor_manager(self) -> EditorManager:
        return self._host.editor_manager()

    def confirm_proceed_with_unsaved_changes(self, action_description: str) -> bool:
        decision = self.request_unsaved_changes_decision(
            action_description,
            scope=DocumentScope.PROJECT,
            allow_keep_for_next_launch=False,
        )
        return self.apply_unsaved_changes_decision(decision)

    def confirm_proceed_before_tree_delete(
        self,
        target_paths: list[str],
        *,
        action_description: str = "moving items to trash",
    ) -> bool:
        normalized_paths = [str(Path(path).expanduser().resolve()) for path in target_paths]
        affected_tabs: list[object] = []
        for tab in self._editor_manager().all_tabs():
            tab_path = str(Path(tab.file_path).expanduser().resolve())
            for target_path in normalized_paths:
                if tab_path == target_path or tab_path.startswith(f"{target_path}/"):
                    if tab.is_dirty:
                        affected_tabs.append(tab)
                    break
        if not affected_tabs:
            return True
        decision = self.request_unsaved_changes_decision(
            action_description,
            scope=DocumentScope.PROJECT,
            allow_keep_for_next_launch=False,
            dirty_buffers=tuple(affected_tabs),
        )
        if decision.intent is DocumentCloseIntent.CANCEL:
            return False
        return self.apply_unsaved_changes_decision(decision)

    def request_unsaved_changes_decision(
        self,
        action_description: str,
        *,
        scope: DocumentScope,
        allow_keep_for_next_launch: bool,
        dirty_buffers: tuple[object, ...] | None = None,
    ) -> DocumentSafetyDecision:
        buffer_snapshots = (
            dirty_buffer_snapshots(self._editor_manager().all_tabs())
            if dirty_buffers is None
            else dirty_buffer_snapshots(dirty_buffers)
        )
        if not buffer_snapshots:
            return DocumentSafetyDecision(intent=DocumentCloseIntent.PROCEED, scope=scope)

        if (
            scope is DocumentScope.APPLICATION
            and self._host.editor_exit_behavior() == constants.UI_EDITOR_EXIT_BEHAVIOR_KEEP_UNSAVED
        ):
            return DocumentSafetyDecision(
                intent=DocumentCloseIntent.KEEP_FOR_NEXT_LAUNCH,
                scope=scope,
                dirty_buffers=buffer_snapshots,
            )

        return prompt_for_unsaved_changes(
            self._host.dialog_parent(),
            action_description=action_description,
            scope=scope,
            dirty_buffers=buffer_snapshots,
            allow_keep_for_next_launch=allow_keep_for_next_launch,
        )

    def apply_unsaved_changes_decision(self, decision: DocumentSafetyDecision) -> bool:
        if decision.intent is DocumentCloseIntent.CANCEL:
            return False
        if decision.intent is DocumentCloseIntent.PROCEED:
            return True
        if decision.intent is DocumentCloseIntent.DISCARD:
            self._local_history.discard_drafts_for_paths(decision.affected_paths)
            return True
        if decision.intent is DocumentCloseIntent.KEEP_FOR_NEXT_LAUNCH:
            self._local_history.keep_drafts_for_paths(decision.affected_paths)
            return True

        any_failure = False
        for file_path in decision.affected_paths:
            if not self.save_tab(file_path):
                any_failure = True
        return not any_failure

    def handle_save_action(self) -> bool:
        active_tab = self._editor_manager().active_tab()
        if active_tab is None:
            return False
        return self.save_tab(active_tab.file_path)

    def handle_save_all_action(self) -> bool:
        any_failure = False
        for tab in self._editor_manager().all_tabs():
            if not tab.is_dirty:
                continue
            if not self.save_tab(tab.file_path):
                any_failure = True
        self._host.refresh_save_action_states()
        return not any_failure

    def handle_toggle_auto_save(self, checked: bool) -> None:
        self._host.set_editor_auto_save(checked)
        self._settings_service.update_global(
            lambda payload: _merge_auto_save_setting(payload, checked)
        )
        if not checked:
            self._host.stop_auto_save_timer()

    def flush_auto_save_to_file(self) -> None:
        if not self._host.editor_auto_save():
            return
        logger = self._host.logger()
        for tab in self._editor_manager().all_tabs():
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
                getattr(logger, "warning")(
                    "Auto-save to file failed for %s",
                    tab.file_path,
                    exc_info=True,
                )

    def save_tab(
        self,
        file_path: str,
        *,
        show_style_warnings: bool = True,
        checkpoint_source: str = "save",
        apply_transforms: bool = True,
    ) -> bool:
        host = self._host
        path_existed_before_save = Path(file_path).expanduser().resolve().exists()
        if apply_transforms:
            self.apply_save_transforms(file_path, show_style_warnings=show_style_warnings)
        try:
            saved_tab = self._editor_manager().save_tab(file_path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(host.dialog_parent(), "Save failed", str(exc))
            getattr(host.logger(), "warning")("Save failed for %s: %s", file_path, exc)
            return False

        if host.has_editor_tabs_widget():
            tab_index = host.tab_index_for_path(saved_tab.file_path)
            if tab_index >= 0:
                host.refresh_tab_presentation(saved_tab.file_path)

        self._local_history.discard_pending_autosave(saved_tab.file_path)
        self._local_history.record_checkpoint(
            saved_tab.file_path,
            saved_tab.current_content,
            source=checkpoint_source,
        )
        self._local_history.delete_draft(saved_tab.file_path)
        project_id, _project_root = self._local_history.local_history_context_for_path(saved_tab.file_path)
        loaded_project = host.loaded_project()
        if not path_existed_before_save and project_id is not None:
            host.rescan_project_from_disk(reload_plugins=False, reindex=True)
        elif should_refresh_index_after_save(
            host.intelligence_runtime_settings(),
            has_loaded_project=loaded_project is not None,
        ) and loaded_project is not None:
            self._intelligence_cache.start_symbol_indexing(
                getattr(loaded_project, "project_root"),
                inventory_snapshot=host.project_inventory_snapshot(),
            )
        host.refresh_save_action_states()
        host.update_editor_status_for_path(saved_tab.file_path)
        if saved_tab.file_path.lower().endswith(".py"):
            host.render_lint_for_file(saved_tab.file_path, trigger="save")
            host.refresh_test_discovery()
        getattr(host.logger(), "info")("Saved file: %s", saved_tab.file_path)
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
        host = self._host
        tab_state = self._editor_manager().get_tab(file_path)
        if tab_state is None:
            return

        original_text = tab_state.current_content
        transformed_text = format_text_basic(
            original_text,
            trim_trailing_whitespace=host.editor_trim_trailing_whitespace_on_save(),
            ensure_final_newline=host.editor_insert_final_newline_on_save(),
        ).formatted_text

        warning_messages: list[str] = []
        is_python_file = file_path.lower().endswith(".py")
        should_run_python_style = is_python_file and (
            host.editor_organize_imports_on_save() or host.editor_format_on_save()
        )
        if should_run_python_style:
            if self.should_skip_python_style_on_save(transformed_text):
                warning_messages.append(
                    "Python style automation was skipped on save because the file exceeds the size guardrail."
                )
            else:
                project_root = host.resolve_python_tooling_project_root(file_path)
                if host.editor_organize_imports_on_save():
                    try:
                        _provider, organize_result = organize_imports_with_workflow(
                            host.workflow_broker(),
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
                if host.editor_format_on_save():
                    try:
                        _provider, format_result = format_python_with_workflow(
                            host.workflow_broker(),
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
            host.apply_text_to_open_tab(file_path, transformed_text)
        if show_style_warnings and warning_messages:
            QMessageBox.warning(host.dialog_parent(), "Save formatting", "\n\n".join(warning_messages))


def _merge_auto_save_setting(payload: Mapping[str, Any], enabled: bool) -> dict[str, Any]:
    merged = dict(payload)
    editor = dict(merged.get(constants.UI_EDITOR_SETTINGS_KEY, {}))
    editor[constants.UI_EDITOR_AUTO_SAVE_KEY] = enabled
    merged[constants.UI_EDITOR_SETTINGS_KEY] = editor
    return merged
