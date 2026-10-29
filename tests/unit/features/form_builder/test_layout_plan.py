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


def test_the_code_split_narrows_then_rails_the_outline_then_the_inspector() -> None:
    from app.features.form_builder.integration.layout import BesideFit, fit_beside

    # Wide row: 45 %, both panes stay.
    assert fit_beside(1200, 6) == BesideFit(540)
    # Narrow: never less than 300 px of code, and the canvas keeps 360 px.
    assert fit_beside(666, 6) == BesideFit(300)
    # A 1366 px ChoreBoy screen (canvas row ~520): the Outline goes to its rail.
    assert fit_beside(520, 6, left_gain=164, right_gain=236) == BesideFit(307, rail_left=True)
    # Still short: the inspector follows.
    assert fit_beside(400, 6, left_gain=164, right_gain=236) == BesideFit(360, rail_left=True, rail_right=True)
    # Nothing left to give: refused.
    assert fit_beside(600, 6) is None
