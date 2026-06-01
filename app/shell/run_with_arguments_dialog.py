"""Modal dialog for launching a one-off run with custom CLI arguments."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping, Optional, Sequence

from PySide2.QtCore import Qt
from PySide2.QtGui import QKeySequence
from PySide2.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QShortcut,
    QVBoxLayout,
    QWidget,
)

from app.core.errors import AppValidationError
from app.project.run_configs import RunConfiguration
from app.shell.dialog_chrome import (
    FOOTER_ROLE_LINK,
    FOOTER_ROLE_PRIMARY,
    FOOTER_ROLE_SECONDARY,
    add_footer_button,
    add_footer_stretch,
    add_meta_chip,
    build_dialog_chrome,
)
from app.shell.run_arguments_editor import RunArgumentsEditorRow
from app.shell.run_arguments_helpers import (
    can_submit_run_invocation,
    format_command_preview_lines,
    join_argv_for_display,
    normalize_entry_path_for_project,
    try_parse_argv_text,
)
from app.shell.run_config_controller import tokenize_argv_text
from app.shell.run_env_overrides_row import RunEnvOverridesRow
from app.shell.style_sheet import build_run_dialog_style_sheet
from app.shell.theme_tokens import ShellThemeTokens, tokens_from_palette

_DIALOG_OBJECT_NAME = "shell.runWithArgumentsDialog"
_SUBTITLE = (
    "Run once with custom arguments. Nothing is saved to the project "
    "unless you choose Save as Configuration."
)
_ARGV_FIELD_TOOLTIP = (
    "Shell-style quoting is supported. ChoreBoy has no terminal; "
    "this is how you set sys.argv for the runner."
)


@dataclass(frozen=True)
class RunInvocation:
    """Result returned by :class:`RunWithArgumentsDialog` when the user runs or saves."""

    entry_file: str
    argv: list[str]
    argv_text: str
    working_directory: Optional[str]
    env_overrides: dict[str, str]
    save_request: bool = False
    save_name: str = ""


@dataclass(frozen=True)
class RunWithArgumentsResult:
    """Outcome of :meth:`RunWithArgumentsDialog.run_dialog`."""

    invocation: RunInvocation | None = None
    open_configurations: bool = False


@dataclass(frozen=True)
class RunWithArgumentsInitial:
    """Initial values used to seed the dialog's fields."""

    entry_file: str = ""
    argv: Sequence[str] = field(default_factory=tuple)
    working_directory: Optional[str] = None
    env_overrides: Mapping[str, str] = field(default_factory=dict)
    recent_argv_history: Sequence[str] = field(default_factory=tuple)
    project_root: Optional[str] = None
    entry_file_choices: Sequence[str] = field(default_factory=tuple)
    named_configurations: Sequence[RunConfiguration] = field(default_factory=tuple)


class RunWithArgumentsDialog(QDialog):
    """One-off "Run With Arguments" dialog."""

    def __init__(
        self,
        initial: RunWithArgumentsInitial,
        parent: QWidget | None = None,
        *,
        tokens: ShellThemeTokens | None = None,
        on_manage_configurations: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Run With Arguments")
        self.setModal(True)
        self.setObjectName(_DIALOG_OBJECT_NAME)
        self.setMinimumSize(640, 520)
        self.resize(720, 620)

        if tokens is None:
            tokens = tokens_from_palette(self.palette())
        self._tokens = tokens
        self.setStyleSheet(build_run_dialog_style_sheet(tokens))

        self._initial = initial
        self._on_manage_configurations = on_manage_configurations
        self._result: RunInvocation | None = None
        self._open_configurations = False

        chrome = build_dialog_chrome(
            self,
            title="Run With Arguments",
            subtitle=_SUBTITLE,
            object_name=_DIALOG_OBJECT_NAME,
            body_margins=True,
        )
        self._chrome = chrome
        add_meta_chip(chrome.meta_row, "One-off run")

        body_layout = chrome.body.layout()
        assert isinstance(body_layout, QVBoxLayout)

        self._command_preview = QLabel(chrome.body)
        self._command_preview.setObjectName("shell.runWithArgumentsDialog.commandPreview")
        self._command_preview.setWordWrap(True)
        self._command_preview.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body_layout.addWidget(self._command_preview)

        form_host = QWidget(chrome.body)
        form_layout = QFormLayout(form_host)
        form_layout.setLabelAlignment(Qt.AlignLeft | Qt.AlignTop)
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(10)
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self._prefill_combo: QComboBox | None = None
        if initial.named_configurations:
            self._prefill_combo = QComboBox(form_host)
            self._prefill_combo.setObjectName("shell.runWithArgumentsDialog.prefill")
            self._prefill_combo.addItem("Prefill from configuration\u2026", None)
            for config in initial.named_configurations:
                self._prefill_combo.addItem(config.name, config)
            self._prefill_combo.currentIndexChanged.connect(self._on_prefill_selected)
            form_layout.addRow("Prefill:", self._prefill_combo)

        self._entry_combo = QComboBox(form_host)
        self._entry_combo.setObjectName("shell.runWithArgumentsDialog.entry")
        self._entry_combo.setEditable(True)
        self._entry_combo.setInsertPolicy(QComboBox.NoInsert)
        for choice in initial.entry_file_choices:
            self._entry_combo.addItem(choice)
        entry_row = QWidget(form_host)
        entry_row_layout = QHBoxLayout(entry_row)
        entry_row_layout.setContentsMargins(0, 0, 0, 0)
        entry_row_layout.setSpacing(8)
        entry_row_layout.addWidget(self._entry_combo, 1)
        browse_entry_button = QPushButton("Browse\u2026", entry_row)
        browse_entry_button.clicked.connect(self._on_browse_entry_clicked)
        entry_row_layout.addWidget(browse_entry_button, 0)
        form_layout.addRow("Entry file:", entry_row)
        self._entry_combo.currentTextChanged.connect(self._refresh_validation_state)

        argv_label = QLabel("Arguments:", form_host)
        argv_label.setToolTip(_ARGV_FIELD_TOOLTIP)
        self._argv_editor = RunArgumentsEditorRow(
            form_host,
            tokens=tokens,
            recent_argv_history=initial.recent_argv_history,
            object_name_prefix="shell.runWithArgumentsDialog",
            show_recent=True,
        )
        form_layout.addRow(argv_label, self._argv_editor)
        self._argv_editor.validation_changed.connect(self._refresh_validation_state)

        self._advanced_group = QGroupBox("Advanced", form_host)
        self._advanced_group.setObjectName("shell.runWithArgumentsDialog.advancedGroup")
        self._advanced_group.setCheckable(True)
        advanced_layout = QFormLayout(self._advanced_group)
        advanced_layout.setLabelAlignment(Qt.AlignLeft | Qt.AlignTop)
        advanced_layout.setHorizontalSpacing(12)
        advanced_layout.setVerticalSpacing(10)
        advanced_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self._working_dir_edit = QLineEdit(self._advanced_group)
        self._working_dir_edit.setObjectName("shell.runWithArgumentsDialog.workingDir")
        self._working_dir_edit.setPlaceholderText("Leave empty to use project root")
        wd_row = QWidget(self._advanced_group)
        wd_row_layout = QHBoxLayout(wd_row)
        wd_row_layout.setContentsMargins(0, 0, 0, 0)
        wd_row_layout.setSpacing(8)
        wd_row_layout.addWidget(self._working_dir_edit, 1)
        browse_wd_button = QPushButton("Browse\u2026", wd_row)
        browse_wd_button.clicked.connect(self._on_browse_working_dir_clicked)
        wd_row_layout.addWidget(browse_wd_button, 0)
        advanced_layout.addRow("Working directory:", wd_row)
        self._working_dir_edit.textChanged.connect(self._refresh_validation_state)

        self._env_row = RunEnvOverridesRow(
            self._advanced_group,
            tokens=tokens,
            object_name_prefix="shell.runWithArgumentsDialog.env",
        )
        advanced_layout.addRow("Environment:", self._env_row)
        self._env_row.value_changed.connect(self._refresh_validation_state)

        has_advanced_values = bool(
            (initial.working_directory or "").strip() or initial.env_overrides
        )
        self._advanced_group.setChecked(has_advanced_values)
        self._advanced_group.toggled.connect(self._on_advanced_toggled)
        form_layout.addRow(self._advanced_group)

        body_layout.addWidget(form_host, 1)

        self._error_label = QLabel(chrome.body)
        self._error_label.setObjectName("shell.runWithArgumentsDialog.error")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        body_layout.addWidget(self._error_label)

        if on_manage_configurations is not None:
            manage_button = add_footer_button(
                chrome, "Manage configurations\u2026", role=FOOTER_ROLE_LINK
            )
            manage_button.clicked.connect(self._on_manage_configurations_clicked)

        add_footer_stretch(chrome)
        self._save_button = add_footer_button(
            chrome,
            "Save as Configuration\u2026",
            role=FOOTER_ROLE_SECONDARY,
        )
        self._save_button.setToolTip(
            "Run now and remember these values as a named run configuration in cbcs/project.json."
        )
        cancel_button = add_footer_button(chrome, "Cancel", role=FOOTER_ROLE_SECONDARY)
        self._run_button = add_footer_button(chrome, "Run", role=FOOTER_ROLE_PRIMARY, default=True)

        self._run_button.clicked.connect(self._on_run_clicked)
        self._save_button.clicked.connect(self._on_save_clicked)
        cancel_button.clicked.connect(self.reject)

        run_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        run_shortcut.activated.connect(self._on_run_clicked)

        self._seed_initial_values()
        self._on_advanced_toggled(self._advanced_group.isChecked())
        self._refresh_validation_state()
        if (initial.entry_file or "").strip():
            self._argv_editor.focus_argv_field()

    @classmethod
    def run_dialog(
        cls,
        parent: QWidget | None,
        *,
        initial: RunWithArgumentsInitial,
        tokens: ShellThemeTokens | None = None,
        on_manage_configurations: Callable[[], None] | None = None,
    ) -> RunWithArgumentsResult:
        dialog = cls(
            initial,
            parent=parent,
            tokens=tokens,
            on_manage_configurations=on_manage_configurations,
        )
        if dialog.exec_() != QDialog.Accepted:
            if dialog._open_configurations:
                return RunWithArgumentsResult(open_configurations=True)
            return RunWithArgumentsResult()
        return RunWithArgumentsResult(invocation=dialog.invocation())

    def invocation(self) -> RunInvocation | None:
        return self._result

    def _seed_initial_values(self) -> None:
        normalized_entry = normalize_entry_path_for_project(
            self._initial.entry_file,
            project_root=self._initial.project_root,
        )
        if normalized_entry:
            index = self._entry_combo.findText(normalized_entry)
            if index >= 0:
                self._entry_combo.setCurrentIndex(index)
            else:
                self._entry_combo.setEditText(normalized_entry)
        self._argv_editor.set_argv_from_tokens(self._initial.argv)
        self._working_dir_edit.setText(self._initial.working_directory or "")
        self._env_row.set_env_overrides(self._initial.env_overrides)

    def _entry_file_text(self) -> str:
        return self._entry_combo.currentText().strip()

    def _on_advanced_toggled(self, expanded: bool) -> None:
        self._working_dir_edit.setEnabled(expanded)
        self._env_row.setEnabled(expanded)
        for child in self._advanced_group.findChildren(QPushButton):
            child.setEnabled(expanded)

    def _on_prefill_selected(self, index: int) -> None:
        if self._prefill_combo is None or index <= 0:
            return
        config = self._prefill_combo.currentData()
        if not isinstance(config, RunConfiguration):
            return
        entry = normalize_entry_path_for_project(
            config.entry_file,
            project_root=self._initial.project_root,
        )
        if entry:
            combo_index = self._entry_combo.findText(entry)
            if combo_index >= 0:
                self._entry_combo.setCurrentIndex(combo_index)
            else:
                self._entry_combo.setEditText(entry)
        self._argv_editor.set_argv_from_tokens(config.argv)
        self._working_dir_edit.setText(config.working_directory or "")
        self._env_row.set_env_overrides(config.env_overrides)
        if config.working_directory or config.env_overrides:
            self._advanced_group.setChecked(True)
        self._prefill_combo.setCurrentIndex(0)
        self._refresh_validation_state()

    def _on_browse_entry_clicked(self) -> None:
        start_dir = self._initial.project_root or ""
        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Python entry file",
            start_dir,
            "Python files (*.py *.fcmacro);;All files (*)",
        )
        if selected_path:
            normalized = normalize_entry_path_for_project(
                selected_path,
                project_root=self._initial.project_root,
            )
            index = self._entry_combo.findText(normalized)
            if index >= 0:
                self._entry_combo.setCurrentIndex(index)
            else:
                self._entry_combo.setEditText(normalized)

    def _on_browse_working_dir_clicked(self) -> None:
        start_dir = self._working_dir_edit.text() or self._initial.project_root or ""
        selected_dir = QFileDialog.getExistingDirectory(self, "Select working directory", start_dir)
        if selected_dir:
            self._working_dir_edit.setText(selected_dir)

    def _on_manage_configurations_clicked(self) -> None:
        self._open_configurations = True
        if self._on_manage_configurations is not None:
            self._on_manage_configurations()
        self.reject()

    def _refresh_validation_state(self) -> None:
        entry = self._entry_file_text()
        argv_text = self._argv_editor.argv_text()
        env_overrides = self._env_row.env_overrides()

        argv_tokens, argv_error = try_parse_argv_text(argv_text)
        if argv_error is not None:
            argv_tokens = []

        working_dir = self._working_dir_edit.text().strip() or None
        preview_lines = format_command_preview_lines(
            entry_file=entry,
            argv_tokens=argv_tokens or [],
            working_directory=working_dir,
            project_root=self._initial.project_root,
            env_overrides=env_overrides,
        )
        self._command_preview.setText("\n".join(preview_lines))

        can_submit, error_message = can_submit_run_invocation(
            entry_file=entry,
            argv_text=argv_text,
            env_text=env_overrides_to_text_for_validation(env_overrides),
        )
        self._run_button.setEnabled(can_submit)
        self._save_button.setEnabled(can_submit)
        if error_message and not can_submit:
            self._show_error(error_message)
        else:
            self._clear_error()

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()

    def _clear_error(self) -> None:
        if self._error_label.isVisible():
            self._error_label.hide()
        self._error_label.setText("")

    def _collect_invocation(self, *, save_request: bool) -> RunInvocation | None:
        entry = self._entry_file_text()
        if not entry:
            self._show_error("Entry file is required.")
            self._entry_combo.setFocus()
            return None

        argv_text = self._argv_editor.argv_text()
        try:
            argv_tokens = tokenize_argv_text(argv_text)
        except AppValidationError as exc:
            self._show_error(str(exc))
            self._argv_editor.focus_argv_field()
            return None

        env_overrides = self._env_row.env_overrides()
        working_dir = self._working_dir_edit.text().strip() or None

        return RunInvocation(
            entry_file=entry,
            argv=argv_tokens,
            argv_text=argv_text.strip(),
            working_directory=working_dir,
            env_overrides=env_overrides,
            save_request=save_request,
        )

    def _on_run_clicked(self) -> None:
        if not self._run_button.isEnabled():
            return
        invocation = self._collect_invocation(save_request=False)
        if invocation is None:
            self._refresh_validation_state()
            return
        self._result = invocation
        self.accept()

    def _on_save_clicked(self) -> None:
        if not self._save_button.isEnabled():
            return
        invocation = self._collect_invocation(save_request=True)
        if invocation is None:
            self._refresh_validation_state()
            return
        self._result = invocation
        self.accept()


def env_overrides_to_text_for_validation(env_overrides: Mapping[str, str]) -> str:
    """Serialize env overrides for :func:`can_submit_run_invocation` validation."""

    from app.project.run_configs import env_overrides_to_text

    return env_overrides_to_text(env_overrides)


def _join_argv_for_display(argv: Sequence[str]) -> str:
    """Backward-compatible alias for :func:`join_argv_for_display`."""

    return join_argv_for_display(argv)
