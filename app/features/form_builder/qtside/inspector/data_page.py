"""The inspector Data tab body. Sections come from ``data_ext``."""

from __future__ import annotations

from typing import Dict, Sequence

from types import SimpleNamespace

from app.features.form_builder.qtside.checkbox_qss import checkbox_indicators
from app.qt.QtWidgets import QVBoxLayout, QWidget

from app.features.form_builder.qtside.data_panel.host import note_data_tab
from app.features.form_builder.qtside.inspector.data_ext import default_registry


class DataPage(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.dataBody")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.addStretch(1)
        self._built: Dict[str, QWidget] = {}
        self._class_name = ""

    def paint(self, class_name: str) -> None:
        changed = class_name != self._class_name or not self._built
        self._class_name = class_name
        self._show(class_name)
        if not changed:
            return
        for widget in self._built.values():
            if widget.isHidden():
                continue
            refresh = getattr(widget, "refresh", None)
            if callable(refresh):
                refresh()

    def showEvent(self, event: object) -> None:  # noqa: N802
        super().showEvent(event)  # type: ignore[arg-type]
        self._show(self._class_name)
        note_data_tab(self, "inspector", True)

    def hideEvent(self, event: object) -> None:  # noqa: N802
        super().hideEvent(event)  # type: ignore[arg-type]
        note_data_tab(self, "inspector", False)

    def apply_colors(
        self,
        panel: str,
        text: str,
        faint: str,
        warning: str = "",
        error: str = "",
        accent: str = "",
        input_bg: str = "",
        border: str = "",
        focus_width: int = 1,
    ) -> None:
        warning = warning or faint
        error = error or warning
        accent = accent or text
        input_bg = input_bg or panel
        border = border or faint
        width = focus_width if focus_width > 0 else 1
        body = "QWidget#formBuilder\\.dataBody"
        sheet = (
            "%s { background: %s; color: %s; }"
            "%s QLabel { color: %s; background: transparent; }"
            "%s QLabel#formBuilder\\.inspectorData\\.sentence, %s QLabel#formBuilder\\.inspectorData\\.notBound,"
            " %s QLabel#formBuilder\\.inspectorData\\.typeWords, %s QLabel[fbFaint=\"true\"] { color: %s; background: transparent; }"
            "%s QLabel#formBuilder\\.inspectorData\\.problem[fbProblem=\"warning\"], %s QLabel#formBuilder\\.inspectorData\\.lookupRows[fbProblem=\"warning\"] { color: %s; }"
            "%s QLabel#formBuilder\\.inspectorData\\.problem[fbProblem=\"error\"], %s QLabel#formBuilder\\.inspectorData\\.lookupRows[fbProblem=\"error\"] { color: %s; }"
            "%s QLineEdit, %s QComboBox, %s QListWidget, %s QPlainTextEdit { color: %s; background: %s; border: 1px solid %s; }"
            "%s QLineEdit:focus, %s QComboBox:focus, %s QListWidget:focus, %s QPlainTextEdit:focus { border: %dpx solid %s; }"
            "%s QCheckBox { color: %s; background: transparent; }"
            "%s QPushButton, %s QToolButton { color: %s; background: %s; border: 1px solid %s; padding: 2px 8px; }"
            "%s QPushButton:disabled, %s QToolButton:disabled { color: %s; }"
            "%s QPushButton:focus, %s QToolButton:focus { border: %dpx solid %s; }"
            "%s QToolButton#formBuilder\\.inspectorData\\.lookupAlsoAdd::menu-indicator { image: none; width: 0px; }"
            % (
                body, panel, text,
                body, text,
                body, body, body, body, faint or text,
                body, body, warning,
                body, body, error,
                body, body, body, body, text, input_bg, border,
                body, body, body, body, width, accent,
                body, text,
                body, body, text, input_bg, border,
                body, body, faint or text,
                body, body, width, accent,
                body,
            )
        )
        marks = SimpleNamespace(
            focus_border_width=width,
            accent=accent,
            border=border,
            input_bg=input_bg,
            panel_bg=panel,
        )
        self.setStyleSheet(sheet + checkbox_indicators(marks))

    def _show(self, class_name: str) -> None:
        sections = default_registry().sections()
        for section in sections:
            if not section.applies(class_name):
                widget = self._built.get(section.section_id)
                if widget is not None:
                    widget.hide()
                continue
            widget = self._built.get(section.section_id)
            if widget is None:
                # Building a focusable editor before this tab is on screen pulls
                # keyboard focus off the canvas and Insert (the source list, and
                # the lookup combos).
                if section.section_id in ("form-source", "lookup") and not self.isVisible():
                    continue
                widget = section.create(self)
                self._built[section.section_id] = widget
                self._layout.insertWidget(self._layout.count() - 1, widget)
            widget.show()


def selected_class(document: object, ids: Sequence[object]) -> str:
    """The class of the single selected node, ``@form`` for the document root, or ``""``."""

    if len(ids) != 1:
        return ""
    root = getattr(document, "root", None)
    if root is not None and ids[0] == getattr(root, "id", None):
        return "@form"
    node = document.node(ids[0])  # type: ignore[attr-defined]
    class_name = getattr(node, "class_name", "") or ""
    if not class_name:
        class_name = type(node).__name__
    return class_name.rsplit(".", 1)[-1]
