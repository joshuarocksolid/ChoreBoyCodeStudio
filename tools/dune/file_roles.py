from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


class FileRoleError(ValueError):
    pass


@dataclass(frozen=True)
class FileRole:
    name: str
    source_patterns: tuple[str, ...]
    denied_imports: tuple[str, ...]
    allowed_files: frozenset[str] = frozenset()
    allowed_imports: tuple[str, ...] = ()


_UI_IMPORT_CONTRACTS = (
    "app.packaging.config",
    "app.packaging.layout",
    "app.packaging.models",
    "app.runner.repl_protocol",
)

FILE_ROLES = (
    FileRole("app.core", ("app/core/**",), ("PySide2",)),
    FileRole("app.bootstrap", ("app/bootstrap/**",), ("PySide2",)),
    FileRole("app.run", ("app/run/**",), ("PySide2",)),
    FileRole("app.intelligence", ("app/intelligence/**",), ("PySide2",)),
    FileRole("app.persistence", ("app/persistence/**",), ("PySide2",)),
    FileRole("app.plugins", ("app/plugins/**",), ("PySide2",)),
    FileRole("app.packaging", ("app/packaging/**",), ("PySide2",)),
    FileRole(
        "app.project",
        ("app/project/**",),
        ("PySide2",),
        allowed_files=frozenset({"app/project/project_tree_widget.py"}),
    ),
    FileRole(
        "app.shell",
        ("app/shell/**",),
        ("app.runner", "app.packaging"),
        allowed_imports=_UI_IMPORT_CONTRACTS,
    ),
    FileRole(
        "app.editors",
        ("app/editors/**",),
        ("app.runner", "app.packaging"),
        allowed_imports=_UI_IMPORT_CONTRACTS,
    ),
    FileRole("app.runner", ("app/runner/**",), ("app.features",)),
    FileRole(
        "app.plugins.host_runtime",
        ("app/plugins/host_runtime.py", "app/plugins/host_runtime/**"),
        ("app.features",),
    ),
)


@dataclass(frozen=True)
class _ImportStatement:
    module: str
    imported_names: tuple[str, ...]
    line_number: int


def find_file_role_violations(
    repo_root: Path,
    tracked_files: Iterable[str],
) -> list[str]:
    violations: list[str] = []
    python_files = sorted(
        {
            path.replace("\\", "/")
            for path in tracked_files
            if path.endswith(".py")
            and (path == "app" or path.startswith("app/"))
        }
    )

    for relative_path in python_files:
        roles = [
            role
            for role in FILE_ROLES
            if relative_path not in role.allowed_files
            and any(
                _path_matches(pattern, relative_path)
                for pattern in role.source_patterns
            )
        ]
        if not roles:
            continue
        source_path = repo_root / relative_path
        try:
            tree = ast.parse(
                source_path.read_text(encoding="utf-8"),
                filename=relative_path,
            )
        except SyntaxError as exc:
            line_number = exc.lineno or 1
            raise FileRoleError(
                f"{relative_path}:{line_number}: invalid Python syntax: {exc.msg}"
            ) from exc

        statements = _import_statements(relative_path, tree)
        for role in roles:
            for statement in statements:
                forbidden_modules = _forbidden_modules(role, statement)
                for module in forbidden_modules:
                    violations.append(
                        f"file-role: {relative_path}:{statement.line_number}: "
                        f"{role.name} must not import {module}"
                    )

    return violations


def _import_statements(
    relative_path: str,
    tree: ast.AST,
) -> list[_ImportStatement]:
    statements: list[_ImportStatement] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            statements.extend(
                _ImportStatement(alias.name, (), node.lineno)
                for alias in node.names
            )
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        module = _resolve_import_from_module(
            relative_path,
            node.module,
            node.level,
        )
        if not module:
            continue
        imported_names = tuple(
            alias.name
            for alias in node.names
            if alias.name != "*"
        )
        statements.append(
            _ImportStatement(module, imported_names, node.lineno)
        )
    return sorted(
        statements,
        key=lambda statement: (
            statement.line_number,
            statement.module,
            statement.imported_names,
        ),
    )


def _resolve_import_from_module(
    relative_path: str,
    module: Optional[str],
    level: int,
) -> str:
    if level == 0:
        return module or ""

    package_parts = relative_path.removesuffix(".py").split("/")[:-1]
    parent_count = level - 1
    if parent_count > len(package_parts):
        return module or ""
    base_parts = package_parts[: len(package_parts) - parent_count]
    if module:
        base_parts.extend(module.split("."))
    return ".".join(base_parts)


def _forbidden_modules(
    role: FileRole,
    statement: _ImportStatement,
) -> list[str]:
    module = statement.module
    denied_root = next(
        (
            denied
            for denied in role.denied_imports
            if _module_matches(denied, module)
        ),
        "",
    )
    if denied_root:
        if _module_is_allowed(role, module):
            return []
        if (
            module == denied_root
            and statement.imported_names
            and _has_allowed_children(role, denied_root)
        ):
            return [
                candidate
                for candidate in _imported_candidates(statement)
                if not _module_is_allowed(role, candidate)
            ]
        return [module]

    return [
        candidate
        for candidate in _imported_candidates(statement)
        if any(
            _module_matches(denied, candidate)
            for denied in role.denied_imports
        )
        and not _module_is_allowed(role, candidate)
    ]


def _imported_candidates(statement: _ImportStatement) -> list[str]:
    return [
        f"{statement.module}.{name}"
        for name in statement.imported_names
    ]


def _module_is_allowed(role: FileRole, module: str) -> bool:
    return any(
        _module_matches(allowed, module)
        for allowed in role.allowed_imports
    )


def _has_allowed_children(role: FileRole, module: str) -> bool:
    return any(
        allowed.startswith(f"{module}.")
        for allowed in role.allowed_imports
    )


def _module_matches(prefix: str, module: str) -> bool:
    return module == prefix or module.startswith(f"{prefix}.")


def _path_matches(pattern: str, path: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path.startswith(f"{prefix}/")
    return path == pattern
