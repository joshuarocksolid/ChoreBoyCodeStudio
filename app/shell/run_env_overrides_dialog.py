"""Modal table editor for run environment variable overrides."""

from __future__ import annotations

from typing import Mapping, Sequence

from PySide2.QtGui import QGuiApplication
from PySide2.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.project.run_configs import env_overrides_to_text, parse_env_overrides_text
from app.shell.dialog_chrome import (
    FOOTER_ROLE_PRIMARY,
    FOOTER_ROLE_SECONDARY,
    add_footer_button,
    add_footer_stretch,
    build_dialog_chrome,
)
from app.shell.style_sheet import build_run_dialog_style_sheet
from app.shell.theme_tokens import ShellThemeTokens, tokens_from_palette

_DIALOG_OBJECT_NAME = "shell.runEnvOverridesDialog"


def collect_env_overrides_from_rows(rows: Sequence[tuple[str, str]]) -> dict[str, str]:
    """Build env overrides from ``(name, value)`` table rows, skipping blank names."""

    collected: dict[str, str] = {}
    for name, value in rows:
        normalized_name = name.strip()
        if not normalized_name:
            continue
        collected[normalized_name] = value
    return collected


class RunEnvOverridesDialog(QDialog):
    """Key/value table editor for environment overrides."""

    def __init__(
        self,
        initial: Mapping[str, str],
        parent: QWidget | None = None,
        *,
        tokens: ShellThemeTokens | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Environment Variables")
        self.setModal(True)
        self.setObjectName(_DIALOG_OBJECT_NAME)
        self.setMinimumSize(560, 400)
        self.resize(640, 480)

        if tokens is None:
            tokens = tokens_from_palette(self.palette())
        self._tokens = tokens
        self.setStyleSheet(build_run_dialog_style_sheet(tokens))

        self._result: dict[str, str] | None = None

        chrome = build_dialog_chrome(
            self,
            title="Environment Variables",
            subtitle="Add name/value pairs applied only for this run.",
            object_name=_DIALOG_OBJECT_NAME,
            body_margins=True,
        )

        body_layout = chrome.body.layout()
        assert isinstance(body_layout, QVBoxLayout)

        self._table = QTableWidget(0, 2, chrome.body)
        self._table.setObjectName("shell.runEnvOverridesDialog.table")
        self._table.setHorizontalHeaderLabels(["Name", "Value"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        body_layout.addWidget(self._table, 1)

        toolbar = QWidget(chrome.body)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(8)
        add_row_button = QPushButton("+ Add row", toolbar)
        add_row_button.clicked.connect(self._on_add_row_clicked)
        remove_row_button = QPushButton("\u2212 Remove row", toolbar)
        remove_row_button.clicked.connect(self._on_remove_row_clicked)
        paste_button = QPushButton("Paste", toolbar)
        paste_button.setToolTip("Paste comma-separated KEY=VALUE text from the clipboard.")
        paste_button.clicked.connect(self._on_paste_clicked)
        toolbar_layout.addWidget(add_row_button)
        toolbar_layout.addWidget(remove_row_button)
        toolbar_layout.addWidget(paste_button)
        toolbar_layout.addStretch(1)
        body_layout.addWidget(toolbar)

        add_footer_stretch(chrome)
        cancel_button = add_footer_button(chrome, "Cancel", role=FOOTER_ROLE_SECONDARY)
        ok_button = add_footer_button(chrome, "OK", role=FOOTER_ROLE_PRIMARY, default=True)
        cancel_button.clicked.connect(self.reject)
        ok_button.clicked.connect(self._on_ok_clicked)

        self._populate_table(dict(initial))
        if self._table.rowCount() == 0:
            self._append_empty_row()

    @classmethod
    def run_dialog(
        cls,
        parent: QWidget | None,
        *,
        initial: Mapping[str, str],
        tokens: ShellThemeTokens | None = None,
    ) -> dict[str, str] | None:
        dialog = cls(initial, parent=parent, tokens=tokens)
        if dialog.exec_() != QDialog.Accepted:
            return None
        return dialog._result

    def _populate_table(self, env_overrides: dict[str, str]) -> None:
        self._table.setRowCount(0)
        for key, value in sorted(env_overrides.items()):
            self._append_row(key, value)

    def _append_empty_row(self) -> None:
        self._append_row("", "")

    def _append_row(self, name: str, value: str) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(name))
        self._table.setItem(row, 1, QTableWidgetItem(value))

    def _on_add_row_clicked(self) -> None:
        self._append_empty_row()
        self._table.setCurrentCell(self._table.rowCount() - 1, 0)
        self._table.editItem(self._table.item(self._table.rowCount() - 1, 0))

    def _on_remove_row_clicked(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        self._table.removeRow(row)
        if self._table.rowCount() == 0:
            self._append_empty_row()

    def _on_paste_clicked(self) -> None:
        clipboard = QGuiApplication.clipboard()
        text = clipboard.text() if clipboard is not None else ""
        if not text.strip():
            return
        try:
            parsed = parse_env_overrides_text(text)
        except ValueError:
            return
        self._populate_table(parsed)
        if self._table.rowCount() == 0:
            self._append_empty_row()

    def _collect_env_overrides(self) -> dict[str, str]:
        rows: list[tuple[str, str]] = []
        for row in range(self._table.rowCount()):
            name_item = self._table.item(row, 0)
            value_item = self._table.item(row, 1)
            name = name_item.text() if name_item is not None else ""
            value = value_item.text() if value_item is not None else ""
            rows.append((name, value))
        return collect_env_overrides_from_rows(rows)

    def _on_ok_clicked(self) -> None:
        self._result = self._collect_env_overrides()
        self.accept()


def summarize_env_overrides(env_overrides: Mapping[str, str], *, max_length: int = 72) -> str:
    """Return a compact summary string for read-only display rows."""

    if not env_overrides:
        return "(none)"
    text = env_overrides_to_text(env_overrides)
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3]}..."
