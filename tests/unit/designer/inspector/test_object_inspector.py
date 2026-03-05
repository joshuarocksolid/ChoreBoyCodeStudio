"""Unit tests for designer object inspector selection sync."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QApplication

from app.designer.canvas.selection_controller import SelectionController
from app.designer.inspector.object_inspector import ObjectInspector
from app.designer.model import UIModel, WidgetNode

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _ensure_qapp():  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_object_inspector_updates_tree_from_selection_controller() -> None:
    inspector = ObjectInspector()
    model = UIModel(
        form_class_name="Form",
        root_widget=WidgetNode(
            class_name="QWidget",
            object_name="rootWidget",
            children=[WidgetNode(class_name="QPushButton", object_name="pushButton")],
        ),
    )
    controller = SelectionController()
    inspector.bind_model(model)
    inspector.set_selection_controller(controller)

    controller.set_selected_object_name("pushButton")

    current_item = inspector._tree.currentItem()  # type: ignore[attr-defined]
    assert current_item is not None
    assert "pushButton" in current_item.text(0)


def test_object_inspector_pushes_tree_selection_to_controller() -> None:
    inspector = ObjectInspector()
    model = UIModel(
        form_class_name="Form",
        root_widget=WidgetNode(
            class_name="QWidget",
            object_name="rootWidget",
            children=[WidgetNode(class_name="QLabel", object_name="statusLabel")],
        ),
    )
    controller = SelectionController()
    inspector.bind_model(model)
    inspector.set_selection_controller(controller)

    items = inspector._tree.findItems(  # type: ignore[attr-defined]
        "statusLabel : QLabel",
        Qt.MatchExactly | Qt.MatchRecursive,
    )
    assert items
    target_item = items[0]
    target_item.setSelected(True)
    inspector._tree.setCurrentItem(target_item)  # type: ignore[attr-defined]
    inspector._handle_tree_selection_changed()  # type: ignore[attr-defined]

    assert controller.selected_object_name == "statusLabel"


def test_object_inspector_reparent_moves_widget_under_target_container() -> None:
    inspector = ObjectInspector()
    model = UIModel(
        form_class_name="Form",
        root_widget=WidgetNode(
            class_name="QWidget",
            object_name="rootWidget",
            children=[
                WidgetNode(class_name="QPushButton", object_name="sourceButton"),
                WidgetNode(class_name="QGroupBox", object_name="targetGroup"),
            ],
        ),
    )
    inspector.bind_model(model)

    moved = inspector._handle_drop_reparent("sourceButton", "targetGroup")  # type: ignore[attr-defined]

    assert moved is True
    target = model.root_widget.find_by_object_name("targetGroup")
    assert target is not None
    assert [child.object_name for child in target.children] == ["sourceButton"]


def test_object_inspector_reparent_rejects_non_container_targets() -> None:
    inspector = ObjectInspector()
    model = UIModel(
        form_class_name="Form",
        root_widget=WidgetNode(
            class_name="QWidget",
            object_name="rootWidget",
            children=[
                WidgetNode(class_name="QPushButton", object_name="sourceButton"),
                WidgetNode(class_name="QLineEdit", object_name="lineEdit"),
            ],
        ),
    )
    inspector.bind_model(model)

    moved = inspector._handle_drop_reparent("sourceButton", "lineEdit")  # type: ignore[attr-defined]

    assert moved is False
