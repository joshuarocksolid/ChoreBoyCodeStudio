from __future__ import annotations

from pathlib import Path

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from app.bootstrap.paths import PathInput
from app.plugins.discovery import discover_installed_plugins
from app.plugins.exporter import export_installed_plugin
from app.plugins.installer import install_plugin, set_plugin_enabled, uninstall_plugin
from app.plugins.registry_store import load_plugin_registry
from app.plugins.trust_store import is_runtime_plugin_trusted, set_runtime_plugin_trust
from app.shell.file_dialogs import choose_existing_directory, choose_open_file


class PluginManagerDialog(QDialog):
    def __init__(
        self,
        *,
        state_root: PathInput | None = None,
        on_plugins_changed=None,
        safe_mode_enabled: bool = False,
        on_safe_mode_changed=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._state_root = state_root
        self._on_plugins_changed = on_plugins_changed
        self._on_safe_mode_changed = on_safe_mode_changed
        self._plugins_tree = QTreeWidget(self)
        self._plugins_tree.setColumnCount(5)
        self._plugins_tree.setHeaderLabels(["Plugin", "Version", "Enabled", "Compatibility", "Path"])
        self._plugins_tree.setSelectionMode(QTreeWidget.SingleSelection)
        self._plugins_tree.setRootIsDecorated(False)
        self._plugins_tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._plugins_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._plugins_tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._plugins_tree.header().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._plugins_tree.header().setSectionResizeMode(4, QHeaderView.Stretch)

        self._install_button = QPushButton("Install...", self)
        self._uninstall_button = QPushButton("Uninstall", self)
        self._enable_button = QPushButton("Enable", self)
        self._disable_button = QPushButton("Disable", self)
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
        self._export_button.clicked.connect(self._handle_export)
        self._refresh_button.clicked.connect(self.refresh_plugins)
        self._close_button.clicked.connect(self.accept)
        self._safe_mode_checkbox.toggled.connect(self._handle_safe_mode_toggled)
        self._plugins_tree.itemSelectionChanged.connect(self._update_button_states)

        self.refresh_plugins()

    def refresh_plugins(self) -> None:
        self._plugins_tree.clear()
        registry = load_plugin_registry(self._state_root)
        enabled_map = {
            (entry.plugin_id, entry.version): entry.enabled
            for entry in registry.entries
        }
        discovered_plugins = discover_installed_plugins(state_root=self._state_root)
        for discovered in discovered_plugins:
            key = (discovered.plugin_id, discovered.version)
            enabled = enabled_map.get(key, True)
            if discovered.compatibility is None:
                compatibility_text = "invalid"
            elif discovered.compatibility.is_compatible:
                compatibility_text = "compatible"
            else:
                compatibility_text = "; ".join(discovered.compatibility.reasons) or "incompatible"
            enabled_text = "yes" if enabled else "no"
            item = QTreeWidgetItem(
                [
                    discovered.plugin_id,
                    discovered.version,
                    enabled_text,
                    compatibility_text,
                    discovered.install_path,
                ]
            )
            item.setData(0, Qt.UserRole, discovered.plugin_id)
            item.setData(1, Qt.UserRole, discovered.version)
            item.setData(2, Qt.UserRole, enabled)
            runtime_flag = bool(
                discovered.manifest is not None
                and discovered.manifest.runtime_entrypoint is not None
            )
            item.setData(3, Qt.UserRole, runtime_flag)
            self._plugins_tree.addTopLevelItem(item)
        self._update_button_states()

    def set_safe_mode_enabled(self, enabled: bool) -> None:
        self._safe_mode_checkbox.setChecked(bool(enabled))

    def _update_button_states(self) -> None:
        selected = self._selected_plugin_key()
        has_selection = selected is not None
        self._uninstall_button.setEnabled(has_selection)
        self._enable_button.setEnabled(has_selection and not self._selected_enabled())
        self._disable_button.setEnabled(has_selection and self._selected_enabled())
        self._export_button.setEnabled(has_selection)

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

    def _handle_install(self) -> None:
        source_path = self._select_source_path()
        if source_path is None:
            return
        try:
            result = install_plugin(source_path, state_root=self._state_root)
        except Exception as exc:
            QMessageBox.warning(self, "Plugin Install Failed", str(exc))
            return
        self.refresh_plugins()
        if self._on_plugins_changed is not None:
            self._on_plugins_changed()
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
            "Uninstall Plugin",
            f"Uninstall {plugin_id}@{version}?",
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
        self.refresh_plugins()
        if self._on_plugins_changed is not None:
            self._on_plugins_changed()

    def _handle_enable(self) -> None:
        selected = self._selected_plugin_key()
        if selected is None:
            return
        plugin_id, version = selected
        if self._selected_runtime() and not is_runtime_plugin_trusted(
            plugin_id,
            version,
            state_root=self._state_root,
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
            set_plugin_enabled(plugin_id, version, enabled=True, state_root=self._state_root)
        except Exception as exc:
            QMessageBox.warning(self, "Plugin Enable Failed", str(exc))
            return
        self.refresh_plugins()
        if self._on_plugins_changed is not None:
            self._on_plugins_changed()

    def _handle_disable(self) -> None:
        selected = self._selected_plugin_key()
        if selected is None:
            return
        plugin_id, version = selected
        try:
            set_plugin_enabled(plugin_id, version, enabled=False, state_root=self._state_root)
        except Exception as exc:
            QMessageBox.warning(self, "Plugin Disable Failed", str(exc))
            return
        self.refresh_plugins()
        if self._on_plugins_changed is not None:
            self._on_plugins_changed()

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
            archive_path = export_installed_plugin(
                plugin_id,
                version,
                output_directory=destination_dir,
                state_root=self._state_root,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Plugin Export Failed", str(exc))
            return
        QMessageBox.information(
            self,
            "Plugin Exported",
            f"Exported to {archive_path}",
        )
