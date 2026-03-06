"""Unit tests for project tree presenter view models."""

from __future__ import annotations

import pytest

from app.project.project_tree import ProjectTreeNode
from app.project.project_tree_presenter import build_project_tree_display

pytestmark = pytest.mark.unit


def test_build_project_tree_display_adds_directory_label_suffix() -> None:
    root = ProjectTreeNode(
        name="app",
        relative_path="app",
        absolute_path="/tmp/project/app",
        is_directory=True,
        children=[
            ProjectTreeNode(
                name="main.py",
                relative_path="app/main.py",
                absolute_path="/tmp/project/app/main.py",
                is_directory=False,
            )
        ],
    )

    display_nodes = build_project_tree_display([root])

    assert display_nodes[0].display_label == "app/"
    assert display_nodes[0].children[0].display_label == "main.py"
