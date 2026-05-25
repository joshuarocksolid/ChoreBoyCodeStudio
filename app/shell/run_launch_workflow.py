"""Run and debug launch orchestration for the shell."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Protocol, Union

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QMenu, QMessageBox, QToolButton, QWidget

from app.core import constants
from app.core.errors import AppValidationError, ProjectManifestValidationError
from app.core.models import LoadedProject
from app.debug.debug_models import DebugBreakpoint, DebugExceptionPolicy, DebugSourceMap
from app.project.project_manifest import set_project_default_argv
from app.project.run_configs import RunConfiguration
from app.shell.run_config_controller import RunConfigController
from app.shell.run_configurations_dialog import (
    RunConfigurationsDialog,
    RunConfigurationsInitial,
    RunConfigurationsResult,
)
from app.shell.run_with_arguments_dialog import RunInvocation, RunWithArgumentsDialog, RunWithArgumentsInitial
from app.support.preflight import build_run_preflight


@dataclass(frozen=True)
class ProjectTarget:
    """Last debug target: project default or active named configuration."""

    kind: str = "project"


@dataclass(frozen=True)
class ActiveFileTarget:
    """Last debug target: active editor Python file."""

    file_path: str
    kind: str = "active_file"


@dataclass(frozen=True)
class CurrentTestTarget:
    """Last debug target: pytest run for the current file."""

    target_path: str
    kind: str = "current_test"


@dataclass(frozen=True)
class TestNodeTarget:
    """Last debug target: a single pytest node."""

    node_id: str
    kind: str = "test_node"


DebugTarget = Union[ProjectTarget, ActiveFileTarget, CurrentTestTarget, TestNodeTarget]


def debug_target_from_mapping(payload: Mapping[str, object]) -> DebugTarget | None:
    """Parse a legacy debug-target dict into a typed :class:`DebugTarget`."""

    kind = str(payload.get("kind", "")).strip()
    if kind == "project":
        return ProjectTarget()
    if kind == "active_file":
        file_path = str(payload.get("file_path", "")).strip()
        if not file_path:
            return None
        return ActiveFileTarget(file_path=file_path)
    if kind == "current_test":
        target_path = str(payload.get("target_path", "")).strip()
        if not target_path:
            return None
        return CurrentTestTarget(target_path=target_path)
    if kind == "test_node":
        node_id = str(payload.get("node_id", "")).strip()
        if not node_id:
            return None
        return TestNodeTarget(node_id=node_id)
    return None


def _proposed_new_config_name(existing_configs: list[RunConfiguration]) -> str:
    """Return a unique default name for a freshly created run configuration."""

    base = "New Configuration"
    existing_names = {config.name for config in existing_configs}
    if base not in existing_names:
        return base
    index = 2
    while f"{base} {index}" in existing_names:
        index += 1
    return f"{base} {index}"


class RunLaunchWorkflowHost(Protocol):
    """Host ports for :class:`RunLaunchWorkflow`."""

    def dialog_parent(self) -> QWidget:
        ...

    def loaded_project(self) -> LoadedProject | None:
        ...

    def set_loaded_project(self, project: LoadedProject) -> None:
        ...

    def active_named_run_config_name(self) -> str | None:
        ...

    def set_active_named_run_config_name(self, name: str | None) -> None:
        ...

    def editor_manager(self) -> Any:
        ...

    def debug_control_workflow(self) -> Any:
        ...

    def debug_exception_policy(self) -> DebugExceptionPolicy:
        ...

    def run_config_controller(self) -> RunConfigController:
        ...

    def run_debug_presenter(self) -> Any:
        ...

    def settings_service(self) -> Any:
        ...

    def resolve_theme_tokens(self) -> Any:
        ...

    def show_run_preflight_result(self, title: str, summary: str, issues: list[Any]) -> None:
        ...

    def refresh_run_action_states(self) -> None:
        ...

    def editor_tab_factory(self) -> Any:
        ...

    def editor_tabs_widget(self) -> Any | None:
        ...

    def tab_index_for_path(self, file_path: str) -> int:
        ...

    def test_runner_workflow(self) -> Any:
        ...

    def active_transient_entry_file_path(self) -> str | None:
        ...

    def set_active_transient_entry_file_path(self, path: str | None) -> None:
        ...

    def status_bar(self) -> Any:
        ...

    def show_warning(self, title: str, message: str) -> None:
        ...

    def show_information(self, title: str, message: str) -> None:
        ...

    def logger(self) -> Any:
        ...


class RunLaunchWorkflow:
    """Owns run/debug launch actions, run-configuration UX, and debug-target memory."""

    def __init__(self, host: RunLaunchWorkflowHost) -> None:
        self._host = host
        self._last_debug_target: DebugTarget | None = None
        self._active_run_config_button: QToolButton | None = None

    @property
    def last_debug_target(self) -> DebugTarget | None:
        return self._last_debug_target

    def has_rerun_target(self) -> bool:
        return self._last_debug_target is not None

    def record_debug_target(self, target: DebugTarget) -> None:
        self._last_debug_target = target

    def record_debug_target_from_dict(self, payload: Mapping[str, object]) -> None:
        parsed = debug_target_from_mapping(payload)
        if parsed is not None:
            self._last_debug_target = parsed

    def start_session(
        self,
        *,
        mode: str,
        entry_file: str | None = None,
        argv: list[str] | None = None,
        working_directory: str | None = None,
        env_overrides: dict[str, str] | None = None,
        breakpoints: list[DebugBreakpoint] | list[dict[str, object]] | None = None,
        debug_exception_policy: DebugExceptionPolicy | None = None,
        source_maps: list[DebugSourceMap] | None = None,
        skip_save: bool = False,
    ) -> bool:
        return self._host.run_debug_presenter().start_session(
            mode=mode,
            entry_file=entry_file,
            argv=argv,
            working_directory=working_directory,
            env_overrides=env_overrides,
            breakpoints=breakpoints,
            debug_exception_policy=debug_exception_policy,
            source_maps=source_maps,
            skip_save=skip_save,
        )

    def handle_run_action(self) -> bool:
        return self._start_active_file_session(mode=constants.RUN_MODE_PYTHON_SCRIPT)

    def handle_debug_action(self) -> bool:
        return self._start_active_file_session(mode=constants.RUN_MODE_PYTHON_DEBUG)

    def handle_run_project_action(self) -> bool:
        loaded_project = self._host.loaded_project()
        if loaded_project is None:
            self._host.show_warning("Run unavailable", "Open a project before running.")
            return False
        active_config = self._resolve_active_named_run_config()
        if active_config is not None:
            return self._launch_run_configuration(active_config, debug=False)
        entry_file = (loaded_project.metadata.default_entry or "").strip()
        if not self._ensure_run_preflight_ready(title="Run Project", entry_file=entry_file):
            return False
        return self.start_session(mode=constants.RUN_MODE_PYTHON_SCRIPT, entry_file=entry_file)

    def handle_debug_project_action(self) -> bool:
        loaded_project = self._host.loaded_project()
        if loaded_project is None:
            self._host.show_warning("Run unavailable", "Open a project before running.")
            return False
        active_config = self._resolve_active_named_run_config()
        if active_config is not None:
            return self._launch_run_configuration(active_config, debug=True)
        entry_file = (loaded_project.metadata.default_entry or "").strip()
        if not self._ensure_run_preflight_ready(title="Debug Project", entry_file=entry_file):
            return False
        started = self.start_session(
            mode=constants.RUN_MODE_PYTHON_DEBUG,
            entry_file=entry_file,
            breakpoints=self._host.debug_control_workflow().build_debug_breakpoints_for_launch(),
            debug_exception_policy=self._host.debug_exception_policy(),
        )
        if started:
            self.record_debug_target(ProjectTarget())
        return started

    def handle_run_with_configuration_action(self) -> bool:
        loaded_project = self._host.loaded_project()
        if loaded_project is None:
            self._host.show_warning("Run Configurations", "Open a project first.")
            return False
        existing_configs = self._host.run_config_controller().load_configs(loaded_project)
        initial = RunConfigurationsInitial(
            configurations=existing_configs,
            default_argv=loaded_project.metadata.default_argv,
            default_entry=loaded_project.metadata.default_entry,
            project_root=loaded_project.project_root,
            active_config_name=self._host.active_named_run_config_name(),
            initial_selection_name=self._host.active_named_run_config_name(),
        )
        result = RunConfigurationsDialog.run_dialog(
            self._host.dialog_parent(),
            initial=initial,
            tokens=self._host.resolve_theme_tokens(),
        )
        if result is None:
            return False
        persisted = self._persist_run_configurations_result(result)
        if not persisted:
            return False
        selected_name = result.selected_config_name
        if not selected_name:
            return True
        target = next(
            (config for config in result.configurations if config.name == selected_name),
            None,
        )
        if target is None:
            return True
        return self._launch_run_configuration(target, debug=False)

    def handle_run_with_arguments_action(self) -> bool:
        loaded_project = self._host.loaded_project()
        active_tab = self._host.editor_manager().active_tab()
        active_file_path: str | None = None
        if active_tab is not None and getattr(active_tab, "file_path", None):
            active_file_path = active_tab.file_path
        default_entry = ""
        default_argv: tuple[str, ...] = ()
        default_env: Mapping[str, str] = {}
        project_root: str | None = None
        if loaded_project is not None:
            default_entry = (loaded_project.metadata.default_entry or "").strip()
            default_argv = tuple(loaded_project.metadata.default_argv)
            default_env = dict(loaded_project.metadata.env_overrides)
            project_root = loaded_project.project_root

        initial_entry = active_file_path or default_entry
        initial = RunWithArgumentsInitial(
            entry_file=initial_entry,
            argv=default_argv,
            working_directory=None,
            env_overrides=default_env,
            recent_argv_history=tuple(self._host.settings_service().load_recent_argv_history()),
            project_root=project_root,
        )
        invocation = RunWithArgumentsDialog.run_dialog(
            self._host.dialog_parent(),
            initial=initial,
            tokens=self._host.resolve_theme_tokens(),
        )
        if invocation is None:
            return False
        if invocation.argv_text:
            self._host.settings_service().push_recent_argv_history(invocation.argv_text)
        return self.launch_ad_hoc_run_invocation(invocation)

    def launch_ad_hoc_run_invocation(self, invocation: RunInvocation) -> bool:
        if invocation.save_request:
            self._open_save_invocation_as_configuration_dialog(invocation)
        if not self._ensure_run_preflight_ready(
            title="Run With Arguments",
            entry_file=invocation.entry_file,
            working_directory=invocation.working_directory,
        ):
            return False
        return self.start_session(
            mode=constants.RUN_MODE_PYTHON_SCRIPT,
            entry_file=invocation.entry_file,
            argv=list(invocation.argv),
            working_directory=invocation.working_directory,
            env_overrides=dict(invocation.env_overrides),
        )

    def handle_run_active_configuration_action(self) -> bool:
        active_config = self._resolve_active_named_run_config()
        if active_config is None:
            return self.handle_run_project_action()
        return self._launch_run_configuration(active_config, debug=False)

    def handle_rerun_last_debug_target_action(self) -> None:
        target = self._last_debug_target
        if target is None:
            self._host.show_information(
                "Rerun Last Debug Target",
                "No previous debug target is available yet.",
            )
            return
        if isinstance(target, ProjectTarget):
            self.handle_debug_project_action()
            return
        if isinstance(target, ActiveFileTarget):
            if not self._host.editor_tab_factory().open_file_in_editor(target.file_path, preview=False):
                self._host.show_warning(
                    "Rerun Last Debug Target",
                    "The previous debug file could not be reopened.",
                )
                return
            tabs_widget = self._host.editor_tabs_widget()
            if tabs_widget is not None:
                index = self._host.tab_index_for_path(target.file_path)
                if index >= 0:
                    tabs_widget.setCurrentIndex(index)
            self.handle_debug_action()
            return
        if isinstance(target, CurrentTestTarget):
            file_path = target.target_path
            if file_path and self._host.editor_tab_factory().open_file_in_editor(file_path, preview=False):
                tabs_widget = self._host.editor_tabs_widget()
                if tabs_widget is not None:
                    index = self._host.tab_index_for_path(file_path)
                    if index >= 0:
                        tabs_widget.setCurrentIndex(index)
            self._host.test_runner_workflow().debug_current_file_tests()
            return
        if isinstance(target, TestNodeTarget):
            self._host.test_runner_workflow().debug_test_node(target.node_id)

    def handle_tree_run_file(self, absolute_path: str) -> bool:
        entry_path = Path(absolute_path).expanduser().resolve()
        if entry_path.suffix.lower() != ".py":
            return False
        return self.start_session(
            mode=constants.RUN_MODE_PYTHON_SCRIPT,
            entry_file=str(entry_path),
        )

    def handle_tree_run_file_with_arguments(self, absolute_path: str) -> bool:
        entry_path = Path(absolute_path).expanduser().resolve()
        if entry_path.suffix.lower() != ".py":
            return False
        loaded_project = self._host.loaded_project()
        project_root = loaded_project.project_root if loaded_project is not None else None
        default_env: Mapping[str, str] = (
            dict(loaded_project.metadata.env_overrides)
            if loaded_project is not None
            else {}
        )
        initial = RunWithArgumentsInitial(
            entry_file=str(entry_path),
            argv=(),
            working_directory=None,
            env_overrides=default_env,
            recent_argv_history=tuple(self._host.settings_service().load_recent_argv_history()),
            project_root=project_root,
        )
        invocation = RunWithArgumentsDialog.run_dialog(
            self._host.dialog_parent(),
            initial=initial,
            tokens=self._host.resolve_theme_tokens(),
        )
        if invocation is None:
            return False
        if invocation.argv_text:
            self._host.settings_service().push_recent_argv_history(invocation.argv_text)
        return self.launch_ad_hoc_run_invocation(invocation)

    def install_active_run_config_indicator(self) -> None:
        if self._active_run_config_button is not None:
            return
        status_bar = self._host.status_bar()
        button = QToolButton(status_bar)
        button.setObjectName("shell.statusBar.activeRunConfig")
        button.setText("Default")
        button.setToolTip(
            "Active run target for F5 / Run Project. Click to switch configurations or edit them."
        )
        button.setPopupMode(QToolButton.InstantPopup)
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.NoFocus)
        button.setMenu(QMenu(button))
        button.menu().aboutToShow.connect(self._populate_active_run_config_menu)
        status_bar.addPermanentWidget(button)
        self._active_run_config_button = button
        self.refresh_active_run_config_indicator()

    def refresh_active_run_config_indicator(self) -> None:
        button = self._active_run_config_button
        if button is None:
            return
        active_name = self._host.active_named_run_config_name()
        button.setText(active_name if active_name else "Default")
        button.setEnabled(True)

    def _resolve_active_named_run_config(self) -> RunConfiguration | None:
        loaded_project = self._host.loaded_project()
        active_name = self._host.active_named_run_config_name()
        if loaded_project is None or not active_name:
            return None
        configs = self._host.run_config_controller().load_configs(loaded_project)
        for config in configs:
            if config.name == active_name:
                return config
        self._host.set_active_named_run_config_name(None)
        self.refresh_active_run_config_indicator()
        return None

    def _ensure_run_preflight_ready(
        self,
        *,
        title: str,
        entry_file: str,
        working_directory: str | None = None,
        config_name: str | None = None,
    ) -> bool:
        result = build_run_preflight(
            loaded_project=self._host.loaded_project(),
            entry_file=entry_file,
            working_directory=working_directory,
            config_name=config_name,
        )
        if result.is_ready:
            return True
        self._host.show_run_preflight_result(title, result.summary, result.issues)
        return False

    def _launch_run_configuration(
        self,
        config: RunConfiguration,
        *,
        debug: bool,
    ) -> bool:
        mode = constants.RUN_MODE_PYTHON_DEBUG if debug else constants.RUN_MODE_PYTHON_SCRIPT
        title = (
            f"Debug Configuration: {config.name}" if debug else f"Run Configuration: {config.name}"
        )
        if not self._ensure_run_preflight_ready(
            title=title,
            entry_file=config.entry_file,
            working_directory=config.working_directory,
            config_name=config.name,
        ):
            return False
        breakpoints: list[DebugBreakpoint] | None = None
        debug_exception_policy: DebugExceptionPolicy | None = None
        if debug:
            breakpoints = self._host.debug_control_workflow().build_debug_breakpoints_for_launch()
            debug_exception_policy = self._host.debug_exception_policy()
        started = self.start_session(
            mode=mode,
            entry_file=config.entry_file,
            argv=list(config.argv),
            working_directory=config.working_directory,
            env_overrides=dict(config.env_overrides),
            breakpoints=breakpoints,
            debug_exception_policy=debug_exception_policy,
        )
        if started and debug:
            self.record_debug_target(ProjectTarget())
        return started

    def _persist_run_configurations_result(self, result: RunConfigurationsResult) -> bool:
        loaded_project = self._host.loaded_project()
        if loaded_project is None:
            return False
        try:
            self._host.run_config_controller().persist_run_configs(
                loaded_project=loaded_project,
                run_configs=result.configurations,
            )
        except AppValidationError as exc:
            self._host.show_warning("Run Configurations", str(exc))
            return False
        try:
            updated_metadata = set_project_default_argv(
                loaded_project.manifest_path,
                default_argv=list(result.default_argv),
                metadata_if_absent=None
                if loaded_project.manifest_materialized
                else loaded_project.metadata,
            )
        except (ProjectManifestValidationError, ValueError) as exc:
            self._host.show_warning("Run Configurations", str(exc))
            return False
        self._host.set_loaded_project(
            replace(
                loaded_project,
                metadata=updated_metadata,
                manifest_materialized=True,
            )
        )
        selected_name = result.selected_config_name
        existing_names = {config.name for config in result.configurations}
        if selected_name and selected_name in existing_names:
            self._host.set_active_named_run_config_name(selected_name)
        elif (
            self._host.active_named_run_config_name() is not None
            and self._host.active_named_run_config_name() not in existing_names
        ):
            self._host.set_active_named_run_config_name(None)
        self._host.refresh_run_action_states()
        self.refresh_active_run_config_indicator()
        return True

    def _open_save_invocation_as_configuration_dialog(self, invocation: RunInvocation) -> None:
        loaded_project = self._host.loaded_project()
        if loaded_project is None:
            self._host.show_information(
                "Save as Configuration",
                "Open a project first to save named run configurations.",
            )
            return
        existing_configs = self._host.run_config_controller().load_configs(loaded_project)
        proposed_name = _proposed_new_config_name(existing_configs)
        new_config = RunConfiguration(
            name=proposed_name,
            entry_file=invocation.entry_file,
            argv=list(invocation.argv),
            working_directory=invocation.working_directory,
            env_overrides=dict(invocation.env_overrides),
        )
        initial = RunConfigurationsInitial(
            configurations=[*existing_configs, new_config],
            default_argv=loaded_project.metadata.default_argv,
            default_entry=loaded_project.metadata.default_entry,
            project_root=loaded_project.project_root,
            active_config_name=self._host.active_named_run_config_name(),
            initial_selection_name=new_config.name,
        )
        result = RunConfigurationsDialog.run_dialog(
            self._host.dialog_parent(),
            initial=initial,
            tokens=self._host.resolve_theme_tokens(),
        )
        if result is None:
            return
        self._persist_run_configurations_result(result)

    def _populate_active_run_config_menu(self) -> None:
        button = self._active_run_config_button
        if button is None:
            return
        menu = button.menu()
        if menu is None:
            return
        menu.clear()
        loaded_project = self._host.loaded_project()

        default_action = menu.addAction("Default (no named configuration)")
        default_action.setCheckable(True)
        default_action.setChecked(self._host.active_named_run_config_name() is None)
        default_action.triggered.connect(self._set_active_run_config_to_default)

        if loaded_project is not None:
            configs = self._host.run_config_controller().load_configs(loaded_project)
        else:
            configs = []
        if configs:
            menu.addSeparator()
            for config in configs:
                action = menu.addAction(config.name)
                action.setCheckable(True)
                action.setChecked(config.name == self._host.active_named_run_config_name())
                action.triggered.connect(
                    lambda _checked=False, name=config.name: self._set_active_run_config_by_name(name)
                )
        menu.addSeparator()
        run_with_args_action = menu.addAction("Run With Arguments...")
        run_with_args_action.triggered.connect(self.handle_run_with_arguments_action)
        edit_action = menu.addAction("Edit Configurations...")
        edit_action.setEnabled(loaded_project is not None)
        edit_action.triggered.connect(self.handle_run_with_configuration_action)

    def _set_active_run_config_to_default(self) -> None:
        if self._host.active_named_run_config_name() is None:
            return
        self._host.set_active_named_run_config_name(None)
        self._host.refresh_run_action_states()
        self.refresh_active_run_config_indicator()

    def _set_active_run_config_by_name(self, name: str) -> None:
        normalized = (name or "").strip()
        if not normalized:
            return
        if normalized == self._host.active_named_run_config_name():
            return
        self._host.set_active_named_run_config_name(normalized)
        self._host.refresh_run_action_states()
        self.refresh_active_run_config_indicator()

    def _start_active_file_session(self, *, mode: str) -> bool:
        active_tab = self._host.editor_manager().active_tab()
        if active_tab is None:
            self._host.show_warning("Run unavailable", "Open a file tab before running.")
            return False
        entry_path = Path(active_tab.file_path).expanduser().resolve()
        active_file_path = str(entry_path)
        if entry_path.suffix.lower() != ".py":
            self._host.show_warning("Run unavailable", "Active file must be a Python file.")
            return False
        transient_entry_file: str | None = None
        entry_file = active_file_path
        skip_save = False
        source_maps: list[DebugSourceMap] | None = None
        if active_tab.is_dirty:
            transient_entry_file = self._write_transient_entry_file(
                source_file_path=active_tab.file_path,
                source_content=active_tab.current_content,
            )
            entry_file = transient_entry_file
            skip_save = True
            source_maps = [DebugSourceMap(runtime_path=transient_entry_file, source_path=active_file_path)]
        breakpoints: list[DebugBreakpoint] | None = None
        if mode == constants.RUN_MODE_PYTHON_DEBUG:
            breakpoints = self._host.debug_control_workflow().build_debug_breakpoints_for_launch(
                active_file_path=active_file_path,
                remapped_active_path=transient_entry_file,
            )
        started = self.start_session(
            mode=mode,
            entry_file=entry_file,
            breakpoints=breakpoints,
            debug_exception_policy=self._host.debug_exception_policy()
            if mode == constants.RUN_MODE_PYTHON_DEBUG
            else None,
            source_maps=source_maps,
            skip_save=skip_save,
        )
        if started and mode == constants.RUN_MODE_PYTHON_DEBUG:
            self.record_debug_target(ActiveFileTarget(file_path=active_file_path))
        if transient_entry_file is not None:
            if started:
                self._host.set_active_transient_entry_file_path(transient_entry_file)
            else:
                self._delete_transient_entry_file(transient_entry_file)
        return started

    def _write_transient_entry_file(self, *, source_file_path: str, source_content: str) -> str:
        source_name = Path(source_file_path).name
        safe_stem = Path(source_name).stem or "buffer"
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".py",
            prefix=f"cbcs_{safe_stem}_",
            delete=False,
        ) as handle:
            handle.write(source_content)
            return str(Path(handle.name).resolve())

    def delete_transient_entry_file(self, path: str) -> None:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            self._host.logger().warning("Failed to delete transient run file: %s", path)

    def _delete_transient_entry_file(self, path: str) -> None:
        self.delete_transient_entry_file(path)
