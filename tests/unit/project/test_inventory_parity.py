"""Parity tests comparing inventory scopes across tree/search/python surfaces."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.project.file_inventory import (
    InventoryScope,
    iter_project_entries,
    iter_python_files,
    iter_text_file_paths,
)
from tests.unit.project.inventory_parity_fixtures import (
    InventoryParityFixture,
    build_fixture_tree,
)

pytestmark = pytest.mark.unit


def test_inventory_parity_fixtures_build_expected_trees(tmp_path: Path) -> None:
    for fixture_name in ("flat_layout", "src_layout", "vendor", "cbcs_metadata"):
        root = tmp_path / fixture_name
        root.mkdir()
        build_fixture_tree(root, fixture_name)
        assert list(root.iterdir()), f"fixture {fixture_name} should not be empty"


def test_slash_pattern_excluded_consistently_from_tree_and_search(tmp_path: Path) -> None:
    build_fixture_tree(tmp_path, "slash_exclude")
    fixture = InventoryParityFixture(
        name="slash_exclude",
        exclude_patterns=("src/generated/*",),
    )

    tree_python = {
        entry.relative_path
        for entry in iter_project_entries(tmp_path, exclude_patterns=fixture.exclude_patterns)
        if entry.relative_path.endswith(".py")
    }
    search_files = {
        rel
        for _absolute, rel in iter_text_file_paths(
            tmp_path,
            exclude_patterns=fixture.exclude_patterns,
        )
        if rel.endswith(".py")
    }
    analysis_python = {
        path.relative_to(tmp_path).as_posix()
        for path in iter_python_files(tmp_path, exclude_patterns=fixture.exclude_patterns)
    }

    assert tree_python == search_files == analysis_python
    assert "src/generated/code.py" not in tree_python


@pytest.mark.parametrize(
    "fixture_name",
    ("cbcs_metadata", "vendor"),
)
def test_cbcs_vendor_policy_matrix(tmp_path: Path, fixture_name: str) -> None:
    if fixture_name == "cbcs_metadata":
        build_fixture_tree(tmp_path, fixture_name)
        cbcs_entries = {entry.relative_path for entry in iter_project_entries(tmp_path)}
        assert "cbcs/package.json" in cbcs_entries
        assert "cbcs/runs/run.log" in cbcs_entries
        return

    build_fixture_tree(tmp_path, "vendor")
    vendor_python = {
        path.relative_to(tmp_path).as_posix()
        for path in iter_python_files(tmp_path, extra_top_level_skips=("vendor",))
    }
    assert "vendor/pkg.py" not in vendor_python
    assert "main.py" in vendor_python


def test_search_glob_equivalent_to_exclude_pattern(tmp_path: Path) -> None:
    from app.editors.search_panel import SearchOptions, find_in_files

    build_fixture_tree(tmp_path, "slash_exclude")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "out.py").write_text("# out\n", encoding="utf-8")

    pattern_files = {
        rel
        for _absolute, rel in iter_text_file_paths(
            tmp_path,
            exclude_patterns=("build",),
        )
    }
    glob_results = find_in_files(
        tmp_path,
        "out",
        options=SearchOptions(exclude_globs=["build/**"]),
        exclude_patterns=["build"],
    )

    assert "build/out.py" not in pattern_files
    assert glob_results == []


def test_inventory_scope_enum_documents_surfaces() -> None:
    assert InventoryScope.tree_entries.value == "tree_entries"
    assert InventoryScope.python_analysis.value == "python_analysis"
    assert InventoryScope.text_search.value == "text_search"
    assert InventoryScope.packaging_payload.value == "packaging_payload"
    assert InventoryScope.packaging_audit.value == "packaging_audit"
