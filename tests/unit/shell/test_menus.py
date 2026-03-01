"""Unit tests for shell menu helper logic."""

import pytest

from app.shell.menus import build_recent_project_menu_items

pytestmark = pytest.mark.unit


def test_build_recent_project_menu_items_dedupes_and_preserves_order() -> None:
    """Recent menu items should dedupe without reordering first appearances."""
    items = build_recent_project_menu_items(
        [
            "/tmp/projects/alpha",
            "/tmp/projects/beta",
            "/tmp/projects/alpha",
            "   ",
            "/tmp/projects/gamma",
        ]
    )

    assert [item.project_path for item in items] == [
        "/tmp/projects/alpha",
        "/tmp/projects/beta",
        "/tmp/projects/gamma",
    ]


def test_build_recent_project_menu_items_uses_leaf_name_for_display_prefix() -> None:
    """Display text should include leaf name and full project path."""
    items = build_recent_project_menu_items(["/tmp/projects/my_project"])

    assert len(items) == 1
    assert items[0].display_text == "my_project — /tmp/projects/my_project"
