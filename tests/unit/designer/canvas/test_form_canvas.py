"""Unit tests for form canvas model insertion helpers."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication

from app.designer.canvas.form_canvas import FormCanvas
from app.designer.model import LayoutNode, UIModel, WidgetNode
from app.designer.palette import default_widget_palette_registry

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _ensure_qapp():  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_insert_palette_widget_into_children_list() -> None:
    canvas = FormCanvas()
    model = UIModel(
        form_class_name="CanvasForm",
        root_widget=WidgetNode(class_name="QWidget", object_name="rootWidget"),
    )
    canvas.load_model(model)
    registry = default_widget_palette_registry()
    button_definition = registry.lookup("QPushButton")
    assert button_definition is not None

    inserted = canvas.insert_palette_widget(parent_object_name="rootWidget", definition=button_definition)
    assert getattr(inserted, "class_name", None) == "QPushButton"
    assert model.root_widget.find_by_object_name("pushButton") is not None


def test_insert_layout_item_requires_parent_layout() -> None:
    canvas = FormCanvas()
    model = UIModel(
        form_class_name="CanvasForm",
        root_widget=WidgetNode(
            class_name="QWidget",
            object_name="rootWidget",
            layout=LayoutNode(class_name="QVBoxLayout", object_name="rootLayout"),
        ),
    )
    canvas.load_model(model)
    registry = default_widget_palette_registry()
    spacer_definition = registry.lookup("QSpacerItem")
    assert spacer_definition is not None

    inserted = canvas.insert_palette_widget(parent_object_name="rootWidget", definition=spacer_definition)
    assert getattr(inserted, "name", "") == "spacerItem"
    assert model.root_widget.layout is not None
    assert len(model.root_widget.layout.items) == 1


def test_insert_palette_widget_rejects_invalid_parent_class() -> None:
    canvas = FormCanvas()
    model = UIModel(
        form_class_name="CanvasForm",
        root_widget=WidgetNode(
            class_name="QWidget",
            object_name="rootWidget",
            children=[WidgetNode(class_name="QLineEdit", object_name="lineEdit")],
        ),
    )
    canvas.load_model(model)
    registry = default_widget_palette_registry()
    button_definition = registry.lookup("QPushButton")
    assert button_definition is not None

    with pytest.raises(ValueError, match="not allowed"):
        canvas.insert_palette_widget(parent_object_name="lineEdit", definition=button_definition)
