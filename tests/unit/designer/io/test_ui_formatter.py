"""Unit tests for deterministic `.ui` formatter helper."""

from __future__ import annotations

import pytest

from app.designer.io import format_ui_xml

pytestmark = pytest.mark.unit


def test_format_ui_xml_normalizes_minified_source() -> None:
    source = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<ui version=\"4.0\"><class>Form</class><widget class=\"QWidget\" name=\"Form\"/>"
        "<resources/><connections/></ui>\n"
    )
    formatted = format_ui_xml(source)
    assert formatted.startswith("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<ui")
    assert "\n <class>Form</class>" in formatted


def test_format_ui_xml_is_deterministic() -> None:
    source = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<ui version=\"4.0\"><class>Form</class><widget class=\"QWidget\" name=\"Form\"/>"
        "<resources/><connections/></ui>\n"
    )
    once = format_ui_xml(source)
    twice = format_ui_xml(once)
    assert once == twice


def test_format_ui_xml_preserves_action_related_nodes() -> None:
    source = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<ui version=\"4.0\">"
        "<class>MainWindow</class>"
        "<widget class=\"QMainWindow\" name=\"MainWindow\">"
        "<widget class=\"QWidget\" name=\"centralWidget\"/>"
        "<action name=\"actionOpen\"/>"
        "<zorder>centralWidget</zorder>"
        "<addaction name=\"actionOpen\"/>"
        "</widget>"
        "<actiongroup name=\"fileActions\">"
        "<property name=\"text\"><string>File Actions</string></property>"
        "</actiongroup>"
        "<buttongroups><buttongroup name=\"choiceGroup\"/></buttongroups>"
        "<resources/><connections/></ui>\n"
    )
    formatted = format_ui_xml(source)
    assert "<action name=\"actionOpen\"" in formatted
    assert "<actiongroup name=\"fileActions\"" in formatted
    assert "<addaction name=\"actionOpen\"" in formatted
    assert "<zorder>centralWidget</zorder>" in formatted
    assert "<buttongroup name=\"choiceGroup\"" in formatted
