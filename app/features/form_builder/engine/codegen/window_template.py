"""The user-owned window class file (CONTRACTS.md section 9.5).

Created once, never overwritten. After creation the builder only inserts empty
method stubs on request.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Optional, Tuple

from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.codegen.literals import py_string
from app.features.form_builder.engine.codegen.names import check_cpp_name, python_class_stem
from app.features.form_builder.engine.codegen.qtmap import base_qt_class, class_module
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import ConnectionNode, CustomWidgetNode, WidgetNode
from app.features.form_builder.engine.ui4.values import StringValue

_INHERITED_SLOTS = frozenset(
    {
        "accept",
        "close",
        "deleteLater",
        "hide",
        "lower",
        "raise_",
        "reject",
        "repaint",
        "setDisabled",
        "setEnabled",
        "setFocus",
        "setVisible",
        "setWindowTitle",
        "show",
        "update",
    }
)


def _custom_by_class(doc: UiDocument) -> dict:
    found = {}
    for node in doc.ui.children("customwidgets"):
        if isinstance(node, CustomWidgetNode) and node.class_name:
            found[node.class_name] = node
    return found


def render_window_class(doc: UiDocument, *, scope: FormScope) -> str:
    """Initial ``<stem>_window.py``.

    Base class: the root's class, or a promoted root's ``extends``. Class name:
    ``<class>`` + ``Window``. Import is absolute from the project root.
    """
    raw_class = doc.form_class_name()
    if not check_cpp_name(raw_class):
        raise ValueError(
            'The class name "%s" can\'t be used in the generated Python.' % raw_class
        )
    class_name = python_class_stem(raw_class)
    root = doc.root
    custom = _custom_by_class(doc).get(root.class_name)
    extends = ""
    if custom is not None:
        extends = custom.extends
    base = base_qt_class(root.class_name, extends)
    module = class_module(base) or "PySide6.QtWidgets"
    ui_class = "Ui_%s" % class_name
    if scope.module_name:
        ui_module = scope.module_name
    else:
        stem = scope.ui_path.rsplit("/", 1)[-1]
        if stem.endswith(".ui"):
            stem = stem[:-3]
        ui_module = "forms.ui_%s" % stem
    window_class = "%sWindow" % class_name
    lines = [
        "from %s import %s" % (module, base),
        "",
        "from %s import %s" % (ui_module, ui_class),
        "",
        "",
        "class %s(%s):" % (window_class, base),
        "    def __init__(self, parent=None):",
        "        super().__init__(parent)",
        "        self.ui = %s()" % ui_class,
        "        self.ui.setupUi(self)",
    ]
    status = _startup_status(doc)
    if status:
        lines.append("        self.statusBar().showMessage(%s)" % py_string(status))
    for name in _handler_names(doc):
        lines.extend(["", "    def %s(self):" % name, "        pass"])
    return "\n".join(lines) + "\n"


def _startup_status(doc: UiDocument) -> str:
    """Initial status-bar text stored as a dynamic ``currentMessage`` property."""
    for child in doc.root.child_widgets:
        if not isinstance(child, WidgetNode) or child.class_name != "QStatusBar":
            continue
        value = child.value("currentMessage")
        if isinstance(value, StringValue) and value.text:
            return value.text
    return ""


def _handler_names(doc: UiDocument) -> Tuple[str, ...]:
    """Slots the form connects to itself, skipping methods the base class already has."""
    receiver = doc.root.object_name or ""
    names: list[str] = []
    for node in doc.connections():
        if not isinstance(node, ConnectionNode) or node.receiver != receiver:
            continue
        slot = node.slot.split("(", 1)[0].strip()
        if not slot.isidentifier() or slot in _INHERITED_SLOTS or slot in names:
            continue
        names.append(slot)
    return tuple(names)


@dataclass(frozen=True)
class TextEdit:
    """Replace ``[start, end)`` (character offsets) of the file text with ``text``."""

    start: int
    end: int
    text: str


@dataclass(frozen=True)
class StubPlan:
    """``edit``: where to insert. ``stub_text``: exactly what is inserted; its
    sha256 is kept by the M6.2 compound command so undo removes the stub only
    while the method's current text still hashes the same."""

    edit: TextEdit
    stub_text: str
    method_name: str


def _line_offset(source: str, line: int, column: int) -> int:
    lines = source.splitlines(keepends=True)
    total = 0
    for index in range(line - 1):
        total += len(lines[index])
    return total + column


def _indent_at(source: str, line: int) -> str:
    lines = source.splitlines()
    if line < 1 or line > len(lines):
        return "    "
    text = lines[line - 1]
    return text[: len(text) - len(text.lstrip(" \t"))]


def plan_stub(
    window_source: str,
    *,
    class_name: str,
    method_name: str,
    params: Tuple[str, ...],
    decorator: Optional[str],
) -> StubPlan:
    """Parse ``window_source`` with ``ast`` (never execute it) and append a method.

    ValueError when the source is not Python, the class is missing, or the
    method already exists.
    """
    try:
        tree = ast.parse(window_source)
    except SyntaxError as exc:
        raise ValueError("The window file is not valid Python.") from exc
    target = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            target = node
            break
    if target is None:
        raise ValueError("The window file has no class %s." % class_name)
    last_method = None
    for node in target.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == method_name:
                raise ValueError("The method %s already exists." % method_name)
            last_method = node
    if last_method is not None and last_method.end_lineno is not None:
        indent = _indent_at(window_source, last_method.lineno)
        start = _line_offset(window_source, last_method.end_lineno, last_method.end_col_offset or 0)
    elif target.end_lineno is not None:
        indent = _indent_at(window_source, target.lineno) + "    "
        start = _line_offset(window_source, target.end_lineno, target.end_col_offset or 0)
    else:
        raise ValueError("The window file has no class %s." % class_name)
    arg_text = ""
    if params:
        arg_text = ", " + ", ".join(params)
    lines = ["", ""]
    if decorator:
        rendered = decorator if decorator.startswith("@") else "@" + decorator
        lines.append("%s%s" % (indent, rendered))
    lines.append("%sdef %s(self%s):" % (indent, method_name, arg_text))
    lines.append("%s    pass" % indent)
    lines.append("")
    stub = "\n".join(lines)
    return StubPlan(
        edit=TextEdit(start=start, end=start, text=stub),
        stub_text=stub,
        method_name=method_name,
    )
