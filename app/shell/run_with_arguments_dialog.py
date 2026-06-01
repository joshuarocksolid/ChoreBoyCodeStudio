"""Modal dialog for launching a one-off run with custom CLI arguments.

Modeled after VS Code's launch configuration args and PyCharm's Program arguments row,
but scoped to a single ad-hoc invocation that does **not** persist into ``cbcs/project.json``
unless the user saves as a named configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence, cast

from PySide2.QtCore import Qt
from PySide2.QtGui import QKeySequence
from PySide2.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QShortcut,
    QVBoxLayout,
    QWidget,
)

from app.core.errors import AppValidationError
from app.project.run_configs import RunConfiguration, env_overrides_to_text, parse_env_overrides_text
from app.shell.dialog_chrome import (
    FOOTER_ROLE_LINK,
    FOOTER_ROLE_PRIMARY,
    FOOTER_ROLE_SECONDARY,
    add_footer_button,
    add_footer_stretch,
    build_dialog_chrome,
)
from app.shell.run_arguments_editor import RunArgumentsEditorRow
from app.shell.run_arguments_helpers import (
    can_submit_run_invocation,
    format_command_preview_lines,
    join_argv_for_display,
    normalize_entry_path_for_project,
    try_parse_argv_text,
    try_parse_env_text,
)
from app.shell.run_config_controller import tokenize_argv_text
from app.shell.style_sheet import build_run_with_arguments_style_sheet
from app.shell.theme_tokens import ShellThemeTokens, tokens_from_palette

_DIALOG_OBJECT_NAME = "shell.runWithArgumentsDialog"
_SUBTITLE = (
    "One-off run — does not change cbcs/project.json unless you save as a configuration. "
    "ChoreBoy has no terminal; this is how you set sys.argv."
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
        self.resize(680, 520)

        if tokens is None:
            tokens = tokens_from_palette(self.palette())
        self._tokens = tokens
        self.setStyleSheet(build_run_with_arguments_style_sheet(tokens))

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
        form_layout.setVerticalSpacing(8)
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self._prefill_combo: QComboBox | None = None
        if initial.named_configurations:
            self._prefill_combo = QComboBox(form_host)
            self._prefill_combo.setObjectName("shell.runWithArgumentsDialog.prefill")
            self._prefill_combo.addItem("Prefill from configuration…", None)
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
        browse_entry_button = QPushButton("Browse…", entry_row)
        browse_entry_button.clicked.connect(self._on_browse_entry_clicked)
        entry_row_layout.addWidget(browse_entry_button, 0)
        form_layout.addRow("Entry file:", entry_row)
        self._entry_combo.currentTextChanged.connect(self._refresh_validation_state)

        self._argv_editor = RunArgumentsEditorRow(
            form_host,
            tokens=tokens,
            recent_argv_history=initial.recent_argv_history,
            object_name_prefix="shell.runWithArgumentsDialog",
            show_recent=True,
        )
        form_layout.addRow("Arguments:", self._argv_editor)
        self._argv_editor.validation_changed.connect(self._refresh_validation_state)

        self._working_dir_edit = QLineEdit(form_host)
        self._working_dir_edit.setObjectName("shell.runWithArgumentsDialog.workingDir")
        self._working_dir_edit.setPlaceholderText("Leave empty to use project root")
        wd_row = QWidget(form_host)
        wd_row_layout = QHBoxLayout(wd_row)
        wd_row_layout.setContentsMargins(0, 0, 0, 0)
        wd_row_layout.setSpacing(8)
        wd_row_layout.addWidget(self._working_dir_edit, 1)
        browse_wd_button = QPushButton("Browse…", wd_row)
        browse_wd_button.clicked.connect(self._on_browse_working_dir_clicked)
        wd_row_layout.addWidget(browse_wd_button, 0)
        form_layout.addRow("Working directory:", wd_row)
        self._working_dir_edit.textChanged.connect(self._refresh_validation_state)

        self._env_edit = QLineEdit(form_host)
        self._env_edit.setObjectName("shell.runWithArgumentsDialog.env")
        self._env_edit.setPlaceholderText("e.g. DEBUG=1, LOG_LEVEL=debug")
        form_layout.addRow("Environment overrides:", self._env_edit)
        self._env_edit.textChanged.connect(self._refresh_validation_state)

        body_layout.addWidget(form_host, 1)

        self._error_label = QLabel(chrome.body)
        self._error_label.setObjectName("shell.runWithArgumentsDialog.error")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        body_layout.addWidget(self._error_label)

        manage_button = None
        if on_manage_configurations is not None:
            manage_button = add_footer_button(
                chrome, "Manage configurations…", role=FOOTER_ROLE_LINK
            )
            manage_button.clicked.connect(self._on_manage_configurations_clicked)

        add_footer_stretch(chrome)
        self._save_button = add_footer_button(
            chrome,
            "Save as Configuration…",
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
        self._env_edit.setText(env_overrides_to_text(self._initial.env_overrides))

    def _entry_file_text(self) -> str:
        return self._entry_combo.currentText().strip()

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
        self._env_edit.setText(env_overrides_to_text(config.env_overrides))
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
        env_text = self._env_edit.text()

        argv_tokens, argv_error = try_parse_argv_text(argv_text)
        env_mapping, env_error = try_parse_env_text(env_text)
        if argv_error is not None:
            argv_tokens = []
        if env_error is not None:
            env_mapping = {}

        working_dir = self._working_dir_edit.text().strip() or None
        preview_lines = format_command_preview_lines(
            entry_file=entry,
            argv_tokens=argv_tokens or [],
            working_directory=working_dir,
            project_root=self._initial.project_root,
            env_overrides=env_mapping or {},
        )
        self._command_preview.setText("\n".join(preview_lines))

        can_submit, error_message = can_submit_run_invocation(
            entry_file=entry,
            argv_text=argv_text,
            env_text=env_text,
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

        env_text = self._env_edit.text()
        try:
            env_overrides = parse_env_overrides_text(env_text)
        except ValueError as exc:
            self._show_error(f"Invalid environment overrides: {exc}")
            self._env_edit.setFocus()
            return None

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


def _join_argv_for_display(argv: Sequence[str]) -> str:
    """Backward-compatible alias for :func:`join_argv_for_display`."""

    return join_argv_for_display(argv)
