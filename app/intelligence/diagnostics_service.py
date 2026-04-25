"""Diagnostics helpers for Python projects."""

from __future__ import annotations

import ast
import logging
from dataclasses import replace
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import sys
from typing import Any, Mapping

from app.core import constants
from app.intelligence.lint_profile import (
    LINT_SEVERITY_ERROR,
    LINT_SEVERITY_INFO,
    resolve_lint_rule_settings,
)
from app.intelligence.runtime_import_probe import (
    probe_runtime_module_importability,
)
from app.project.dependency_classifier import (
    has_compiled_extension_candidate,
    is_module_resolvable,
)
from app.project.file_inventory import iter_python_files

_logger = logging.getLogger(__name__)
_pyflakes_import_warning_emitted = False


@dataclass(frozen=True)
class ImportDiagnostic:
    """Unresolved import diagnostic record."""

    file_path: str
    line_number: int
    message: str


@dataclass(frozen=True)
class ImportExplanation:
    """Structured explanation for an unresolved import."""

    module_name: str
    kind: str
    summary: str
    why_it_happened: str
    next_steps: list[str]
    evidence: dict[str, Any]


class DiagnosticSeverity(str, Enum):
    """Severity levels for editor diagnostics."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class CodeDiagnostic:
    """Structured diagnostic used by file linting workflows."""

    code: str
    severity: DiagnosticSeverity
    file_path: str
    line_number: int
    message: str
    col_start: int | None = None
    col_end: int | None = None


def find_unresolved_imports(
    project_root: str,
    *,
    source_overrides: dict[str, str] | None = None,
    known_runtime_modules: frozenset[str] | None = None,
    allow_runtime_import_probe: bool = False,
    lint_rule_overrides: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[ImportDiagnostic]:
    """Find unresolved project-local imports in Python files.

    When *source_overrides* is provided it maps absolute file paths to
    in-memory source text (e.g. unsaved editor buffers).  Overridden
    content is used instead of reading from disk so that unsaved edits
    are included in the analysis.
    """
    root = Path(project_root).expanduser().resolve()
    resolved_overrides: dict[str, str] = {}
    if source_overrides:
        for p, src in source_overrides.items():
            resolved_overrides[str(Path(p).expanduser().resolve())] = src
    diagnostics: list[ImportDiagnostic] = []
    for file_path in iter_python_files(root):
        override = resolved_overrides.get(str(file_path.resolve()))
        diagnostics.extend(
            _diagnostics_for_file(
                root,
                file_path,
                source=override,
                known_runtime_modules=known_runtime_modules,
                allow_runtime_import_probe=allow_runtime_import_probe,
                lint_rule_overrides=lint_rule_overrides,
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
        diagnostics.extend(_duplicate_definition_diagnostics(syntax_tree, path))
        diagnostics.extend(_duplicate_import_diagnostics(syntax_tree, path))
        diagnostics.extend(_unused_import_diagnostics(syntax_tree, path))
        diagnostics.extend(_unreachable_statement_diagnostics(syntax_tree, path))
        if project_root:
            diagnostics.extend(
                _unresolved_import_diagnostics(
                    Path(project_root).expanduser().resolve(), path, syntax_tree,
                    known_runtime_modules=known_runtime_modules,
                    allow_runtime_import_probe=allow_runtime_import_probe,
                    lint_rule_overrides=lint_rule_overrides,
                )
            )
    diagnostics = _apply_lint_rule_profile(diagnostics, lint_rule_overrides)
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

    diagnostics: list[ImportDiagnostic] = []
    for diagnostic in _unresolved_import_diagnostics(
        project_root,
        file_path.resolve(),
        tree,
        known_runtime_modules=known_runtime_modules,
        allow_runtime_import_probe=allow_runtime_import_probe,
        lint_rule_overrides=lint_rule_overrides,
    ):
        diagnostics.append(
            ImportDiagnostic(
                file_path=diagnostic.file_path,
                line_number=diagnostic.line_number,
                message=diagnostic.message,
            )
        )
    return diagnostics


def _col_offset(node: ast.AST) -> int | None:
    value = getattr(node, "col_offset", None)
    return int(value) if value is not None else None


def _end_col_offset(node: ast.AST) -> int | None:
    value = getattr(node, "end_col_offset", None)
    return int(value) if value is not None else None


def explain_unresolved_import(
    project_root: str,
    module_name: str,
    *,
    known_runtime_modules: frozenset[str] | None = None,
    allow_runtime_import_probe: bool = False,
) -> ImportExplanation:
    """Classify an unresolved import into a user-facing explanation."""
    root = Path(project_root).expanduser().resolve()
    vendor_root = root / "vendor"
    top_level = module_name.split(".")[0].strip()
    probe_result = None
    if allow_runtime_import_probe and top_level:
        probe_result = probe_runtime_module_importability(top_level)

    project_prefix_exists = _module_path_prefix_exists(root, module_name)
    vendor_prefix_exists = _module_path_prefix_exists(vendor_root, module_name)
    compiled_extension_candidate = has_compiled_extension_candidate(root, top_level) or has_compiled_extension_candidate(
        vendor_root,
        top_level,
    )
    evidence = {
        "module_name": module_name,
        "top_level": top_level,
        "project_prefix_exists": project_prefix_exists,
        "vendor_prefix_exists": vendor_prefix_exists,
        "vendor_dir_exists": vendor_root.exists(),
        "compiled_extension_candidate": compiled_extension_candidate,
    }
    if probe_result is not None:
        evidence["runtime_probe_reason"] = probe_result.failure_reason
        evidence["runtime_probe_detail"] = probe_result.detail
        evidence["runtime_path"] = probe_result.runtime_path

    if project_prefix_exists:
        return ImportExplanation(
            module_name=module_name,
            kind="project_module_missing",
            summary=f"Project module path is incomplete or missing: {module_name}",
            why_it_happened=(
                "The import points at code that should live inside the project tree, but the full module path cannot be resolved from the current files."
            ),
            next_steps=[
                "Check the module/package file names inside the project.",
                "Add missing `__init__.py` files where package imports are expected.",
                "Update the import path if the module was moved or renamed.",
            ],
            evidence=evidence,
        )

    if compiled_extension_candidate:
        return ImportExplanation(
            module_name=module_name,
            kind="compiled_extension_unknown",
            summary=f"Compiled dependency may not be compatible with the runtime: {module_name}",
            why_it_happened=(
                "The import name matches a compiled extension candidate, and compiled modules can fail on ChoreBoy when the Python/AppRun build does not match."
            ),
            next_steps=[
                "Prefer a pure-Python dependency when possible.",
                "If this must be compiled, verify it targets the same runtime and Python ABI as the shipped AppRun environment.",
                "Re-run import analysis after replacing or rebuilding the dependency.",
            ],
            evidence=evidence,
        )

    if (
        probe_result is not None
        and not probe_result.is_importable
        and probe_result.failure_reason == "import_error"
        and _looks_like_runtime_specific_module(top_level)
    ):
        return ImportExplanation(
            module_name=module_name,
            kind="runtime_module_unavailable",
            summary=f"Module is not available in the shipped runtime: {module_name}",
            why_it_happened=(
                "The editor checked the top-level import in the target runtime process and it did not import successfully there."
            ),
            next_steps=[
                "Do not assume this module exists just because it imports on another machine or Python install.",
                "Vendor the dependency under `vendor/` if the workflow allows it.",
                "Or change the code to use modules known to exist in the AppRun runtime.",
            ],
            evidence=evidence,
        )

    return ImportExplanation(
        module_name=module_name,
        kind="vendored_dependency_missing",
        summary=f"Dependency is not present in the project or vendored runtime: {module_name}",
        why_it_happened=(
            "The import is not resolved from project files, vendored dependencies, or known runtime modules."
        ),
        next_steps=[
            "Vendor the dependency under `vendor/` if it is a third-party package.",
            "If it should be part of the project, add the missing module/package files under the project root.",
            "Re-run import analysis after updating the project or vendored dependency tree.",
        ],
        evidence=evidence,
    )


def _module_path_prefix_exists(base: Path, module_name: str) -> bool:
    if not base.exists():
        return False
    probe_base = base
    for part in [segment for segment in module_name.split(".") if segment.strip()]:
        if (probe_base / f"{part}.py").exists() or (probe_base / part).exists():
            return True
        probe_base = probe_base / part
    return False


def _looks_like_runtime_specific_module(top_level: str) -> bool:
    if not top_level:
        return False
    if top_level[0].isupper():
        return True
    return top_level.startswith("PySide")


def _unresolved_import_diagnostics(
    project_root: Path,
    file_path: Path,
    syntax_tree: ast.AST,
    *,
    known_runtime_modules: frozenset[str] | None = None,
    allow_runtime_import_probe: bool = False,
    lint_rule_overrides: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[CodeDiagnostic]:
    is_enabled, severity = resolve_lint_rule_settings("PY200", lint_rule_overrides)
    if not is_enabled:
        return []
    diagnostic_severity = _severity_from_profile_value(severity)
    diagnostics: list[CodeDiagnostic] = []
    for node in ast.walk(syntax_tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if is_module_resolvable(
                    project_root,
                    alias.name,
                    known_runtime_modules=known_runtime_modules,
                    allow_runtime_import_probe=allow_runtime_import_probe,
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
            if node.module is None or node.level > 0:
                continue
            if is_module_resolvable(
                project_root,
                node.module,
                known_runtime_modules=known_runtime_modules,
                allow_runtime_import_probe=allow_runtime_import_probe,
            ):
                continue
            diagnostics.append(
                CodeDiagnostic(
                    code="PY200",
                    severity=diagnostic_severity,
                    file_path=str(file_path),
                    line_number=int(node.lineno),
                    message=f"Unresolved import: {node.module}",
                    col_start=_col_offset(node),
                    col_end=_end_col_offset(node),
                )
            )
    return diagnostics


def _duplicate_definition_diagnostics(syntax_tree: ast.AST, file_path: Path) -> list[CodeDiagnostic]:
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


def _unused_import_diagnostics(syntax_tree: ast.AST, file_path: Path) -> list[CodeDiagnostic]:
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


def _duplicate_import_diagnostics(syntax_tree: ast.AST, file_path: Path) -> list[CodeDiagnostic]:
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


def _unreachable_statement_diagnostics(syntax_tree: ast.AST, file_path: Path) -> list[CodeDiagnostic]:
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


def _apply_lint_rule_profile(
    diagnostics: list[CodeDiagnostic],
    lint_rule_overrides: Mapping[str, Mapping[str, Any]] | None,
) -> list[CodeDiagnostic]:
    if not diagnostics:
        return diagnostics
    profiled: list[CodeDiagnostic] = []
    for diagnostic in diagnostics:
        is_enabled, severity = resolve_lint_rule_settings(diagnostic.code, lint_rule_overrides)
        if not is_enabled:
            continue
        target_severity = _severity_from_profile_value(severity)
        if diagnostic.severity == target_severity:
            profiled.append(diagnostic)
            continue
        profiled.append(replace(diagnostic, severity=target_severity))
    return profiled


def _severity_from_profile_value(value: str) -> DiagnosticSeverity:
    if value == LINT_SEVERITY_ERROR:
        return DiagnosticSeverity.ERROR
    if value == LINT_SEVERITY_INFO:
        return DiagnosticSeverity.INFO
    return DiagnosticSeverity.WARNING


def _normalize_linter_provider(selected_linter: str) -> str:
    if selected_linter == constants.LINTER_PROVIDER_PYFLAKES:
        return constants.LINTER_PROVIDER_PYFLAKES
    return constants.LINTER_PROVIDER_DEFAULT


def _pyflakes_diagnostics(source: str, file_path: Path) -> list[CodeDiagnostic]:
    checker = _create_pyflakes_checker(source, file_path)
    if checker is None:
        return []
    diagnostics: list[CodeDiagnostic] = []
    for message in getattr(checker, "messages", []):
        diagnostic = _diagnostic_from_pyflakes_message(message, file_path)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
    return diagnostics


def _create_pyflakes_checker(source: str, file_path: Path) -> Any | None:
    global _pyflakes_import_warning_emitted
    _ensure_vendor_path_on_sys_path()
    try:
        from pyflakes import checker as pyflakes_checker  # type: ignore[import-not-found]
    except ImportError:
        if not _pyflakes_import_warning_emitted:
            _pyflakes_import_warning_emitted = True
            _logger.warning(
                "Pyflakes linter selected but pyflakes is not importable "
                "(add vendor/pyflakes per docs or install pyflakes)."
            )
        return None
    try:
        syntax_tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return None
    return pyflakes_checker.Checker(syntax_tree, str(file_path))


def _diagnostic_from_pyflakes_message(message: Any, file_path: Path) -> CodeDiagnostic | None:
    message_type = type(message).__name__
    code = "PY399"
    severity = DiagnosticSeverity.WARNING
    if message_type == "UndefinedName":
        code = "PY301"
        severity = DiagnosticSeverity.ERROR
    elif message_type == "UndefinedLocal":
        code = "PY302"
        severity = DiagnosticSeverity.ERROR
    elif message_type == "RedefinedWhileUnused":
        code = "PY303"
    elif message_type == "ImportShadowedByLoopVar":
        code = "PY304"
    elif message_type == "ImportStarUsed":
        code = "PY305"
    elif message_type == "UnusedImport":
        code = "PY220"

    line_number = int(getattr(message, "lineno", 1))
    col_start_value = getattr(message, "col", None)
    col_start = int(col_start_value) if col_start_value is not None else None
    col_end = None
    if col_start is not None:
        message_args = getattr(message, "message_args", ())
        if message_args and isinstance(message_args[0], str):
            col_end = col_start + len(message_args[0])
        else:
            col_end = col_start + 1
    raw_text = str(message)
    text = raw_text.strip()
    if not text:
        return None
    return CodeDiagnostic(
        code=code,
        severity=severity,
        file_path=str(file_path),
        line_number=max(1, line_number),
        message=text,
        col_start=col_start,
        col_end=col_end,
    )


def _ensure_vendor_path_on_sys_path() -> None:
    vendor_dir = Path(__file__).resolve().parents[2] / "vendor"
    vendor_text = str(vendor_dir)
    if vendor_text not in sys.path:
        sys.path.insert(0, vendor_text)
