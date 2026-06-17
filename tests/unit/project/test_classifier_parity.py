"""Cross-consumer parity tests for dependency classification."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.packaging.dependency_audit import run_dependency_audit
from app.project.dependency_classifier import (
    CATEGORY_FIRST_PARTY,
    CATEGORY_MISSING,
    CATEGORY_RUNTIME,
    CATEGORY_STDLIB,
    CATEGORY_VENDORED,
    CATEGORY_VENDORED_NATIVE,
    RuntimeModuleInventory,
    classify_module,
    is_module_resolvable,
)
from app.intelligence.import_diagnostics import collect_unresolved_import_diagnostics
import ast

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("module_name", "inventory", "expected_category", "expected_resolvable"),
    [
        ("json", None, CATEGORY_STDLIB, True),
        ("json", frozenset({"freecad_only_module"}), CATEGORY_MISSING, False),
        ("freecad_only_module", frozenset({"freecad_only_module"}), CATEGORY_RUNTIME, True),
        ("nonexistent_pkg", None, CATEGORY_MISSING, False),
    ],
)
def test_classifier_and_resolvability_parity_for_runtime_inventory_policy(
    tmp_path: Path,
    module_name: str,
    inventory: frozenset[str] | None,
    expected_category: str,
    expected_resolvable: bool,
) -> None:
    classification = classify_module(
        project_root=tmp_path,
        module_name=module_name,
        known_runtime_modules=inventory,
    )

    assert classification.category == expected_category
    assert (
        is_module_resolvable(tmp_path, module_name, known_runtime_modules=inventory)
        is expected_resolvable
    )


def test_runtime_module_inventory_tri_state_unknown(tmp_path: Path) -> None:
    inventory = RuntimeModuleInventory.unknown()

    assert inventory.state == "unknown"
    assert classify_module(project_root=tmp_path, module_name="json", runtime_inventory=inventory).category == CATEGORY_STDLIB


def test_runtime_module_inventory_tri_state_empty(tmp_path: Path) -> None:
    inventory = RuntimeModuleInventory.from_optional_frozenset(frozenset())

    assert inventory.state == "empty"
    assert classify_module(project_root=tmp_path, module_name="json", runtime_inventory=inventory).category == CATEGORY_STDLIB


def test_runtime_module_inventory_tri_state_loaded(tmp_path: Path) -> None:
    inventory = RuntimeModuleInventory.from_optional_frozenset(frozenset({"FreeCAD"}))

    assert inventory.state == "loaded"
    assert classify_module(project_root=tmp_path, module_name="json", runtime_inventory=inventory).category == CATEGORY_MISSING


def test_first_party_src_layout_parity_across_classifier_audit_and_diagnostics(tmp_path: Path) -> None:
    package_dir = tmp_path / "src" / "myapp"
    package_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    main_file = tmp_path / "main.py"
    main_file.write_text("from myapp import core\n", encoding="utf-8")
    tree = ast.parse(main_file.read_text(encoding="utf-8"))

    classification = classify_module(project_root=tmp_path, module_name="myapp.core")
    audit = run_dependency_audit(project_root=str(tmp_path), known_runtime_modules=frozenset())
    diagnostics = collect_unresolved_import_diagnostics(
        project_root=tmp_path,
        file_path=main_file,
        syntax_tree=tree,
        known_runtime_modules=frozenset(),
    )

    assert classification.category == CATEGORY_FIRST_PARTY
    assert any(record.module_name == "myapp" and record.classification == "first_party" for record in audit.records)
    assert diagnostics == []


def test_vendored_native_parity_between_classifier_and_audit(tmp_path: Path) -> None:
    vendor_dir = tmp_path / "vendor"
    vendor_dir.mkdir()
    (vendor_dir / "fastlib.cpython-39-x86_64-linux-gnu.so").write_bytes(b"")
    (tmp_path / "main.py").write_text("import fastlib\n", encoding="utf-8")

    classification = classify_module(project_root=tmp_path, module_name="fastlib")
    audit = run_dependency_audit(project_root=str(tmp_path), known_runtime_modules=frozenset())

    assert classification.category == CATEGORY_VENDORED_NATIVE
    assert any(record.classification == "vendored_native" for record in audit.records)


def test_vendored_pure_python_parity_between_classifier_and_audit(tmp_path: Path) -> None:
    vendor_pkg = tmp_path / "vendor" / "thirdparty"
    vendor_pkg.mkdir(parents=True)
    (vendor_pkg / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "main.py").write_text("import thirdparty\n", encoding="utf-8")

    classification = classify_module(project_root=tmp_path, module_name="thirdparty")
    audit = run_dependency_audit(project_root=str(tmp_path), known_runtime_modules=frozenset())

    assert classification.category == CATEGORY_VENDORED
    assert any(record.classification == "vendored" for record in audit.records)
