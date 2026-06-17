"""Single source of truth for Python module classification.

This module unifies classification for packaging audit, editor diagnostics,
and dependency ingestion. Both :func:`classify_module` and
:func:`is_module_resolvable` delegate to the same :func:`_classify_import`
pipeline; diagnostics uses inventory-authoritative stdlib policy when a loaded
runtime inventory is supplied.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.core.models import ProjectMetadata
from app.project.import_layout import (
    ProjectImportLayout,
    resolve_import_from_module,
    resolve_project_import_layout,
)
from app.project.import_resolution import resolve_project_import
from app.project.native_extension_scan import (
    COMPILED_EXTENSION_SUFFIXES,
    import_resolves_to_native,
)
from app.project.runtime_import_probe import is_runtime_module_importable

# Defensive fallback: well-known Python 3.9 stdlib top-level module names.
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

# Module categories produced by :func:`classify_module`.
CATEGORY_STDLIB = "stdlib"
CATEGORY_FIRST_PARTY = "first_party"
CATEGORY_FIRST_PARTY_RELATIVE = "first_party_relative"
CATEGORY_VENDORED = "vendored"
CATEGORY_VENDORED_NATIVE = "vendored_native"
CATEGORY_RUNTIME = "runtime"
CATEGORY_MISSING = "missing"
CATEGORY_MISSING_RELATIVE = "missing_relative"

RuntimeInventoryState = Literal["unknown", "empty", "loaded"]


@dataclass(frozen=True)
class RuntimeModuleInventory:
    """Tri-state runtime module inventory for classification policy."""

    state: RuntimeInventoryState
    modules: frozenset[str]

    @classmethod
    def unknown(cls) -> RuntimeModuleInventory:
        return cls(state="unknown", modules=frozenset())

    @classmethod
    def from_optional_frozenset(cls, modules: frozenset[str] | None) -> RuntimeModuleInventory:
        if modules is None:
            return cls.unknown()
        if len(modules) == 0:
            return cls(state="empty", modules=frozenset())
        return cls(state="loaded", modules=modules)


@dataclass(frozen=True)
class ClassifiedModule:
    """Classification result for one absolute Python import."""

    module_name: str
    top_level: str
    category: str
    resolved_path: str | None = None


def has_compiled_extension_candidate(base: Path, top_level: str) -> bool:
    """Return True if *base* ships a compiled extension for *top_level*."""
    return import_resolves_to_native(base, top_level)


def _classify_import(
    *,
    project_root: Path,
    module_name: str,
    inventory: RuntimeModuleInventory,
    allow_runtime_import_probe: bool,
    metadata: ProjectMetadata | None,
    layout: ProjectImportLayout,
) -> ClassifiedModule:
    top_level = module_name.split(".")[0].strip()

    if inventory.state != "loaded" and top_level in STDLIB_TOP_LEVELS:
        return ClassifiedModule(
            module_name=module_name,
            top_level=top_level,
            category=CATEGORY_STDLIB,
        )

    resolution = resolve_project_import(
        str(project_root),
        module_name,
        known_runtime_modules=inventory.modules if inventory.state == "loaded" else frozenset(),
        allow_runtime_import_probe=False,
        metadata=metadata,
        layout=layout,
    )
    if resolution.is_resolved and resolution.resolved_path:
        resolved_path = Path(resolution.resolved_path).resolve()
        is_vendored = "vendor" in resolved_path.parts
        if is_vendored and has_compiled_extension_candidate(project_root / "vendor", top_level):
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

    if inventory.state == "loaded" and top_level in inventory.modules:
        return ClassifiedModule(
            module_name=module_name,
            top_level=top_level,
            category=CATEGORY_RUNTIME,
        )

    if inventory.state != "loaded" and top_level in STDLIB_TOP_LEVELS:
        return ClassifiedModule(
            module_name=module_name,
            top_level=top_level,
            category=CATEGORY_STDLIB,
        )

    if allow_runtime_import_probe and top_level and is_runtime_module_importable(top_level):
        return ClassifiedModule(
            module_name=module_name,
            top_level=top_level,
            category=CATEGORY_RUNTIME,
        )

    if has_compiled_extension_candidate(project_root / "vendor", top_level):
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


def classify_module(
    *,
    project_root: Path | str,
    module_name: str,
    known_runtime_modules: frozenset[str] | None = None,
    runtime_inventory: RuntimeModuleInventory | None = None,
    allow_runtime_import_probe: bool = False,
    metadata: ProjectMetadata | None = None,
    layout: ProjectImportLayout | None = None,
) -> ClassifiedModule:
    """Classify an absolute Python import name against project + runtime layers."""
    root = Path(project_root).expanduser().resolve()
    inventory = runtime_inventory or RuntimeModuleInventory.from_optional_frozenset(
        known_runtime_modules
    )
    resolved_layout = layout or resolve_project_import_layout(root, metadata)
    return _classify_import(
        project_root=root,
        module_name=module_name,
        inventory=inventory,
        allow_runtime_import_probe=allow_runtime_import_probe,
        metadata=metadata,
        layout=resolved_layout,
    )


def classify_relative_import(
    *,
    project_root: Path | str,
    file_path: Path,
    module_name: str,
    level: int,
    metadata: ProjectMetadata | None = None,
    layout: ProjectImportLayout | None = None,
) -> ClassifiedModule:
    """Classify a relative import from *file_path* using canonical layout resolution."""
    root = Path(project_root).expanduser().resolve()
    resolved_layout = layout or resolve_project_import_layout(root, metadata)
    display_name = f".{module_name}" if module_name else "." * level
    top_level = module_name.split(".")[0].strip() if module_name else ""

    resolved_module = resolve_import_from_module(
        file_path,
        module_name or None,
        level,
        layout=resolved_layout,
    )
    if resolved_module is None:
        return ClassifiedModule(
            module_name=display_name,
            top_level=top_level,
            category=CATEGORY_MISSING_RELATIVE,
        )

    absolute = classify_module(
        project_root=root,
        module_name=resolved_module,
        metadata=metadata,
        layout=resolved_layout,
    )
    if absolute.category == CATEGORY_MISSING:
        return ClassifiedModule(
            module_name=display_name,
            top_level=top_level,
            category=CATEGORY_MISSING_RELATIVE,
        )
    return ClassifiedModule(
        module_name=display_name,
        top_level=top_level,
        category=CATEGORY_FIRST_PARTY_RELATIVE,
        resolved_path=absolute.resolved_path,
    )


def is_module_resolvable(
    project_root: Path | str,
    module_name: str,
    *,
    known_runtime_modules: frozenset[str] | None = None,
    runtime_inventory: RuntimeModuleInventory | None = None,
    allow_runtime_import_probe: bool = False,
    metadata: ProjectMetadata | None = None,
    layout: ProjectImportLayout | None = None,
) -> bool:
    """Return True if the import looks resolvable for editor diagnostics."""
    classification = classify_module(
        project_root=project_root,
        module_name=module_name,
        known_runtime_modules=known_runtime_modules,
        runtime_inventory=runtime_inventory,
        allow_runtime_import_probe=allow_runtime_import_probe,
        metadata=metadata,
        layout=layout,
    )
    return classification.category not in {CATEGORY_MISSING, CATEGORY_MISSING_RELATIVE}
