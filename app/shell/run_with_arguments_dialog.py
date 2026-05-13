"""Modal dialog for launching a one-off run with custom CLI arguments.

Modeled after VS Code's "Run With Arguments" / PyCharm's "Edit Run/Debug Configurations" entry-row,
but scoped to a single, ad-hoc invocation that does **not** persist into ``cbcs/project.json``.
For persistent named configurations see :mod:`app.shell.run_configurations_dialog`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence, cast

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.errors import AppValidationError
from app.project.run_configs import env_overrides_to_text, parse_env_overrides_text
from app.shell.run_config_controller import tokenize_argv_text
from app.shell.style_sheet import build_settings_style_sheet
from app.shell.theme_tokens import ShellThemeTokens, tokens_from_palette


@dataclass(frozen=True)
class RunInvocation:
    """Result returned by :class:`RunWithArgumentsDialog`."""

    entry_file: str
    argv: list[str]
    argv_text: str
    working_directory: Optional[str]
    env_overrides: dict[str, str]
    save_request: bool = False
    save_name: str = ""


@dataclass(frozen=True)
class RunWithArgumentsInitial:
    """Initial values used to seed the dialog's fields."""

    entry_file: str = ""
    argv: Sequence[str] = field(default_factory=tuple)
    working_directory: Optional[str] = None
    env_overrides: Mapping[str, str] = field(default_factory=dict)
    recent_argv_history: Sequence[str] = field(default_factory=tuple)
    project_root: Optional[str] = None


class RunWithArgumentsDialog(QDialog):
    """One-off "Run With Arguments" dialog.

    The dialog is purely a value-collector. It does not invoke the runner directly so it can be
    instantiated in tests without a live :class:`~app.run.run_service.RunService` and so the
    calling main window stays in charge of the actual ``_start_session`` plumbing.
    """

    def __init__(
        self,
        initial: RunWithArgumentsInitial,
        parent: QWidget | None = None,
        *,
        tokens: ShellThemeTokens | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Run With Arguments")
        self.setModal(True)
        self.setObjectName("shell.runWithArgumentsDialog")
        self.resize(640, 360)

        if tokens is None:
            tokens = tokens_from_palette(self.palette())
        self._tokens = tokens
        self.setStyleSheet(build_settings_style_sheet(tokens))

        self._initial = initial
        self._result: RunInvocation | None = None

        self._build_ui()
        self._seed_initial_values()
        self._update_argv_preview()

    @classmethod
    def run_dialog(
        cls,
        parent: QWidget | None,
        *,
        initial: RunWithArgumentsInitial,
        tokens: ShellThemeTokens | None = None,
    ) -> RunInvocation | None:
        """Open the dialog modally and return the chosen :class:`RunInvocation` or ``None``."""

        dialog = cls(initial, parent=parent, tokens=tokens)
        if dialog.exec_() != QDialog.Accepted:
            return None
        return dialog.invocation()

    def invocation(self) -> RunInvocation | None:
        return self._result

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignLeft | Qt.AlignTop)
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(8)

        self._entry_edit = QLineEdit(self)
        self._entry_edit.setObjectName("shell.runWithArgumentsDialog.entry")
        entry_row = QWidget(self)
        entry_row_layout = QHBoxLayout(entry_row)
        entry_row_layout.setContentsMargins(0, 0, 0, 0)
        entry_row_layout.setSpacing(8)
        entry_row_layout.addWidget(self._entry_edit, 1)
        browse_entry_button = QPushButton("Browse...", entry_row)
        browse_entry_button.clicked.connect(self._on_browse_entry_clicked)
        entry_row_layout.addWidget(browse_entry_button, 0)
        form_layout.addRow("Entry file:", entry_row)

        self._argv_edit = QLineEdit(self)
        self._argv_edit.setObjectName("shell.runWithArgumentsDialog.argv")
        self._argv_edit.setPlaceholderText('e.g. --config "/tmp/cfg.toml" --verbose')
        self._argv_edit.textChanged.connect(self._update_argv_preview)
        argv_row = QWidget(self)
        argv_row_layout = QHBoxLayout(argv_row)
        argv_row_layout.setContentsMargins(0, 0, 0, 0)
        argv_row_layout.setSpacing(8)
        argv_row_layout.addWidget(self._argv_edit, 1)
        self._recent_combo = QComboBox(argv_row)
        self._recent_combo.setObjectName("shell.runWithArgumentsDialog.recent")
        self._recent_combo.setToolTip("Recently used argument strings (global to all projects).")
        self._recent_combo.activated[str].connect(self._on_recent_argv_selected)
        argv_row_layout.addWidget(self._recent_combo, 0)
        form_layout.addRow("Arguments:", argv_row)

        self._argv_preview_label = QLabel(self)
        self._argv_preview_label.setObjectName("shell.runWithArgumentsDialog.argvPreview")
        self._argv_preview_label.setWordWrap(True)
        self._argv_preview_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        muted_color = self._tokens.text_muted or self._tokens.text_primary
        self._argv_preview_label.setStyleSheet(f"color: {muted_color};")
        form_layout.addRow("", self._argv_preview_label)

        self._working_dir_edit = QLineEdit(self)
        self._working_dir_edit.setObjectName("shell.runWithArgumentsDialog.workingDir")
        wd_row = QWidget(self)
        wd_row_layout = QHBoxLayout(wd_row)
        wd_row_layout.setContentsMargins(0, 0, 0, 0)
        wd_row_layout.setSpacing(8)
        wd_row_layout.addWidget(self._working_dir_edit, 1)
        browse_wd_button = QPushButton("Browse...", wd_row)
        browse_wd_button.clicked.connect(self._on_browse_working_dir_clicked)
        wd_row_layout.addWidget(browse_wd_button, 0)
        form_layout.addRow("Working directory:", wd_row)

        self._env_edit = QLineEdit(self)
        self._env_edit.setObjectName("shell.runWithArgumentsDialog.env")
        self._env_edit.setPlaceholderText("KEY1=value1, KEY2=value2")
        form_layout.addRow("Environment overrides:", self._env_edit)

        layout.addLayout(form_layout)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("shell.runWithArgumentsDialog.error")
        self._error_label.setWordWrap(True)
        error_color = self._tokens.diag_error_color or "#d9534f"
        self._error_label.setStyleSheet(f"color: {error_color};")
        self._error_label.hide()
        layout.addWidget(self._error_label)

        button_box = QDialogButtonBox(self)
        self._run_button = cast(QPushButton, button_box.addButton("Run", QDialogButtonBox.AcceptRole))
        self._run_button.setObjectName("shell.runWithArgumentsDialog.runButton")
        self._run_button.setDefault(True)
        self._save_button = cast(
            QPushButton,
            button_box.addButton("Save as Configuration...", QDialogButtonBox.ActionRole),
        )
        self._save_button.setObjectName("shell.runWithArgumentsDialog.saveButton")
        self._save_button.setToolTip(
            "Run now and remember these values as a named run configuration in cbcs/project.json."
        )
        self._cancel_button = cast(QPushButton, button_box.addButton(QDialogButtonBox.Cancel))
        self._cancel_button.setObjectName("shell.runWithArgumentsDialog.cancelButton")

        self._run_button.clicked.connect(self._on_run_clicked)
        self._save_button.clicked.connect(self._on_save_clicked)
        self._cancel_button.clicked.connect(self.reject)
        layout.addWidget(button_box)

    def _seed_initial_values(self) -> None:
        self._entry_edit.setText(self._initial.entry_file)
        argv_text = _join_argv_for_display(self._initial.argv)
        self._argv_edit.setText(argv_text)
        self._working_dir_edit.setText(self._initial.working_directory or "")
        self._env_edit.setText(env_overrides_to_text(self._initial.env_overrides))

        self._recent_combo.clear()
        self._recent_combo.addItem("Recent...", "")
        for entry in self._initial.recent_argv_history:
            display = entry if len(entry) <= 80 else f"{entry[:77]}..."
            self._recent_combo.addItem(display, entry)
        self._recent_combo.setCurrentIndex(0)
        self._recent_combo.setEnabled(self._recent_combo.count() > 1)

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

    def _on_browse_working_dir_clicked(self) -> None:
        start_dir = self._working_dir_edit.text() or self._initial.project_root or ""
        selected_dir = QFileDialog.getExistingDirectory(self, "Select working directory", start_dir)
        if selected_dir:
            self._working_dir_edit.setText(selected_dir)

    def _on_recent_argv_selected(self, _label: str) -> None:
        data = self._recent_combo.currentData()
        if isinstance(data, str) and data:
            self._argv_edit.setText(data)
        self._recent_combo.setCurrentIndex(0)

    def _update_argv_preview(self) -> None:
        text = self._argv_edit.text()
        if not text.strip():
            self._argv_preview_label.setText("No arguments — entry file will receive an empty argv list.")
            self._clear_error()
            return
        try:
            tokens = tokenize_argv_text(text)
        except AppValidationError as exc:
            self._show_error(str(exc))
            self._argv_preview_label.setText("(unable to parse arguments)")
            return
        self._clear_error()
        preview = ", ".join(repr(token) for token in tokens) or "<empty>"
        self._argv_preview_label.setText(f"Parsed argv: [{preview}]")

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()

    def _clear_error(self) -> None:
        if self._error_label.isVisible():
            self._error_label.hide()
        self._error_label.setText("")

    def _collect_invocation(self, *, save_request: bool) -> RunInvocation | None:
        entry = self._entry_edit.text().strip()
        if not entry:
            self._show_error("Entry file is required.")
            self._entry_edit.setFocus()
            return None

        argv_text = self._argv_edit.text()
        try:
            argv_tokens = tokenize_argv_text(argv_text)
        except AppValidationError as exc:
            self._show_error(str(exc))
            self._argv_edit.setFocus()
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
        invocation = self._collect_invocation(save_request=False)
        if invocation is None:
            return
        self._result = invocation
        self.accept()

    def _on_save_clicked(self) -> None:
        invocation = self._collect_invocation(save_request=True)
        if invocation is None:
            return
        self._result = invocation
        self.accept()


def _join_argv_for_display(argv: Sequence[str]) -> str:
    """Best-effort reverse of :func:`tokenize_argv_text` for display.

    Tokens containing whitespace are quoted with double quotes; embedded double quotes are
    escaped. Round-trip-equivalent for typical argv values; not a full shell escape.
    """

    parts: list[str] = []
    for token in argv:
        text = str(token)
        if not text:
            parts.append('""')
            continue
        needs_quoting = any(ch.isspace() for ch in text) or '"' in text or "'" in text
        if needs_quoting:
            escaped = text.replace("\\", "\\\\").replace('"', '\\"')
            parts.append(f'"{escaped}"')
        else:
            parts.append(text)
    return " ".join(parts)
