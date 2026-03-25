"""Grid-snapping helpers for canvas placement ergonomics."""

from __future__ import annotations


def snap_to_grid(value: int, grid_size: int) -> int:
    """Snap integer position to nearest lower grid multiple."""
    safe_grid = max(1, int(grid_size))
    return (int(value) // safe_grid) * safe_grid


def default_snapped_geometry(*, insert_index: int, grid_size: int, class_name: str) -> dict[str, int]:
    """Generate deterministic snapped geometry for newly inserted freeform widgets."""
    base_x = 16 + insert_index * 24
    base_y = 16 + insert_index * 24
    width = 120
    height = 32
    if class_name in {"QWidget", "QFrame", "QGroupBox", "QTabWidget", "QScrollArea"}:
        width = 220
        height = 140
    return {
        "x": snap_to_grid(base_x, grid_size),
        "y": snap_to_grid(base_y, grid_size),
        "width": width,
        "height": height,
    }
