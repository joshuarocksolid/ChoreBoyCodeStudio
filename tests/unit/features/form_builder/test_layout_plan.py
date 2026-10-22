"""Breakpoints follow the tab content size."""

from __future__ import annotations

import pytest

from app.features.form_builder.integration.layout import WorkbenchMemory, plan_workbench

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("width", "height", "density", "short", "compact_toolbar", "left_docked", "inspector_docked"),
    [
        (1280, 800, "wide", False, False, True, True),
        (1080, 600, "compact", False, False, True, True),
        (800, 600, "rail", False, True, False, True),
        (700, 500, "drawer", True, True, False, False),
        (1080, 420, "compact", True, False, True, True),
    ],
)
def test_breakpoint(
    width: int,
    height: int,
    density: str,
    short: bool,
    compact_toolbar: bool,
    left_docked: bool,
    inspector_docked: bool,
) -> None:
    plan = plan_workbench(width, height, WorkbenchMemory())
    assert plan.density == density
    assert plan.short is short
    assert plan.toolbar_compact is compact_toolbar
    assert plan.left_docked is left_docked
    assert plan.inspector_docked is inspector_docked
    assert plan.stack_left is short


def test_pin_keeps_the_left_pane_docked_on_a_rail() -> None:
    plan = plan_workbench(800, 600, WorkbenchMemory(pin_left=True))
    assert plan.density == "rail"
    assert plan.left_docked is True
    assert plan.left_width >= 184
