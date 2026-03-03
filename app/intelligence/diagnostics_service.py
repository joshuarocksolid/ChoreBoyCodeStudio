"""Diagnostics helpers for Python projects."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from app.core import constants
from app.intelligence.runtime_import_probe import is_runtime_module_importable

# Defensive fallback: well-known Python 3.x stdlib top-level module names.
# Used when the runtime probe has not yet completed or failed, so that
# common imports like ``os``, ``sys``, ``json`` are never flagged as
# unresolved.  This is intentionally a broad but not exhaustive set —
# the runtime probe provides the authoritative list once available.
_STDLIB_FALLBACK: frozenset[str] = frozenset({
    "abc", "argparse", "array", "ast", "asyncio", "atexit",
    "base64", "binascii", "bisect", "builtins", "bz2",
    "cProfile", "calendar", "cmath", "cmd", "code", "codecs",
    "codeop", "collections", "colorsys", "compileall", "concurrent",
    "configparser", "contextlib", "contextvars", "copy", "copyreg", "csv",
    "ctypes", "curses",
    "dataclasses", "datetime", "dbm", "decimal", "difflib", "dis", "doctest",
    "email", "encodings", "enum", "errno",
    "faulthandler", "fcntl", "filecmp", "fileinput", "fnmatch",
    "fractions", "ftplib", "functools",
    "gc", "getopt", "getpass", "gettext", "glob", "graphlib", "grp", "gzip",
    "hashlib", "heapq", "hmac", "html", "http",
    "idlelib", "imaplib", "importlib", "inspect", "io", "ipaddress",
    "itertools",
    "json",
    "keyword",
    "linecache", "locale", "logging", "lzma",
    "mailbox", "marshal", "math", "mimetypes", "mmap", "modulefinder",
    "multiprocessing",
    "netrc", "numbers",
    "operator", "optparse", "os",
    "pathlib", "pdb", "pickle", "pickletools", "pkgutil", "platform",
    "plistlib", "poplib", "posixpath", "pprint", "profile", "pstats",
    "pty", "pwd", "py_compile", "pyclbr", "pydoc",
    "queue", "quopri",
    "random", "re", "readline", "reprlib", "resource", "rlcompleter",
    "runpy",
    "sched", "secrets", "select", "selectors", "shelve", "shlex",
    "shutil", "signal", "site", "smtplib", "socket", "socketserver",
    "sqlite3", "ssl", "stat", "statistics", "string", "stringprep",
    "struct", "subprocess", "symtable", "sys", "sysconfig", "syslog",
    "tarfile", "tempfile", "termios", "textwrap", "threading", "time",
    "timeit", "tkinter", "token", "tokenize", "tomllib", "trace",
    "traceback", "tracemalloc", "tty", "turtle", "types", "typing",
    "unicodedata", "unittest", "urllib", "uuid",
    "venv",
    "warnings", "wave", "weakref", "webbrowser",
    "wsgiref",
    "xml", "xmlrpc",
    "zipfile", "zipimport", "zlib", "zoneinfo",
})


@dataclass(frozen=True)
class ImportDiagnostic:
    """Unresolved import diagnostic record."""

    file_path: str
    line_number: int
    message: str


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
    for file_path in sorted(root.rglob("*.py")):
        if constants.PROJECT_META_DIRNAME in file_path.parts:
            continue
        override = resolved_overrides.get(str(file_path.resolve()))
        diagnostics.extend(
            _diagnostics_for_file(
                root,
                file_path,
                source=override,
                known_runtime_modules=known_runtime_modules,
                allow_runtime_import_probe=allow_runtime_import_probe,
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
        col_end = (int(exc.end_offset) - 1) if getattr(exc, "end_offset", None) is not None else None
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
            )
        )
    diagnostics.sort(key=lambda item: (item.file_path, item.line_number, item.code))
    return diagnostics


def _diagnostics_for_file(
    project_root: Path,
    file_path: Path,
    *,
    source: str | None = None,
    known_runtime_modules: frozenset[str] | None = None,
    allow_runtime_import_probe: bool = False,
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


def _is_import_resolvable(
    project_root: Path,
    module_name: str,
    known_runtime_modules: frozenset[str] | None = None,
    allow_runtime_import_probe: bool = False,
) -> bool:
    top_level = module_name.split(".")[0]
    effective_modules = known_runtime_modules if known_runtime_modules else _STDLIB_FALLBACK
    if top_level in effective_modules:
        return True
    module_path = Path(*module_name.split("."))
    for base in (project_root, project_root / "vendor"):
        if (base / module_path).with_suffix(".py").exists():
            return True
        if (base / module_path / "__init__.py").exists():
            return True
    if allow_runtime_import_probe and is_runtime_module_importable(top_level):
        return True
    return False


def _unresolved_import_diagnostics(
    project_root: Path,
    file_path: Path,
    syntax_tree: ast.AST,
    *,
    known_runtime_modules: frozenset[str] | None = None,
    allow_runtime_import_probe: bool = False,
) -> list[CodeDiagnostic]:
    diagnostics: list[CodeDiagnostic] = []
    for node in ast.walk(syntax_tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_import_resolvable(
                    project_root,
                    alias.name,
                    known_runtime_modules,
                    allow_runtime_import_probe=allow_runtime_import_probe,
                ):
                    continue
                diagnostics.append(
                    CodeDiagnostic(
                        code="PY200",
                        severity=DiagnosticSeverity.ERROR,
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
            if _is_import_resolvable(
                project_root,
                node.module,
                known_runtime_modules,
                allow_runtime_import_probe=allow_runtime_import_probe,
            ):
                continue
            diagnostics.append(
                CodeDiagnostic(
                    code="PY200",
                    severity=DiagnosticSeverity.ERROR,
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
