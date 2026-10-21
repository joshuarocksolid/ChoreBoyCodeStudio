"""Move CBCS Qt imports onto ``app.qt`` and ``exec_`` calls onto ``exec_qt``.

Usage::

    python3 tools/qt_codemod.py [--check] [PATH ...]

With no paths it covers ``app/``, ``tests/``, ``testing/`` and ``run_editor.py``.
``app/qt/`` itself is skipped. ``--check`` exits 1 and lists what is left
instead of writing. The tool is idempotent.

Rewrites:

- ``from PySide2.QtX import a, b`` -> ``from app.qt.QtX import a, b``
- ``from PySide2 import QtX`` -> ``from app.qt import QtX``
- ``import PySide2.QtX as m`` -> ``from app.qt import QtX as m``
- ``import_module("PySide2.QtX")`` and ``importorskip("PySide2.QtX")`` -> ``"app.qt.QtX"``
- ``obj.exec_(args)`` -> ``exec_qt(obj, args)`` plus ``from app.qt.qt_compat import exec_qt``

A bare ``import PySide2`` or ``import PySide2.QtX`` without an alias is reported,
not rewritten.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = ("app", "tests", "testing", "run_editor.py")
SKIP_PREFIXES = ("app/qt/",)
BINDINGS = ("PySide2", "PySide6")
EXEC_IMPORT = "from app.qt.qt_compat import exec_qt"
_STRING_CALLS = {"import_module", "importorskip"}
_BINDING_STRING = re.compile(r"^(PySide2|PySide6)(\.(Qt\w+))?$")

# (start_offset, end_offset, replacement)
Edit = Tuple[int, int, str]


class CodemodError(ValueError):
    pass


def _line_offsets(source: str) -> List[int]:
    offsets = [0]
    for line in source.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def _offset(offsets: Sequence[int], lineno: int, col: int, source: str) -> int:
    # ast columns are UTF-8 byte offsets; convert within the line.
    line_start = offsets[lineno - 1]
    line_end = offsets[lineno] if lineno < len(offsets) else len(source)
    line_bytes = source[line_start:line_end].encode("utf-8")
    return line_start + len(line_bytes[:col].decode("utf-8"))


def _new_module(module: str) -> Optional[str]:
    for binding in BINDINGS:
        if module == binding:
            return "app.qt"
        if module.startswith(binding + "."):
            return "app.qt" + module[len(binding):]
    return None


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def plan_edits(source: str, path_label: str = "<source>") -> Tuple[List[Edit], List[str]]:
    """Return text edits and manual-review notes for one module."""
    tree = ast.parse(source, filename=path_label)
    offsets = _line_offsets(source)
    edits: List[Edit] = []
    notes: List[str] = []
    needs_exec_import = False

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            new_module = _new_module(node.module)
            if new_module is None:
                continue
            start = _offset(offsets, node.lineno, node.col_offset, source)
            match = re.compile(r"from\s+" + re.escape(node.module) + r"\b").match(source, start)
            if match is None:
                raise CodemodError(f"{path_label}:{node.lineno}: cannot locate 'from {node.module}'")
            edits.append((match.start(), match.end(), "from " + new_module))
        elif isinstance(node, ast.Import):
            binding_aliases = [alias for alias in node.names if _new_module(alias.name) is not None]
            if not binding_aliases:
                continue
            if len(node.names) != 1:
                notes.append(f"{path_label}:{node.lineno}: multi-name import of a Qt binding; rewrite by hand")
                continue
            alias = node.names[0]
            if alias.asname is None or "." not in alias.name:
                notes.append(f"{path_label}:{node.lineno}: bare 'import {alias.name}'; rewrite by hand")
                continue
            submodule = alias.name.split(".", 1)[1]
            start = _offset(offsets, node.lineno, node.col_offset, source)
            end = _offset(offsets, node.end_lineno or node.lineno, node.end_col_offset or 0, source)
            edits.append((start, end, f"from app.qt import {submodule} as {alias.asname}"))
        elif isinstance(node, ast.Call):
            name = _call_name(node)
            if name in _STRING_CALLS and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    match = _BINDING_STRING.match(first.value)
                    if match is not None:
                        replacement = "app.qt" + (match.group(2) or "")
                        start = _offset(offsets, first.lineno, first.col_offset, source)
                        end = _offset(offsets, first.end_lineno or first.lineno, first.end_col_offset or 0, source)
                        quote = source[start]
                        edits.append((start, end, quote + replacement + quote))
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "exec_" and not node.keywords:
                receiver = ast.get_source_segment(source, func.value)
                args = [ast.get_source_segment(source, arg) for arg in node.args]
                if receiver is None or any(arg is None for arg in args):
                    notes.append(f"{path_label}:{node.lineno}: cannot read exec_ call source; rewrite by hand")
                    continue
                start = _offset(offsets, node.lineno, node.col_offset, source)
                end = _offset(offsets, node.end_lineno or node.lineno, node.end_col_offset or 0, source)
                joined = ", ".join([receiver] + [str(arg) for arg in args])
                edits.append((start, end, f"exec_qt({joined})"))
                needs_exec_import = True

    if needs_exec_import and EXEC_IMPORT not in source:
        insert_at = _exec_import_offset(tree, offsets, source)
        edits.append((insert_at, insert_at, EXEC_IMPORT + "\n"))
    _reject_overlaps(edits, path_label)
    return edits, notes


def _exec_import_offset(tree: ast.Module, offsets: Sequence[int], source: str) -> int:
    """Insert after the last top-level import, else after the docstring/__future__."""
    last_import: Optional[ast.stmt] = None
    for stmt in tree.body:
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            last_import = stmt
        elif last_import is not None:
            break
    if last_import is not None:
        line = last_import.end_lineno or last_import.lineno
        return offsets[line] if line < len(offsets) else len(source)
    if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(getattr(tree.body[0], "value", None), ast.Constant):
        line = tree.body[0].end_lineno or tree.body[0].lineno
        return offsets[line] if line < len(offsets) else len(source)
    return 0


def _reject_overlaps(edits: List[Edit], path_label: str) -> None:
    ordered = sorted(edits)
    for previous, current in zip(ordered, ordered[1:]):
        if current[0] < previous[1]:
            raise CodemodError(f"{path_label}: overlapping edits (nested exec_ calls?); rewrite by hand")


def apply_edits(source: str, edits: Sequence[Edit]) -> str:
    result = source
    for start, end, replacement in sorted(edits, reverse=True):
        result = result[:start] + replacement + result[end:]
    return result


def rewrite_source(source: str, path_label: str = "<source>") -> Tuple[str, List[str]]:
    """Apply every rewrite to ``source``. Repeats until stable (exec_ nesting)."""
    notes: List[str] = []
    current = source
    for _ in range(5):
        edits, round_notes = plan_edits(current, path_label)
        notes = round_notes
        if not edits:
            return current, notes
        current = apply_edits(current, edits)
    raise CodemodError(f"{path_label}: did not converge")


def _iter_files(targets: Sequence[str]) -> List[Path]:
    files: List[Path] = []
    for target in targets:
        path = (REPO_ROOT / target) if not Path(target).is_absolute() else Path(target)
        if path.is_file() and path.suffix == ".py":
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(p for p in path.rglob("*.py") if "__pycache__" not in p.parts))
    selected = []
    for path in files:
        try:
            relative = path.resolve().relative_to(REPO_ROOT).as_posix()
        except ValueError:
            relative = path.as_posix()
        if any(relative.startswith(prefix) for prefix in SKIP_PREFIXES):
            continue
        if "/fixtures/" in "/" + relative:
            continue
        selected.append(path)
    return selected


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="report pending rewrites; do not write")
    parser.add_argument("paths", nargs="*", default=list(DEFAULT_TARGETS))
    args = parser.parse_args(argv)

    pending: List[str] = []
    all_notes: List[str] = []
    for path in _iter_files(args.paths):
        source = path.read_text(encoding="utf-8")
        label = path.relative_to(REPO_ROOT).as_posix() if path.is_relative_to(REPO_ROOT) else str(path)
        try:
            rewritten, notes = rewrite_source(source, label)
        except SyntaxError:
            continue
        all_notes.extend(notes)
        if rewritten == source:
            continue
        pending.append(label)
        if not args.check:
            path.write_text(rewritten, encoding="utf-8")

    for note in all_notes:
        print("manual: " + note, file=sys.stderr)
    if args.check:
        for label in pending:
            print("qt-codemod: pending rewrite: " + label)
        return 1 if (pending or all_notes) else 0
    print(f"qt-codemod: rewrote {len(pending)} files", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
