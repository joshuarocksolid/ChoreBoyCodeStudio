"""The feature-install-imports dune rule rejects module-level Qt imports."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.dune.feature_install_imports import find_feature_install_import_violations

pytestmark = pytest.mark.unit


def _write(repo_root: Path, relative_path: str, source: str) -> None:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def test_module_level_binding_import_fails(tmp_path: Path) -> None:
    relative_path = "app/features/demo/install.py"
    _write(tmp_path, relative_path, "import PySide6\nfrom app.qt.QtWidgets import QWidget\n")

    violations = find_feature_install_import_violations(tmp_path, [relative_path])

    assert any("PySide6" in violation for violation in violations)
    assert any("app.qt" in violation for violation in violations)


def test_import_inside_function_passes(tmp_path: Path) -> None:
    relative_path = "app/features/demo/install.py"
    _write(
        tmp_path,
        relative_path,
        "def install(ctx):\n    import PySide6\n    from app.qt.QtWidgets import QWidget\n",
    )

    assert find_feature_install_import_violations(tmp_path, [relative_path]) == []


def test_type_checking_import_passes(tmp_path: Path) -> None:
    relative_path = "app/features/demo/__init__.py"
    _write(
        tmp_path,
        relative_path,
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from PySide6.QtWidgets import QWidget\n",
    )

    assert find_feature_install_import_violations(tmp_path, [relative_path]) == []
