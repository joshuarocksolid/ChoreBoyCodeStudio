"""The inspector Data tab body. Sections come from ``data_ext``."""

from __future__ import annotations

from typing import Dict, Sequence

from app.qt.QtWidgets import QVBoxLayout, QWidget

from app.features.form_builder.qtside.inspector.data_ext import DataSection, default_registry


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
        if class_name == self._class_name and self._built:
            self._show(class_name)
            return
        self._class_name = class_name
        self._show(class_name)

    def apply_colors(self, panel: str, text: str, faint: str) -> None:
        self.setStyleSheet(
            "QWidget#formBuilder\\.dataBody { background: %s; color: %s; }"
            "QLabel#formBuilder\\.inspectorData\\.sentence, QLabel#formBuilder\\.inspectorData\\.notBound"
            " { color: %s; background: transparent; }"
            % (panel, text, faint or text)
        )

    def _show(self, class_name: str) -> None:
        sections = default_registry().sections()
        shown = set()
        for section in sections:
            if not section.applies(class_name):
                widget = self._built.get(section.section_id)
                if widget is not None:
                    widget.hide()
                continue
            shown.add(section.section_id)
            widget = self._built.get(section.section_id)
            if widget is None:
                widget = section.create(self)
                self._built[section.section_id] = widget
                self._layout.insertWidget(self._layout.count() - 1, widget)
            widget.show()
        if not shown:
            return


def selected_class(document: object, ids: Sequence[object]) -> str:
    """The class of the single selected node, or an empty string."""

    if len(ids) != 1:
        return ""
    node = document.node(ids[0])  # type: ignore[attr-defined]
    class_name = getattr(node, "class_name", "") or ""
    if not class_name:
        class_name = type(node).__name__
    return class_name.rsplit(".", 1)[-1]
