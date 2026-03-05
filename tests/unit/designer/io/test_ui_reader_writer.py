"""Unit tests for Designer `.ui` reader/writer subset."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.designer.io import read_ui_file, read_ui_string, write_ui_file, write_ui_string

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
