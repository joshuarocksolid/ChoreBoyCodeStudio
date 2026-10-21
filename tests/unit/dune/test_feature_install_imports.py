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


def test_type_checking_else_branch_is_scanned(tmp_path: Path) -> None:
    relative_path = "app/features/demo/__init__.py"
    _write(
        tmp_path,
        relative_path,
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from PySide6.QtWidgets import QWidget\n"
        "else:\n"
        "    import PySide6\n",
    )

    violations = find_feature_install_import_violations(tmp_path, [relative_path])

    assert len(violations) == 1
    assert "PySide6" in violations[0]
    assert "QtWidgets" not in violations[0]


def test_features_package_init_is_scanned(tmp_path: Path) -> None:
    relative_path = "app/features/__init__.py"
    _write(tmp_path, relative_path, "import PySide6\n")

    violations = find_feature_install_import_violations(tmp_path, [relative_path])

    assert any("PySide6" in violation for violation in violations)


@pytest.mark.parametrize(
    "source",
    [
        "import importlib\nimportlib.import_module('PySide6')\n",
        "import importlib\nimportlib.__import__('PySide6')\n",
        "__import__('PySide6')\n",
    ],
)
def test_module_level_dynamic_import_fails(tmp_path: Path, source: str) -> None:
    relative_path = "app/features/demo/install.py"
    _write(tmp_path, relative_path, source)

    violations = find_feature_install_import_violations(tmp_path, [relative_path])

    assert any("PySide6" in violation for violation in violations)


def test_dynamic_import_inside_function_passes(tmp_path: Path) -> None:
    relative_path = "app/features/demo/install.py"
    _write(
        tmp_path,
        relative_path,
        "import importlib\n"
        "def install(ctx):\n"
        "    importlib.import_module('PySide6')\n"
        "    __import__('shiboken6')\n",
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
