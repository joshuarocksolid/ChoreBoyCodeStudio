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
