"""Designer editor surface shell widget."""

from __future__ import annotations

from pathlib import Path

from PySide2.QtWidgets import QLabel, QListWidget, QSplitter, QTabWidget, QVBoxLayout, QWidget

from app.designer.canvas import FormCanvas, SelectionController
from app.designer.inspector import ObjectInspector
from app.designer.io import read_ui_file
from app.designer.model import UIModel, WidgetNode
from app.designer.palette import default_widget_palette_registry
from app.designer.palette.palette_panel import PalettePanel
from app.designer.properties import PropertyEditorController
from app.designer.validation import build_validation_issues


class DesignerEditorSurface(QWidget):
    """Host widget for visual `.ui` designer workflows."""

    def __init__(self, file_path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._file_path = str(Path(file_path).expanduser().resolve())
        self._model: UIModel | None = None
        self._selection_controller = SelectionController(self)
        self._property_editor = PropertyEditorController()
        self._palette_registry = default_widget_palette_registry()
        self._build_layout()
        self._selection_controller.selection_changed.connect(self._handle_selection_changed)
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

        self._palette_panel = PalettePanel(self._splitter, registry=self._palette_registry)
        self._palette_panel.widget_insert_requested.connect(self._handle_palette_insert_request)
        self._canvas = FormCanvas(self._splitter)
        self._inspector_tabs = QTabWidget(self._splitter)
        self._object_inspector = ObjectInspector(self._inspector_tabs)
        self._object_inspector.set_selection_controller(self._selection_controller)
        self._property_summary = QLabel("Select a widget to view editable properties.", self._inspector_tabs)
        self._property_summary.setWordWrap(True)
        self._inspector_tabs.addTab(self._object_inspector, "Object Inspector")
        self._inspector_tabs.addTab(self._property_summary, "Property Editor")
        self._splitter.addWidget(self._palette_panel)
        self._splitter.addWidget(self._canvas)
        self._splitter.addWidget(self._inspector_tabs)
        self._splitter.setSizes([280, 760, 320])

        self._validation_list = QListWidget(self)
        self._validation_list.setObjectName("designer.surface.validationList")
        root_layout.addWidget(self._validation_list, 0)

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
        self._refresh_validation_issues()

    def _handle_selection_changed(self, object_name: str) -> None:
        if self._model is None or not object_name:
            self._property_summary.setText("Select a widget to view editable properties.")
            return
        widget = self._model.root_widget.find_by_object_name(object_name)
        if widget is None:
            self._property_summary.setText("Select a widget to view editable properties.")
            return
        self._property_summary.setText(self._build_property_summary(widget))

    def _build_property_summary(self, widget: WidgetNode) -> str:
        fields = self._property_editor.field_definitions_for_widget(widget)
        lines = [f"{widget.object_name} : {widget.class_name}", "", "Editable properties:"]
        for field in fields:
            lines.append(f"• {field.display_label} ({field.name})")
        return "\n".join(lines)

    def _refresh_validation_issues(self) -> None:
        self._validation_list.clear()
        if self._model is None:
            return
        for issue in build_validation_issues(self._model):
            self._validation_list.addItem(f"[{issue.severity}] {issue.code} — {issue.message}")

    def _handle_palette_insert_request(self, class_name: str) -> None:
        if self._model is None:
            return
        definition = self._palette_registry.lookup(class_name)
        if definition is None:
            return
        parent_name = self._selection_controller.selected_object_name or self._model.root_widget.object_name
        try:
            inserted = self._canvas.insert_palette_widget(
                parent_object_name=parent_name,
                definition=definition,
            )
        except ValueError as exc:
            self._error_label.setText(str(exc))
            self._error_label.setVisible(True)
            return
        self._error_label.setVisible(False)
        self._object_inspector.bind_model(self._model)
        self._refresh_validation_issues()
        inserted_name = getattr(inserted, "object_name", "")
        if inserted_name:
            self._selection_controller.set_selected_object_name(inserted_name)

