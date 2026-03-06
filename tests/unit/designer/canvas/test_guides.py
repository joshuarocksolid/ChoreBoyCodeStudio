"""Unit tests for canvas guide snapping helpers."""

from __future__ import annotations

import pytest

from app.designer.canvas import default_snapped_geometry, snap_to_grid

pytestmark = pytest.mark.unit


def test_snap_to_grid_rounds_down_to_multiple() -> None:
    assert snap_to_grid(23, 8) == 16
    assert snap_to_grid(24, 8) == 24


def test_default_snapped_geometry_uses_container_defaults() -> None:
    geometry = default_snapped_geometry(insert_index=2, grid_size=8, class_name="QGroupBox")
    assert geometry["x"] % 8 == 0
    assert geometry["y"] % 8 == 0
    assert geometry["width"] == 220
    assert geometry["height"] == 140
