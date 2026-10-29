"""Allowed sides reads "All sides" or the side names, never "Dock widget area"."""

from __future__ import annotations

import pytest

from app.features.form_builder.qtside.inspector.editors._enum_words import dock_area_summary

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("names", "expected"),
    (
        (
            (
                "LeftDockWidgetArea",
                "RightDockWidgetArea",
                "TopDockWidgetArea",
                "BottomDockWidgetArea",
            ),
            "All sides",
        ),
        (("AllDockWidgetAreas",), "All sides"),
        (("RightDockWidgetArea", "LeftDockWidgetArea"), "Left, Right"),
        (("BottomDockWidgetArea",), "Bottom"),
        (("NoDockWidgetArea",), "None"),
        ((), "None"),
    ),
)
def test_dock_area_summary(names: tuple, expected: str) -> None:
    assert dock_area_summary(names) == expected
