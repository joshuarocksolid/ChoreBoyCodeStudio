"""AST import diagnostics extracted from ``diagnostics_service``."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Mapping

from app.core.models import ProjectMetadata
from app.intelligence.diagnostics_models import CodeDiagnostic, DiagnosticSeverity
from app.intelligence.lint_profile import resolve_lint_rule_settings
from app.project.dependency_classifier import is_module_resolvable
from app.project.import_layout import (
    ProjectImportLayout,
    module_name_for_file,
    resolve_project_import_layout,
)


def collect_unresolved_import_diagnostics(
    project_root: Path,
    file_path: Path,
    syntax_tree: ast.AST,
    *,
    known_runtime_modules: frozenset[str] | None = None,
    allow_runtime_import_probe: bool = False,
    lint_rule_overrides: Mapping[str, Mapping[str, Any]] | None = None,
    layout: ProjectImportLayout | None = None,
    project_metadata: ProjectMetadata | None = None,
) -> list[CodeDiagnostic]:
    """Collect PY200 diagnostics for unresolved imports in one file."""
    is_enabled, severity = resolve_lint_rule_settings("PY200", lint_rule_overrides)
    if not is_enabled:
        return []
    diagnostic_severity = _severity_from_profile_value(severity)
    resolved_layout = layout or resolve_project_import_layout(project_root, project_metadata)
    diagnostics: list[CodeDiagnostic] = []
    for node in ast.walk(syntax_tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if is_module_resolvable(
                    project_root,
                    alias.name,
                    known_runtime_modules=known_runtime_modules,
                    allow_runtime_import_probe=allow_runtime_import_probe,
                    metadata=project_metadata,
                    layout=resolved_layout,
                ):
                    continue
                diagnostics.append(
                    CodeDiagnostic(
                        code="PY200",
                        severity=diagnostic_severity,
                        file_path=str(file_path),
                        line_number=int(node.lineno),
                        message=f"Unresolved import: {alias.name}",
                        col_start=_col_offset(node),
                        col_end=_end_col_offset(node),
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            resolved_module = resolve_import_from_module(
                file_path,
                node.module,
                int(node.level),
                layout=resolved_layout,
            )
            if resolved_module is None:
                display_module = _relative_import_display(node)
                diagnostics.append(
                    CodeDiagnostic(
                        code="PY200",
                        severity=diagnostic_severity,
                        file_path=str(file_path),
                        line_number=int(node.lineno),
                        message=f"Unresolved import: {display_module}",
                        col_start=_col_offset(node),
                        col_end=_end_col_offset(node),
                    )
                )
                continue
            if is_module_resolvable(
                project_root,
                resolved_module,
                known_runtime_modules=known_runtime_modules,
                allow_runtime_import_probe=allow_runtime_import_probe,
                metadata=project_metadata,
                layout=resolved_layout,
            ):
                continue
            diagnostics.append(
                CodeDiagnostic(
                    code="PY200",
                    severity=diagnostic_severity,
                    file_path=str(file_path),
                    line_number=int(node.lineno),
                    message=f"Unresolved import: {resolved_module}",
                    col_start=_col_offset(node),
                    col_end=_end_col_offset(node),
                )
            )
    return diagnostics


def resolve_import_from_module(
    file_path: Path,
    module: str | None,
    level: int,
    *,
    layout: ProjectImportLayout,
) -> str | None:
    if level <= 0:
        return module
    package_name = package_name_for_file(file_path, layout=layout)
    if package_name is None:
        return None
    try:
        from importlib.util import resolve_name

        relative_spec = module if module is not None else ""
        return resolve_name(relative_spec, package_name, level)
    except (ImportError, ValueError):
        return None


def package_name_for_file(file_path: Path, *, layout: ProjectImportLayout) -> str | None:
    module_name = module_name_for_file(layout, file_path)
    if module_name is None:
        return None
    if file_path.name == "__init__.py":
        return module_name
    if "." not in module_name:
        return None
    return module_name.rsplit(".", 1)[0]


def _relative_import_display(node: ast.ImportFrom) -> str:
    module = node.module or ""
    prefix = "." * int(node.level)
    if module:
        return f"{prefix}{module}"
    return prefix or "relative import"


def _col_offset(node: ast.AST) -> int | None:
    raw = getattr(node, "col_offset", None)
    return int(raw) if isinstance(raw, int) else None


def _end_col_offset(node: ast.AST) -> int | None:
    raw = getattr(node, "end_col_offset", None)
    return int(raw) if isinstance(raw, int) else None


def _severity_from_profile_value(value: str) -> DiagnosticSeverity:
    from app.intelligence.lint_profile import LINT_SEVERITY_ERROR, LINT_SEVERITY_INFO

    if value == LINT_SEVERITY_ERROR:
        return DiagnosticSeverity.ERROR
    if value == LINT_SEVERITY_INFO:
        return DiagnosticSeverity.INFO
    return DiagnosticSeverity.WARNING
