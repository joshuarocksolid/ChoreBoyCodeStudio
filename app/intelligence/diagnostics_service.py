"""Diagnostics helpers for Python projects."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Mapping

from app.core import constants
from app.core.models import ProjectMetadata
from app.intelligence.builtin_lint_rules import (
    duplicate_definition_diagnostics,
    duplicate_import_diagnostics,
    unreachable_statement_diagnostics,
    unused_import_diagnostics,
)
from app.intelligence.diagnostics_models import (
    CodeDiagnostic,
    DiagnosticSeverity,
    ImportDiagnostic,
    ImportExplanation,
)
from app.intelligence.import_diagnostics import collect_unresolved_import_diagnostics
from app.intelligence.import_explanations import build_import_explanation
from app.intelligence.lint_profile import apply_lint_rule_profile
from app.intelligence.pyflakes_adapter import (
    pyflakes_diagnostics as _pyflakes_diagnostics,
)
from app.project.file_inventory import ProjectInventorySnapshot
from app.project.import_layout import ProjectImportLayout, resolve_project_import_layout

__all__ = [
    "CodeDiagnostic",
    "DiagnosticSeverity",
    "ImportDiagnostic",
    "ImportExplanation",
    "analyze_python_file",
    "explain_unresolved_import",
    "find_unresolved_imports",
]


def find_unresolved_imports(
    project_root: str,
    *,
    source_overrides: dict[str, str] | None = None,
    known_runtime_modules: frozenset[str] | None = None,
    allow_runtime_import_probe: bool = False,
    lint_rule_overrides: Mapping[str, Mapping[str, Any]] | None = None,
    project_metadata: ProjectMetadata | None = None,
    inventory_snapshot: ProjectInventorySnapshot | None = None,
    manifest_materialized: bool = True,
) -> list[ImportDiagnostic]:
    """Find unresolved project-local imports in Python files.

    When *source_overrides* is provided it maps absolute file paths to
    in-memory source text (e.g. unsaved editor buffers).  Overridden
    content is used instead of reading from disk so that unsaved edits
    are included in the analysis.
    """
    root = Path(project_root).expanduser().resolve()
    layout = resolve_project_import_layout(
        root,
        project_metadata,
        manifest_materialized=manifest_materialized,
    )
    resolved_overrides: dict[str, str] = {}
    if source_overrides:
        for p, src in source_overrides.items():
            resolved_overrides[str(Path(p).expanduser().resolve())] = src
    diagnostics: list[ImportDiagnostic] = []
    if inventory_snapshot is None:
        return []
    python_paths = [Path(path) for path in inventory_snapshot.python_file_paths]
    for file_path in python_paths:
        override = resolved_overrides.get(str(file_path.resolve()))
        diagnostics.extend(
            _diagnostics_for_file(
                root,
                file_path,
                source=override,
                known_runtime_modules=known_runtime_modules,
                allow_runtime_import_probe=allow_runtime_import_probe,
                lint_rule_overrides=lint_rule_overrides,
                layout=layout,
                project_metadata=project_metadata,
            )
        )
    return diagnostics


def analyze_python_file(
    file_path: str,
    *,
    project_root: str | None = None,
    source: str | None = None,
    known_runtime_modules: frozenset[str] | None = None,
    allow_runtime_import_probe: bool = False,
    selected_linter: str = constants.LINTER_PROVIDER_DEFAULT,
    lint_rule_overrides: Mapping[str, Mapping[str, Any]] | None = None,
    project_metadata: ProjectMetadata | None = None,
    manifest_materialized: bool = True,
) -> list[CodeDiagnostic]:
    """Run focused diagnostics for one Python file.

    When *source* is provided, it is used instead of reading from disk.
    This enables linting unsaved editor buffer content.
    """
    path = Path(file_path).expanduser().resolve()
    if source is None:
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            return []

    syntax_tree: ast.AST | None = None
    diagnostics: list[CodeDiagnostic] = []
    try:
        syntax_tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        col_start = (int(exc.offset) - 1) if exc.offset is not None else None
        raw_end_offset = getattr(exc, "end_offset", None)
        col_end = (int(raw_end_offset) - 1) if isinstance(raw_end_offset, int) else None
        diagnostics.append(
            CodeDiagnostic(
                code="PY100",
                severity=DiagnosticSeverity.ERROR,
                file_path=str(path),
                line_number=max(1, int(exc.lineno or 1)),
                message=f"Syntax error: {exc.msg}",
                col_start=col_start,
                col_end=col_end,
            )
        )
        return diagnostics

    provider = _normalize_linter_provider(selected_linter)
    if provider == constants.LINTER_PROVIDER_PYFLAKES:
        diagnostics.extend(_pyflakes_diagnostics(source, path))
    else:
        diagnostics.extend(duplicate_definition_diagnostics(syntax_tree, path))
        diagnostics.extend(duplicate_import_diagnostics(syntax_tree, path))
        diagnostics.extend(unused_import_diagnostics(syntax_tree, path))
        diagnostics.extend(unreachable_statement_diagnostics(syntax_tree, path))

    if project_root:
        resolved_root = Path(project_root).expanduser().resolve()
        layout = resolve_project_import_layout(
            resolved_root,
            project_metadata,
            manifest_materialized=manifest_materialized,
        )
        diagnostics.extend(
            collect_unresolved_import_diagnostics(
                resolved_root,
                path,
                syntax_tree,
                known_runtime_modules=known_runtime_modules,
                allow_runtime_import_probe=allow_runtime_import_probe,
                lint_rule_overrides=lint_rule_overrides,
                layout=layout,
                project_metadata=project_metadata,
            )
        )

    diagnostics = apply_lint_rule_profile(diagnostics, lint_rule_overrides)
    diagnostics.sort(key=lambda item: (item.file_path, item.line_number, item.code))
    return diagnostics


def _diagnostics_for_file(
    project_root: Path,
    file_path: Path,
    *,
    source: str | None = None,
    known_runtime_modules: frozenset[str] | None = None,
    allow_runtime_import_probe: bool = False,
    lint_rule_overrides: Mapping[str, Mapping[str, Any]] | None = None,
    layout: ProjectImportLayout | None = None,
    project_metadata: ProjectMetadata | None = None,
) -> list[ImportDiagnostic]:
    if source is None:
        try:
            source = file_path.read_text(encoding="utf-8")
        except OSError:
            return []
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []

    resolved_layout = layout or resolve_project_import_layout(project_root, project_metadata)
    diagnostics: list[ImportDiagnostic] = []
    for diagnostic in collect_unresolved_import_diagnostics(
        project_root,
        file_path.resolve(),
        tree,
        known_runtime_modules=known_runtime_modules,
        allow_runtime_import_probe=allow_runtime_import_probe,
        lint_rule_overrides=lint_rule_overrides,
        layout=resolved_layout,
        project_metadata=project_metadata,
    ):
        diagnostics.append(
            ImportDiagnostic(
                file_path=diagnostic.file_path,
                line_number=diagnostic.line_number,
                message=diagnostic.message,
            )
        )
    return diagnostics


def explain_unresolved_import(
    project_root: str,
    module_name: str,
    *,
    known_runtime_modules: frozenset[str] | None = None,
    allow_runtime_import_probe: bool = False,
    project_metadata: ProjectMetadata | None = None,
) -> ImportExplanation:
    """Classify an unresolved import into a user-facing explanation."""
    return build_import_explanation(
        project_root,
        module_name,
        known_runtime_modules=known_runtime_modules,
        allow_runtime_import_probe=allow_runtime_import_probe,
        project_metadata=project_metadata,
    )


def _normalize_linter_provider(selected_linter: str) -> str:
    if selected_linter == constants.LINTER_PROVIDER_PYFLAKES:
        return constants.LINTER_PROVIDER_PYFLAKES
    return constants.LINTER_PROVIDER_DEFAULT
