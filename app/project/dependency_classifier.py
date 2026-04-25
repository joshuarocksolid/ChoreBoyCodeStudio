"""Single source of truth for Python module classification.

This module unifies the two slightly different classifier implementations that
used to live side by side in :mod:`app.intelligence.diagnostics_service` and
:mod:`app.packaging.dependency_audit`:

- The diagnostics linter only needs a yes/no answer for "is this import
  resolvable" (used to flag unresolved imports in the editor).
- The packaging audit needs a labeled classification (``stdlib``,
  ``first_party``, ``vendored``, ``vendored_native``, ``runtime``,
  ``missing``) so it can produce per-import audit records and runtime issues.

Both flavors share the same primitives:

- :data:`STDLIB_TOP_LEVELS` — defensive fallback list of Python 3.9 stdlib
  top-level module names. Used when no runtime probe inventory is available.
- :data:`COMPILED_EXTENSION_SUFFIXES` — file extensions that imply a compiled
  Python extension module (``.so``, ``.pyd``, ``.dll``, ``.dylib``).
- :func:`has_compiled_extension_candidate` — looks for an extension file
  matching ``top_level`` directly under ``base`` or inside a ``base/top_level``
  package directory.
- :func:`resolve_project_import` — low-level filesystem probe used for the
  ``project`` / ``vendor`` file lookup (re-exported from
  :mod:`app.intelligence.import_resolver`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.intelligence.import_resolver import resolve_project_import
from app.intelligence.runtime_import_probe import is_runtime_module_importable

# Defensive fallback: well-known Python 3.9 stdlib top-level module names.
# Used when the runtime probe has not yet completed or failed, so common
# imports like ``os``, ``sys``, ``json`` are never flagged as unresolved.
# This is intentionally a broad but not exhaustive set; the runtime probe
# provides the authoritative list once available.
STDLIB_TOP_LEVELS: frozenset[str] = frozenset({
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
    "timeit", "tkinter", "token", "tokenize", "trace",
    "traceback", "tracemalloc", "tty", "turtle", "types", "typing",
    "unicodedata", "unittest", "urllib", "uuid",
    "venv",
    "warnings", "wave", "weakref", "webbrowser",
    "wsgiref",
    "xml", "xmlrpc",
    "zipfile", "zipimport", "zlib", "zoneinfo",
})

COMPILED_EXTENSION_SUFFIXES: tuple[str, ...] = (".so", ".pyd", ".dll", ".dylib")

# Module categories produced by :func:`classify_module`.
CATEGORY_STDLIB = "stdlib"
CATEGORY_FIRST_PARTY = "first_party"
CATEGORY_VENDORED = "vendored"
CATEGORY_VENDORED_NATIVE = "vendored_native"
CATEGORY_RUNTIME = "runtime"
CATEGORY_MISSING = "missing"


@dataclass(frozen=True)
class ClassifiedModule:
    """Classification result for one absolute Python import."""

    module_name: str
    top_level: str
    category: str
    resolved_path: str | None = None


def has_compiled_extension_candidate(base: Path, top_level: str) -> bool:
    """Return True if *base* looks like it ships a compiled extension for *top_level*.

    Checks for ``top_level*.{so,pyd,dll,dylib}`` directly under ``base`` and
    for ``*.{so,pyd,dll,dylib}`` inside a ``base/top_level`` package directory.
    """
    if not top_level or not base.exists():
        return False
    for suffix in COMPILED_EXTENSION_SUFFIXES:
        if any(base.glob(f"{top_level}*{suffix}")):
            return True
        package_dir = base / top_level
        if package_dir.exists() and any(package_dir.glob(f"*{suffix}")):
            return True
    return False


def classify_module(
    *,
    project_root: Path | str,
    module_name: str,
    known_runtime_modules: frozenset[str] | None = None,
    allow_runtime_import_probe: bool = False,
) -> ClassifiedModule:
    """Classify an absolute Python import name against project + runtime layers.

    Resolution order:

    1. ``STDLIB_TOP_LEVELS`` -> ``stdlib``.
    2. Filesystem probe under ``project_root`` and ``project_root/vendor``
       via :func:`resolve_project_import`. ``vendor/`` hits with compiled
       extension artifacts upgrade to ``vendored_native``.
    3. ``known_runtime_modules`` membership -> ``runtime``.
    4. Optional :func:`is_runtime_module_importable` probe -> ``runtime``.
    5. ``vendor/`` compiled extension artifacts even when no Python file
       resolves -> ``vendored_native``.
    6. Otherwise ``missing``.

    Mirrors the existing packaging audit semantics so the audit adapter is a
    direct one-to-one mapping onto :class:`DependencyAuditRecord` strings.
    """
    root = Path(project_root).expanduser().resolve()
    top_level = module_name.split(".")[0].strip()

    if top_level in STDLIB_TOP_LEVELS:
        return ClassifiedModule(
            module_name=module_name,
            top_level=top_level,
            category=CATEGORY_STDLIB,
        )

    resolution = resolve_project_import(
        str(root),
        module_name,
        known_runtime_modules=frozenset(),
        allow_runtime_import_probe=False,
    )
    if resolution.is_resolved and resolution.resolved_path:
        resolved_path = Path(resolution.resolved_path).resolve()
        is_vendored = "vendor" in resolved_path.parts
        if is_vendored and has_compiled_extension_candidate(root / "vendor", top_level):
            return ClassifiedModule(
                module_name=module_name,
                top_level=top_level,
                category=CATEGORY_VENDORED_NATIVE,
                resolved_path=str(resolved_path),
            )
        return ClassifiedModule(
            module_name=module_name,
            top_level=top_level,
            category=CATEGORY_VENDORED if is_vendored else CATEGORY_FIRST_PARTY,
            resolved_path=str(resolved_path),
        )

    if known_runtime_modules and top_level in known_runtime_modules:
        return ClassifiedModule(
            module_name=module_name,
            top_level=top_level,
            category=CATEGORY_RUNTIME,
        )

    if allow_runtime_import_probe and top_level and is_runtime_module_importable(top_level):
        return ClassifiedModule(
            module_name=module_name,
            top_level=top_level,
            category=CATEGORY_RUNTIME,
        )

    if has_compiled_extension_candidate(root / "vendor", top_level):
        return ClassifiedModule(
            module_name=module_name,
            top_level=top_level,
            category=CATEGORY_VENDORED_NATIVE,
        )

    return ClassifiedModule(
        module_name=module_name,
        top_level=top_level,
        category=CATEGORY_MISSING,
    )


def is_module_resolvable(
    project_root: Path | str,
    module_name: str,
    *,
    known_runtime_modules: frozenset[str] | None = None,
    allow_runtime_import_probe: bool = False,
) -> bool:
    """Return True if the import looks resolvable for the editor diagnostics linter.

    Diagnostics has a deliberately stricter semantic than the packaging audit:
    when ``known_runtime_modules`` is provided, it is treated as the
    authoritative runtime inventory and ``STDLIB_TOP_LEVELS`` is bypassed.
    This avoids masking runtime-specific stdlib reductions (e.g. when AppRun
    advertises a slimmer subset than CPython 3.9).
    """
    top_level = module_name.split(".")[0]
    effective_modules = known_runtime_modules if known_runtime_modules else STDLIB_TOP_LEVELS
    if top_level in effective_modules:
        return True
    root = Path(project_root).expanduser().resolve()
    resolution = resolve_project_import(
        str(root),
        module_name,
        known_runtime_modules=frozenset(),
        allow_runtime_import_probe=False,
    )
    if resolution.is_resolved:
        return True
    if allow_runtime_import_probe and is_runtime_module_importable(top_level):
        return True
    return False
