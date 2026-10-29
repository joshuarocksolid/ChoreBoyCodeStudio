"""The user-owned window class file (CONTRACTS.md section 9.5).

Created once, never overwritten. After creation the builder only inserts empty
method stubs on request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from app.features.form_builder.engine.codegen.literals import py_string
from app.features.form_builder.engine.codegen.names import check_cpp_name, python_class_stem
from app.features.form_builder.engine.codegen.qtmap import base_qt_class, class_module
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.project.handler_names import docstring_words, signal_name
from app.features.form_builder.engine.project.window_file import (
    WindowRead,
    file_label,
    method_source_hash,
)
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
    for name, sender, signal in _handler_names(doc):
        lines.append("")
        for line in _method_lines("    ", name, (), sender, docstring_words(signal), "\n"):
            lines.append(line.rstrip("\r\n"))
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


def _handler_names(doc: UiDocument) -> Tuple[Tuple[str, str, str], ...]:
    """Slots the form connects to itself, skipping methods the base class already has.

    Each item is the method name, the sender's object name and the signal.
    """
    receiver = doc.root.object_name or ""
    found: list[Tuple[str, str, str]] = []
    seen = set()
    for node in doc.connections():
        if not isinstance(node, ConnectionNode) or node.receiver != receiver:
            continue
        slot = signal_name(node.slot)
        if not slot.isidentifier() or slot in _INHERITED_SLOTS or slot in seen:
            continue
        seen.add(slot)
        found.append((slot, node.sender, node.signal))
    return tuple(found)


@dataclass(frozen=True)
class TextEdit:
    """Replace ``[start, end)`` (character offsets) of the file text with ``text``."""

    start: int
    end: int
    text: str


@dataclass(frozen=True)
class StubPlan:
    """A whole-line insertion. ``stub_hash`` covers the ``def`` line through the
    last line of the method, with line endings normalised to LF.

    ``blank_lines`` is how many empty lines were inserted before ``def``.
    ``opened_line`` is true when the file had no trailing newline and the edit
    adds one so the method starts on its own line. Pass both back to
    ``plan_unstub`` so undo restores the bytes.
    """

    edit: TextEdit
    stub_text: str
    method_name: str
    stub_hash: str
    blank_lines: int
    opened_line: bool = False


def method_lines(
    indent: str,
    method_name: str,
    params: Tuple[str, ...],
    sender: str,
    event_words: str,
    ending: str,
) -> Tuple[str, ...]:
    """The three lines of UX-CODE-004, without a leading blank line."""
    return tuple(_method_lines(indent, method_name, params, sender, event_words, ending))


def _method_lines(
    indent: str,
    method_name: str,
    params: Tuple[str, ...],
    sender: str,
    event_words: str,
    ending: str,
) -> list:
    arguments = "self"
    if params:
        arguments = "self, " + ", ".join(params)
    safe_sender = sender.replace('"""', "").replace("\n", "").replace("\r", "")
    safe_words = event_words.replace('"""', "").replace("\n", "").replace("\r", "")
    unit = indent + indent
    body = [
        "%sdef %s(%s):" % (indent, method_name, arguments),
        '%s"""Runs when %s is %s."""' % (unit, safe_sender, safe_words),
        "%spass" % unit,
    ]
    return [line + ending for line in body]


def plan_stub(
    read: WindowRead,
    *,
    method_name: str,
    params: Tuple[str, ...],
    sender: str,
    event_words: str,
) -> StubPlan:
    """Where to insert ``method_name``. ValueError carries a UX-CODE-006 sentence.

    The edit is empty-width and starts at a line boundary. Nothing outside the
    inserted lines changes.
    """
    label = file_label(read.relative)
    _refuse_unless_readable(read, label, method_name)
    facts = read.facts
    window = facts.window if facts is not None else None
    if window is None:
        raise ValueError(
            "%s has no class that calls self.ui.setupUi(self)." % label
        )
    for method in window.methods:
        if method.name == method_name:
            raise ValueError(
                "%s already has %s. This event will call it." % (window.name, method_name)
            )
    source = _source_of(read)
    if source is None:
        raise ValueError(
            "%s can't be read, so Code Studio won't change it: the file is missing."
            % label
        )
    raw = source.splitlines(keepends=True)
    ending = window.line_ending
    start, opened = _insertion_offset(source, raw, window.last_line)
    blanks = window.blank_line_style
    body = "".join(
        _method_lines(window.indent_unit, method_name, params, sender, event_words, ending)
    )
    prefix = ending if opened else ""
    inserted = prefix + (ending * blanks) + body
    method_text = "".join(
        _method_lines(window.indent_unit, method_name, params, sender, event_words, "\n")
    )
    return StubPlan(
        edit=TextEdit(start=start, end=start, text=inserted),
        stub_text=inserted,
        method_name=method_name,
        stub_hash=method_source_hash(method_text),
        blank_lines=blanks,
        opened_line=opened,
    )


def plan_unstub(
    read: WindowRead,
    method_name: str,
    stub_hash: str,
    blank_lines: int,
    opened_line: bool = False,
) -> Optional[TextEdit]:
    """Remove the method when its text still hashes to ``stub_hash``.

    Blank lines before it go too, while they are still blank. ``opened_line``
    also drops the newline that was added so a file without one gets it back.
    """
    facts = read.facts
    window = facts.window if facts is not None else None
    if read.status != "ok" or window is None:
        return None
    method = next((item for item in window.methods if item.name == method_name), None)
    if method is None or method.source_hash != stub_hash:
        return None
    source = _source_of(read)
    if source is None:
        return None
    raw = source.splitlines(keepends=True)
    if method.line < 1 or method.end_line > len(raw):
        return None
    first = method.line
    removed = 0
    while removed < blank_lines and first > 1 and raw[first - 2].strip() == "":
        first -= 1
        removed += 1
    start = _offset_of(raw, first)
    end = _offset_of(raw, method.end_line + 1)
    if opened_line and start > 0 and source[start - 1] in ("\n", "\r"):
        start -= 2 if start >= 2 and source[start - 2 : start] == "\r\n" else 1
    if start < 0 or end < start or end > len(source):
        return None
    return TextEdit(start=start, end=end, text="")


def _refuse_unless_readable(read: WindowRead, label: str, method_name: str) -> None:
    if read.status == "ok":
        return
    if read.status == "syntax_error":
        raise ValueError(
            "Fix the error on line %s of %s first, so Code Studio can find where to add %s."
            % (read.line or 1, label, method_name)
        )
    if read.reason == "it isn't UTF-8 text":
        raise ValueError("%s isn't UTF-8 text, so Code Studio won't change it." % label)
    reason = read.reason or "it can't be read"
    raise ValueError(
        "%s can't be read, so Code Studio won't change it: %s." % (label, reason)
    )


def _source_of(read: WindowRead) -> Optional[str]:
    if isinstance(read.source, str):
        return read.source
    return None


def _offset_of(raw: list, line_number: int) -> int:
    """Character offset of the start of a 1-based line. Past the end is the length."""
    total = 0
    limit = min(line_number - 1, len(raw))
    for index in range(limit):
        total += len(raw[index])
    return total


def _insertion_offset(source: str, raw: list, last_line: int) -> Tuple[int, bool]:
    """The line after the class, and whether the file is missing a final newline."""
    if last_line < len(raw):
        return _offset_of(raw, last_line + 1), False
    opened = bool(source) and not source.endswith("\n")
    return len(source), opened
