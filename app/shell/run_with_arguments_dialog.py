"""Modal dialog for launching a one-off run with custom CLI arguments."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional, Sequence

from PySide2.QtCore import Qt
from PySide2.QtGui import QKeySequence
from PySide2.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QShortcut,
    QSizePolicy,
    QToolButton,
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
from app.shell.field_action_button import make_field_action_button
from app.shell.run_arguments_editor import RunArgumentsEditorRow
from app.shell.run_arguments_helpers import (
    collect_run_invocation_fields,
    format_command_summary_strip,
    format_overrides_collapsed_summary,
    join_argv_for_display,
    normalize_entry_path_for_project,
    try_parse_argv_text,
)
from app.shell.run_config_controller import tokenize_argv_text
from app.shell.run_env_overrides_row import RunEnvOverridesRow
from app.shell.run_form_section import build_run_form_section
from app.shell.style_sheet import build_run_dialog_style_sheet
from app.shell.theme_tokens import ShellThemeTokens, tokens_from_palette
from app.shell.toolbar_icons import icon_run

_DIALOG_OBJECT_NAME = "shell.runWithArgumentsDialog"
_SUBTITLE = "Run once with custom arguments."
_ARGV_FIELD_TOOLTIP = (
    "Shell-style quoting is supported. ChoreBoy has no terminal; "
    "this is how you set sys.argv for the runner."
)
_WD_HELPER_TEXT = "Defaults to project root when empty."


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


class RunWithArgumentsOutcomeKind(Enum):
    """How :meth:`RunWithArgumentsDialog.run_dialog` closed."""

    CANCELLED = "cancelled"
    RUN = "run"
    OPEN_CONFIGURATIONS = "open_configurations"


@dataclass(frozen=True)
class RunWithArgumentsResult:
    """Outcome of :meth:`RunWithArgumentsDialog.run_dialog`."""

    outcome: RunWithArgumentsOutcomeKind = RunWithArgumentsOutcomeKind.CANCELLED
    invocation: RunInvocation | None = None


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
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Run With Arguments")
        self.setModal(True)
        self.setObjectName(_DIALOG_OBJECT_NAME)
        self.setMinimumSize(600, 480)
        self.resize(680, 540)

        if tokens is None:
            tokens = tokens_from_palette(self.palette())
        self._tokens = tokens
        self.setStyleSheet(build_run_dialog_style_sheet(tokens))

        self._initial = initial
        self._result: RunInvocation | None = None
        self._outcome = RunWithArgumentsOutcomeKind.CANCELLED
        self._overrides_expanded = False

        chrome = build_dialog_chrome(
            self,
            title="Run With Arguments",
            subtitle=_SUBTITLE,
            object_name=_DIALOG_OBJECT_NAME,
            icon=icon_run(tokens.accent),
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
        self._command_preview.setProperty("commandPreviewState", "incomplete")
        body_layout.addWidget(self._command_preview)

        form_host = QWidget(chrome.body)
        form_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        form_host_layout = QVBoxLayout(form_host)
        form_host_layout.setContentsMargins(0, 0, 0, 0)
        form_host_layout.setSpacing(12)

        run_target_section, run_target_layout = build_run_form_section(form_host, "Run target")
        run_target_form = QWidget(run_target_section)
        run_target_form_layout = QFormLayout(run_target_form)
        run_target_form_layout.setLabelAlignment(Qt.AlignLeft | Qt.AlignTop)
        run_target_form_layout.setHorizontalSpacing(12)
        run_target_form_layout.setVerticalSpacing(10)
        run_target_form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        run_target_layout.addWidget(run_target_form)

        self._prefill_combo: QComboBox | None = None
        if initial.named_configurations:
            self._prefill_combo = QComboBox(run_target_form)
            self._prefill_combo.setObjectName("shell.runWithArgumentsDialog.prefill")
            self._prefill_combo.addItem("Prefill from configuration\u2026", None)
            for config in initial.named_configurations:
                self._prefill_combo.addItem(config.name, config)
            self._prefill_combo.currentIndexChanged.connect(self._on_prefill_selected)
            run_target_form_layout.addRow("Prefill:", self._prefill_combo)

        self._entry_combo = QComboBox(run_target_form)
        self._entry_combo.setObjectName("shell.runWithArgumentsDialog.entry")
        self._entry_combo.setEditable(True)
        self._entry_combo.setInsertPolicy(QComboBox.NoInsert)
        for choice in initial.entry_file_choices:
            self._entry_combo.addItem(choice)
        entry_row = QWidget(run_target_form)
        entry_row_layout = QHBoxLayout(entry_row)
        entry_row_layout.setContentsMargins(0, 0, 0, 0)
        entry_row_layout.setSpacing(8)
        entry_row_layout.addWidget(self._entry_combo, 1)
        browse_entry_button = make_field_action_button("Browse\u2026", entry_row)
        browse_entry_button.clicked.connect(self._on_browse_entry_clicked)
        entry_row_layout.addWidget(browse_entry_button, 0)
        entry_label = QLabel("Entry file (required):", run_target_form)
        run_target_form_layout.addRow(entry_label, entry_row)
        self._entry_combo.currentTextChanged.connect(self._refresh_validation_state)

        argv_label = QLabel("Arguments:", run_target_form)
        argv_label.setToolTip(_ARGV_FIELD_TOOLTIP)
        self._argv_editor = RunArgumentsEditorRow(
            run_target_form,
            tokens=tokens,
            recent_argv_history=initial.recent_argv_history,
            object_name_prefix="shell.runWithArgumentsDialog",
            show_recent=True,
            argv_tooltip=_ARGV_FIELD_TOOLTIP,
        )
        run_target_form_layout.addRow(argv_label, self._argv_editor)
        self._argv_editor.validation_changed.connect(self._refresh_validation_state)

        form_host_layout.addWidget(run_target_section)

        overrides_section, overrides_layout = build_run_form_section(form_host, "Overrides")
        self._overrides_disclosure = QWidget(overrides_section)
        disclosure_layout = QHBoxLayout(self._overrides_disclosure)
        disclosure_layout.setContentsMargins(0, 0, 0, 0)
        disclosure_layout.setSpacing(8)

        self._overrides_toggle = QToolButton(self._overrides_disclosure)
        self._overrides_toggle.setObjectName("shell.runWithArgumentsDialog.overridesToggle")
        self._overrides_toggle.setProperty("overridesToggle", True)
        self._overrides_toggle.setAutoRaise(True)
        self._overrides_toggle.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self._overrides_toggle.clicked.connect(self._on_overrides_toggle_clicked)
        disclosure_layout.addWidget(self._overrides_toggle, 0)

        disclosure_title = QLabel("Working directory and environment", self._overrides_disclosure)
        disclosure_title.setObjectName("shell.runWithArgumentsDialog.overridesTitle")
        disclosure_layout.addWidget(disclosure_title, 0)

        self._overrides_summary_label = QLabel(self._overrides_disclosure)
        self._overrides_summary_label.setObjectName("shell.runWithArgumentsDialog.overridesSummary")
        self._overrides_summary_label.setProperty("overridesSummary", True)
        self._overrides_summary_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        disclosure_layout.addWidget(self._overrides_summary_label, 1)

        overrides_layout.addWidget(self._overrides_disclosure)

        self._overrides_panel = QWidget(overrides_section)
        self._overrides_panel.setObjectName("shell.runWithArgumentsDialog.advancedGroup")
        overrides_panel_layout = QFormLayout(self._overrides_panel)
        overrides_panel_layout.setLabelAlignment(Qt.AlignLeft | Qt.AlignTop)
        overrides_panel_layout.setHorizontalSpacing(12)
        overrides_panel_layout.setVerticalSpacing(10)
        overrides_panel_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self._working_dir_edit = QLineEdit(self._overrides_panel)
        self._working_dir_edit.setObjectName("shell.runWithArgumentsDialog.workingDir")
        self._working_dir_edit.setPlaceholderText("Leave empty to use project root")
        wd_row = QWidget(self._overrides_panel)
        wd_row_layout = QHBoxLayout(wd_row)
        wd_row_layout.setContentsMargins(0, 0, 0, 0)
        wd_row_layout.setSpacing(8)
        wd_row_layout.addWidget(self._working_dir_edit, 1)
        browse_wd_button = make_field_action_button("Browse\u2026", wd_row)
        browse_wd_button.clicked.connect(self._on_browse_working_dir_clicked)
        wd_row_layout.addWidget(browse_wd_button, 0)
        overrides_panel_layout.addRow("Working directory:", wd_row)

        self._wd_helper_label = QLabel(_WD_HELPER_TEXT, self._overrides_panel)
        self._wd_helper_label.setObjectName("shell.runWithArgumentsDialog.wdHelper")
        self._wd_helper_label.setProperty("previewLabel", True)
        overrides_panel_layout.addRow("", self._wd_helper_label)

        self._working_dir_edit.textChanged.connect(self._refresh_validation_state)

        self._env_row = RunEnvOverridesRow(
            self._overrides_panel,
            tokens=tokens,
            object_name_prefix="shell.runWithArgumentsDialog.env",
        )
        overrides_panel_layout.addRow("Environment:", self._env_row)
        self._env_row.value_changed.connect(self._refresh_validation_state)

        overrides_layout.addWidget(self._overrides_panel)
        form_host_layout.addWidget(overrides_section)

        body_layout.addWidget(form_host, 1)

        self._error_label = QLabel(chrome.body)
        self._error_label.setObjectName("shell.runWithArgumentsDialog.error")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        body_layout.addWidget(self._error_label)

        manage_button = add_footer_button(
            chrome, "Manage configurations\u2026", role=FOOTER_ROLE_LINK
        )
        manage_button.clicked.connect(self._on_manage_configurations_clicked)

        add_footer_stretch(chrome)
        cancel_button = add_footer_button(chrome, "Cancel", role=FOOTER_ROLE_SECONDARY)

        footer_separator = QFrame(chrome.footer)
        footer_separator.setObjectName("shell.runWithArgumentsDialog.footerSeparator")
        footer_separator.setFrameShape(QFrame.VLine)
        footer_separator.setFrameShadow(QFrame.Sunken)
        chrome.footer_layout.addWidget(footer_separator)

        self._save_button = add_footer_button(
            chrome,
            "Save as Configuration\u2026",
            role=FOOTER_ROLE_LINK,
        )
        self._save_button.setToolTip(
            "Run now and remember these values as a named run configuration in cbcs/project.json. "
            "Nothing is saved unless you choose this action."
        )
        self._run_button = add_footer_button(chrome, "Run", role=FOOTER_ROLE_PRIMARY, default=True)
        self._run_button.setIcon(icon_run("#FFFFFF"))
        self._run_button.setToolTip("Run once without saving (Ctrl+Enter)")

        self._run_button.clicked.connect(self._on_run_clicked)
        self._save_button.clicked.connect(self._on_save_clicked)
        cancel_button.clicked.connect(self.reject)

        run_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        run_shortcut.activated.connect(self._on_run_clicked)

        has_advanced_values = bool(
            (initial.working_directory or "").strip() or initial.env_overrides
        )
        self._set_overrides_expanded(has_advanced_values)
        self._seed_initial_values()
        self._refresh_validation_state()
        self._configure_tab_order()
        if (initial.entry_file or "").strip():
            self._argv_editor.focus_argv_field()

    @classmethod
    def run_dialog(
        cls,
        parent: QWidget | None,
        *,
        initial: RunWithArgumentsInitial,
        tokens: ShellThemeTokens | None = None,
    ) -> RunWithArgumentsResult:
        dialog = cls(
            initial,
            parent=parent,
            tokens=tokens,
        )
        if dialog.exec_() != QDialog.Accepted:
            return RunWithArgumentsResult(outcome=dialog._outcome)
        return RunWithArgumentsResult(
            outcome=RunWithArgumentsOutcomeKind.RUN,
            invocation=dialog.invocation(),
        )

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

    def _set_overrides_expanded(self, expanded: bool) -> None:
        self._overrides_expanded = expanded
        self._overrides_panel.setVisible(expanded)
        self._overrides_toggle.setArrowType(
            Qt.DownArrow if expanded else Qt.RightArrow
        )
        self._working_dir_edit.setEnabled(expanded)
        self._env_row.setEnabled(expanded)
        for child in self._overrides_panel.findChildren(QPushButton):
            child.setEnabled(expanded)
        self._wd_helper_label.setVisible(expanded)
        self._refresh_overrides_summary()
        self._configure_tab_order()

    def _on_overrides_toggle_clicked(self) -> None:
        self._set_overrides_expanded(not self._overrides_expanded)

    def _refresh_overrides_summary(self) -> None:
        working_dir = self._working_dir_edit.text().strip() or None
        self._overrides_summary_label.setText(
            format_overrides_collapsed_summary(
                working_directory=working_dir,
                project_root=self._initial.project_root,
                env_overrides=self._env_row.env_overrides(),
            )
        )

    def _set_entry_validation_error(self, *, error: bool) -> None:
        state = "error" if error else "ok"
        if self._entry_combo.property("validationState") != state:
            self._entry_combo.setProperty("validationState", state)
            self._entry_combo.style().unpolish(self._entry_combo)
            self._entry_combo.style().polish(self._entry_combo)

    def _set_command_preview_state(self, state: str) -> None:
        if self._command_preview.property("commandPreviewState") != state:
            self._command_preview.setProperty("commandPreviewState", state)
            self._command_preview.style().unpolish(self._command_preview)
            self._command_preview.style().polish(self._command_preview)

    def _configure_tab_order(self) -> None:
        previous: QWidget = self
        if self._prefill_combo is not None:
            self.setTabOrder(previous, self._prefill_combo)
            previous = self._prefill_combo
        self.setTabOrder(previous, self._entry_combo)
        self.setTabOrder(self._entry_combo, self._argv_editor)
        self.setTabOrder(self._argv_editor, self._argv_editor.recent_combo_widget())
        self.setTabOrder(self._argv_editor.recent_combo_widget(), self._overrides_toggle)
        if self._overrides_expanded:
            self.setTabOrder(self._overrides_toggle, self._working_dir_edit)
            self.setTabOrder(self._working_dir_edit, self._env_row)
            self.setTabOrder(self._env_row, self._run_button)
        else:
            self.setTabOrder(self._overrides_toggle, self._run_button)

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
            self._set_overrides_expanded(True)
        self._prefill_combo.setCurrentIndex(0)
        self._refresh_validation_state()
        if config.argv:
            self._argv_editor.focus_argv_field()
        elif entry:
            self._entry_combo.setFocus()

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
        self._outcome = RunWithArgumentsOutcomeKind.OPEN_CONFIGURATIONS
        self.reject()

    def _refresh_validation_state(self) -> None:
        entry = self._entry_file_text()
        argv_text = self._argv_editor.argv_text()
        env_overrides = self._env_row.env_overrides()

        argv_tokens, argv_error = try_parse_argv_text(argv_text)
        if argv_error is not None:
            argv_tokens = []

        working_dir = self._working_dir_edit.text().strip() or None
        summary_text, detail_tooltip, preview_state = format_command_summary_strip(
            entry_file=entry,
            argv_tokens=argv_tokens,
            working_directory=working_dir,
            project_root=self._initial.project_root,
            env_overrides=env_overrides,
            argv_error=argv_error,
        )
        self._command_preview.setText(summary_text)
        self._command_preview.setToolTip(detail_tooltip)
        self._set_command_preview_state(preview_state)

        entry_missing = not entry
        self._set_entry_validation_error(error=entry_missing)
        self._argv_editor.set_argv_validation_error(error=argv_error is not None)

        _fields, error_message = collect_run_invocation_fields(
            entry_file=entry,
            argv_text=argv_text,
            env_overrides=env_overrides,
            working_directory=working_dir,
        )
        can_submit = _fields is not None
        self._run_button.setEnabled(can_submit)
        self._save_button.setEnabled(can_submit)

        if error_message and not can_submit and not entry_missing and argv_error is None:
            self._show_error(error_message)
        else:
            self._clear_error()

        self._refresh_overrides_summary()

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


def _join_argv_for_display(argv: Sequence[str]) -> str:
    """Backward-compatible alias for :func:`join_argv_for_display`."""

    return join_argv_for_display(argv)
