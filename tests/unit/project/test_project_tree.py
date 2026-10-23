"""Unit tests for project tree model helpers."""

from app.core.models import ProjectFileEntry
from app.project.project_tree import build_project_tree

import pytest

pytestmark = pytest.mark.unit


def test_build_project_tree_creates_hierarchy_with_stable_sorting() -> None:
    """Tree should nest children and sort directories before files."""
    entries = [
        ProjectFileEntry("run.py", "/tmp/project/run.py", False),
        ProjectFileEntry("app/main.py", "/tmp/project/app/main.py", False),
        ProjectFileEntry("app", "/tmp/project/app", True),
        ProjectFileEntry("README.md", "/tmp/project/README.md", False),
        ProjectFileEntry("app/utils", "/tmp/project/app/utils", True),
        ProjectFileEntry("app/utils/helpers.py", "/tmp/project/app/utils/helpers.py", False),
    ]

    root_nodes = build_project_tree(entries)
    assert [node.relative_path for node in root_nodes] == ["app", "README.md", "run.py"]

    app_node = root_nodes[0]
    assert [child.relative_path for child in app_node.children] == ["app/utils", "app/main.py"]
    utils_node = app_node.children[0]
    assert [child.relative_path for child in utils_node.children] == ["app/utils/helpers.py"]


def test_build_project_tree_creates_missing_parent_directories_for_files() -> None:
    """File-only entries should still produce synthetic parent directories."""
    entries = [
        ProjectFileEntry("src/pkg/module.py", "/tmp/project/src/pkg/module.py", False),
    ]

    root_nodes = build_project_tree(entries)
    assert [node.relative_path for node in root_nodes] == ["src"]
    assert [child.relative_path for child in root_nodes[0].children] == ["src/pkg"]
    assert [child.relative_path for child in root_nodes[0].children[0].children] == ["src/pkg/module.py"]


def test_a_generated_file_sorts_immediately_after_its_source() -> None:
    entries = [
        ProjectFileEntry("forms/zzz.py", "/tmp/project/forms/zzz.py", False),
        ProjectFileEntry("forms/ui_invoice.py", "/tmp/project/forms/ui_invoice.py", False),
        ProjectFileEntry("forms/invoice.ui", "/tmp/project/forms/invoice.ui", False),
        ProjectFileEntry("forms/icons_rc.py", "/tmp/project/forms/icons_rc.py", False),
        ProjectFileEntry("forms/icons.qrc", "/tmp/project/forms/icons.qrc", False),
        ProjectFileEntry("forms/aaa.py", "/tmp/project/forms/aaa.py", False),
        ProjectFileEntry("forms", "/tmp/project/forms", True),
    ]

    forms = build_project_tree(entries)[0]
    assert [child.name for child in forms.children] == [
        "aaa.py",
        "icons.qrc",
        "icons_rc.py",
        "invoice.ui",
        "ui_invoice.py",
        "zzz.py",
    ]
