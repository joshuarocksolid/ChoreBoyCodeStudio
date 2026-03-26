"""Unit tests for form canvas model insertion helpers."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtCore import QMimeData
from PySide2.QtWidgets import QApplication

from app.designer.canvas import SelectionController
from app.designer.canvas.form_canvas import FormCanvas
from app.designer.model import LayoutNode, UIModel, WidgetNode
from app.designer.palette import default_widget_palette_registry
from app.designer.palette.palette_panel import PALETTE_WIDGET_MIME

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
    inserted_widget = model.root_widget.find_by_object_name("pushButton")
    assert inserted_widget is not None
    geometry = inserted_widget.properties.get("geometry")
    assert geometry is not None
    assert geometry.value_type == "rect"
    assert geometry.value["x"] % 8 == 0
    assert geometry.value["y"] % 8 == 0


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


class _FakeDropEvent:
    def __init__(self, class_name: str) -> None:
        self._mime_data = QMimeData()
        self._mime_data.setData(PALETTE_WIDGET_MIME, class_name.encode("utf-8"))
        self.accepted = False
        self.ignored = False

    def mimeData(self) -> QMimeData:  # noqa: N802 - Qt-style
        return self._mime_data

    def acceptProposedAction(self) -> None:
        self.accepted = True

    def ignore(self) -> None:
        self.ignored = True


def test_drop_event_inserts_widget_from_palette_mime() -> None:
    canvas = FormCanvas()
    model = UIModel(
        form_class_name="CanvasForm",
        root_widget=WidgetNode(class_name="QWidget", object_name="rootWidget"),
    )
    canvas.load_model(model)
    event = _FakeDropEvent("QPushButton")

    canvas.dropEvent(event)

    assert event.accepted is True
    assert model.root_widget.find_by_object_name("pushButton") is not None


def test_canvas_tree_selection_syncs_with_selection_controller() -> None:
    canvas = FormCanvas()
    model = UIModel(
        form_class_name="CanvasForm",
        root_widget=WidgetNode(
            class_name="QWidget",
            object_name="rootWidget",
            children=[WidgetNode(class_name="QLabel", object_name="statusLabel")],
        ),
    )
    controller = SelectionController()
    canvas.set_selection_controller(controller)
    canvas.load_model(model)

    controller.set_selected_object_name("statusLabel")

    current_item = canvas._canvas_tree.currentItem()  # type: ignore[attr-defined]
    assert current_item is not None
    assert "statusLabel" in current_item.text(0)


def test_insert_widget_by_class_name_resolves_container_from_ancestor_selection() -> None:
    canvas = FormCanvas()
    model = UIModel(
        form_class_name="CanvasForm",
        root_widget=WidgetNode(
            class_name="QWidget",
            object_name="rootWidget",
            children=[
                WidgetNode(
                    class_name="QWidget",
                    object_name="containerWidget",
                    children=[WidgetNode(class_name="QPushButton", object_name="existingButton")],
                )
            ],
        ),
    )
    controller = SelectionController()
    canvas.set_selection_controller(controller)
    canvas.load_model(model)

    controller.set_selected_object_name("existingButton")

    inserted = canvas.insert_widget_by_class_name("QLineEdit")

    assert inserted is True
    container = model.root_widget.find_by_object_name("containerWidget")
    assert container is not None
    assert container.find_by_object_name("lineEdit") is not None


def test_insert_widget_by_class_name_falls_back_to_root_when_selection_invalid() -> None:
    canvas = FormCanvas()
    model = UIModel(
        form_class_name="CanvasForm",
        root_widget=WidgetNode(class_name="QWidget", object_name="rootWidget"),
    )
    controller = SelectionController()
    canvas.set_selection_controller(controller)
    canvas.load_model(model)

    controller.set_selected_object_name("missingWidget")

    inserted = canvas.insert_widget_by_class_name("QPushButton")

    assert inserted is True
    assert model.root_widget.find_by_object_name("pushButton") is not None


def test_insert_widget_by_class_name_falls_back_when_selection_is_non_container() -> None:
    canvas = FormCanvas()
    model = UIModel(
        form_class_name="CanvasForm",
        root_widget=WidgetNode(class_name="QWidget", object_name="rootWidget"),
    )
    selection = SelectionController()
    canvas.set_selection_controller(selection)
    canvas.load_model(model)

    assert canvas.insert_widget_by_class_name("QPushButton") is True
    assert selection.selected_object_name == "pushButton"

    assert canvas.insert_widget_by_class_name("QLabel") is True
    assert model.root_widget.find_by_object_name("label") is not None



