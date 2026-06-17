"""File and project menu commands: open, create, restore, quick-open, settings entry."""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import Any, Protocol

from PySide2.QtWidgets import QDialog, QInputDialog, QLineEdit, QMessageBox, QWidget

from app.core import constants
from app.core.errors import AppValidationError
from app.core.models import LoadedProject
from app.editors.quick_open import QuickOpenCandidate
from app.editors.quick_open_dialog import QuickOpenDialog
from app.examples.example_project_service import ExampleProjectService
from app.persistence.settings_service import SettingsService
from app.plugins.workflow_adapters import list_templates_with_workflow
from app.plugins.workflow_broker import WorkflowBroker
from app.project.file_excludes import load_effective_exclude_patterns
from app.project.project_service import ProjectRootState, assess_project_root, create_blank_project
from app.run.runtime_launch import (
    build_runpy_bootstrap_payload,
    is_freecad_runtime_executable,
    resolve_runtime_executable,
    sanitize_apprun_child_env,
)
from app.shell.events import ProjectOpenFailedEvent, ShellEventBus
from app.shell.file_dialogs import choose_existing_directory, choose_open_files
from app.shell.menus import MenuStubRegistry
from app.shell.project_controller import ProjectController
from app.shell.project_load_workflow import ProjectLoadWorkflow
from app.shell.settings_apply_workflow import SettingsApplyWorkflow, capture_settings_apply_baseline
from app.shell.settings_dialog import SettingsDialog
from app.shell.settings_models import (
    merge_editor_settings_snapshot_for_scope,
    merge_last_project_path,
    parse_editor_settings_snapshot,
    parse_effective_editor_settings_snapshot,
)
from app.shell.source_root_workflow import SourceRootWorkflow
from app.shell.theme_tokens import ShellThemeTokens
from app.templates.template_service import TemplateMetadata, TemplateService


class FileProjectCommandsHost(Protocol):
    """Narrow host ports for :class:`FileProjectCommandsWorkflow`."""

    def dialog_parent(self) -> QWidget:
        ...

    @property
    def is_shutting_down(self) -> bool:
        ...

    @property
    def loaded_project(self) -> LoadedProject | None:
        ...

    def settings_service(self) -> SettingsService:
        ...

    def logger(self) -> logging.Logger:
        ...

    def project_controller(self) -> ProjectController:
        ...

    def save_workflow(self) -> Any:
        ...

    def project_load_workflow(self) -> ProjectLoadWorkflow:
        ...

    def settings_apply_workflow(self) -> SettingsApplyWorkflow:
        ...

    def source_root_workflow(self) -> SourceRootWorkflow:
        ...

    def event_bus(self) -> ShellEventBus:
        ...

    def menu_registry(self) -> MenuStubRegistry | None:
        ...

    def workflow_broker(self) -> WorkflowBroker:
        ...

    def template_service(self) -> TemplateService:
        ...

    def example_project_service(self) -> ExampleProjectService:
        ...

    def editor_manager(self) -> Any:
        ...

    def editor_tab_factory(self) -> Any:
        ...

    def shell_theme_workflow(self) -> Any:
        ...

    def quick_open_dialog(self) -> QuickOpenDialog | None:
        ...

    def set_quick_open_dialog(self, dialog: QuickOpenDialog | None) -> None:
        ...

    def tree_file_icon_map(self) -> dict[str, Any]:
        ...

    def tree_filename_icon_map(self) -> dict[str, Any]:
        ...

    def show_editor_screen(self) -> None:
        ...

    def open_file_at_line(self, file_path: str, line_number: int, *, preview: bool = False) -> None:
        ...

    def active_editor_widget(self) -> Any | None:
        ...

    def show_status_message(self, message: str, timeout_ms: int = 0) -> None:
        ...

    def current_project_root(self) -> str | None:
        ...

    def lint_rule_overrides(self) -> dict[str, dict[str, object]]:
        ...

    def diagnostics_enabled(self) -> bool:
        ...

    def selected_linter(self) -> str:
        ...

    def editor_enable_preview(self) -> bool:
        ...

    def settings_dialog_python_tooling_copy(self) -> tuple[str, str, str, str]:
        ...


class MainWindowFileProjectCommandsHost:
    """Adapts :class:`MainWindow` to :class:`FileProjectCommandsHost`."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def dialog_parent(self) -> QWidget:
        return self._window

    @property
    def is_shutting_down(self) -> bool:
        return bool(self._window._is_shutting_down)

    @property
    def loaded_project(self) -> LoadedProject | None:
        return self._window._loaded_project

    def settings_service(self) -> SettingsService:
        return self._window._settings_service

    def logger(self) -> logging.Logger:
        return self._window._logger

    def project_controller(self) -> ProjectController:
        return self._window._project_controller

    def save_workflow(self) -> Any:
        return self._window._save_workflow

    def project_load_workflow(self) -> ProjectLoadWorkflow:
        return self._window._project_load_workflow

    def settings_apply_workflow(self) -> SettingsApplyWorkflow:
        return self._window._settings_apply_workflow

    def source_root_workflow(self) -> SourceRootWorkflow:
        return self._window._source_root_workflow

    def event_bus(self) -> ShellEventBus:
        return self._window._event_bus

    def menu_registry(self) -> MenuStubRegistry | None:
        return self._window._menu_registry

    def workflow_broker(self) -> WorkflowBroker:
        return self._window._workflow_broker

    def template_service(self) -> TemplateService:
        return self._window._template_service

    def example_project_service(self) -> ExampleProjectService:
        return self._window._example_project_service

    def editor_manager(self) -> Any:
        return self._window._editor_manager

    def editor_tab_factory(self) -> Any:
        return self._window._editor_tab_factory

    def shell_theme_workflow(self) -> Any:
        return self._window._shell_theme_workflow

    def quick_open_dialog(self) -> QuickOpenDialog | None:
        return self._window._quick_open_dialog

    def set_quick_open_dialog(self, dialog: QuickOpenDialog | None) -> None:
        self._window._quick_open_dialog = dialog

    def tree_file_icon_map(self) -> dict[str, Any]:
        return self._window._tree_file_icon_map

    def tree_filename_icon_map(self) -> dict[str, Any]:
        return self._window._tree_filename_icon_map

    def show_editor_screen(self) -> None:
        self._window._runtime_onboarding_workflow.show_editor_screen()

    def open_file_at_line(self, file_path: str, line_number: int, *, preview: bool = False) -> None:
        self._window._editor_tab_workflow.open_file_at_line(file_path, line_number, preview=preview)

    def active_editor_widget(self) -> Any | None:
        return self._window._editor_tab_workflow.active_editor_widget()

    def show_status_message(self, message: str, timeout_ms: int = 0) -> None:
        self._window.statusBar().showMessage(message, timeout_ms)

    def current_project_root(self) -> str | None:
        return self._window._current_project_root()

    def lint_rule_overrides(self) -> dict[str, dict[str, object]]:
        return self._window._lint_rule_overrides

    def diagnostics_enabled(self) -> bool:
        return self._window._diagnostics_enabled

    def selected_linter(self) -> str:
        return self._window._selected_linter

    def editor_enable_preview(self) -> bool:
        return self._window._editor_enable_preview

    def settings_dialog_python_tooling_copy(self) -> tuple[str, str, str, str]:
        return self._window._settings_dialog_python_tooling_copy()


class FileProjectCommandsWorkflow:
    """Owns file/project menu actions and the project-open funnel."""

    def __init__(self, host: FileProjectCommandsHost) -> None:
        self._host = host

    def try_restore_last_project(self) -> None:
        """Attempt to reopen the last project from the previous session."""
        if self._host.is_shutting_down or self._host.loaded_project is not None:
            return
        try:
            settings = self._host.settings_service().load_global()
        except Exception as exc:
            self._host.logger().debug(
                "Skipped last-project restore; global settings failed to load: %s",
                exc,
            )
            return
        last_path = settings.get(constants.LAST_PROJECT_PATH_KEY)
        if not isinstance(last_path, str) or not last_path.strip():
            return
        project_root = Path(last_path.strip())
        if not project_root.is_dir():
            return
        try:
            assessment = assess_project_root(project_root)
        except Exception as exc:
            self._host.logger().debug(
                "Skipped last-project restore; project assessment failed for %s: %s",
                project_root,
                exc,
            )
            return
        if assessment.state not in (ProjectRootState.CANONICAL, ProjectRootState.IMPORTABLE):
            return
        self.open_project_by_path(str(project_root))

    def handle_open_project_action(self) -> None:
        parent = self._host.dialog_parent()
        selected_path = choose_existing_directory(parent, "Open Project", str(Path.home()))
        if not selected_path:
            return
        self.open_project_by_path(selected_path)

    def handle_open_file_action(self) -> None:
        parent = self._host.dialog_parent()
        start_dir = str(Path.home())
        loaded_project = self._host.loaded_project
        if loaded_project is not None:
            start_dir = loaded_project.project_root
        active_tab = self._host.editor_manager().active_tab()
        if active_tab is not None and active_tab.file_path:
            parent_dir = Path(active_tab.file_path).parent
            if parent_dir.is_dir():
                start_dir = str(parent_dir)

        file_paths = choose_open_files(
            parent,
            "Open File",
            start_dir,
            "Python Files (*.py);;"
            "JSON Files (*.json);;"
            "Shell Scripts (*.sh *.bash);;"
            "Markdown Files (*.md);;"
            "Text Files (*.txt);;"
            "All Files (*)",
        )
        if not file_paths:
            return

        if self._host.loaded_project is None:
            self._maybe_open_parent_directory_as_project(file_paths[0])

        for file_path in file_paths:
            self._host.editor_tab_factory().open_file_in_editor(file_path, preview=False)

        self._host.show_editor_screen()

    def _maybe_open_parent_directory_as_project(self, file_path: str) -> None:
        try:
            parent_dir = Path(file_path).expanduser().resolve().parent
        except OSError:
            return
        if not parent_dir.is_dir():
            return
        try:
            assessment = assess_project_root(parent_dir)
        except Exception as exc:
            self._host.logger().debug("Skipped parent project assessment for %s: %s", parent_dir, exc)
            return
        if assessment.state not in (ProjectRootState.CANONICAL, ProjectRootState.IMPORTABLE):
            return
        self.open_project_by_path(str(parent_dir))

    def handle_new_window_action(self) -> None:
        parent = self._host.dialog_parent()
        repo_root = self._resolve_repo_root_for_launch()
        editor_boot = (repo_root / "run_editor.py").resolve()
        if not editor_boot.exists():
            QMessageBox.warning(
                parent,
                "New Window unavailable",
                f"Editor boot script not found: {editor_boot}",
            )
            return
        command = self._build_new_window_command(repo_root=repo_root, editor_boot=editor_boot)
        env = sanitize_apprun_child_env() if command and is_freecad_runtime_executable(command[0]) else None
        try:
            subprocess.Popen(command, cwd=str(repo_root), env=env, start_new_session=True)
        except OSError as exc:
            QMessageBox.warning(parent, "New Window unavailable", f"Unable to launch new window: {exc}")

    def _resolve_repo_root_for_launch(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def _build_new_window_command(self, *, repo_root: Path, editor_boot: Path) -> list[str]:
        runtime_executable = resolve_runtime_executable(None)
        if is_freecad_runtime_executable(runtime_executable):
            payload = build_runpy_bootstrap_payload(
                script_path=str(editor_boot),
                path_entry=str(repo_root),
            )
            return [runtime_executable, "-c", payload]
        return [runtime_executable, str(editor_boot)]

    def handle_new_project_action(self) -> None:
        parent = self._host.dialog_parent()
        project_details = self._prompt_for_new_project_destination()
        if project_details is None:
            return
        project_name, destination_path = project_details

        try:
            created_path = create_blank_project(destination_path, project_name=project_name)
        except AppValidationError as exc:
            QMessageBox.warning(parent, "Failed to create project", str(exc))
            return

        self.open_project_by_path(str(created_path))

    def handle_new_project_from_template_action(self) -> None:
        parent = self._host.dialog_parent()
        try:
            _provider, templates = list_templates_with_workflow(self._host.workflow_broker())
        except Exception as exc:
            QMessageBox.warning(parent, "No templates available", f"Unable to load templates: {exc}")
            return
        if not templates:
            QMessageBox.warning(parent, "No templates available", "No project templates were found.")
            return

        selected_template = self._prompt_for_template(templates)
        if selected_template is None:
            return

        project_details = self._prompt_for_new_project_destination()
        if project_details is None:
            return
        project_name, destination_path = project_details

        try:
            created_path = self._host.template_service().materialize_template(
                template_id=selected_template.template_id,
                destination_path=destination_path,
                project_name=project_name,
            )
        except AppValidationError as exc:
            QMessageBox.warning(parent, "Failed to create project", str(exc))
            return

        self.open_project_by_path(str(created_path))

    def _prompt_for_new_project_destination(self) -> tuple[str, Path] | None:
        parent = self._host.dialog_parent()
        project_name, accepted_name = QInputDialog.getText(parent, "New Project", "Project name:", QLineEdit.Normal, "")
        normalized_name = project_name.strip()
        if not accepted_name or not normalized_name:
            return None

        destination_parent = choose_existing_directory(parent, "Choose Project Folder", str(Path.home()))
        if not destination_parent:
            return None

        return normalized_name, Path(destination_parent) / normalized_name

    def _prompt_for_template(self, templates: list[TemplateMetadata]) -> TemplateMetadata | None:
        parent = self._host.dialog_parent()
        labels = [f"{template.display_name} ({template.template_id})" for template in templates]
        selected_label, ok = QInputDialog.getItem(parent, "New Project", "Template:", labels, 0, editable=False)
        if not ok:
            return None
        for template in templates:
            if selected_label == f"{template.display_name} ({template.template_id})":
                return template
        return None

    def handle_open_settings_action(self) -> None:
        settings_service = self._host.settings_service()
        global_settings_payload = settings_service.load_global()
        global_snapshot = parse_editor_settings_snapshot(global_settings_payload)
        project_root = self._host.current_project_root()
        project_settings_payload: dict[str, Any] = {}
        effective_snapshot = global_snapshot
        if project_root is not None:
            project_settings_payload = settings_service.load_project(project_root)
            effective_snapshot = parse_effective_editor_settings_snapshot(
                global_settings_payload,
                project_settings_payload,
            )

        previous_theme_mode = global_snapshot.theme_mode
        previous_lint_rule_overrides = dict(self._host.lint_rule_overrides())
        previous_diagnostics_enabled = self._host.diagnostics_enabled()
        previous_selected_linter = self._host.selected_linter()
        previous_enable_preview = self._host.editor_enable_preview()
        previous_effective_excludes = self.load_effective_exclude_patterns(project_root)
        (
            python_tooling_runtime_text,
            python_tooling_runtime_details,
            python_tooling_config_text,
            python_tooling_config_details,
        ) = self._host.settings_dialog_python_tooling_copy()
        parent = self._host.dialog_parent()
        dialog = SettingsDialog(
            global_snapshot,
            parent,
            tokens=self._host.shell_theme_workflow().resolve_theme_tokens(),
            project_snapshot=effective_snapshot if project_root is not None else None,
            project_scope_available=project_root is not None,
            python_tooling_runtime_text=python_tooling_runtime_text,
            python_tooling_runtime_details=python_tooling_runtime_details,
            python_tooling_config_text=python_tooling_config_text,
            python_tooling_config_details=python_tooling_config_details,
        )
        if dialog.exec_() != QDialog.Accepted:
            return

        selected_scope = dialog.selected_scope
        updated_snapshot = dialog.snapshot()
        merged_global_settings, merged_project_settings = merge_editor_settings_snapshot_for_scope(
            scope=selected_scope,
            global_settings_payload=global_settings_payload,
            project_settings_payload=project_settings_payload,
            snapshot=updated_snapshot,
            global_snapshot=dialog.global_scope_snapshot(),
            project_snapshot=dialog.project_scope_snapshot(),
        )
        if merged_global_settings != global_settings_payload:
            settings_service.save_global(merged_global_settings)
        if project_root is not None and merged_project_settings != project_settings_payload:
            settings_service.save_project(project_root, merged_project_settings)

        baseline = capture_settings_apply_baseline(
            theme_mode=previous_theme_mode,
            lint_rule_overrides=previous_lint_rule_overrides,
            diagnostics_enabled=previous_diagnostics_enabled,
            selected_linter=previous_selected_linter,
            enable_preview=previous_enable_preview,
            effective_excludes=previous_effective_excludes,
        )
        self._host.settings_apply_workflow().apply_after_settings_saved(
            updated_snapshot=updated_snapshot,
            baseline=baseline,
            project_root=project_root,
        )

    def handle_quick_open_action(self) -> None:
        parent = self._host.dialog_parent()
        if self._host.loaded_project is None:
            QMessageBox.warning(parent, "Quick Open unavailable", "Open a project first.")
            return

        open_paths = set(self._host.editor_manager().open_paths()) if self._host.editor_manager() else set()
        candidates = [
            QuickOpenCandidate(
                relative_path=entry.relative_path,
                absolute_path=entry.absolute_path,
                is_open=entry.absolute_path in open_paths,
            )
            for entry in self._host.loaded_project.entries
            if not entry.is_directory
        ]

        quick_open_dialog = self._host.quick_open_dialog()
        if quick_open_dialog is None:
            tokens: ShellThemeTokens = self._host.shell_theme_workflow().resolve_theme_tokens()
            quick_open_dialog = QuickOpenDialog(
                parent,
                tokens=tokens,
                icon_map=self._host.tree_file_icon_map(),
                filename_icon_map=self._host.tree_filename_icon_map(),
            )
            quick_open_dialog.file_preview_requested.connect(
                lambda file_path: self._host.editor_tab_factory().open_file_in_editor(file_path, preview=True)
            )
            quick_open_dialog.file_selected.connect(
                lambda file_path: self._host.editor_tab_factory().open_file_in_editor(file_path, preview=False)
            )
            quick_open_dialog.file_preview_at_line_requested.connect(
                lambda file_path, line_number: self._host.open_file_at_line(
                    file_path,
                    line_number,
                    preview=True,
                )
            )
            quick_open_dialog.file_selected_at_line.connect(
                lambda file_path, line_number: self._host.open_file_at_line(
                    file_path,
                    line_number,
                    preview=False,
                )
            )
            self._host.set_quick_open_dialog(quick_open_dialog)

        quick_open_dialog.set_candidates(candidates)
        quick_open_dialog.open_dialog()

    def handle_go_to_line_action(self) -> None:
        parent = self._host.dialog_parent()
        editor_widget = self._host.active_editor_widget()
        if editor_widget is None:
            QMessageBox.warning(parent, "Go To Line", "Open a file tab first.")
            return

        total_lines = max(1, editor_widget.document().blockCount())
        line_number, ok = QInputDialog.getInt(parent, "Go To Line", "Line:", 1, 1, total_lines, 1)
        if not ok:
            return

        editor_widget.go_to_line(line_number)

    def handle_load_example_project_action(self) -> None:
        parent = self._host.dialog_parent()
        project_details = self._prompt_for_new_project_destination()
        if project_details is None:
            return
        project_name, destination_path = project_details

        try:
            created_path = self._host.example_project_service().materialize_showcase(
                destination_path=destination_path,
                project_name=project_name,
            )
        except AppValidationError as exc:
            QMessageBox.warning(parent, "Failed to load example project", str(exc))
            return

        self.open_project_by_path(str(created_path))

    def open_project_by_path(self, project_root: str) -> bool:
        started_at = time.perf_counter()
        return self._host.project_controller().open_project_by_path(
            project_root,
            confirm_proceed=self._host.save_workflow().confirm_proceed_with_unsaved_changes,
            on_loading=lambda: self._host.show_status_message("Opening project… (scanning files)", 0),
            on_loaded=lambda loaded_project: self.apply_loaded_project(loaded_project, started_at=started_at),
            on_error=self.show_open_project_error,
            exclude_patterns=self.load_effective_exclude_patterns(project_root),
        )

    def load_effective_exclude_patterns(self, project_root: str | None = None) -> list[str]:
        return load_effective_exclude_patterns(self._host.settings_service(), project_root)

    def refresh_open_recent_menu(self) -> None:
        self._host.project_controller().refresh_open_recent_menu(
            self._host.menu_registry(),
            open_project_by_path=self.open_project_by_path,
            theme_tokens=self._host.shell_theme_workflow().resolve_theme_tokens(),
        )

    def show_open_project_error(self, project_root: str, details: str) -> None:
        parent = self._host.dialog_parent()
        self._host.logger().warning("Project open failed for %s: %s", project_root, details)
        self._host.event_bus().publish(
            ProjectOpenFailedEvent(project_root=project_root, error_message=details)
        )
        QMessageBox.critical(
            parent,
            "Unable to open project",
            f"Could not open project:\n{project_root}\n\n{details}",
        )

    def apply_loaded_project(self, loaded_project: LoadedProject, *, started_at: float) -> None:
        self._host.project_load_workflow().apply(loaded_project, started_at=started_at)
        self._host.source_root_workflow().maybe_prompt_import_source_roots()

    def persist_last_project_path(self, project_root: str) -> None:
        try:
            self._host.settings_service().update_global(
                lambda settings: merge_last_project_path(settings, project_root)
            )
        except Exception as exc:
            self._host.logger().warning("Failed to persist last project path: %s", exc)


def build_file_project_commands_workflow(window: Any) -> FileProjectCommandsWorkflow:
    return FileProjectCommandsWorkflow(MainWindowFileProjectCommandsHost(window))

