"""Unit tests for Designer `.ui` reader/writer subset."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.designer.io import read_ui_file, read_ui_string, write_ui_file, write_ui_string
from app.designer.model import ConnectionModel, CustomWidgetModel, ResourceModel, UIModel, WidgetNode

pytestmark = pytest.mark.unit

_FIXTURE_ROOT = Path(__file__).resolve().parents[3] / "fixtures" / "designer"


def test_read_ui_file_parses_minimal_fixture() -> None:
    model = read_ui_file(str((_FIXTURE_ROOT / "minimal_form.ui").resolve()))

    assert model.ui_version == "4.0"
    assert model.form_class_name == "MinimalForm"
    assert model.root_widget.class_name == "QWidget"
    assert model.root_widget.object_name == "MinimalForm"
    run_button = model.root_widget.find_by_object_name("pushButton")
    assert run_button is not None
    assert run_button.class_name == "QPushButton"


def test_read_write_round_trip_for_layout_fixture(tmp_path: Path) -> None:
    source_model = read_ui_file(str((_FIXTURE_ROOT / "layout_form.ui").resolve()))
    destination = tmp_path / "roundtrip.ui"
    write_ui_file(source_model, str(destination))
    reloaded_model = read_ui_file(str(destination))

    assert reloaded_model.form_class_name == "LayoutForm"
    assert reloaded_model.root_widget.find_by_object_name("scrollArea") is not None
    assert reloaded_model.root_widget.find_by_object_name("tabWidget") is not None


def test_write_ui_string_is_deterministic_for_unchanged_model() -> None:
    source_xml = (_FIXTURE_ROOT / "layout_form.ui").read_text(encoding="utf-8")
    model = read_ui_string(source_xml)

    serialized_once = write_ui_string(model)
    serialized_twice = write_ui_string(model)

    assert serialized_once == serialized_twice
    assert "<class>LayoutForm</class>" in serialized_once


def test_read_ui_string_parses_connections_and_resources() -> None:
    model = read_ui_string(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\">"
            "<class>ConnForm</class>"
            "<widget class=\"QWidget\" name=\"ConnForm\"/>"
            "<resources><include location=\"icons.qrc\"/></resources>"
            "<connections>"
            "<connection><sender>pushButton</sender><signal>clicked()</signal>"
            "<receiver>ConnForm</receiver><slot>accept()</slot></connection>"
            "</connections>"
            "</ui>\n"
        )
    )

    assert len(model.resources) == 1
    assert model.resources[0].location == "icons.qrc"
    assert len(model.connections) == 1
    assert model.connections[0].sender == "pushButton"
    assert model.connections[0].slot == "accept()"


def test_write_ui_string_serializes_connections_and_resources() -> None:
    model = UIModel(
        form_class_name="WriterForm",
        root_widget=WidgetNode(class_name="QWidget", object_name="WriterForm"),
        resources=[ResourceModel(location="icons.qrc")],
        connections=[
            ConnectionModel(
                sender="okButton",
                signal="clicked()",
                receiver="WriterForm",
                slot="accept()",
            )
        ],
    )

    xml = write_ui_string(model)
    reparsed = read_ui_string(xml)

    assert "resources" in xml
    assert "connections" in xml
    assert len(reparsed.resources) == 1
    assert reparsed.resources[0].location == "icons.qrc"
    assert len(reparsed.connections) == 1
    assert reparsed.connections[0].sender == "okButton"


def test_read_ui_string_parses_tab_stops() -> None:
    model = read_ui_string(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\">"
            "<class>TabStopForm</class>"
            "<widget class=\"QWidget\" name=\"TabStopForm\"/>"
            "<tabstops><tabstop>lineEdit</tabstop><tabstop>okButton</tabstop></tabstops>"
            "<resources/><connections/>"
            "</ui>\n"
        )
    )
    assert model.tab_stops == ["lineEdit", "okButton"]


def test_write_ui_string_serializes_tab_stops() -> None:
    model = UIModel(
        form_class_name="WriterForm",
        root_widget=WidgetNode(class_name="QWidget", object_name="WriterForm"),
        tab_stops=["lineEdit", "okButton"],
    )

    xml = write_ui_string(model)
    reparsed = read_ui_string(xml)

    assert "<tabstops>" in xml
    assert "<tabstop>lineEdit</tabstop>" in xml
    assert reparsed.tab_stops == ["lineEdit", "okButton"]


def test_read_write_round_trip_preserves_buddy_property() -> None:
    model = read_ui_string(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\">"
            "<class>BuddyForm</class>"
            "<widget class=\"QWidget\" name=\"BuddyForm\">"
            "<widget class=\"QLabel\" name=\"nameLabel\">"
            "<property name=\"buddy\"><cstring>lineEdit</cstring></property>"
            "</widget>"
            "<widget class=\"QLineEdit\" name=\"lineEdit\"/>"
            "</widget>"
            "<resources/><connections/>"
            "</ui>\n"
        )
    )

    serialized = write_ui_string(model)
    reparsed = read_ui_string(serialized)
    label = reparsed.root_widget.find_by_object_name("nameLabel")
    assert label is not None
    assert label.properties["buddy"].value_type == "cstring"
    assert label.properties["buddy"].value == "lineEdit"


def test_read_write_round_trip_preserves_iconset_property() -> None:
    model = read_ui_string(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\">"
            "<class>IconForm</class>"
            "<widget class=\"QWidget\" name=\"IconForm\">"
            "<widget class=\"QPushButton\" name=\"pushButton\">"
            "<property name=\"icon\"><iconset><normaloff>icons/run.png</normaloff></iconset></property>"
            "</widget>"
            "</widget>"
            "<resources/><connections/>"
            "</ui>\n"
        )
    )
    serialized = write_ui_string(model)
    reparsed = read_ui_string(serialized)
    button = reparsed.root_widget.find_by_object_name("pushButton")
    assert button is not None
    assert button.properties["icon"].value_type == "iconset"
    assert button.properties["icon"].value == "icons/run.png"


def test_read_write_round_trip_preserves_custom_widget_metadata() -> None:
    model = read_ui_string(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\">"
            "<class>PromoteForm</class>"
            "<widget class=\"QWidget\" name=\"PromoteForm\">"
            "<widget class=\"MyFancyWidget\" name=\"fancyWidget\"/>"
            "</widget>"
            "<customwidgets><customwidget><class>MyFancyWidget</class><extends>QWidget</extends>"
            "<header>my_fancy_widget</header></customwidget></customwidgets>"
            "<resources/><connections/>"
            "</ui>\n"
        )
    )
    assert len(model.custom_widgets) == 1
    assert model.custom_widgets[0].class_name == "MyFancyWidget"

    serialized = write_ui_string(model)
    reparsed = read_ui_string(serialized)
    assert len(reparsed.custom_widgets) == 1
    assert reparsed.custom_widgets[0].header == "my_fancy_widget"


def test_write_ui_string_serializes_custom_widget_metadata() -> None:
    model = UIModel(
        form_class_name="WriterForm",
        root_widget=WidgetNode(class_name="MyFancyWidget", object_name="fancyWidget"),
        custom_widgets=[
            CustomWidgetModel(
                class_name="MyFancyWidget",
                extends="QWidget",
                header="my_fancy_widget",
            )
        ],
    )

    xml = write_ui_string(model)
    assert "<customwidgets>" in xml
    assert "<class>MyFancyWidget</class>" in xml


def test_read_write_round_trip_preserves_unknown_top_level_nodes() -> None:
    source_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<ui version=\"4.0\">"
        "<class>UnknownForm</class>"
        "<widget class=\"QWidget\" name=\"UnknownForm\"/>"
        "<designerdata><value>keep-me</value></designerdata>"
        "<resources/><connections/>"
        "</ui>\n"
    )
    model = read_ui_string(source_xml)
    assert len(model.unknown_top_level_xml) == 1
    assert "designerdata" in model.unknown_top_level_xml[0]

    rewritten = write_ui_string(model)
    assert "<designerdata>" in rewritten
    assert "keep-me" in rewritten


def test_read_write_round_trip_preserves_unknown_nested_widget_nodes() -> None:
    source_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<ui version=\"4.0\">"
        "<class>UnknownNestedForm</class>"
        "<widget class=\"QWidget\" name=\"UnknownNestedForm\">"
        "<widget class=\"QPushButton\" name=\"pushButton\">"
        "<attribute name=\"customAttr\"><string>keep-this</string></attribute>"
        "</widget>"
        "</widget>"
        "<resources/><connections/>"
        "</ui>\n"
    )
    model = read_ui_string(source_xml)
    rewritten = write_ui_string(model)
    assert "<attribute name=\"customAttr\">" in rewritten
    assert "keep-this" in rewritten


def test_read_write_round_trip_preserves_unknown_property_payloads() -> None:
    source_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<ui version=\"4.0\">"
        "<class>UnknownPropertyForm</class>"
        "<widget class=\"QWidget\" name=\"UnknownPropertyForm\">"
        "<property name=\"fancyProperty\"><fancytype><value>123</value></fancytype></property>"
        "</widget>"
        "<resources/><connections/>"
        "</ui>\n"
    )
    model = read_ui_string(source_xml)
    rewritten = write_ui_string(model)
    assert "<fancytype>" in rewritten
    assert "<value>123</value>" in rewritten


def test_read_write_round_trip_preserves_grid_layout_item_attributes() -> None:
    source_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<ui version=\"4.0\">"
        "<class>GridForm</class>"
        "<widget class=\"QWidget\" name=\"GridForm\">"
        "<layout class=\"QGridLayout\" name=\"gridLayout\">"
        "<item row=\"0\" column=\"0\">"
        "<widget class=\"QLabel\" name=\"label\">"
        "<property name=\"text\"><string>Name</string></property>"
        "</widget>"
        "</item>"
        "<item row=\"1\" column=\"0\" rowspan=\"1\" colspan=\"2\" alignment=\"Qt::AlignCenter\">"
        "<widget class=\"QLineEdit\" name=\"lineEdit\"/>"
        "</item>"
        "</layout>"
        "</widget>"
        "<resources/><connections/>"
        "</ui>\n"
    )
    model = read_ui_string(source_xml)

    rewritten = write_ui_string(model)
    assert "<item row=\"0\" column=\"0\">" in rewritten
    assert "<item row=\"1\" column=\"0\" rowspan=\"1\" colspan=\"2\" alignment=\"Qt::AlignCenter\">" in rewritten

    reparsed = read_ui_string(rewritten)
    assert reparsed.root_widget.layout is not None
    assert len(reparsed.root_widget.layout.items) == 2
    assert reparsed.root_widget.layout.items[0].attributes == {"row": "0", "column": "0"}
    assert reparsed.root_widget.layout.items[1].attributes == {
        "row": "1",
        "column": "0",
        "rowspan": "1",
        "colspan": "2",
        "alignment": "Qt::AlignCenter",
    }
