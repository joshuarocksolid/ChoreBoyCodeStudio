"""Unit tests for project import layout resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.models import ProjectMetadata
from app.project.file_inventory import build_project_inventory_snapshot
from app.intelligence.diagnostics_service import analyze_python_file, find_unresolved_imports
from app.intelligence.import_resolver import resolve_project_import
from app.project.import_layout import (
    detect_suggested_source_root,
    resolve_project_import_layout,
)

pytestmark = pytest.mark.unit


def test_resolve_project_import_layout_auto_detects_src_without_init(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    package_dir = project_root / "src" / "my_pkg"
    package_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "util.py").write_text("VALUE = 1\n", encoding="utf-8")
    (project_root / "main.py").write_text("import my_pkg.util\n", encoding="utf-8")

    layout = resolve_project_import_layout(project_root)
    resolution = resolve_project_import(str(project_root), "my_pkg.util", layout=layout)

    assert tuple(path.name for path in layout.source_roots) == ("src",)
    assert resolution.is_resolved is True


def test_resolve_project_import_layout_skips_src_when_init_present(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    src_dir = project_root / "src"
    src_dir.mkdir()
    (src_dir / "__init__.py").write_text("", encoding="utf-8")
    (src_dir / "module.py").write_text("x = 1\n", encoding="utf-8")

    layout = resolve_project_import_layout(project_root)

    assert layout.source_roots == ()


def test_manifest_empty_source_roots_skips_auto_detect(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    src_dir = project_root / "src" / "pkg"
    src_dir.mkdir(parents=True)
    (src_dir / "__init__.py").write_text("", encoding="utf-8")
    metadata = ProjectMetadata(schema_version=2, name="demo", source_roots=[])

    layout = resolve_project_import_layout(project_root, metadata)

    assert layout.source_roots == ()


def test_manifest_source_roots_override_auto_detect(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    lib_dir = project_root / "lib" / "pkg"
    lib_dir.mkdir(parents=True)
    (lib_dir / "__init__.py").write_text("", encoding="utf-8")
    (project_root / "src").mkdir()
    metadata = ProjectMetadata(schema_version=2, name="demo", source_roots=["lib"])

    layout = resolve_project_import_layout(project_root, metadata)

    assert len(layout.source_roots) == 1
    assert layout.source_roots[0].name == "lib"


def test_analyze_python_file_resolves_src_layout_import(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    package_dir = project_root / "src" / "my_pkg"
    package_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    file_path = project_root / "main.py"
    file_path.write_text("import my_pkg\n", encoding="utf-8")

    diagnostics = analyze_python_file(
        str(file_path),
        project_root=str(project_root),
        known_runtime_modules=frozenset(),
    )
    py200 = [item for item in diagnostics if item.code == "PY200"]

    assert py200 == []


def test_find_unresolved_imports_respects_manifest_source_roots(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    lib_pkg = project_root / "lib" / "pkg"
    lib_pkg.mkdir(parents=True)
    (lib_pkg / "__init__.py").write_text("", encoding="utf-8")
    (project_root / "main.py").write_text("import pkg\n", encoding="utf-8")
    metadata = ProjectMetadata(schema_version=2, name="demo", source_roots=["lib"])

    diagnostics = find_unresolved_imports(
        str(project_root),
        known_runtime_modules=frozenset(),
        project_metadata=metadata,
        inventory_snapshot=build_project_inventory_snapshot(str(project_root)),
    )

    assert diagnostics == []


def test_detect_suggested_source_root_returns_src_for_src_layout(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    (project_root / "src" / "pkg").mkdir(parents=True)
    (project_root / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")

    assert detect_suggested_source_root(project_root) == "src"


def test_runtime_sys_path_entries_deduplicates_by_resolved_path(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    src_dir = project_root / "src"
    src_dir.mkdir(parents=True)
    layout = resolve_project_import_layout(project_root)

    duplicate_layout = resolve_project_import_layout(project_root)
    duplicate_layout = type(duplicate_layout)(
        project_root=duplicate_layout.project_root,
        source_roots=(src_dir, src_dir.resolve()),
        vendor_root=duplicate_layout.vendor_root,
    )

    entries = duplicate_layout.runtime_sys_path_entries
    assert len(entries) == len(set(entries))


def test_unresolved_relative_import_emits_py200(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "main.py"
    file_path.write_text("from .missing import value\n", encoding="utf-8")

    diagnostics = analyze_python_file(
        str(file_path),
        project_root=str(project_root),
        known_runtime_modules=frozenset(),
    )
    py200 = [item for item in diagnostics if item.code == "PY200"]

    assert len(py200) == 1
    assert "Unresolved import:" in py200[0].message
