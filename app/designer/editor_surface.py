"""Designer editor surface shell widget."""

from __future__ import annotations

from pathlib import Path

from PySide2.QtWidgets import QLabel, QSplitter, QTabWidget, QVBoxLayout, QWidget

from app.designer.canvas import FormCanvas, SelectionController
from app.designer.inspector import ObjectInspector
from app.designer.io import read_ui_file
from app.designer.model import UIModel
from app.designer.palette.palette_panel import PalettePanel

class DesignerEditorSurface(QWidget):
    """Host widget for visual `.ui` designer workflows."""

    def __init__(self, file_path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._file_path = str(Path(file_path).expanduser().resolve())
        self._model: UIModel | None = None
        self._selection_controller = SelectionController(self)
        self._build_layout()
        self._load_file_into_model()

    @property
    def file_path(self) -> str:
        return self._file_path

    @property
    def model(self) -> UIModel | None:
        return self._model

    def _build_layout(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._splitter = QSplitter(self)
        self._splitter.setChildrenCollapsible(False)
        root_layout.addWidget(self._splitter, 1)

        self._palette_panel = PalettePanel(self._splitter)
        self._canvas = FormCanvas(self._splitter)
        self._inspector_tabs = QTabWidget(self._splitter)
        self._object_inspector = ObjectInspector(self._inspector_tabs)
        self._object_inspector.set_selection_controller(self._selection_controller)
        self._inspector_tabs.addTab(self._object_inspector, "Object Inspector")
        self._inspector_tabs.addTab(QLabel("Property Editor (coming soon)", self._inspector_tabs), "Property Editor")
        self._splitter.addWidget(self._palette_panel)
        self._splitter.addWidget(self._canvas)
        self._splitter.addWidget(self._inspector_tabs)
        self._splitter.setSizes([280, 760, 320])

        self._error_label = QLabel("", self)
        self._error_label.setObjectName("designer.surface.errorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)
        root_layout.addWidget(self._error_label, 0)

    def _load_file_into_model(self) -> None:
        try:
            model = read_ui_file(self._file_path)
        except (OSError, ValueError) as exc:
            self._error_label.setText(f"Failed to load UI file: {exc}")
            self._error_label.setVisible(True)
            return
        self._model = model
        self._canvas.load_model(model)
        self._object_inspector.bind_model(model)

