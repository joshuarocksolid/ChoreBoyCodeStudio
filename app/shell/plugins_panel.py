from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from app.bootstrap.paths import PathInput, global_plugins_logs_dir
from app.plugins.exporter import export_installed_plugin
from app.plugins.installer import install_plugin, set_plugin_enabled, uninstall_plugin
from app.plugins.project_config import (
    set_project_plugin_enabled,
    set_project_preferred_provider,
    set_project_plugin_version_pin,
)
from app.plugins.trust_store import is_runtime_plugin_trusted, set_runtime_plugin_trust
from app.shell.file_dialogs import choose_existing_directory, choose_open_file
from app.shell.plugin_activation_workflow import PluginActivationSnapshot, provider_preference_options


class PluginManagerDialog(QDialog):
    def __init__(
        self,
        *,
        state_root: PathInput | None = None,
        project_root: str | None = None,
        activation_snapshot_provider: Callable[[], PluginActivationSnapshot],
        on_plugins_changed=None,
        safe_mode_enabled: bool = False,
        on_safe_mode_changed=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._state_root = state_root
        self._project_root = project_root
        self._activation_snapshot_provider = activation_snapshot_provider
        self._on_plugins_changed = on_plugins_changed
        self._on_safe_mode_changed = on_safe_mode_changed
        self._plugins_tree = QTreeWidget(self)
        self._plugins_tree.setColumnCount(9)
        self._plugins_tree.setHeaderLabels(
            ["Plugin", "Version", "Source", "Enabled", "Project", "Providers", "Permissions", "Compatibility", "Path"]
        )
        self._plugins_tree.setSelectionMode(QTreeWidget.SingleSelection)
        self._plugins_tree.setRootIsDecorated(False)
        self._plugins_tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._plugins_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._plugins_tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._plugins_tree.header().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._plugins_tree.header().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._plugins_tree.header().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self._plugins_tree.header().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self._plugins_tree.header().setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self._plugins_tree.header().setSectionResizeMode(8, QHeaderView.Stretch)

        self._install_button = QPushButton("Install...", self)
        self._uninstall_button = QPushButton("Uninstall", self)
        self._enable_button = QPushButton("Enable", self)
        self._disable_button = QPushButton("Disable", self)
        self._pin_button = QPushButton("Pin To Project", self)
        self._clear_pin_button = QPushButton("Clear Pin", self)
        self._project_enable_button = QPushButton("Enable In Project", self)
        self._project_disable_button = QPushButton("Disable In Project", self)
        self._prefer_provider_button = QPushButton("Prefer Provider", self)
        self._clear_preference_button = QPushButton("Clear Preference", self)
        self._export_button = QPushButton("Export...", self)
        self._refresh_button = QPushButton("Refresh", self)
        self._close_button = QPushButton("Close", self)
        self._safe_mode_checkbox = QCheckBox("Safe mode (disable all plugins)", self)
        self._safe_mode_checkbox.setChecked(bool(safe_mode_enabled))

        controls_row = QHBoxLayout()
        controls_row.addWidget(self._safe_mode_checkbox)
        controls_row.addStretch(1)
        controls_row.addWidget(self._install_button)
        controls_row.addWidget(self._uninstall_button)
        controls_row.addWidget(self._enable_button)
        controls_row.addWidget(self._disable_button)
        controls_row.addWidget(self._pin_button)
        controls_row.addWidget(self._clear_pin_button)
        controls_row.addWidget(self._project_enable_button)
        controls_row.addWidget(self._project_disable_button)
        controls_row.addWidget(self._prefer_provider_button)
        controls_row.addWidget(self._clear_preference_button)
        controls_row.addWidget(self._export_button)
        controls_row.addWidget(self._refresh_button)
        controls_row.addWidget(self._close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._plugins_tree)
        layout.addLayout(controls_row)

        self.setWindowTitle("Plugin Manager")
        self.resize(980, 480)

        self._install_button.clicked.connect(self._handle_install)
        self._uninstall_button.clicked.connect(self._handle_uninstall)
        self._enable_button.clicked.connect(self._handle_enable)
        self._disable_button.clicked.connect(self._handle_disable)
        self._pin_button.clicked.connect(self._handle_pin_version)
        self._clear_pin_button.clicked.connect(self._handle_clear_pin)
        self._project_enable_button.clicked.connect(self._handle_project_enable)
        self._project_disable_button.clicked.connect(self._handle_project_disable)
        self._prefer_provider_button.clicked.connect(self._handle_prefer_provider)
        self._clear_preference_button.clicked.connect(self._handle_clear_provider_preference)
        self._export_button.clicked.connect(self._handle_export)
        self._refresh_button.clicked.connect(self.refresh_plugins)
        self._close_button.clicked.connect(self.accept)
        self._safe_mode_checkbox.toggled.connect(self._handle_safe_mode_toggled)
        self._plugins_tree.itemSelectionChanged.connect(self._update_button_states)

        self.refresh_plugins()

    def refresh_plugins(self) -> None:
        self._plugins_tree.clear()
        snapshot = self._activation_snapshot_provider()
        for discovered in snapshot.discovered_plugins:
            key = (discovered.plugin_id, discovered.version)
            registry_entry = snapshot.registry_map.get(key)
            display_state = snapshot.display_state_for(discovered)
            effective_enabled = display_state.effective_enabled
            project_status = display_state.project_status
            if discovered.compatibility is None:
                compatibility_text = "invalid"
            elif discovered.compatibility.is_compatible:
                compatibility_text = "compatible"
            else:
                compatibility_text = "; ".join(discovered.compatibility.reasons) or "incompatible"
            source_text = "bundled" if discovered.is_bundled else "installed"
            providers_text = "-"
            permissions_text = "-"
            provider_entries: list[dict[str, object]] = []
            if discovered.manifest is not None:
                provider_entries = [
                    provider.to_dict() for provider in discovered.manifest.workflow_providers
                ]
                provider_ids = [provider.provider_id for provider in discovered.manifest.workflow_providers]
                if provider_ids:
                    providers_text = ", ".join(provider_ids)
                if discovered.manifest.permissions:
                    permissions_text = ", ".join(discovered.manifest.permissions)
            preferred_selectors = list(display_state.preferred_selectors)
            if preferred_selectors:
                preferred_text = ", ".join(preferred_selectors)
                project_status = preferred_text if project_status == "-" else f"{project_status}; {preferred_text}"
            detail_lines = [
                f"Plugin: {discovered.plugin_id}@{discovered.version}",
                f"Source: {source_text}",
                f"Path: {discovered.install_path}",
                f"Plugin host log: {global_plugins_logs_dir(self._state_root) / 'plugin_host.log'}",
            ]
            if discovered.manifest is not None and discovered.manifest.capabilities:
                detail_lines.append(f"Capabilities: {', '.join(discovered.manifest.capabilities)}")
            if discovered.manifest is not None and discovered.manifest.permissions:
                detail_lines.append(f"Permissions: {', '.join(discovered.manifest.permissions)}")
            if preferred_selectors:
                detail_lines.append(f"Preferred selectors: {', '.join(preferred_selectors)}")
            if registry_entry is not None and registry_entry.failure_count > 0:
                compatibility_text = f"{compatibility_text}; failures={registry_entry.failure_count}"
                detail_lines.append(f"Failure count: {registry_entry.failure_count}")
            if registry_entry is not None and registry_entry.last_error:
                compatibility_text = f"{compatibility_text}; last error recorded"
                detail_lines.append(f"Last error: {registry_entry.last_error}")
            if discovered.errors:
                detail_lines.append("Issues:")
                detail_lines.extend(f"- {error}" for error in discovered.errors)
            enabled_text = "yes" if effective_enabled else "no"
            item = QTreeWidgetItem(
                [
                    discovered.plugin_id,
                    discovered.version,
                    source_text,
                    enabled_text,
                    project_status,
                    providers_text,
                    permissions_text,
                    compatibility_text,
                    discovered.install_path,
                ]
            )
            item.setData(0, Qt.UserRole, discovered.plugin_id)
            item.setData(1, Qt.UserRole, discovered.version)
            item.setData(2, Qt.UserRole, effective_enabled)
            runtime_flag = bool(
                discovered.manifest is not None
                and discovered.manifest.runtime_entrypoint is not None
            )
            item.setData(3, Qt.UserRole, runtime_flag)
            item.setData(4, Qt.UserRole, discovered.source_kind)
            item.setData(5, Qt.UserRole, discovered.install_path)
            item.setData(6, Qt.UserRole, provider_entries)
            item.setData(7, Qt.UserRole, preferred_selectors)
            detail_text = "\n".join(detail_lines)
            for column in range(self._plugins_tree.columnCount()):
                item.setToolTip(column, detail_text)
            self._plugins_tree.addTopLevelItem(item)
        self._update_button_states()

    def set_safe_mode_enabled(self, enabled: bool) -> None:
        self._safe_mode_checkbox.setChecked(bool(enabled))

    def set_project_root(self, project_root: str | None) -> None:
        self._project_root = project_root

    def _update_button_states(self) -> None:
        selected = self._selected_plugin_key()
        has_selection = selected is not None
        self._uninstall_button.setEnabled(has_selection and self._selected_source_kind() != "bundled")
        self._enable_button.setEnabled(has_selection and not self._selected_enabled())
        self._disable_button.setEnabled(has_selection and self._selected_enabled())
        self._export_button.setEnabled(has_selection)
        project_controls_enabled = has_selection and bool(self._project_root)
        self._pin_button.setEnabled(project_controls_enabled)
        self._clear_pin_button.setEnabled(project_controls_enabled)
        self._project_enable_button.setEnabled(project_controls_enabled)
        self._project_disable_button.setEnabled(project_controls_enabled)
        self._prefer_provider_button.setEnabled(project_controls_enabled and bool(self._selected_provider_entries()))
        self._clear_preference_button.setEnabled(
            project_controls_enabled and bool(self._selected_preferred_selectors())
        )

    def _selected_plugin_key(self) -> tuple[str, str] | None:
        selected_items = self._plugins_tree.selectedItems()
        if not selected_items:
            return None
        selected_item = selected_items[0]
        plugin_id = selected_item.data(0, Qt.UserRole)
        version = selected_item.data(1, Qt.UserRole)
        if not isinstance(plugin_id, str) or not isinstance(version, str):
            return None
        return plugin_id, version

    def _selected_enabled(self) -> bool:
        selected_items = self._plugins_tree.selectedItems()
        if not selected_items:
            return False
        enabled = selected_items[0].data(2, Qt.UserRole)
        return bool(enabled)

    def _selected_runtime(self) -> bool:
        selected_items = self._plugins_tree.selectedItems()
        if not selected_items:
            return False
        runtime_flag = selected_items[0].data(3, Qt.UserRole)
        return bool(runtime_flag)

    def _selected_provider_entries(self) -> list[dict[str, object]]:
        selected_items = self._plugins_tree.selectedItems()
        if not selected_items:
            return []
        provider_entries = selected_items[0].data(6, Qt.UserRole)
        if not isinstance(provider_entries, list):
            return []
        normalized_entries: list[dict[str, object]] = []
        for entry in provider_entries:
            if isinstance(entry, dict):
                normalized_entries.append(entry)
        return normalized_entries

    def _selected_preferred_selectors(self) -> list[str]:
        selected_items = self._plugins_tree.selectedItems()
        if not selected_items:
            return []
        selectors = selected_items[0].data(7, Qt.UserRole)
        if not isinstance(selectors, list):
            return []
        return [selector for selector in selectors if isinstance(selector, str)]

    def _selected_source_kind(self) -> str:
        selected_items = self._plugins_tree.selectedItems()
        if not selected_items:
            return ""
        source_kind = selected_items[0].data(4, Qt.UserRole)
        return source_kind if isinstance(source_kind, str) else ""

    def _selected_install_path(self) -> str | None:
        selected_items = self._plugins_tree.selectedItems()
        if not selected_items:
            return None
        install_path = selected_items[0].data(5, Qt.UserRole)
        return install_path if isinstance(install_path, str) else None

    def _notify_plugins_changed(self) -> None:
        if self._on_plugins_changed is not None:
            self._on_plugins_changed()
        self.refresh_plugins()

    def _handle_install(self) -> None:
        source_path = self._select_source_path()
        if source_path is None:
            return
        try:
            result = install_plugin(source_path, state_root=self._state_root)
        except Exception as exc:
            QMessageBox.warning(self, "Plugin Install Failed", str(exc))
            return
        self._notify_plugins_changed()
        QMessageBox.information(
            self,
            "Plugin Installed",
            f"Installed {result.plugin_id}@{result.version}",
        )

    def _select_source_path(self) -> str | None:
        selected_directory = choose_existing_directory(self, "Select Plugin Folder", str(Path.home()))
        if selected_directory:
            return selected_directory
        selected_file = choose_open_file(
            self,
            "Select Plugin Package",
            str(Path.home()),
            "Plugin Packages (*.zip)",
        )
        if selected_file:
            return selected_file
        return None

    def _handle_uninstall(self) -> None:
        selected = self._selected_plugin_key()
        if selected is None:
            return
        plugin_id, version = selected
        confirmation = QMessageBox.question(
            self,
            "Move Plugin to Trash",
            (
                f"Move {plugin_id}@{version} to trash and uninstall?\n"
                "You can restore it from trash if needed."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirmation != QMessageBox.Yes:
            return
        try:
            uninstall_plugin(plugin_id, version=version, state_root=self._state_root)
        except Exception as exc:
            QMessageBox.warning(self, "Plugin Uninstall Failed", str(exc))
            return
        self._notify_plugins_changed()
        QMessageBox.information(
            self,
            "Plugin Uninstalled",
            f"{plugin_id}@{version} was moved to trash and uninstalled.",
        )

    def _handle_enable(self) -> None:
        selected = self._selected_plugin_key()
        if selected is None:
            return
        plugin_id, version = selected
        source_kind = self._selected_source_kind()
        if (
            self._selected_runtime()
            and source_kind != "bundled"
            and not is_runtime_plugin_trusted(
            plugin_id,
            version,
            state_root=self._state_root,
        )
        ):
            confirmation = QMessageBox.question(
                self,
                "Trust Runtime Plugin",
                (
                    f"{plugin_id}@{version} contains runtime code that executes outside the editor process."
                    "\n\nEnable only if you trust this plugin."
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirmation != QMessageBox.Yes:
                return
            set_runtime_plugin_trust(
                plugin_id,
                version,
                trusted=True,
                state_root=self._state_root,
            )
        try:
            set_plugin_enabled(
                plugin_id,
                version,
                enabled=True,
                state_root=self._state_root,
                install_path=self._selected_install_path(),
                source_kind=source_kind or "installed",
            )
        except Exception as exc:
            QMessageBox.warning(self, "Plugin Enable Failed", str(exc))
            return
        self._notify_plugins_changed()

    def _handle_disable(self) -> None:
        selected = self._selected_plugin_key()
        if selected is None:
            return
        plugin_id, version = selected
        try:
            set_plugin_enabled(
                plugin_id,
                version,
                enabled=False,
                state_root=self._state_root,
                install_path=self._selected_install_path(),
                source_kind=self._selected_source_kind() or "installed",
            )
        except Exception as exc:
            QMessageBox.warning(self, "Plugin Disable Failed", str(exc))
            return
        self._notify_plugins_changed()

    def _handle_safe_mode_toggled(self, checked: bool) -> None:
        if self._on_safe_mode_changed is not None:
            self._on_safe_mode_changed(bool(checked))

    def _handle_export(self) -> None:
        selected = self._selected_plugin_key()
        if selected is None:
            return
        plugin_id, version = selected
        destination_dir = choose_existing_directory(self, "Select Export Destination", str(Path.home()))
        if not destination_dir:
            return
        try:
            state_root = None if self._state_root is None else str(self._state_root)
            archive_path = export_installed_plugin(
                plugin_id,
                version,
                output_directory=destination_dir,
                state_root=state_root,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Plugin Export Failed", str(exc))
            return
        QMessageBox.information(
            self,
            "Plugin Exported",
            f"Exported to {archive_path}",
        )

    def _handle_pin_version(self) -> None:
        if not self._project_root:
            return
        selected = self._selected_plugin_key()
        if selected is None:
            return
        plugin_id, version = selected
        set_project_plugin_version_pin(self._project_root, plugin_id, version)
        self._notify_plugins_changed()

    def _handle_clear_pin(self) -> None:
        if not self._project_root:
            return
        selected = self._selected_plugin_key()
        if selected is None:
            return
        plugin_id, _version = selected
        set_project_plugin_version_pin(self._project_root, plugin_id, None)
        self._notify_plugins_changed()

    def _handle_project_enable(self) -> None:
        if not self._project_root:
            return
        selected = self._selected_plugin_key()
        if selected is None:
            return
        plugin_id, _version = selected
        set_project_plugin_enabled(self._project_root, plugin_id, enabled=True)
        self._notify_plugins_changed()

    def _handle_project_disable(self) -> None:
        if not self._project_root:
            return
        selected = self._selected_plugin_key()
        if selected is None:
            return
        plugin_id, _version = selected
        set_project_plugin_enabled(self._project_root, plugin_id, enabled=False)
        self._notify_plugins_changed()

    def _handle_prefer_provider(self) -> None:
        if not self._project_root:
            return
        selected = self._selected_plugin_key()
        if selected is None:
            return
        plugin_id, _version = selected
        options = self._provider_preference_options(plugin_id, self._selected_provider_entries())
        if not options:
            QMessageBox.information(self, "No Providers", "Selected plugin does not contribute workflow providers.")
            return
        selected_option = options[0]
        if len(options) > 1:
            labels = [option["label"] for option in options]
            chosen_label, accepted = QInputDialog.getItem(
                self,
                "Prefer Provider",
                "Choose workflow preference scope:",
                labels,
                0,
                False,
            )
            if not accepted:
                return
            for option in options:
                if option["label"] == chosen_label:
                    selected_option = option
                    break
        set_project_preferred_provider(
            self._project_root,
            selected_option["selector_key"],
            selected_option["provider_key"],
        )
        self._notify_plugins_changed()

    def _handle_clear_provider_preference(self) -> None:
        if not self._project_root:
            return
        selectors = self._selected_preferred_selectors()
        if not selectors:
            return
        selected_selector = selectors[0]
        if len(selectors) > 1:
            chosen_selector, accepted = QInputDialog.getItem(
                self,
                "Clear Provider Preference",
                "Choose preference to clear:",
                selectors,
                0,
                False,
            )
            if not accepted:
                return
            selected_selector = chosen_selector
        set_project_preferred_provider(self._project_root, selected_selector, None)
        self._notify_plugins_changed()

    @staticmethod
    def _provider_preference_options(
        plugin_id: str,
        provider_entries: list[dict[str, object]],
    ) -> list[dict[str, str]]:
        return [
            {
                "label": option.label,
                "selector_key": option.selector_key,
                "provider_key": option.provider_key,
            }
            for option in provider_preference_options(plugin_id, provider_entries)
        ]
