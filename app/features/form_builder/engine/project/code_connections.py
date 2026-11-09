"""Connections and property calls found in a window file. Parse only.

The window module is never imported and never executed. A syntax error, or a
file whose classes never call ``self.ui.setupUi(self)``, is an empty tuple.
"""

from __future__ import annotations

import ast
import hashlib
from typing import Dict, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.logic.uses import Use

# Same window text is one parse. A later edit of the form must not scan it again.
_PARSED: Dict[str, Tuple[Use, ...]] = {}

_SETTERS = {
    "setEnabled": "cbcsEnabledWhen",
    "setDisabled": "cbcsEnabledWhen",
    "setVisible": "cbcsVisibleWhen",
    "setHidden": "cbcsVisibleWhen",
    "setReadOnly": "cbcsReadOnlyWhen",
    "setText": "cbcsValue",
    "setPlainText": "cbcsValue",
    "setValue": "cbcsValue",
    "setChecked": "cbcsValue",
}
_GETTERS = frozenset({"text", "value", "isChecked", "isEnabled", "isVisible", "isReadOnly"})


def read_connections(source: str, relative: str = "") -> Tuple[Use, ...]:
    """Uses of ``self.ui`` in the class that calls ``setupUi``. Empty on a bad file."""
    text = source if isinstance(source, str) else ""
    digest = hashlib.sha256(("%s\0%s" % (relative, text)).encode("utf-8")).hexdigest()
    cached = _PARSED.get(digest)
    if cached is not None:
        return cached
    try:
        tree = ast.parse(text)
    except SyntaxError:
        _PARSED[digest] = ()
        return ()
    owner = _setup_class(tree)
    if owner is None:
        _PARSED[digest] = ()
        return ()
    found: List[Use] = []
    consumed = set()
    _walk(owner, relative, found, consumed)
    result = tuple(found)
    _PARSED[digest] = result
    return result


def _setup_class(tree: ast.AST) -> Optional[ast.ClassDef]:
    for node in getattr(tree, "body", ()):
        if isinstance(node, ast.ClassDef) and _calls_setup(node):
            return node
    return None


def _calls_setup(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and _is_setup_call(child):
            return True
    return False


def _is_setup_call(call: ast.Call) -> bool:
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr != "setupUi":
        return False
    if len(call.args) != 1 or not _is_self(call.args[0]):
        return False
    return _is_self_ui(func.value)


def _walk(node: ast.AST, relative: str, found: List[Use], consumed: set) -> None:
    if isinstance(node, ast.Call):
        _take_call(node, relative, found, consumed)
    elif isinstance(node, ast.Attribute) and id(node) not in consumed:
        widget = _widget_name(node)
        if widget:
            consumed.add(id(node))
            found.append(_use(widget, "read", widget, "", "", "", node.lineno, relative, ""))
    for child in ast.iter_child_nodes(node):
        _walk(child, relative, found, consumed)


def _take_call(call: ast.Call, relative: str, found: List[Use], consumed: set) -> None:
    connected = _connect(call)
    if connected is not None:
        widget, signal, method, nodes = connected
        line = int(call.lineno or 0)
        found.append(_use(method, "call", widget, "", "", signal, line, relative, method))
        found.append(_use(widget, "call", widget, "", "", signal, line, relative, method))
        consumed.update(id(node) for node in nodes)
        return
    func = call.func
    if not isinstance(func, ast.Attribute):
        return
    widget = _widget_name(func.value)
    if not widget:
        return
    line = int(call.lineno or 0)
    if func.attr in _SETTERS:
        found.append(_use(widget, "set", widget, func.attr, _SETTERS[func.attr], "", line, relative, ""))
        consumed.add(id(func))
        consumed.add(id(func.value))
        return
    if func.attr in _GETTERS:
        found.append(_use(widget, "read", widget, func.attr, "", "", line, relative, ""))
        consumed.add(id(func))
        consumed.add(id(func.value))


def _connect(call: ast.Call) -> Optional[Tuple[str, str, str, Sequence[ast.AST]]]:
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr != "connect" or len(call.args) != 1:
        return None
    signal_node = func.value
    if not isinstance(signal_node, ast.Attribute):
        return None
    widget_node = signal_node.value
    widget = _widget_name(widget_node)
    method_node = call.args[0]
    if not widget or not isinstance(method_node, ast.Attribute) or not _is_self(method_node.value):
        return None
    if not method_node.attr:
        return None
    return widget, signal_node.attr, method_node.attr, (func, signal_node, widget_node)


def _use(
    name: str,
    role: str,
    widget: str,
    summary: str,
    property_key: str,
    signal: str,
    line: int,
    path: str,
    method: str,
) -> Use:
    return Use(name, role, "code", widget, summary, property_key, -1, signal, line, path, method)


def _widget_name(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute) and _is_self_ui(node.value) and node.attr and node.attr != "setupUi":
        return node.attr
    return ""


def _is_self_ui(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "ui" and _is_self(node.value)


def _is_self(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "self"
