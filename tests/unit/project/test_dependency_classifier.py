"""Unit tests for the dependency classifier SSOT."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.project.dependency_classifier import (
    CATEGORY_FIRST_PARTY,
    CATEGORY_MISSING,
    CATEGORY_RUNTIME,
    CATEGORY_STDLIB,
    CATEGORY_VENDORED,
    CATEGORY_VENDORED_NATIVE,
    classify_module,
    has_compiled_extension_candidate,
    is_module_resolvable,
)

pytestmark = pytest.mark.unit


def test_classify_module_returns_stdlib_for_well_known_top_level(tmp_path: Path) -> None:
    classification = classify_module(project_root=tmp_path, module_name="json")

    assert classification.category == CATEGORY_STDLIB
    assert classification.top_level == "json"
    assert classification.resolved_path is None


def test_classify_module_returns_first_party_for_project_module(tmp_path: Path) -> None:
    package_dir = tmp_path / "myapp"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "core.py").write_text("X = 1\n", encoding="utf-8")

    classification = classify_module(project_root=tmp_path, module_name="myapp.core")

    assert classification.category == CATEGORY_FIRST_PARTY
    assert classification.resolved_path is not None
    assert classification.resolved_path.endswith("myapp/core.py")


def test_classify_module_returns_first_party_for_namespace_init_only(tmp_path: Path) -> None:
    package_dir = tmp_path / "mypkg"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("", encoding="utf-8")

    classification = classify_module(project_root=tmp_path, module_name="mypkg")

    assert classification.category == CATEGORY_FIRST_PARTY


def test_classify_module_returns_vendored_for_pure_python_vendor_module(tmp_path: Path) -> None:
    vendor_pkg = tmp_path / "vendor" / "thirdparty"
    vendor_pkg.mkdir(parents=True)
    (vendor_pkg / "__init__.py").write_text("", encoding="utf-8")

    classification = classify_module(project_root=tmp_path, module_name="thirdparty")

    assert classification.category == CATEGORY_VENDORED


def test_classify_module_upgrades_vendored_to_native_when_extension_present(tmp_path: Path) -> None:
    vendor_pkg = tmp_path / "vendor" / "fastlib"
    vendor_pkg.mkdir(parents=True)
    (vendor_pkg / "__init__.py").write_text("", encoding="utf-8")
    (vendor_pkg / "_core.cpython-39-x86_64-linux-gnu.so").write_bytes(b"")

    classification = classify_module(project_root=tmp_path, module_name="fastlib")

    assert classification.category == CATEGORY_VENDORED_NATIVE


def test_classify_module_returns_vendored_native_when_only_so_present(tmp_path: Path) -> None:
    vendor_dir = tmp_path / "vendor"
    vendor_dir.mkdir()
    (vendor_dir / "fastthing.cpython-39-x86_64-linux-gnu.so").write_bytes(b"")

    classification = classify_module(project_root=tmp_path, module_name="fastthing")

    assert classification.category == CATEGORY_VENDORED_NATIVE
    assert classification.resolved_path is None


def test_classify_module_returns_runtime_when_known_runtime_modules_match(tmp_path: Path) -> None:
    classification = classify_module(
        project_root=tmp_path,
        module_name="FreeCAD",
        known_runtime_modules=frozenset({"FreeCAD"}),
    )

    assert classification.category == CATEGORY_RUNTIME


def test_classify_module_returns_missing_when_no_match_found(tmp_path: Path) -> None:
    classification = classify_module(project_root=tmp_path, module_name="nonexistent_pkg")

    assert classification.category == CATEGORY_MISSING


def test_has_compiled_extension_candidate_detects_top_level_so(tmp_path: Path) -> None:
    (tmp_path / "fastlib.cpython-39-x86_64-linux-gnu.so").write_bytes(b"")

    assert has_compiled_extension_candidate(tmp_path, "fastlib") is True


def test_has_compiled_extension_candidate_detects_package_internal_so(tmp_path: Path) -> None:
    package_dir = tmp_path / "fastlib"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "_internal.cpython-39-x86_64-linux-gnu.so").write_bytes(b"")

    assert has_compiled_extension_candidate(tmp_path, "fastlib") is True


def test_has_compiled_extension_candidate_returns_false_when_only_python_present(tmp_path: Path) -> None:
    (tmp_path / "puremod.py").write_text("X = 1\n", encoding="utf-8")

    assert has_compiled_extension_candidate(tmp_path, "puremod") is False


def test_is_module_resolvable_uses_stdlib_fallback_when_no_runtime_inventory(tmp_path: Path) -> None:
    assert is_module_resolvable(tmp_path, "json") is True


def test_is_module_resolvable_resolves_project_files(tmp_path: Path) -> None:
    (tmp_path / "myapp.py").write_text("# entry\n", encoding="utf-8")

    assert is_module_resolvable(tmp_path, "myapp") is True


def test_is_module_resolvable_treats_known_runtime_inventory_as_authoritative(tmp_path: Path) -> None:
    """When known_runtime_modules is provided, stdlib fallback is bypassed."""
    runtime_inventory = frozenset({"freecad_only_module"})

    assert (
        is_module_resolvable(tmp_path, "json", known_runtime_modules=runtime_inventory) is False
    )
    assert (
        is_module_resolvable(
            tmp_path, "freecad_only_module", known_runtime_modules=runtime_inventory
        )
        is True
    )


def test_is_module_resolvable_returns_false_for_unresolved_imports(tmp_path: Path) -> None:
    assert is_module_resolvable(tmp_path, "nonexistent_module") is False
