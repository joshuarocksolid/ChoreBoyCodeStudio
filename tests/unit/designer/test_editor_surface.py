"""Unit tests for Designer editor surface composition."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication

from app.designer.editor_surface import DesignerEditorSurface
from app.designer.preview import PreviewCompatibilityResult

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _ensure_qapp():  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_editor_surface_loads_model_and_panels(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\"/>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    surface = DesignerEditorSurface(str(ui_file.resolve()))

    assert surface.model is not None
    assert surface.model.form_class_name == "SampleForm"
    assert surface.file_path == str(ui_file.resolve())
    validation_rows = [surface._validation_list.item(index).text() for index in range(surface._validation_list.count())]  # type: ignore[attr-defined]
    assert any("DLAYOUT001" in row for row in validation_rows)
    assert any("DLINT001" in row for row in validation_rows)

    surface._selection_controller.set_selected_object_name("SampleForm")  # type: ignore[attr-defined]
    assert "SampleForm" in surface._property_panel._header_label.text()  # type: ignore[attr-defined]


def test_editor_surface_can_disable_naming_lint(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\"/>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )
    surface = DesignerEditorSurface(str(ui_file.resolve()), enable_naming_lint=False)
    validation_rows = [surface._validation_list.item(index).text() for index in range(surface._validation_list.count())]  # type: ignore[attr-defined]
    assert any("DLAYOUT001" in row for row in validation_rows)
    assert not any("DLINT001" in row for row in validation_rows)


def test_editor_surface_palette_insert_updates_model(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\"/>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.model is not None
    surface._handle_palette_insert_request("QPushButton")  # type: ignore[attr-defined]

    inserted = surface.model.root_widget.find_by_object_name("pushButton")
    assert inserted is not None
    assert inserted.class_name == "QPushButton"


def test_editor_surface_canvas_insert_route_updates_dirty_and_undo(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\"/>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.model is not None
    assert surface.is_dirty is False
    assert surface.can_undo is False

    inserted, error_message = surface._insert_widget_via_snapshot("QPushButton")  # type: ignore[attr-defined]
    assert inserted is True, error_message
    assert surface.model.root_widget.find_by_object_name("pushButton") is not None
    assert surface.is_dirty is True
    assert surface.can_undo is True


def test_editor_surface_emits_dirty_state_on_mutation(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\"/>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    surface = DesignerEditorSurface(str(ui_file.resolve()))
    states: list[bool] = []
    surface.dirty_state_changed.connect(states.append)

    surface._handle_palette_insert_request("QPushButton")  # type: ignore[attr-defined]
    assert states[-1] is True

    surface.mark_saved()
    assert states[-1] is False


def test_editor_surface_undo_redo_replays_snapshot_mutations(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\"/>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.model is not None
    assert surface.model.root_widget.find_by_object_name("pushButton") is None

    surface._handle_palette_insert_request("QPushButton")  # type: ignore[attr-defined]
    assert surface.can_undo is True
    assert surface.model.root_widget.find_by_object_name("pushButton") is not None

    assert surface.undo() is True
    assert surface.model.root_widget.find_by_object_name("pushButton") is None

    assert surface.redo() is True
    assert surface.model.root_widget.find_by_object_name("pushButton") is not None


def test_editor_surface_mode_switch_updates_current_mode(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\"/>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    surface = DesignerEditorSurface(str(ui_file.resolve()))
    seen: list[str] = []
    surface.mode_changed.connect(seen.append)

    assert surface.current_mode == "widget"
    assert surface.set_mode("signals_slots") is True
    assert surface.current_mode == "signals_slots"
    assert seen[-1] == "signals_slots"
    assert surface.set_mode("invalid_mode") is False


def test_editor_surface_property_mutation_pushes_undo_snapshot(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\">"
            "<widget class=\"QPushButton\" name=\"pushButton\">"
            "<property name=\"text\"><string>Click me</string></property>"
            "</widget>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.model is not None
    surface._apply_property_mutation("pushButton", "text", "set", "Run")  # type: ignore[attr-defined]

    push_button = surface.model.root_widget.find_by_object_name("pushButton")
    assert push_button is not None
    assert push_button.properties["text"].value == "Run"
    assert surface.can_undo is True

    assert surface.undo() is True
    push_button_after_undo = surface.model.root_widget.find_by_object_name("pushButton")
    assert push_button_after_undo is not None
    assert push_button_after_undo.properties["text"].value == "Click me"


def test_editor_surface_geometry_property_mutation_snaps_to_grid(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\">"
            "<widget class=\"QPushButton\" name=\"pushButton\"/>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )
    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.model is not None
    surface._apply_property_mutation(  # type: ignore[attr-defined]
        "pushButton",
        "geometry",
        "set",
        {"x": 23, "y": 17, "width": 100, "height": 40},
    )
    push_button = surface.model.root_widget.find_by_object_name("pushButton")
    assert push_button is not None
    geometry = push_button.properties["geometry"].value
    assert geometry["x"] == 16
    assert geometry["y"] == 16


def test_editor_surface_geometry_snap_can_be_disabled(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\">"
            "<widget class=\"QPushButton\" name=\"pushButton\"/>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )
    surface = DesignerEditorSurface(str(ui_file.resolve()), snap_to_grid=False)
    assert surface.model is not None
    surface._apply_property_mutation(  # type: ignore[attr-defined]
        "pushButton",
        "geometry",
        "set",
        {"x": 23, "y": 17, "width": 100, "height": 40},
    )
    push_button = surface.model.root_widget.find_by_object_name("pushButton")
    assert push_button is not None
    geometry = push_button.properties["geometry"].value
    assert geometry["x"] == 23
    assert geometry["y"] == 17


def test_editor_surface_reparent_mutation_pushes_undo_snapshot(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\">"
            "<widget class=\"QPushButton\" name=\"sourceButton\"/>"
            "<widget class=\"QGroupBox\" name=\"targetGroup\"/>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.model is not None
    moved = surface._handle_inspector_reparent_request("sourceButton", "targetGroup")  # type: ignore[attr-defined]
    assert moved is True

    target = surface.model.root_widget.find_by_object_name("targetGroup")
    assert target is not None
    assert [child.object_name for child in target.children] == ["sourceButton"]
    assert surface.can_undo is True

    assert surface.undo() is True
    target_after_undo = surface.model.root_widget.find_by_object_name("targetGroup")
    assert target_after_undo is not None
    assert target_after_undo.children == []


def test_editor_surface_reparent_invalid_target_surfaces_error(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\">"
            "<widget class=\"QPushButton\" name=\"sourceButton\"/>"
            "<widget class=\"QLineEdit\" name=\"lineEdit\"/>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    surface = DesignerEditorSurface(str(ui_file.resolve()))
    moved = surface._handle_inspector_reparent_request("sourceButton", "lineEdit")  # type: ignore[attr-defined]
    assert moved is False
    assert surface._error_label.isHidden() is False  # type: ignore[attr-defined]
    assert "cannot accept child widgets" in surface._error_label.text()  # type: ignore[attr-defined]


def test_editor_surface_add_resource_include_pushes_undo_snapshot(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\"/>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.model is not None
    assert surface.add_resource_include("icons.qrc") is True
    assert [resource.location for resource in surface.model.resources] == ["icons.qrc"]
    assert surface.add_resource_include("icons.qrc") is False
    assert surface.can_undo is True

    assert surface.undo() is True
    assert surface.model.resources == []


def test_editor_surface_connection_add_remove_is_undoable(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\">"
            "<widget class=\"QPushButton\" name=\"pushButton\"/>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.model is not None
    surface._selection_controller.set_selected_object_name("pushButton")  # type: ignore[attr-defined]
    surface._handle_add_connection_request()  # type: ignore[attr-defined]

    assert len(surface.model.connections) == 1
    assert surface.model.connections[0].sender == "pushButton"
    assert surface.can_undo is True

    surface._handle_remove_connection_request(0)  # type: ignore[attr-defined]
    assert surface.model.connections == []
    assert surface.undo() is True
    assert len(surface.model.connections) == 1


def test_editor_surface_connection_edit_is_undoable(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\">"
            "<widget class=\"QPushButton\" name=\"pushButton\"/>"
            "</widget>"
            "<resources/>"
            "<connections><connection><sender>pushButton</sender><signal>clicked(bool)</signal>"
            "<receiver>SampleForm</receiver><slot>setEnabled(bool)</slot></connection></connections>"
            "</ui>\n"
        ),
        encoding="utf-8",
    )

    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.model is not None
    surface._handle_connection_edited(0, "slot", "setVisible(bool)")  # type: ignore[attr-defined]
    assert surface.model.connections[0].slot == "setVisible(bool)"
    assert surface.can_undo is True
    assert surface.undo() is True
    assert surface.model.connections[0].slot == "setEnabled(bool)"


def test_editor_surface_connection_edit_rejects_incompatible_signature_update(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\">"
            "<widget class=\"QPushButton\" name=\"pushButton\"/>"
            "</widget>"
            "<resources/>"
            "<connections><connection><sender>pushButton</sender><signal>clicked()</signal>"
            "<receiver>SampleForm</receiver><slot>setFocus()</slot></connection></connections>"
            "</ui>\n"
        ),
        encoding="utf-8",
    )

    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.model is not None
    surface._handle_connection_edited(0, "slot", "setText(QString)")  # type: ignore[attr-defined]

    assert surface.model.connections[0].slot == "setFocus()"
    assert surface.can_undo is False
    assert surface._error_label.isHidden() is False  # type: ignore[attr-defined]
    error_text = surface._error_label.text().lower()  # type: ignore[attr-defined]
    assert "not available" in error_text or "incompatible" in error_text


def test_editor_surface_signals_mode_switches_to_connections_tab(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\"/>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.set_mode("signals_slots") is True
    assert surface._inspector_tabs.tabText(surface._inspector_tabs.currentIndex()) == "Signals"  # type: ignore[attr-defined]


def test_editor_surface_signals_mode_selection_gesture_creates_connection(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\">"
            "<widget class=\"QPushButton\" name=\"pushButton\"/>"
            "<widget class=\"QLineEdit\" name=\"lineEdit\"/>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )
    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.model is not None
    assert surface.set_mode("signals_slots") is True

    surface._selection_controller.set_selected_object_name("pushButton")  # type: ignore[attr-defined]
    surface._selection_controller.set_selected_object_name("lineEdit")  # type: ignore[attr-defined]

    assert len(surface.model.connections) == 1
    assert surface.model.connections[0].sender == "pushButton"
    assert surface.model.connections[0].receiver == "lineEdit"
    assert surface.can_undo is True


def test_editor_surface_tab_order_mode_switches_to_tab_order_tab(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\">"
            "<widget class=\"QLineEdit\" name=\"lineEdit\"/>"
            "<widget class=\"QPushButton\" name=\"okButton\"/>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.set_mode("tab_order") is True
    assert surface._inspector_tabs.tabText(surface._inspector_tabs.currentIndex()) == "Tab \u2195"  # type: ignore[attr-defined]


def test_editor_surface_tab_order_changes_are_undoable(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\">"
            "<widget class=\"QLineEdit\" name=\"lineEdit\"/>"
            "<widget class=\"QPushButton\" name=\"okButton\"/>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )
    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.model is not None
    surface._handle_tab_order_changed(["okButton", "lineEdit"])  # type: ignore[attr-defined]
    assert surface.model.tab_stops == ["okButton", "lineEdit"]
    assert surface.can_undo is True
    assert surface.undo() is True
    assert surface.model.tab_stops == []


def test_editor_surface_tab_order_mode_selection_gesture_reorders_chain(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\">"
            "<widget class=\"QLineEdit\" name=\"lineEdit\"/>"
            "<widget class=\"QPushButton\" name=\"okButton\"/>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )
    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.model is not None
    assert surface.set_mode("tab_order") is True

    surface._selection_controller.set_selected_object_name("lineEdit")  # type: ignore[attr-defined]
    surface._selection_controller.set_selected_object_name("okButton")  # type: ignore[attr-defined]

    assert surface.model.tab_stops[-1] == "okButton"
    assert surface.can_undo is True


def test_editor_surface_buddy_mode_switches_to_buddy_tab(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\">"
            "<widget class=\"QLabel\" name=\"nameLabel\"/>"
            "<widget class=\"QLineEdit\" name=\"lineEdit\"/>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.set_mode("buddy") is True
    assert surface._inspector_tabs.tabText(surface._inspector_tabs.currentIndex()) == "Buddy"  # type: ignore[attr-defined]


def test_editor_surface_buddy_assignment_is_undoable(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\">"
            "<widget class=\"QLabel\" name=\"nameLabel\"/>"
            "<widget class=\"QLineEdit\" name=\"lineEdit\"/>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )
    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.model is not None
    surface._handle_buddy_assignment_changed("nameLabel", "lineEdit")  # type: ignore[attr-defined]
    label = surface.model.root_widget.find_by_object_name("nameLabel")
    assert label is not None
    assert label.properties["buddy"].value == "lineEdit"
    assert surface.can_undo is True
    assert surface.undo() is True
    label_after_undo = surface.model.root_widget.find_by_object_name("nameLabel")
    assert label_after_undo is not None
    assert "buddy" not in label_after_undo.properties


def test_editor_surface_buddy_mode_selection_gesture_assigns_buddy(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\">"
            "<widget class=\"QLabel\" name=\"nameLabel\"/>"
            "<widget class=\"QLineEdit\" name=\"lineEdit\"/>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )
    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.model is not None
    assert surface.set_mode("buddy") is True
    surface._selection_controller.set_selected_object_name("nameLabel")  # type: ignore[attr-defined]
    surface._selection_controller.set_selected_object_name("lineEdit")  # type: ignore[attr-defined]
    label = surface.model.root_widget.find_by_object_name("nameLabel")
    assert label is not None
    assert label.properties["buddy"].value == "lineEdit"


def test_editor_surface_promote_selected_widget_updates_custom_widget_metadata(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\">"
            "<widget class=\"QPushButton\" name=\"pushButton\"/>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )
    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.model is not None
    surface._selection_controller.set_selected_object_name("pushButton")  # type: ignore[attr-defined]

    assert surface.promote_selected_widget("FancyButton", "fancy_button") is True
    promoted_widget = surface.model.root_widget.find_by_object_name("pushButton")
    assert promoted_widget is not None
    assert promoted_widget.class_name == "FancyButton"
    assert len(surface.model.custom_widgets) == 1
    assert surface.model.custom_widgets[0].class_name == "FancyButton"
    assert surface.can_undo is True
    assert surface.undo() is True
    restored_widget = surface.model.root_widget.find_by_object_name("pushButton")
    assert restored_widget is not None
    assert restored_widget.class_name == "QPushButton"


def test_editor_surface_format_ui_model_normalizes_disk_xml(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class><widget class=\"QWidget\" name=\"SampleForm\"/>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )
    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.format_ui_model() is True
    assert surface.is_dirty is True


def test_editor_surface_save_and_insert_component(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\">"
            "<widget class=\"QPushButton\" name=\"pushButton\"/>"
            "<widget class=\"QGroupBox\" name=\"targetGroup\"/>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )
    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.model is not None
    surface._selection_controller.set_selected_object_name("pushButton")  # type: ignore[attr-defined]
    assert surface.save_selected_widget_as_component("ButtonPart") is True
    assert "ButtonPart" in surface.available_component_names()

    surface._selection_controller.set_selected_object_name("targetGroup")  # type: ignore[attr-defined]
    assert surface.insert_component("ButtonPart") is True
    target = surface.model.root_widget.find_by_object_name("targetGroup")
    assert target is not None
    assert any(child.class_name == "QPushButton" for child in target.children)
    assert any(child.object_name == "pushButton1" for child in target.children)


def test_editor_surface_duplicate_selection_creates_renamed_copy(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\">"
            "<widget class=\"QPushButton\" name=\"pushButton\"/>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )
    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.model is not None
    surface._selection_controller.set_selected_object_name("pushButton")  # type: ignore[attr-defined]
    assert surface.duplicate_selection() is True
    duplicated = surface.model.root_widget.find_by_object_name("pushButton1")
    assert duplicated is not None
    assert duplicated.class_name == "QPushButton"


def test_editor_surface_copy_cut_paste_selection_workflow(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\">"
            "<widget class=\"QPushButton\" name=\"pushButton\"/>"
            "<widget class=\"QGroupBox\" name=\"targetGroup\"/>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )
    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.model is not None

    surface._selection_controller.set_selected_object_name("pushButton")  # type: ignore[attr-defined]
    assert surface.copy_selection() is True
    clipboard_text = QApplication.clipboard().text()
    assert "<class>ClipboardPayload</class>" in clipboard_text
    assert "pushButton" in clipboard_text

    surface._selection_controller.set_selected_object_name("targetGroup")  # type: ignore[attr-defined]
    assert surface.paste_selection() is True
    target = surface.model.root_widget.find_by_object_name("targetGroup")
    assert target is not None
    assert any(child.object_name == "pushButton1" for child in target.children)

    surface._selection_controller.set_selected_object_name("pushButton")  # type: ignore[attr-defined]
    assert surface.cut_selection() is True
    assert surface.model.root_widget.find_by_object_name("pushButton") is None
    assert surface.undo() is True
    assert surface.model.root_widget.find_by_object_name("pushButton") is not None


def test_editor_surface_paste_rejects_invalid_parent(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\">"
            "<widget class=\"QPushButton\" name=\"pushButton\"/>"
            "<widget class=\"QLineEdit\" name=\"lineEdit\"/>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )
    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.model is not None

    surface._selection_controller.set_selected_object_name("pushButton")  # type: ignore[attr-defined]
    assert surface.copy_selection() is True
    surface._selection_controller.set_selected_object_name("lineEdit")  # type: ignore[attr-defined]
    assert surface.paste_selection() is False
    assert "does not accept widgets" in surface._error_label.text().lower()  # type: ignore[attr-defined]


def test_editor_surface_action_panel_mutations_are_undoable(tmp_path: Path) -> None:
    ui_file = tmp_path / "actions.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>MainWindow</class>"
            "<widget class=\"QMainWindow\" name=\"MainWindow\">"
            "<widget class=\"QWidget\" name=\"centralWidget\"/>"
            "<widget class=\"QMenuBar\" name=\"menuBar\"/>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )
    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.model is not None

    panel = surface._action_editor_panel  # type: ignore[attr-defined]
    panel.add_action_requested.emit("actionOpen")
    panel.add_group_requested.emit("fileGroup")
    panel.action_group_changed.emit("actionOpen", "fileGroup")
    panel.placement_add_action_requested.emit("menuBar", "actionOpen")

    assert [action.name for action in surface.model.actions] == ["actionOpen"]
    assert [group.name for group in surface.model.action_groups] == ["fileGroup"]
    assert [ref.name for ref in surface.model.action_groups[0].add_actions] == ["actionOpen"]
    menu_bar = surface.model.root_widget.find_by_object_name("menuBar")
    assert menu_bar is not None
    assert [ref.name for ref in menu_bar.add_actions] == ["actionOpen"]

    assert surface.undo() is True
    menu_bar_after_undo = surface.model.root_widget.find_by_object_name("menuBar")  # type: ignore[union-attr]
    assert menu_bar_after_undo is not None
    assert [ref.name for ref in menu_bar_after_undo.add_actions] == []

    assert surface.redo() is True
    menu_bar_after_redo = surface.model.root_widget.find_by_object_name("menuBar")  # type: ignore[union-attr]
    assert menu_bar_after_redo is not None
    assert [ref.name for ref in menu_bar_after_redo.add_actions] == ["actionOpen"]


def test_editor_surface_align_distribute_adjust_size_and_text_edit_mutations(tmp_path: Path) -> None:
    ui_file = tmp_path / "affordances.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>Form</class>"
            "<widget class=\"QWidget\" name=\"Form\">"
            "<widget class=\"QPushButton\" name=\"pushButton\">"
            "<property name=\"text\"><string>One</string></property>"
            "<property name=\"geometry\"><rect><x>16</x><y>16</y><width>120</width><height>32</height></rect></property>"
            "</widget>"
            "<widget class=\"QLabel\" name=\"label\">"
            "<property name=\"text\"><string>Two</string></property>"
            "<property name=\"geometry\"><rect><x>200</x><y>64</y><width>120</width><height>32</height></rect></property>"
            "</widget>"
            "<widget class=\"QLineEdit\" name=\"lineEdit\">"
            "<property name=\"placeholderText\"><string>Three</string></property>"
            "<property name=\"geometry\"><rect><x>300</x><y>80</y><width>200</width><height>32</height></rect></property>"
            "</widget>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )
    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.model is not None

    surface._selection_controller.set_selected_object_names(["pushButton", "label"])  # type: ignore[attr-defined]
    assert surface.align_selection("left") is True
    push_button = surface.model.root_widget.find_by_object_name("pushButton")
    label = surface.model.root_widget.find_by_object_name("label")
    assert push_button is not None and label is not None
    assert push_button.properties["geometry"].value["x"] == label.properties["geometry"].value["x"]

    surface._selection_controller.set_selected_object_names(["pushButton", "label", "lineEdit"])  # type: ignore[attr-defined]
    assert surface.distribute_selection("vertical") is True
    y_positions = [
        int(surface.model.root_widget.find_by_object_name(name).properties["geometry"].value["y"])  # type: ignore[union-attr]
        for name in ("pushButton", "label", "lineEdit")
    ]
    assert y_positions[0] < y_positions[1] < y_positions[2]

    surface._selection_controller.set_selected_object_names(["lineEdit"])  # type: ignore[attr-defined]
    assert surface.adjust_size_for_selection() is True
    line_edit = surface.model.root_widget.find_by_object_name("lineEdit")
    assert line_edit is not None
    assert line_edit.properties["geometry"].value["width"] == 120
    assert line_edit.properties["geometry"].value["height"] == 32

    surface._selection_controller.set_selected_object_names(["pushButton", "label"])  # type: ignore[attr-defined]
    assert surface.edit_text_for_selection("Renamed") is True
    push_button = surface.model.root_widget.find_by_object_name("pushButton")
    label = surface.model.root_widget.find_by_object_name("label")
    assert push_button is not None and label is not None
    assert push_button.properties["text"].value == "Renamed"
    assert label.properties["text"].value == "Renamed"


def test_editor_surface_canvas_context_action_dispatches_core_commands(tmp_path: Path) -> None:
    ui_file = tmp_path / "context.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>Form</class>"
            "<widget class=\"QWidget\" name=\"Form\">"
            "<widget class=\"QPushButton\" name=\"pushButton\">"
            "<property name=\"text\"><string>One</string></property>"
            "<property name=\"geometry\"><rect><x>16</x><y>16</y><width>120</width><height>32</height></rect></property>"
            "</widget>"
            "<widget class=\"QLabel\" name=\"label\">"
            "<property name=\"text\"><string>Two</string></property>"
            "<property name=\"geometry\"><rect><x>200</x><y>48</y><width>120</width><height>32</height></rect></property>"
            "</widget>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )
    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.model is not None
    surface._selection_controller.set_selected_object_names(["pushButton", "label"])  # type: ignore[attr-defined]

    surface._handle_canvas_context_action("designer.canvas.context.align_left")  # type: ignore[attr-defined]
    push_button = surface.model.root_widget.find_by_object_name("pushButton")
    label = surface.model.root_widget.find_by_object_name("label")
    assert push_button is not None and label is not None
    assert push_button.properties["geometry"].value["x"] == label.properties["geometry"].value["x"]

    surface._handle_canvas_context_action("designer.canvas.context.adjust_size")  # type: ignore[attr-defined]
    assert push_button.properties["geometry"].value["width"] == 120
    assert label.properties["geometry"].value["height"] == 32


def test_editor_surface_preview_uses_isolated_mode_for_promoted_custom_widgets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\">"
            "<widget class=\"FancyWidget\" name=\"fancyWidget\"/>"
            "</widget>"
            "<customwidgets><customwidget><class>FancyWidget</class><extends>QWidget</extends>"
            "<header>fancy_widget</header></customwidget></customwidgets>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )
    surface = DesignerEditorSurface(str(ui_file.resolve()))
    monkeypatch.setattr(
        "app.designer.editor_surface.probe_ui_xml_compatibility_isolated",
        lambda *args, **kwargs: PreviewCompatibilityResult(
            is_compatible=True,
            message="isolated ok",
        ),
    )
    assert surface.preview_current_form() is True
    assert "isolated runner preview mode" in surface._error_label.text().lower()  # type: ignore[attr-defined]
    assert "passed in isolated preview mode" in surface.run_compatibility_check().lower()


def test_editor_surface_preview_retains_active_widget_reference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>PreviewForm</class>"
            "<widget class=\"QWidget\" name=\"PreviewForm\"/>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    surface = DesignerEditorSurface(str(ui_file.resolve()))
    shown: list[bool] = []

    class _PreviewWidgetProxy:
        def __init__(self) -> None:
            self.destroyed = surface.destroyed  # pragma: no cover - signal plumbing only

        def setAttribute(self, *_args, **_kwargs) -> None:
            return None

        def setWindowTitle(self, *_args, **_kwargs) -> None:
            return None

        def show(self) -> None:
            shown.append(True)

        def close(self) -> None:
            return None

        def deleteLater(self) -> None:
            return None

    preview_widget = _PreviewWidgetProxy()
    monkeypatch.setattr("app.designer.editor_surface.load_widget_from_ui_xml", lambda _xml: preview_widget)

    assert surface.preview_current_form() is True
    assert shown == [True]
    assert surface._active_preview_widget is preview_widget  # type: ignore[attr-defined]


def test_editor_surface_preview_variant_applies_style_and_window_title(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>PreviewForm</class>"
            "<widget class=\"QWidget\" name=\"PreviewForm\"/>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    surface = DesignerEditorSurface(str(ui_file.resolve()))
    seen_kwargs: dict[str, object] = {}

    class _PreviewWidgetProxy:
        def __init__(self) -> None:
            self.destroyed = surface.destroyed  # pragma: no cover - signal plumbing only

        def setAttribute(self, *_args, **_kwargs) -> None:
            return None

        def setWindowTitle(self, *_args, **_kwargs) -> None:
            return None

        def show(self) -> None:
            return None

        def close(self) -> None:
            return None

        def deleteLater(self) -> None:
            return None

    preview_widget = _PreviewWidgetProxy()
    monkeypatch.setattr("app.designer.editor_surface.load_widget_from_ui_xml", lambda _xml: preview_widget)

    def _fake_configure(widget, **kwargs):  # type: ignore[no-untyped-def]
        seen_kwargs.update(kwargs)
        return widget

    monkeypatch.setattr("app.designer.editor_surface.configure_preview_widget", _fake_configure)

    assert surface.preview_current_form_variant("fusion") is True
    assert surface.active_preview_variant_id == "fusion"
    assert seen_kwargs["style_name"] == "Fusion"
    assert seen_kwargs["viewport_size"] is None
    assert "Fusion Style" in str(seen_kwargs["window_title"])
