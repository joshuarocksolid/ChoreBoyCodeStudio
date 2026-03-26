"""Unit tests for designer widget palette registry."""

from __future__ import annotations

import pytest

from app.designer.palette import default_widget_palette_registry

pytestmark = pytest.mark.unit


def test_default_palette_registry_includes_d1_baseline_widgets() -> None:
    registry = default_widget_palette_registry()
    class_names = {item.class_name for item in registry.list_all()}

    assert "QTabWidget" in class_names
    assert "QScrollArea" in class_names
    assert "QLineEdit" in class_names
    assert "QPushButton" in class_names
    assert "QSpacerItem" in class_names


def test_default_palette_registry_includes_tranche1_must_have_widgets() -> None:
    registry = default_widget_palette_registry()
    class_names = {item.class_name for item in registry.list_all()}

    expected = {
        "QSpinBox",
        "QDoubleSpinBox",
        "QSlider",
        "QProgressBar",
        "QDateEdit",
        "QTimeEdit",
        "QDateTimeEdit",
        "QDial",
        "QToolButton",
        "QDialogButtonBox",
    }
    assert expected.issubset(class_names)


def test_palette_registry_groups_items_by_category() -> None:
    registry = default_widget_palette_registry()
    containers = registry.list_by_category("Containers")
    inputs = registry.list_by_category("Inputs")
    display = registry.list_by_category("Display")
    numeric_inputs = registry.list_by_category("Numeric Inputs")
    date_time_inputs = registry.list_by_category("Date/Time Inputs")
    layout_items = registry.list_by_category("Layout Items")

    assert {item.class_name for item in containers} >= {"QWidget", "QTabWidget", "QScrollArea"}
    assert {item.class_name for item in inputs} >= {"QLineEdit", "QTextEdit"}
    assert {item.class_name for item in display} == {"QLabel"}
    assert {item.class_name for item in numeric_inputs} >= {"QSpinBox", "QDoubleSpinBox", "QSlider", "QDial"}
    assert {item.class_name for item in date_time_inputs} == {"QDateEdit", "QTimeEdit", "QDateTimeEdit"}
    assert {item.class_name for item in layout_items} == {"QSpacerItem"}


def test_palette_registry_lookup_returns_metadata() -> None:
    registry = default_widget_palette_registry()
    definition = registry.lookup("QSpacerItem")
    assert definition is not None
    assert definition.is_layout_item is True
    assert definition.default_object_name_prefix == "spacerItem"
