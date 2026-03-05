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
            "<connections><connection><sender>pushButton</sender><signal>clicked()</signal>"
            "<receiver>SampleForm</receiver><slot>accept()</slot></connection></connections>"
            "</ui>\n"
        ),
        encoding="utf-8",
    )

    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.model is not None
    surface._handle_connection_edited(0, "slot", "reject()")  # type: ignore[attr-defined]
    assert surface.model.connections[0].slot == "reject()"
    assert surface.can_undo is True
    assert surface.undo() is True
    assert surface.model.connections[0].slot == "accept()"


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
    assert surface._inspector_tabs.tabText(surface._inspector_tabs.currentIndex()) == "Connections"  # type: ignore[attr-defined]


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
    assert surface._inspector_tabs.tabText(surface._inspector_tabs.currentIndex()) == "Tab Order"  # type: ignore[attr-defined]


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
    assert surface._inspector_tabs.tabText(surface._inspector_tabs.currentIndex()) == "Buddies"  # type: ignore[attr-defined]


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
