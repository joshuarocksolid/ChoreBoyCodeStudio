"""AST-based builtin lint rules for Python file diagnostics."""

from __future__ import annotations

import ast
from pathlib import Path

from app.intelligence.diagnostics_models import CodeDiagnostic, DiagnosticSeverity


def duplicate_definition_diagnostics(syntax_tree: ast.AST, file_path: Path) -> list[CodeDiagnostic]:
    seen: dict[str, int] = {}
    diagnostics: list[CodeDiagnostic] = []
    body = getattr(syntax_tree, "body", [])
    for node in body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        previous_line = seen.get(node.name)
        if previous_line is None:
            seen[node.name] = int(node.lineno)
            continue
        diagnostics.append(
            CodeDiagnostic(
                code="PY210",
                severity=DiagnosticSeverity.WARNING,
                file_path=str(file_path),
                line_number=int(node.lineno),
                message=f"Duplicate definition '{node.name}' (first defined at line {previous_line}).",
                col_start=_col_offset(node),
                col_end=_end_col_offset(node),
            )
        )
    return diagnostics


def unused_import_diagnostics(syntax_tree: ast.AST, file_path: Path) -> list[CodeDiagnostic]:
    imported_names: dict[str, tuple[int, int | None, int | None]] = {}
    used_names: set[str] = set()
    for node in ast.walk(syntax_tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names[alias.asname or alias.name.split(".")[0]] = (
                    int(node.lineno),
                    _col_offset(node),
                    _end_col_offset(node),
                )
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported_names[alias.asname or alias.name] = (
                    int(node.lineno),
                    _col_offset(node),
                    _end_col_offset(node),
                )
        elif isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load):
                used_names.add(node.id)

    diagnostics: list[CodeDiagnostic] = []
    for imported_name, (line_number, cs, ce) in sorted(imported_names.items(), key=lambda item: item[1][0]):
        if imported_name in used_names:
            continue
        diagnostics.append(
            CodeDiagnostic(
                code="PY220",
                severity=DiagnosticSeverity.WARNING,
                file_path=str(file_path),
                line_number=line_number,
                message=f"Imported name '{imported_name}' is not used.",
                col_start=cs,
                col_end=ce,
            )
        )
    return diagnostics


def duplicate_import_diagnostics(syntax_tree: ast.AST, file_path: Path) -> list[CodeDiagnostic]:
    diagnostics: list[CodeDiagnostic] = []
    seen_imports: dict[tuple[str, int, str, tuple[tuple[str, str], ...]], int] = {}
    body = getattr(syntax_tree, "body", [])
    for node in body:
        if isinstance(node, ast.Import):
            aliases = tuple(sorted((alias.name, alias.asname or "") for alias in node.names))
            key = ("import", 0, "", aliases)
        elif isinstance(node, ast.ImportFrom):
            aliases = tuple(sorted((alias.name, alias.asname or "") for alias in node.names))
            key = ("from", int(node.level), node.module or "", aliases)
        else:
            continue
        previous_line = seen_imports.get(key)
        if previous_line is None:
            seen_imports[key] = int(node.lineno)
            continue
        diagnostics.append(
            CodeDiagnostic(
                code="PY221",
                severity=DiagnosticSeverity.WARNING,
                file_path=str(file_path),
                line_number=int(node.lineno),
                message=f"Duplicate import statement (first seen at line {previous_line}).",
                col_start=_col_offset(node),
                col_end=_end_col_offset(node),
            )
        )
    return diagnostics


def unreachable_statement_diagnostics(syntax_tree: ast.AST, file_path: Path) -> list[CodeDiagnostic]:
    diagnostics: list[CodeDiagnostic] = []
    for node in ast.walk(syntax_tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = node.body
        for index, statement in enumerate(body[:-1]):
            if not isinstance(statement, (ast.Return, ast.Raise)):
                continue
            next_statement = body[index + 1]
            diagnostics.append(
                CodeDiagnostic(
                    code="PY230",
                    severity=DiagnosticSeverity.INFO,
                    file_path=str(file_path),
                    line_number=int(next_statement.lineno),
                    message="Statement is unreachable because previous statement exits function.",
                    col_start=_col_offset(next_statement),
                    col_end=_end_col_offset(next_statement),
                )
            )
    return diagnostics


def _col_offset(node: ast.AST) -> int | None:
    value = getattr(node, "col_offset", None)
    return int(value) if value is not None else None


def _end_col_offset(node: ast.AST) -> int | None:
    value = getattr(node, "end_col_offset", None)
    return int(value) if value is not None else None
