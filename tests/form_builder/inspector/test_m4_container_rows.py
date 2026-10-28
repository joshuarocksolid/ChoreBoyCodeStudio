"""Container rows are registered for their classes only (UX-CONT-010, 013, 014, 015)."""

from __future__ import annotations

import pytest

from app.features.form_builder.qtside.inspector.editors import default_catalog

pytestmark = pytest.mark.unit


def _keys(catalog, cls: str) -> set:
    return {row.key for row in catalog.rows() if not row.classes or cls in row.classes}


def test_scroll_area_rows_are_for_scroll_areas_only() -> None:
    catalog = default_catalog()
    keys = _keys(catalog, "QScrollArea")
    assert {"widgetResizable", "horizontalScrollBarPolicy", "verticalScrollBarPolicy"} <= keys
    assert "widgetResizable" not in _keys(catalog, "QWidget")


def test_wizard_step_rows_are_for_wizard_pages_only() -> None:
    catalog = default_catalog()
    rows = {row.key: row for row in catalog.rows()}
    assert rows["stepTitle"].label == "Step title"
    assert rows["stepSubtitle"].label == "Step subtitle"
    assert rows["stepTitle"].classes == ("QWizardPage",)
    assert "stepTitle" not in _keys(catalog, "QWidget")


def test_group_box_and_frame_rows_have_the_spec_labels() -> None:
    rows = {row.key: row for row in default_catalog().rows()}
    assert rows["checkable"].label == "Can be switched off"
    assert rows["checkable"].classes == ("QGroupBox",)
    assert rows["frameShadow"].label == "Shadow"
    assert rows["lineWidth"].label == "Line width"
    assert rows["midLineWidth"].label == "Middle line width"
