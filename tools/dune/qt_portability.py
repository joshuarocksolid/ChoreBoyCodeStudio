"""Keep CBCS app code portable between PySide2 (Qt 5) and PySide6 (Qt 6).

Only ``app/qt/`` may import a binding. Everything else imports Qt through
``app.qt`` and avoids the APIs that PySide6 removed or that fail there.
See docs/PYSIDE6_MIGRATION_PLAN.md section 2 for the measured breaks.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable

_QT_PACKAGE_PREFIX = "app/qt/"
_BINDING_ROOTS = ("PySide2", "PySide6", "shiboken2", "shiboken6")
_REMOVED_NAMES = {
    "QRegExp": "use QRegularExpression",
    "QDesktopWidget": "use QScreen",
    "QTextCodec": "use Python str encoding",
}
_STR_OVERLOAD_SIGNALS = {"activated", "currentIndexChanged", "highlighted"}
_INT_REJECTING_SUFFIXES = ("Modifier", "Button")
_INT_REJECTING_PREFIXES = ("ItemIs",)
_INT_REJECTING_NAMES = {"Checked", "Unchecked", "PartiallyChecked", "NoModifier", "NoButton"}


class QtPortabilityError(ValueError):
    pass


def find_qt_portability_violations(repo_root: Path, tracked_files: Iterable[str]) -> list[str]:
    violations: list[str] = []
    for relative_path in sorted(
        {path.replace("\\", "/") for path in tracked_files if path.endswith(".py")}
    ):
        if not relative_path.startswith("app/") or relative_path.startswith(_QT_PACKAGE_PREFIX):
            continue
        source_path = repo_root / relative_path
        try:
            tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=relative_path)
        except SyntaxError as exc:
            raise QtPortabilityError(
                f"{relative_path}:{exc.lineno or 1}: invalid Python syntax: {exc.msg}"
            ) from exc
        violations.extend(
            f"qt-portability: {relative_path}:{line}: {message}"
            for line, message in _violations_in(tree)
        )
    return violations


def _violations_in(tree: ast.AST) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_binding(alias.name):
                    found.append((node.lineno, f"import {alias.name} through app.qt"))
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if _is_binding(node.module):
                found.append((node.lineno, f"import {node.module} through app.qt"))
            for alias in node.names:
                if alias.name in _REMOVED_NAMES:
                    found.append((node.lineno, f"{alias.name} is gone in Qt 6; {_REMOVED_NAMES[alias.name]}"))
        elif isinstance(node, ast.Attribute):
            message = _attribute_message(node)
            if message:
                found.append((node.lineno, message))
        elif isinstance(node, ast.Subscript):
            message = _subscript_message(node)
            if message:
                found.append((node.lineno, message))
        elif isinstance(node, ast.Call):
            message = _call_message(node)
            if message:
                found.append((node.lineno, message))
    return sorted(set(found))


def _is_binding(module: str) -> bool:
    return any(module == root or module.startswith(root + ".") for root in _BINDING_ROOTS)


def _attribute_message(node: ast.Attribute) -> str:
    if node.attr in _REMOVED_NAMES:
        return f"{node.attr} is gone in Qt 6; {_REMOVED_NAMES[node.attr]}"
    if node.attr == "MidButton":
        return "Qt.MidButton is gone in Qt 6; use Qt.MiddleButton"
    if node.attr in ("Background", "Foreground") and _dotted_tail(node.value) == "QPalette":
        return f"QPalette.{node.attr} is gone in Qt 6; use Window/WindowText"
    return ""


def _subscript_message(node: ast.Subscript) -> str:
    value = node.value
    if not isinstance(value, ast.Attribute) or value.attr not in _STR_OVERLOAD_SIGNALS:
        return ""
    index = getattr(node.slice, "value", node.slice)  # Python 3.8 wraps it in ast.Index
    if isinstance(index, ast.Name) and index.id == "str":
        return f"{value.attr}[str] is gone in Qt 6; use the text* signal or [int]"
    return ""


def _call_message(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        if func.attr == "exec_":
            return "call exec_qt(obj, ...) instead of .exec_()"
        if func.attr == "setMargin":
            return "setMargin is gone in Qt 6; use setContentsMargins"
    if isinstance(func, ast.Name) and func.id == "int" and len(node.args) == 1:
        if _int_rejecting_enum(node.args[0]):
            return "int() on this Qt enum raises TypeError on PySide6; use enum_value()"
    return ""


def _int_rejecting_enum(arg: ast.expr) -> bool:
    if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute):
        return arg.func.attr in ("modifiers", "buttons", "button", "keyboardModifiers", "checkState", "flags")
    if isinstance(arg, ast.Attribute) and _dotted_tail(arg.value) == "Qt":
        name = arg.attr
        return (
            name in _INT_REJECTING_NAMES
            or name.endswith(_INT_REJECTING_SUFFIXES)
            or name.startswith(_INT_REJECTING_PREFIXES)
        )
    return False


def _dotted_tail(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""
