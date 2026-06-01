"""Read-only env summary row with Browse button opening the table editor."""

from __future__ import annotations

from typing import Mapping

from PySide2.QtCore import Signal
from PySide2.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QWidget

from app.project.run_configs import env_overrides_to_text
from app.shell.run_env_overrides_dialog import RunEnvOverridesDialog, summarize_env_overrides
from app.shell.theme_tokens import ShellThemeTokens


class RunEnvOverridesRow(QWidget):
    """Environment overrides summary with table editor launched via Browse."""

    value_changed = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        tokens: ShellThemeTokens,
        object_name_prefix: str = "shell.runEnvOverridesRow",
    ) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._env_overrides: dict[str, str] = {}
        self.setObjectName(f"{object_name_prefix}.row")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._summary_edit = QLineEdit(self)
        self._summary_edit.setObjectName(f"{object_name_prefix}.summary")
        self._summary_edit.setReadOnly(True)
        self._summary_edit.setPlaceholderText("(none)")
        layout.addWidget(self._summary_edit, 1)

        browse_button = QPushButton("Browse\u2026", self)
        browse_button.clicked.connect(self._on_browse_clicked)
        layout.addWidget(browse_button, 0)

        self._update_summary_display()

    def env_overrides(self) -> dict[str, str]:
        return dict(self._env_overrides)

    def set_env_overrides(self, env_overrides: Mapping[str, str]) -> None:
        self._env_overrides = dict(env_overrides)
        self._update_summary_display()

    def _update_summary_display(self) -> None:
        summary = summarize_env_overrides(self._env_overrides)
        self._summary_edit.setText("" if summary == "(none)" else summary)
        full_text = env_overrides_to_text(self._env_overrides)
        self._summary_edit.setToolTip(full_text if full_text else "No environment overrides")

    def _on_browse_clicked(self) -> None:
        updated = RunEnvOverridesDialog.run_dialog(
            self.window(),
            initial=self._env_overrides,
            tokens=self._tokens,
        )
        if updated is None:
            return
        self._env_overrides = dict(updated)
        self._update_summary_display()
        self.value_changed.emit()
