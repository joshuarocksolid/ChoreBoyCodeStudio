"""Modal dialog for editing named run configurations and the project default argv.

Mirrors the JetBrains "Edit Run/Debug Configurations" / VS Code ``launch.json`` UX. The dialog
collects the user's intent and returns a structured :class:`RunConfigurationsResult`; the caller
is responsible for persisting the result (typically via
:class:`~app.shell.run_config_controller.RunConfigController` and
:func:`~app.project.project_manifest.set_project_default_argv`). Keeping persistence outside
the dialog keeps it testable and aligns with the existing dialog conventions in this package.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence, cast

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.errors import AppValidationError
from app.project.run_configs import (
    RunConfiguration,
    env_overrides_to_text,
    parse_env_overrides_text,
)
from app.shell.run_config_controller import tokenize_argv_text
from app.shell.run_with_arguments_dialog import _join_argv_for_display
from app.shell.style_sheet import build_settings_style_sheet
from app.shell.theme_tokens import ShellThemeTokens, tokens_from_palette


@dataclass(frozen=True)
class RunConfigurationsResult:
    """Outcome returned by :class:`RunConfigurationsDialog` after the user accepts."""

    configurations: list[RunConfiguration]
    default_argv: list[str]
    selected_config_name: Optional[str] = None


@dataclass(frozen=True)
class RunConfigurationsInitial:
    """Initial values used to seed :class:`RunConfigurationsDialog`."""

    configurations: Sequence[RunConfiguration] = field(default_factory=tuple)
    default_argv: Sequence[str] = field(default_factory=tuple)
    default_entry: str = ""
    project_root: Optional[str] = None
    active_config_name: Optional[str] = None
    initial_selection_name: Optional[str] = None


class RunConfigurationsDialog(QDialog):
    """Two-pane editor for ``cbcs/project.json`` run configurations."""

    def __init__(
        self,
        initial: RunConfigurationsInitial,
        parent: QWidget | None = None,
        *,
        tokens: ShellThemeTokens | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Run Configurations")
        self.setModal(True)
        self.setObjectName("shell.runConfigurationsDialog")
        self.resize(860, 560)

        if tokens is None:
            tokens = tokens_from_palette(self.palette())
        self._tokens = tokens
        self.setStyleSheet(build_settings_style_sheet(tokens))

        self._initial = initial
        self._configurations: list[RunConfiguration] = [
            _copy_configuration(config) for config in initial.configurations
        ]
        self._current_index: int = -1
        self._suppress_field_signals: bool = False
        self._result: RunConfigurationsResult | None = None

        self._build_ui()
        self._populate_list(select_name=initial.initial_selection_name)

    @classmethod
    def run_dialog(
        cls,
        parent: QWidget | None,
        *,
        initial: RunConfigurationsInitial,
        tokens: ShellThemeTokens | None = None,
    ) -> RunConfigurationsResult | None:
        dialog = cls(initial, parent=parent, tokens=tokens)
        if dialog.exec_() != QDialog.Accepted:
            return None
        return dialog.configurations_result()

    def configurations_result(self) -> RunConfigurationsResult | None:
        return self._result

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(16, 16, 16, 16)
        outer_layout.setSpacing(12)

        default_group = QGroupBox("Default arguments for Run Project (F5 Project)", self)
        default_group.setObjectName("shell.runConfigurationsDialog.defaultArgvGroup")
        default_layout = QFormLayout(default_group)
        default_layout.setContentsMargins(12, 12, 12, 12)
        default_layout.setHorizontalSpacing(12)
        default_layout.setVerticalSpacing(8)
        self._default_argv_edit = QLineEdit(default_group)
        self._default_argv_edit.setObjectName("shell.runConfigurationsDialog.defaultArgv")
        self._default_argv_edit.setPlaceholderText('e.g. --config "/tmp/cfg.toml"')
        self._default_argv_edit.setText(_join_argv_for_display(self._initial.default_argv))
        default_layout.addRow("Arguments:", self._default_argv_edit)

        default_entry_label = QLabel(self._initial.default_entry or "(not set)", default_group)
        default_entry_label.setObjectName("shell.runConfigurationsDialog.defaultEntryLabel")
        muted_color = self._tokens.text_muted or self._tokens.text_primary
        default_entry_label.setStyleSheet(f"color: {muted_color};")
        default_layout.addRow("Entry file:", default_entry_label)
        outer_layout.addWidget(default_group)

        body_widget = QWidget(self)
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(12)

        left_panel = QWidget(body_widget)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        self._configs_list = QListWidget(left_panel)
        self._configs_list.setObjectName("shell.runConfigurationsDialog.list")
        self._configs_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._configs_list.currentRowChanged.connect(self._on_current_row_changed)
        left_layout.addWidget(self._configs_list, 1)

        list_buttons = QWidget(left_panel)
        list_buttons_layout = QHBoxLayout(list_buttons)
        list_buttons_layout.setContentsMargins(0, 0, 0, 0)
        list_buttons_layout.setSpacing(6)
        self._add_button = QPushButton("+ Add", list_buttons)
        self._add_button.setObjectName("shell.runConfigurationsDialog.addButton")
        self._add_button.clicked.connect(self._on_add_clicked)
        self._duplicate_button = QPushButton("Duplicate", list_buttons)
        self._duplicate_button.setObjectName("shell.runConfigurationsDialog.duplicateButton")
        self._duplicate_button.clicked.connect(self._on_duplicate_clicked)
        self._delete_button = QPushButton("\u2212 Delete", list_buttons)
        self._delete_button.setObjectName("shell.runConfigurationsDialog.deleteButton")
        self._delete_button.clicked.connect(self._on_delete_clicked)
        list_buttons_layout.addWidget(self._add_button)
        list_buttons_layout.addWidget(self._duplicate_button)
        list_buttons_layout.addStretch(1)
        list_buttons_layout.addWidget(self._delete_button)
        left_layout.addWidget(list_buttons)
        left_panel.setFixedWidth(260)
        body_layout.addWidget(left_panel, 0)

        right_panel = QWidget(body_widget)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignLeft | Qt.AlignTop)
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(8)
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self._name_edit = QLineEdit(right_panel)
        self._name_edit.setObjectName("shell.runConfigurationsDialog.nameField")
        self._name_edit.textEdited.connect(self._on_name_changed)
        form_layout.addRow("Name:", self._name_edit)

        self._entry_edit = QLineEdit(right_panel)
        self._entry_edit.setObjectName("shell.runConfigurationsDialog.entryField")
        self._entry_edit.textEdited.connect(self._on_entry_changed)
        entry_row = QWidget(right_panel)
        entry_row_layout = QHBoxLayout(entry_row)
        entry_row_layout.setContentsMargins(0, 0, 0, 0)
        entry_row_layout.setSpacing(8)
        entry_row_layout.addWidget(self._entry_edit, 1)
        browse_entry_button = QPushButton("Browse...", entry_row)
        browse_entry_button.clicked.connect(self._on_browse_entry_clicked)
        entry_row_layout.addWidget(browse_entry_button, 0)
        form_layout.addRow("Entry file:", entry_row)

        self._argv_edit = QLineEdit(right_panel)
        self._argv_edit.setObjectName("shell.runConfigurationsDialog.argvField")
        self._argv_edit.setPlaceholderText('e.g. --config "/tmp/cfg.toml" --verbose')
        self._argv_edit.textEdited.connect(self._on_argv_changed)
        form_layout.addRow("Arguments:", self._argv_edit)

        self._argv_preview_label = QLabel(right_panel)
        self._argv_preview_label.setObjectName("shell.runConfigurationsDialog.argvPreview")
        self._argv_preview_label.setWordWrap(True)
        self._argv_preview_label.setStyleSheet(f"color: {muted_color};")
        form_layout.addRow("", self._argv_preview_label)

        self._working_dir_edit = QLineEdit(right_panel)
        self._working_dir_edit.setObjectName("shell.runConfigurationsDialog.workingDirField")
        self._working_dir_edit.textEdited.connect(self._on_working_dir_changed)
        wd_row = QWidget(right_panel)
        wd_row_layout = QHBoxLayout(wd_row)
        wd_row_layout.setContentsMargins(0, 0, 0, 0)
        wd_row_layout.setSpacing(8)
        wd_row_layout.addWidget(self._working_dir_edit, 1)
        browse_wd_button = QPushButton("Browse...", wd_row)
        browse_wd_button.clicked.connect(self._on_browse_working_dir_clicked)
        wd_row_layout.addWidget(browse_wd_button, 0)
        form_layout.addRow("Working directory:", wd_row)

        self._env_edit = QLineEdit(right_panel)
        self._env_edit.setObjectName("shell.runConfigurationsDialog.envField")
        self._env_edit.setPlaceholderText("KEY1=value1, KEY2=value2")
        self._env_edit.textEdited.connect(self._on_env_changed)
        form_layout.addRow("Environment overrides:", self._env_edit)
        right_layout.addLayout(form_layout)

        right_layout.addStretch(1)

        self._error_label = QLabel(right_panel)
        self._error_label.setObjectName("shell.runConfigurationsDialog.error")
        self._error_label.setWordWrap(True)
        error_color = self._tokens.diag_error_color or "#d9534f"
        self._error_label.setStyleSheet(f"color: {error_color};")
        self._error_label.hide()
        right_layout.addWidget(self._error_label)

        self._empty_state_label = QLabel(
            "No run configurations yet. Click + Add to create one.",
            right_panel,
        )
        self._empty_state_label.setObjectName("shell.runConfigurationsDialog.emptyState")
        self._empty_state_label.setStyleSheet(f"color: {muted_color};")
        self._empty_state_label.setAlignment(Qt.AlignCenter)
        self._empty_state_label.hide()
        right_layout.addWidget(self._empty_state_label)

        body_layout.addWidget(right_panel, 1)
        outer_layout.addWidget(body_widget, 1)

        button_box = QDialogButtonBox(self)
        self._save_run_button = cast(
            QPushButton,
            button_box.addButton("Save and Run Selected", QDialogButtonBox.AcceptRole),
        )
        self._save_run_button.setObjectName("shell.runConfigurationsDialog.saveRunButton")
        self._save_run_button.setToolTip(
            "Commit edits to cbcs/project.json and immediately launch the selected configuration."
        )
        self._save_run_button.clicked.connect(self._on_save_and_run_clicked)

        self._save_button = cast(
            QPushButton, button_box.addButton("Save", QDialogButtonBox.AcceptRole)
        )
        self._save_button.setObjectName("shell.runConfigurationsDialog.saveButton")
        self._save_button.setDefault(True)
        self._save_button.clicked.connect(self._on_save_clicked)

        cancel_button = cast(QPushButton, button_box.addButton(QDialogButtonBox.Cancel))
        cancel_button.setObjectName("shell.runConfigurationsDialog.cancelButton")
        cancel_button.clicked.connect(self.reject)

        outer_layout.addWidget(button_box)

        self._form_widgets: list[QWidget] = [
            self._name_edit,
            self._entry_edit,
            self._argv_edit,
            self._working_dir_edit,
            self._env_edit,
            browse_entry_button,
            browse_wd_button,
        ]

    def _populate_list(self, *, select_name: str | None = None) -> None:
        self._configs_list.clear()
        for config in self._configurations:
            item = QListWidgetItem(config.name)
            self._configs_list.addItem(item)
        if not self._configurations:
            self._current_index = -1
            self._update_form_enabled(False)
            self._clear_form()
            self._empty_state_label.show()
            return
        self._empty_state_label.hide()
        target_index = 0
        if select_name:
            for index, config in enumerate(self._configurations):
                if config.name == select_name:
                    target_index = index
                    break
        self._configs_list.setCurrentRow(target_index)

    def _on_current_row_changed(self, row: int) -> None:
        self._current_index = row
        if row < 0 or row >= len(self._configurations):
            self._update_form_enabled(False)
            self._clear_form()
            return
        self._update_form_enabled(True)
        self._load_form_from_config(self._configurations[row])

    def _load_form_from_config(self, config: RunConfiguration) -> None:
        self._suppress_field_signals = True
        try:
            self._name_edit.setText(config.name)
            self._entry_edit.setText(config.entry_file)
            self._argv_edit.setText(_join_argv_for_display(config.argv))
            self._working_dir_edit.setText(config.working_directory or "")
            self._env_edit.setText(env_overrides_to_text(config.env_overrides))
        finally:
            self._suppress_field_signals = False
        self._update_argv_preview()
        self._clear_error()

    def _clear_form(self) -> None:
        self._suppress_field_signals = True
        try:
            self._name_edit.clear()
            self._entry_edit.clear()
            self._argv_edit.clear()
            self._working_dir_edit.clear()
            self._env_edit.clear()
            self._argv_preview_label.setText("")
        finally:
            self._suppress_field_signals = False
        self._clear_error()

    def _update_form_enabled(self, enabled: bool) -> None:
        for widget in self._form_widgets:
            widget.setEnabled(enabled)

    def _on_name_changed(self, text: str) -> None:
        if self._suppress_field_signals or self._current_index < 0:
            return
        config = self._configurations[self._current_index]
        self._configurations[self._current_index] = _replace_config(config, name=text)
        item = self._configs_list.item(self._current_index)
        if item is not None:
            item.setText(text or "(unnamed)")

    def _on_entry_changed(self, text: str) -> None:
        if self._suppress_field_signals or self._current_index < 0:
            return
        config = self._configurations[self._current_index]
        self._configurations[self._current_index] = _replace_config(config, entry_file=text)

    def _on_argv_changed(self, _text: str) -> None:
        if self._suppress_field_signals or self._current_index < 0:
            return
        self._update_argv_preview()
        try:
            tokens = tokenize_argv_text(self._argv_edit.text())
        except AppValidationError:
            return
        config = self._configurations[self._current_index]
        self._configurations[self._current_index] = _replace_config(config, argv=tokens)

    def _on_working_dir_changed(self, text: str) -> None:
        if self._suppress_field_signals or self._current_index < 0:
            return
        config = self._configurations[self._current_index]
        normalized = text.strip() or None
        self._configurations[self._current_index] = _replace_config(
            config, working_directory=normalized
        )

    def _on_env_changed(self, _text: str) -> None:
        if self._suppress_field_signals or self._current_index < 0:
            return
        try:
            env = parse_env_overrides_text(self._env_edit.text())
        except ValueError:
            return
        config = self._configurations[self._current_index]
        self._configurations[self._current_index] = _replace_config(config, env_overrides=env)

    def _on_browse_entry_clicked(self) -> None:
        start_dir = self._initial.project_root or ""
        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Python entry file",
            start_dir,
            "Python files (*.py *.fcmacro);;All files (*)",
        )
        if selected_path:
            self._entry_edit.setText(selected_path)
            self._on_entry_changed(selected_path)

    def _on_browse_working_dir_clicked(self) -> None:
        start_dir = self._working_dir_edit.text() or self._initial.project_root or ""
        selected_dir = QFileDialog.getExistingDirectory(self, "Select working directory", start_dir)
        if selected_dir:
            self._working_dir_edit.setText(selected_dir)
            self._on_working_dir_changed(selected_dir)

    def _update_argv_preview(self) -> None:
        text = self._argv_edit.text()
        if not text.strip():
            self._argv_preview_label.setText("Parsed argv: []")
            return
        try:
            tokens = tokenize_argv_text(text)
        except AppValidationError as exc:
            self._argv_preview_label.setText(f"(unable to parse arguments: {exc})")
            return
        preview = ", ".join(repr(token) for token in tokens)
        self._argv_preview_label.setText(f"Parsed argv: [{preview}]")

    def _on_add_clicked(self) -> None:
        name = self._propose_unique_name("New Configuration")
        new_config = RunConfiguration(
            name=name,
            entry_file=self._initial.default_entry or "main.py",
            argv=[],
            working_directory=None,
            env_overrides={},
        )
        self._configurations.append(new_config)
        self._configs_list.blockSignals(True)
        try:
            self._configs_list.addItem(QListWidgetItem(name))
        finally:
            self._configs_list.blockSignals(False)
        self._empty_state_label.hide()
        self._configs_list.setCurrentRow(len(self._configurations) - 1)
        self._name_edit.setFocus()
        self._name_edit.selectAll()

    def _on_duplicate_clicked(self) -> None:
        if self._current_index < 0:
            return
        source = self._configurations[self._current_index]
        new_name = self._propose_unique_name(f"{source.name} (copy)")
        duplicated = _replace_config(source, name=new_name)
        insert_index = self._current_index + 1
        self._configurations.insert(insert_index, duplicated)
        self._configs_list.blockSignals(True)
        try:
            self._configs_list.insertItem(insert_index, QListWidgetItem(new_name))
        finally:
            self._configs_list.blockSignals(False)
        self._configs_list.setCurrentRow(insert_index)

    def _on_delete_clicked(self) -> None:
        if self._current_index < 0:
            return
        config = self._configurations[self._current_index]
        confirm = QMessageBox.question(
            self,
            "Delete Configuration",
            f'Delete run configuration "{config.name}"?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        removed_index = self._current_index
        del self._configurations[removed_index]
        self._configs_list.blockSignals(True)
        try:
            self._configs_list.takeItem(removed_index)
        finally:
            self._configs_list.blockSignals(False)
        if not self._configurations:
            self._current_index = -1
            self._update_form_enabled(False)
            self._clear_form()
            self._empty_state_label.show()
            return
        new_index = min(removed_index, len(self._configurations) - 1)
        self._configs_list.setCurrentRow(new_index)

    def _propose_unique_name(self, candidate: str) -> str:
        existing_names = {config.name for config in self._configurations}
        if candidate not in existing_names:
            return candidate
        index = 2
        while f"{candidate} {index}" in existing_names:
            index += 1
        return f"{candidate} {index}"

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()

    def _clear_error(self) -> None:
        if self._error_label.isVisible():
            self._error_label.hide()
        self._error_label.setText("")

    def _validate_default_argv(self) -> list[str] | None:
        text = self._default_argv_edit.text()
        try:
            return tokenize_argv_text(text)
        except AppValidationError as exc:
            self._show_error(f"Default arguments: {exc}")
            self._default_argv_edit.setFocus()
            return None

    def _validate_configurations(self) -> bool:
        seen_names: set[str] = set()
        for index, config in enumerate(self._configurations):
            name = config.name.strip()
            if not name:
                self._show_error(f"Configuration #{index + 1} is missing a name.")
                self._configs_list.setCurrentRow(index)
                return False
            if name in seen_names:
                self._show_error(f'Duplicate configuration name: "{name}".')
                self._configs_list.setCurrentRow(index)
                return False
            seen_names.add(name)
            entry = config.entry_file.strip()
            if not entry:
                self._show_error(f'Configuration "{name}" has no entry file.')
                self._configs_list.setCurrentRow(index)
                return False
        return True

    def _build_result(self, *, run_selected: bool) -> RunConfigurationsResult | None:
        default_argv = self._validate_default_argv()
        if default_argv is None:
            return None
        if not self._validate_configurations():
            return None
        normalized_configs = [_normalize_configuration(config) for config in self._configurations]
        selected_name: str | None = None
        if run_selected and 0 <= self._current_index < len(normalized_configs):
            selected_name = normalized_configs[self._current_index].name
        return RunConfigurationsResult(
            configurations=normalized_configs,
            default_argv=default_argv,
            selected_config_name=selected_name,
        )

    def _on_save_clicked(self) -> None:
        result = self._build_result(run_selected=False)
        if result is None:
            return
        self._result = result
        self.accept()

    def _on_save_and_run_clicked(self) -> None:
        if self._current_index < 0:
            self._show_error("Select a configuration to run, or use Save without running.")
            return
        result = self._build_result(run_selected=True)
        if result is None:
            return
        self._result = result
        self.accept()


def _copy_configuration(config: RunConfiguration) -> RunConfiguration:
    return RunConfiguration(
        name=config.name,
        entry_file=config.entry_file,
        argv=list(config.argv),
        working_directory=config.working_directory,
        env_overrides=dict(config.env_overrides),
    )


_UNSET: object = object()


def _replace_config(
    config: RunConfiguration,
    *,
    name: str | None = None,
    entry_file: str | None = None,
    argv: list[str] | None = None,
    working_directory: object = _UNSET,
    env_overrides: Mapping[str, str] | None = None,
) -> RunConfiguration:
    if working_directory is _UNSET:
        resolved_working_directory: str | None = config.working_directory
    elif working_directory is None or isinstance(working_directory, str):
        resolved_working_directory = working_directory
    else:
        raise TypeError("working_directory must be a string or None")
    return RunConfiguration(
        name=config.name if name is None else name,
        entry_file=config.entry_file if entry_file is None else entry_file,
        argv=list(config.argv) if argv is None else list(argv),
        working_directory=resolved_working_directory,
        env_overrides=dict(config.env_overrides) if env_overrides is None else dict(env_overrides),
    )


def _normalize_configuration(config: RunConfiguration) -> RunConfiguration:
    return RunConfiguration(
        name=config.name.strip(),
        entry_file=config.entry_file.strip(),
        argv=[token for token in config.argv if str(token)],
        working_directory=(
            config.working_directory.strip()
            if isinstance(config.working_directory, str) and config.working_directory.strip()
            else None
        ),
        env_overrides=dict(config.env_overrides),
    )
