"""Interactive property editor panel for Designer widgets."""

from __future__ import annotations

from typing import Any

from PySide2.QtCore import Signal
from PySide2.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.designer.model import PropertyValue, WidgetNode
from app.designer.properties.icon_picker import IconPickerField
from app.designer.properties.property_schema import PropertyFieldDefinition


class PropertyEditorPanel(QWidget):
    """Render and edit typed property fields for selected widget."""

    property_edited = Signal(str, str, object)
    property_reset_requested = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("designer.property.panel")
        self._target_object_name: str | None = None
        self._is_populating = False

        self._header_label = QLabel("Select a widget to edit properties.", self)
        self._header_label.setObjectName("designer.property.header")
        self._form_host = QWidget(self)
        self._form_host.setObjectName("designer.property.formHost")
        self._form_layout = QFormLayout(self._form_host)
        self._form_layout.setContentsMargins(0, 0, 0, 0)
        self._form_layout.setSpacing(6)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(8)
        root_layout.addWidget(self._header_label, 0)
        root_layout.addWidget(self._form_host, 1)

    def bind_widget(
        self,
        widget: WidgetNode | None,
        fields: list[PropertyFieldDefinition],
    ) -> None:
        self._target_object_name = None if widget is None else widget.object_name
        self._header_label.setText(
            "Select a widget to edit properties."
            if widget is None
            else f"{widget.object_name} : {widget.class_name}"
        )

        while self._form_layout.rowCount() > 0:
            self._form_layout.removeRow(0)

        if widget is None:
            return

        self._is_populating = True
        try:
            for field in fields:
                editor = self._build_editor(field, widget)
                reset_button = QPushButton("Reset", self._form_host)
                reset_button.setObjectName(f"designer.property.reset.{field.name}")
                reset_button.clicked.connect(
                    lambda _checked=False, name=field.name: self._emit_reset(name)
                )
                if field.name == "objectName":
                    reset_button.setEnabled(False)

                row_widget = QWidget(self._form_host)
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(4)
                row_layout.addWidget(editor, 1)
                row_layout.addWidget(reset_button, 0)
                self._form_layout.addRow(field.display_label, row_widget)
        finally:
            self._is_populating = False

    def _property_value_for(self, widget: WidgetNode, field: PropertyFieldDefinition) -> Any:
        if field.name == "objectName":
            return widget.object_name
        existing = widget.properties.get(field.name)
        if isinstance(existing, PropertyValue):
            return existing.value
        return field.default_value

    def _build_editor(self, field: PropertyFieldDefinition, widget: WidgetNode) -> QWidget:
        value = self._property_value_for(widget, field)
        if field.enum_values:
            combo = QComboBox(self._form_host)
            combo.addItems(list(field.enum_values))
            if value is not None:
                index = combo.findText(str(value))
                if index >= 0:
                    combo.setCurrentIndex(index)
            combo.currentTextChanged.connect(lambda text, name=field.name: self._emit_edit(name, text))
            return combo
        if field.value_type == "bool":
            checkbox = QCheckBox(self._form_host)
            checkbox.setChecked(bool(value))
            checkbox.toggled.connect(lambda checked, name=field.name: self._emit_edit(name, checked))
            return checkbox
        if field.value_type in {"int", "number"}:
            spin_box = QSpinBox(self._form_host)
            spin_box.setRange(-99999, 99999)
            spin_box.setValue(int(value if value is not None else 0))
            spin_box.valueChanged.connect(lambda v, name=field.name: self._emit_edit(name, v))
            return spin_box
        if field.value_type in {"float", "double"}:
            double_box = QDoubleSpinBox(self._form_host)
            double_box.setRange(-99999.0, 99999.0)
            double_box.setDecimals(3)
            double_box.setValue(float(value if value is not None else 0.0))
            double_box.valueChanged.connect(lambda v, name=field.name: self._emit_edit(name, v))
            return double_box
        if field.value_type == "iconset":
            picker = IconPickerField(self._form_host)
            picker.set_path("" if value is None else str(value))
            picker.path_changed.connect(lambda path, name=field.name: self._emit_edit(name, path))
            return picker
        line_edit = QLineEdit(self._form_host)
        line_edit.setText("" if value is None else str(value))
        line_edit.editingFinished.connect(
            lambda editor=line_edit, name=field.name: self._emit_edit(name, editor.text())
        )
        return line_edit

    def _emit_edit(self, property_name: str, value: object) -> None:
        if self._is_populating or self._target_object_name is None:
            return
        self.property_edited.emit(self._target_object_name, property_name, value)

    def _emit_reset(self, property_name: str) -> None:
        if self._target_object_name is None:
            return
        self.property_reset_requested.emit(self._target_object_name, property_name)
