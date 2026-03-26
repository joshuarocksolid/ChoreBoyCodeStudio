"""Unit tests for interactive property editor panel."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication, QCheckBox, QLineEdit, QSpinBox, QToolButton

from app.designer.model import WidgetNode
from app.designer.properties import IconPickerField, PropertyEditorController
from app.designer.properties.property_editor_panel import PropertyEditorPanel

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _ensure_qapp():  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_property_panel_emits_object_name_scoped_property_edits() -> None:
    panel = PropertyEditorPanel()
    controller = PropertyEditorController()
    widget = WidgetNode(class_name="QPushButton", object_name="pushButton")
    panel.bind_widget(widget, controller.field_definitions_for_widget(widget))

    edits: list[tuple[str, str, object]] = []
    panel.property_edited.connect(lambda obj, prop, value: edits.append((obj, prop, value)))

    line_edits = panel.findChildren(QLineEdit)
    assert line_edits
    line_edits[0].setText("renamedButton")
    line_edits[0].editingFinished.emit()

    checkboxes = panel.findChildren(QCheckBox)
    assert checkboxes
    checkboxes[0].setChecked(False)

    assert ("pushButton", "objectName", "renamedButton") in edits
    assert ("pushButton", "enabled", False) in edits


def test_property_panel_disables_reset_for_object_name() -> None:
    panel = PropertyEditorPanel()
    controller = PropertyEditorController()
    widget = WidgetNode(class_name="QPushButton", object_name="pushButton")
    panel.bind_widget(widget, controller.field_definitions_for_widget(widget))

    resets: list[tuple[str, str]] = []
    panel.property_reset_requested.connect(lambda obj, prop: resets.append((obj, prop)))

    object_name_reset = panel.findChild(QToolButton, "designer.property.reset.objectName")
    assert object_name_reset is not None
    assert object_name_reset.isEnabled() is False

    text_reset = panel.findChild(QToolButton, "designer.property.reset.text")
    assert text_reset is not None
    text_reset.click()
    assert resets == [("pushButton", "text")]


def test_property_panel_uses_icon_picker_for_iconset_fields() -> None:
    panel = PropertyEditorPanel()
    controller = PropertyEditorController()
    widget = WidgetNode(class_name="QPushButton", object_name="pushButton")
    panel.bind_widget(widget, controller.field_definitions_for_widget(widget))

    edits: list[tuple[str, str, object]] = []
    panel.property_edited.connect(lambda obj, prop, value: edits.append((obj, prop, value)))

    icon_pickers = panel.findChildren(IconPickerField)
    picker_by_field = {
        picker.objectName().replace("designer.property.editor.", ""): picker
        for picker in icon_pickers
    }
    picker = picker_by_field.get("icon")
    assert picker is not None
    picker.set_path("icons/run.png")
    picker.path_changed.emit("icons/run.png")

    assert ("pushButton", "icon", "icons/run.png") in edits


def test_property_panel_renders_layout_and_sizing_fields() -> None:
    panel = PropertyEditorPanel()
    controller = PropertyEditorController()
    widget = WidgetNode(class_name="QWidget", object_name="rootWidget")
    panel.bind_widget(widget, controller.field_definitions_for_widget(widget))

    assert panel.findChild(QLineEdit, "designer.property.editor.minimumSize") is not None
    assert panel.findChild(QLineEdit, "designer.property.editor.maximumSize") is not None
    assert panel.findChild(QLineEdit, "designer.property.editor.contentsMargins") is not None

    spacing_spin = panel.findChild(QSpinBox, "designer.property.editor.layoutSpacing")
    assert spacing_spin is not None


def test_property_panel_renders_appearance_and_metadata_fields() -> None:
    panel = PropertyEditorPanel()
    controller = PropertyEditorController()
    widget = WidgetNode(class_name="QWidget", object_name="rootWidget")
    panel.bind_widget(widget, controller.field_definitions_for_widget(widget))

    assert panel.findChild(QLineEdit, "designer.property.editor.styleSheet") is not None
    assert panel.findChild(QLineEdit, "designer.property.editor.windowTitle") is not None
    window_icon_picker = panel.findChild(IconPickerField, "designer.property.editor.windowIcon")
    assert window_icon_picker is not None
    assert panel.findChild(QLineEdit, "designer.property.editor.font") is not None
    assert panel.findChild(QLineEdit, "designer.property.editor.palette") is not None
    assert panel.findChild(QLineEdit, "designer.property.editor.cursor") is not None
