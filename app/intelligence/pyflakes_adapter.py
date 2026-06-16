"""Pyflakes linter integration for Python file diagnostics."""

from __future__ import annotations

import ast
import logging
import sys
from pathlib import Path
from typing import Any

from app.intelligence.diagnostics_models import CodeDiagnostic, DiagnosticSeverity

_logger = logging.getLogger(__name__)
_pyflakes_import_warning_emitted = False


def pyflakes_diagnostics(source: str, file_path: Path) -> list[CodeDiagnostic]:
    """Run pyflakes on source and map messages to CodeDiagnostic records."""
    checker = _create_pyflakes_checker(source, file_path)
    if checker is None:
        return []
    diagnostics: list[CodeDiagnostic] = []
    for message in getattr(checker, "messages", []):
        diagnostic = diagnostic_from_pyflakes_message(message, file_path)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
    return diagnostics


def diagnostic_from_pyflakes_message(message: Any, file_path: Path) -> CodeDiagnostic | None:
    """Map a pyflakes message object to a CodeDiagnostic."""
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


def _ensure_vendor_path_on_sys_path() -> None:
    vendor_dir = Path(__file__).resolve().parents[2] / "vendor"
    vendor_text = str(vendor_dir)
    if vendor_text not in sys.path:
        sys.path.insert(0, vendor_text)
