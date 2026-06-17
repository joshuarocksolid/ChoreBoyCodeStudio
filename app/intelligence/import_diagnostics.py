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
    resolve_import_from_module,
    resolve_project_import_layout,
)

PY200_DETAIL_UNRESOLVED_MODULE = "unresolved_module"


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
    # Hot lint paths are static-only; runtime probe is reserved for explain/import analysis APIs.
    _ = allow_runtime_import_probe
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
                    allow_runtime_import_probe=False,
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
                        detail={PY200_DETAIL_UNRESOLVED_MODULE: alias.name},
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
                        detail={PY200_DETAIL_UNRESOLVED_MODULE: display_module},
                    )
                )
                continue
            if is_module_resolvable(
                project_root,
                resolved_module,
                known_runtime_modules=known_runtime_modules,
                allow_runtime_import_probe=False,
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
                    detail={PY200_DETAIL_UNRESOLVED_MODULE: resolved_module},
                )
            )
    return diagnostics


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
