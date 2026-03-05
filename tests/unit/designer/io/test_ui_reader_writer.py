"""Unit tests for Designer `.ui` reader/writer subset."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.designer.io import read_ui_file, read_ui_string, write_ui_file, write_ui_string
from app.designer.model import ConnectionModel, ResourceModel, UIModel, WidgetNode

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
