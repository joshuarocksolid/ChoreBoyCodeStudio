"""Plugin manager, dependency inspector, and plugin runtime failure UX."""

from __future__ import annotations

from typing import Any, Callable, Protocol, cast

from PySide2.QtWidgets import QDialog, QMessageBox

from app.core import constants
from app.plugins.registry_store import (
    clear_registry_entry_failures,
    record_registry_entry_failure,
)
from app.shell.dependency_panel import DependencyInspectorDialog
from app.shell.dependency_wizard_dialog import AddDependencyWizardDialog
from app.shell.plugins_panel import PluginManagerDialog


class _ConnectableSignal(Protocol):
    def connect(self, slot: Callable[..., object]) -> object:
        ...


class PluginDialogHost(Protocol):
    def dialog_parent(self) -> Any:
        ...

    def state_root(self) -> str | None:
        ...

    def loaded_project_root(self) -> str | None:
        ...

    def plugin_safe_mode_enabled(self) -> bool:
        ...

    def set_plugin_safe_mode(self, enabled: bool) -> None:
        ...

    def plugin_activation_snapshot(self) -> object:
        ...

    def reload_plugin_activation(self) -> None:
        ...

    def reload_current_project(self) -> None:
        ...

    def plugin_api_broker(self) -> Any:
        ...

    def plugin_manager_dialog(self) -> PluginManagerDialog | None:
        ...

    def set_plugin_manager_dialog(self, dialog: PluginManagerDialog | None) -> None:
        ...

    def dependency_inspector_dialog(self) -> DependencyInspectorDialog | None:
        ...

    def set_dependency_inspector_dialog(self, dialog: DependencyInspectorDialog | None) -> None:
        ...


class PluginDialogWorkflow:
    """Owns plugin-manager UI, dependency tooling, and runtime failure bookkeeping."""

    def __init__(self, host: PluginDialogHost) -> None:
        self._host = host

    def handle_open_plugin_manager_action(self) -> None:
        parent = self._host.dialog_parent()
        dialog = self._host.plugin_manager_dialog()
        if dialog is None:
            dialog = PluginManagerDialog(
                state_root=self._host.state_root(),
                project_root=self._host.loaded_project_root(),
                activation_snapshot_provider=self._host.plugin_activation_snapshot,
                on_plugins_changed=self._host.reload_plugin_activation,
                safe_mode_enabled=self._host.plugin_safe_mode_enabled(),
                on_safe_mode_changed=self.handle_plugin_safe_mode_changed,
                parent=parent,
            )
            dialog.finished.connect(
                lambda _result: self._host.set_plugin_manager_dialog(None)
            )
            self._host.set_plugin_manager_dialog(dialog)
        dialog.set_safe_mode_enabled(self._host.plugin_safe_mode_enabled())
        dialog.set_project_root(self._host.loaded_project_root())
        dialog.refresh_plugins()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def handle_open_dependency_inspector_action(self) -> None:
        parent = self._host.dialog_parent()
        project_root = self._host.loaded_project_root()
        if project_root is None:
            QMessageBox.warning(parent, "Dependency Inspector", "Open a project first.")
            return
        dialog = self._host.dependency_inspector_dialog()
        if dialog is None or getattr(dialog, "_project_root", "") != project_root:
            dialog = DependencyInspectorDialog(project_root=project_root, parent=parent)
            dialog.finished.connect(
                lambda _result: self._host.set_dependency_inspector_dialog(None)
            )
            cast(_ConnectableSignal, dialog.dependency_changed).connect(
                self._host.reload_current_project
            )
            self._host.set_dependency_inspector_dialog(dialog)
        dialog.refresh()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def handle_add_dependency_action(self) -> None:
        parent = self._host.dialog_parent()
        project_root = self._host.loaded_project_root()
        if project_root is None:
            QMessageBox.warning(parent, "Add Dependency", "Open a project first.")
            return
        dialog = AddDependencyWizardDialog(project_root=project_root, parent=parent)
        if dialog.exec_() != QDialog.Accepted:
            return
        result = dialog.last_result
        if result is None:
            return
        QMessageBox.information(
            parent,
            "Add Dependency",
            f"Added dependency '{result.name}' ({result.classification}).",
        )
        self._host.reload_current_project()
        dependency_dialog = self._host.dependency_inspector_dialog()
        if dependency_dialog is not None:
            dependency_dialog.refresh()

    def handle_plugin_safe_mode_changed(self, enabled: bool) -> None:
        self._host.set_plugin_safe_mode(enabled)
        self._host.reload_plugin_activation()

    def execute_plugin_runtime_command(self, command_id: str, payload: dict[str, object]) -> object:
        result = self._host.plugin_api_broker().invoke_runtime_command(command_id, payload)
        return self._host.plugin_api_broker().coerce_result_payload(result)

    def record_plugin_runtime_failure(self, plugin_id: str, version: str, error_message: str) -> None:
        parent = self._host.dialog_parent()
        updated_registry = record_registry_entry_failure(
            plugin_id,
            version,
            error_message=error_message,
            disable_after_failures=constants.PLUGIN_DISABLE_AFTER_FAILURES_DEFAULT,
            state_root=self._host.state_root(),
        )
        updated_entry = None
        for entry in updated_registry.entries:
            if entry.plugin_id == plugin_id and entry.version == version:
                updated_entry = entry
                break
        if updated_entry is not None and not updated_entry.enabled:
            QMessageBox.warning(
                parent,
                "Plugin Disabled",
                f"{plugin_id}@{version} was disabled after repeated runtime failures.",
            )
            self._host.reload_plugin_activation()

    def clear_plugin_runtime_failure(self, plugin_id: str, version: str) -> None:
        clear_registry_entry_failures(
            plugin_id,
            version,
            state_root=self._host.state_root(),
        )


class MainWindowPluginDialogHost:
    """Host ports for ``PluginDialogWorkflow`` backed by a MainWindow instance."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def dialog_parent(self) -> Any:
        return self._window

    def state_root(self) -> str | None:
        return self._window._state_root

    def loaded_project_root(self) -> str | None:
        loaded_project = self._window._loaded_project
        return None if loaded_project is None else loaded_project.project_root

    def plugin_safe_mode_enabled(self) -> bool:
        return self._window._plugin_safe_mode

    def set_plugin_safe_mode(self, enabled: bool) -> None:
        self._window._shell_preferences_runtime.set_plugin_safe_mode(enabled)

    def plugin_activation_snapshot(self) -> object:
        return self._window._plugin_activation_workflow.snapshot(
            project_root=self.loaded_project_root()
        )

    def reload_plugin_activation(self) -> None:
        self._window._plugin_activation_workflow.reload()

    def reload_current_project(self) -> None:
        self._window._project_tree_ui_workflow.reload_current_project()

    def plugin_api_broker(self) -> Any:
        return self._window._plugin_api_broker

    def plugin_manager_dialog(self) -> PluginManagerDialog | None:
        return self._window._plugin_manager_dialog

    def set_plugin_manager_dialog(self, dialog: PluginManagerDialog | None) -> None:
        self._window._plugin_manager_dialog = dialog

    def dependency_inspector_dialog(self) -> DependencyInspectorDialog | None:
        return self._window._dependency_inspector_dialog

    def set_dependency_inspector_dialog(self, dialog: DependencyInspectorDialog | None) -> None:
        self._window._dependency_inspector_dialog = dialog


def build_plugin_dialog_workflow(window: Any) -> PluginDialogWorkflow:
    return PluginDialogWorkflow(MainWindowPluginDialogHost(window))
