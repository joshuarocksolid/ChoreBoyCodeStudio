"""The left-pane Data tab. Its body is the registered sections."""

from __future__ import annotations

from typing import Any, Dict

from app.qt.QtCore import Signal
from app.qt.QtWidgets import QVBoxLayout, QWidget

from app.features.form_builder.qtside.data_panel.sections_ext import default_registry


class DataPanel(QWidget):
    """Empty until a form has a source. Add a connection opens Settings › Connections."""

    connect_requested = Signal()
    add_connection_requested = Signal()
    schema_changed = Signal(str)

    def __init__(self, workbench: Any) -> None:
        super().__init__(workbench)
        self.setObjectName("formBuilder.dataPanel")
        self._workbench = workbench
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._built: Dict[str, QWidget] = {}
        self._tokens: object = None
        self.reload()

    def reload(self) -> None:
        document = getattr(getattr(self._workbench, "session", None), "document", None)
        for section in default_registry().sections():
            show = document is not None and section.applies(document)
            widget = self._built.get(section.section_id)
            if not show:
                if widget is not None:
                    widget.hide()
                continue
            if widget is None:
                widget = section.create(self)
                self._built[section.section_id] = widget
                self._layout.addWidget(widget)
            widget.show()

    def showEvent(self, event: object) -> None:  # noqa: N802
        self.reload()
        super().showEvent(event)  # type: ignore[arg-type]

    def apply_theme(self, tokens: object) -> None:
        self._tokens = tokens
        width = int(getattr(tokens, "focus_border_width", 0) or 1)
        self.setStyleSheet(
            "QWidget#formBuilder\\.dataPanel { background: %s; color: %s; }"
            "QLabel#formBuilder\\.data\\.sentence, QLabel#formBuilder\\.data\\.schemaSentence { color: %s; background: transparent; }"
            "QLabel#formBuilder\\.data\\.stale { color: %s; background: transparent; }"
            "QPushButton { color: %s; background: %s; border: 1px solid %s; padding: 4px 8px; }"
            "QPushButton:disabled { color: %s; }"
            "QPushButton:focus { border: %dpx solid %s; }"
            % (
                tokens.panel_bg,  # type: ignore[attr-defined]
                tokens.text_primary,  # type: ignore[attr-defined]
                tokens.text_primary,  # type: ignore[attr-defined]
                tokens.diag_warning_color,  # type: ignore[attr-defined]
                tokens.text_primary,  # type: ignore[attr-defined]
                tokens.input_bg,  # type: ignore[attr-defined]
                tokens.border,  # type: ignore[attr-defined]
                tokens.text_muted,  # type: ignore[attr-defined]
                width,
                tokens.accent,  # type: ignore[attr-defined]
            )
        )
