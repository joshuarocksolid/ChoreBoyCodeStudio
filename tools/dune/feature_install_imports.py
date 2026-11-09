"""Dune rule ``feature-install-imports`` (form-builder contract section 11.5)."""

from __future__ import annotations

import ast
import sys
import sysconfig
from pathlib import Path
from typing import Iterable, Optional


class FeatureInstallImportError(ValueError):
    pass


_ALLOWED_EXACT = (
    "app.bootstrap.qt_binding_choice",
    "app.features.spec",
)


def find_feature_install_import_violations(
    repo_root: Path,
    tracked_files: Iterable[str],
) -> list[str]:
    violations: list[str] = []
    for relative_path in sorted(_candidate_paths(tracked_files)):
        feature_package = _feature_package(relative_path)
        source_path = repo_root / relative_path
        try:
            tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=relative_path)
        except SyntaxError as exc:
            line_number = exc.lineno or 1
            raise FeatureInstallImportError(
                f"{relative_path}:{line_number}: invalid Python syntax: {exc.msg}"
            ) from exc
        for line_number, module in _module_level_imports(relative_path, tree):
            if _import_allowed(module, feature_package):
                continue
            violations.append(
                f"feature-install-imports: {relative_path}:{line_number}: "
                f"module-level import {module} is not allowed"
            )
    return violations


def _candidate_paths(tracked_files: Iterable[str]) -> set[str]:
    candidates: set[str] = set()
    for raw_path in tracked_files:
        path = raw_path.replace("\\", "/")
        if path in {"app/features/spec.py", "app/features/__init__.py"}:
            candidates.add(path)
            continue
        parts = path.split("/")
        if (
            len(parts) == 4
            and parts[0] == "app"
            and parts[1] == "features"
            and parts[3] in {"install.py", "__init__.py"}
        ):
            candidates.add(path)
    return candidates


def _feature_package(relative_path: str) -> Optional[str]:
    parts = relative_path.split("/")
    if len(parts) == 4 and parts[3] in {"install.py", "__init__.py"}:
        return f"app.features.{parts[2]}"
    return None


def _module_level_imports(relative_path: str, tree: ast.Module) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for statement in tree.body:
        if isinstance(statement, ast.If) and _is_type_checking(statement.test):
            for clause in statement.orelse:
                found.extend(_imports_under(relative_path, clause))
            continue
        found.extend(_imports_under(relative_path, statement))
    return found


def _imports_under(relative_path: str, node: ast.AST) -> list[tuple[int, str]]:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        return []
    found: list[tuple[int, str]] = []
    if isinstance(node, ast.Import):
        found.extend((node.lineno, alias.name) for alias in node.names)
        return found
    if isinstance(node, ast.ImportFrom):
        module = _absolute_module(relative_path, node)
        if module:
            found.append((node.lineno, module))
        return found
    if isinstance(node, ast.Call):
        imported = _dynamic_import_module(node)
        if imported is not None:
            found.append((node.lineno, imported))
    for child in ast.iter_child_nodes(node):
        found.extend(_imports_under(relative_path, child))
    return found


def _absolute_module(relative_path: str, node: ast.ImportFrom) -> str:
    if node.level == 0:
        return node.module or ""
    package = relative_path.split("/")[:-1]
    keep = len(package) - (node.level - 1)
    if keep < 0:
        return node.module or ""
    base = package[:keep]
    if node.module:
        base.extend(node.module.split("."))
    return ".".join(base)


def _dynamic_import_module(node: ast.Call) -> Optional[str]:
    func = node.func
    if isinstance(func, ast.Name) and func.id == "__import__":
        return _called_module(node)
    if (
        isinstance(func, ast.Attribute)
        and func.attr in {"import_module", "__import__"}
        and isinstance(func.value, ast.Name)
        and func.value.id == "importlib"
    ):
        return _called_module(node)
    return None


def _called_module(node: ast.Call) -> str:
    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        return str(node.args[0].value)
    return "<dynamic>"


def _is_type_checking(test: ast.AST) -> bool:
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute):
        return test.attr == "TYPE_CHECKING"
    return False


def _import_allowed(module: str, feature_package: Optional[str]) -> bool:
    if not module:
        return True
    if any(module == allowed or module.startswith(f"{allowed}.") for allowed in _ALLOWED_EXACT):
        return True
    if feature_package is not None:
        engine = f"{feature_package}.engine"
        if module == engine or module.startswith(f"{engine}."):
            return True
    return _is_stdlib(module.split(".", 1)[0])


def _is_stdlib(root: str) -> bool:
    if root in {"__future__"} or root in sys.builtin_module_names:
        return True
    stdlib_names = getattr(sys, "stdlib_module_names", None)
    if stdlib_names is not None:
        return root in stdlib_names
    import importlib.util

    spec = importlib.util.find_spec(root)
    if spec is None:
        return False
    origin = spec.origin or ""
    if origin in {"built-in", "frozen"}:
        return True
    stdlib = sysconfig.get_path("stdlib")
    return bool(origin) and origin.startswith(stdlib) and "site-packages" not in origin
