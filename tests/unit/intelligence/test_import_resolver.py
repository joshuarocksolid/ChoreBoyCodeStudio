"""Unit tests for import resolver helper."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.intelligence.import_resolver import resolve_module_binding, resolve_project_import

pytestmark = pytest.mark.unit


def test_resolve_project_import_handles_module_and_package(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "pkg").mkdir()
    (project_root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (project_root / "pkg" / "module.py").write_text("x=1\n", encoding="utf-8")

    module = resolve_project_import(str(project_root), "pkg.module")
    package = resolve_project_import(str(project_root), "pkg")
    missing = resolve_project_import(str(project_root), "missing.module")

    assert module.is_resolved is True
    assert module.resolved_path is not None and module.resolved_path.endswith("module.py")
    assert package.is_resolved is True
    assert package.resolved_path is not None and package.resolved_path.endswith("__init__.py")
    assert missing.is_resolved is False


def test_resolve_module_binding_handles_alias_and_missing_binding(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "pkg").mkdir()
    (project_root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (project_root / "pkg" / "mod.py").write_text("value = 1\n", encoding="utf-8")

    resolved = resolve_module_binding(
        str(project_root),
        bindings={"mod": "pkg.mod"},
        binding_name="mod",
    )
    missing = resolve_module_binding(
        str(project_root),
        bindings={"mod": "pkg.mod"},
        binding_name="unknown",
    )

    assert resolved.is_resolved is True
    assert resolved.resolved_path is not None and resolved.resolved_path.endswith("mod.py")
    assert missing.is_resolved is False


def test_resolve_module_binding_returns_unresolved_for_non_module_target(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "pkg").mkdir()
    (project_root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (project_root / "pkg" / "helpers.py").write_text("def helper():\n    return 1\n", encoding="utf-8")

    unresolved = resolve_module_binding(
        str(project_root),
        bindings={"helper": "pkg.helpers.helper"},
        binding_name="helper",
    )

    assert unresolved.is_resolved is False


def test_resolve_project_import_resolves_known_runtime_module(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    known = frozenset(["FreeCAD", "os", "sys"])

    resolved = resolve_project_import(str(project_root), "FreeCAD", known_runtime_modules=known)

    assert resolved.is_resolved is True
    assert resolved.resolved_path is None


def test_resolve_project_import_resolves_dotted_runtime_module(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    known = frozenset(["FreeCAD"])

    resolved = resolve_project_import(str(project_root), "FreeCAD.Part", known_runtime_modules=known)

    assert resolved.is_resolved is True
    assert resolved.resolved_path is None


def test_resolve_project_import_still_unresolved_without_known_modules(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()

    unresolved = resolve_project_import(str(project_root), "FreeCAD")

    assert unresolved.is_resolved is False


# ---------------------------------------------------------------------------
# vendor/ directory import resolution
# ---------------------------------------------------------------------------


def test_resolve_project_import_resolves_vendor_module(tmp_path: Path) -> None:
    """A .py file under vendor/ should resolve."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    vendor_dir = project_root / "vendor"
    vendor_dir.mkdir()
    (vendor_dir / "vendored_lib.py").write_text("x = 1\n", encoding="utf-8")

    resolved = resolve_project_import(str(project_root), "vendored_lib")

    assert resolved.is_resolved is True
    assert resolved.resolved_path is not None and resolved.resolved_path.endswith("vendored_lib.py")


def test_resolve_project_import_resolves_vendor_package(tmp_path: Path) -> None:
    """A package under vendor/ should resolve."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    vendor_pkg = project_root / "vendor" / "mypkg"
    vendor_pkg.mkdir(parents=True)
    (vendor_pkg / "__init__.py").write_text("", encoding="utf-8")

    resolved = resolve_project_import(str(project_root), "mypkg")

    assert resolved.is_resolved is True
    assert resolved.resolved_path is not None and resolved.resolved_path.endswith("__init__.py")


def test_resolve_project_import_vendor_dotted_submodule(tmp_path: Path) -> None:
    """A dotted import under vendor/ should resolve."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    vendor_pkg = project_root / "vendor" / "mypkg"
    vendor_pkg.mkdir(parents=True)
    (vendor_pkg / "__init__.py").write_text("", encoding="utf-8")
    (vendor_pkg / "sub.py").write_text("y = 2\n", encoding="utf-8")

    resolved = resolve_project_import(str(project_root), "mypkg.sub")

    assert resolved.is_resolved is True
    assert resolved.resolved_path is not None and resolved.resolved_path.endswith("sub.py")
