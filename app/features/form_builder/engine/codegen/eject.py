"""Turn a bound form's generated data methods into methods of the window class.

The bodies are the expander text (lookups 380, record 400, rows 420, listing 430).
``eject_rewrite`` moves them onto the window: widgets are ``self.ui.<name>``, and
generated calls use the window method. Non-ejected generation is untouched.
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.codegen.api_types import CodegenOptions
from app.features.form_builder.engine.codegen.emit import _Emitter
from app.features.form_builder.engine.codegen.eject_rewrite import render_methods
from app.features.form_builder.engine.codegen.literals import py_string
from app.features.form_builder.engine.codegen.logic_hooks import Contribution, Method, helper_table, load_expanders
from app.features.form_builder.engine.commands.base import Command
from app.features.form_builder.engine.commands.catalog import SetLogic
from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
from app.features.form_builder.engine.logic.events import read_events
from app.features.form_builder.engine.logic.events_codec import EventStep
from app.features.form_builder.engine.logic.verbs.m8 import RECORD_VERBS
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.engine.codegen.window_template import TextEdit

MARKER = "cbcs-ejected"
EJECTED_KEY = "cbcsEjected"
_DATA_ORDERS = frozenset({380, 400, 420, 430})
_CLEARED = ("cbcsData", "cbcsBind", "cbcsLookup", "cbcsRows")
_SETUP = "_setup_ejected"

# Generated name -> method the dialog lists.
_USER_OF = {
    "cbcs_open": "load_record",
    "cbcs_save": "save_record",
    "cbcs_delete": "delete_record",
    "cbcs_new": "new_record",
    "cbcs_revert": "revert_record",
    "cbcs_reload": "reload_record",
    "cbcs_first": "first_record",
    "cbcs_previous": "previous_record",
    "cbcs_next": "next_record",
    "cbcs_last": "last_record",
    "cbcs_find": "find_record",
    "cbcs_show_all": "show_all_records",
    "cbcs_load_lookups": "load_lookups",
    "cbcs_read_fields": "read_fields",
    "cbcs_write_fields": "write_fields",
    "cbcs_is_dirty": "is_dirty",
    "cbcs_confirm_leave": "confirm_leave",
    "cbcs_current_key": "current_key",
    "cbcs_read_lines": "read_lines",
    "_cbcs_add_row": "add_line",
    "_cbcs_delete_row": "delete_line",
    "cbcs_refresh_list": "refresh_list",
    "cbcs_open_record": "open_record",
}

_USER_ORDER = (
    "load_record",
    "save_record",
    "delete_record",
    "new_record",
    "revert_record",
    "reload_record",
    "first_record",
    "previous_record",
    "next_record",
    "last_record",
    "find_record",
    "show_all_records",
    "load_lookups",
    "read_fields",
    "write_fields",
    "is_dirty",
    "confirm_leave",
    "current_key",
    "read_lines",
    "add_line",
    "delete_line",
    "refresh_list",
    "open_record",
    "open_new_record",
    "open_selected_record",
)

_VERBS = {
    "new": "new_record",
    "save": "save_record",
    "delete": "delete_record",
    "revert": "revert_record",
    "reload": "reload_record",
    "first": "first_record",
    "previous": "previous_record",
    "next": "next_record",
    "last": "last_record",
    "find": "find_record",
    "showAll": "show_all_records",
    "refreshLookups": "load_lookups",
    "addRow": "add_line",
    "deleteRow": "delete_line",
}


@dataclass(frozen=True)
class EjectPlan:
    """What Eject will add to the window class, and the form commands that go with it."""

    window_filename: str
    ui_filename: str
    first_method: str
    summary: Tuple[str, ...]
    class_block: str
    imports: Tuple[str, ...]
    commands: Tuple[Command, ...]
    method_names: Tuple[str, ...]
    helper_names: Tuple[str, ...]

    @property
    def defined_names(self) -> Tuple[str, ...]:
        return self.method_names + self.helper_names


def ejected_method(doc: UiDocument) -> Optional[str]:
    """The first ejected method, when this form's data code lives in the window file."""

    entry = doc.root.prop(EJECTED_KEY)
    if entry is None or not isinstance(entry.value, StringValue):
        return None
    text = entry.value.text.strip()
    return text or None


def method_line(source: str, name: str) -> int:
    """1-based line of ``def name(``, or 1 when the method is not in the text."""

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 1
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return int(node.lineno)
    return 1


def plan_eject(doc: UiDocument, scope: FormScope) -> EjectPlan:
    """The methods, the form commands and the window text. Raises ValueError when eject cannot run."""

    if ejected_method(doc) is not None:
        raise ValueError("This form's data code is already in the window file.")
    emitter, contributions = _collect(doc, scope)
    data = tuple(item for item in contributions if item.expander_order in _DATA_ORDERS)
    methods = _methods_of(data)
    problems = [item.message for found in data for item in found.diagnostics if item.message]
    if not methods:
        raise ValueError(problems[0] if problems else "This form has no data settings to eject.")
    setup = list(emitter._logic_setup(data))
    by_name = {method.name: method for method in methods}
    extra = _extra_blocks(doc, by_name)
    commands, wrappers = _commands(doc)
    try:
        block, public, helpers = render_methods(
            methods,
            _helper_sources(data),
            setup,
            tuple(emitter.attributes),
            emitter.form_param,
            dict(_USER_OF),
            extra,
            wrappers,
        )
    except SyntaxError as exc:
        raise ValueError("This form's data code can't be moved into the window file.") from exc
    public = _ordered_public(public)
    if not public:
        raise ValueError("This form has no data settings to eject.")
    first = public[0]
    filename = _window_filename(scope)
    ui_name = os.path.basename(scope.ui_path) or "form.ui"
    return EjectPlan(
        window_filename=filename,
        ui_filename=ui_name,
        first_method=first,
        summary=_summary(filename, ui_name, public, helpers),
        class_block=block,
        imports=_import_lines(data),
        commands=commands + (SetLogic(doc.root.id, EJECTED_KEY, first),),
        method_names=public,
        helper_names=helpers,
    )


def splice_window(source: str, plan: EjectPlan) -> str:
    """Insert the ejected methods at the end of the class that calls ``self.ui.setupUi(self)``."""

    if ("%s:" % MARKER) in source:
        raise ValueError("This form's data code is already in the window file.")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError("The window file can't be read as Python.") from exc
    target = _window_class(tree)
    if target is None:
        raise ValueError("The window file has no self.ui.setupUi(self).")
    existing = _class_method_names(target)
    for name in plan.defined_names:
        if name in existing:
            raise ValueError("%s already has %s." % (target.name, name))
    lines = source.splitlines(keepends=True)
    call = _setup_call(target)
    if call is None or call.end_lineno is None:
        raise ValueError("The window file has no self.ui.setupUi(self).")
    indent = _indent_of(lines, target)
    call_indent = _line_indent(lines, call.end_lineno)
    block = _indented(plan.class_block, indent)
    marker = "%s# %s: %s\n" % (indent, MARKER, plan.first_method)
    end_line = target.end_lineno or call.end_lineno
    insert_at = _offset_after_line(lines, end_line)
    addition = "\n" + marker + block
    if not addition.endswith("\n"):
        addition += "\n"
    text = source[:insert_at] + addition + source[insert_at:]
    text = _insert_line_after(text, call.lineno, "%sself.%s()\n" % (call_indent, _SETUP))
    text = _insert_imports(text, plan.imports)
    if not text.endswith("\n"):
        text += "\n"
    try:
        ast.parse(text)
    except SyntaxError as exc:
        raise ValueError("The window file can't be read as Python.") from exc
    return text


def window_edit(source: str, plan: EjectPlan) -> TextEdit:
    """One replacement of the whole window file, so the editor has one undo step."""

    return TextEdit(0, len(source), splice_window(source, plan))


def _collect(doc: UiDocument, scope: FormScope) -> Tuple[_Emitter, Tuple[Contribution, ...]]:
    emitter = _Emitter(doc, scope, CodegenOptions())
    emitter._prepare_custom()
    emitter._check_names()
    if emitter.refused:
        raise ValueError("This form's names can't be used in the generated Python.")
    emitter._assign_names()
    emitter.emit_widget(doc.root, "", is_root=True, skip_attrs=frozenset())
    load_expanders()
    return emitter, tuple(emitter._expand())


def _methods_of(contributions: Sequence[Contribution]) -> Tuple[Method, ...]:
    found: List[Method] = []
    seen = set()
    for item in contributions:
        for method in item.methods:
            if method.name in seen:
                continue
            seen.add(method.name)
            found.append(method)
    return tuple(found)


def _helper_sources(contributions: Sequence[Contribution]) -> Tuple[str, ...]:
    wanted = {helper_id for item in contributions for helper_id in item.helpers}
    line_plan = "_cbcs_line_plan" in wanted
    if line_plan:
        wanted = wanted - {"_cbcs_line_plan"}
    chunks: List[str] = []
    if wanted:
        for helper_id, source in helper_table():
            if helper_id in wanted:
                chunks.append(source.rstrip() + "\n")
    if line_plan:
        from app.features.form_builder.engine.data.lines import line_plan_source

        chunks.append(line_plan_source().rstrip() + "\n")
    return tuple(chunks)


def _import_lines(contributions: Sequence[Contribution]) -> Tuple[str, ...]:
    grouped: Dict[str, List[str]] = {}
    for item in contributions:
        for module, name in item.imports:
            names = grouped.setdefault(module, [])
            if name not in names:
                names.append(name)
    lines = []
    for module in sorted(grouped):
        lines.append("from %s import %s" % (module, ", ".join(sorted(grouped[module]))))
    return tuple(lines)


def _extra_blocks(doc: UiDocument, by_name: Dict[str, Method]) -> Tuple[Tuple[str, str], ...]:
    if "cbcs_open_record" not in by_name:
        return ()
    found = []
    for state in read_events(doc):
        for step in state.steps:
            if step.verb != "openRecord":
                continue
            which = _which(step)
            name = "open_new_record" if which == "new" else "open_selected_record" if which == "selected" else ""
            if name and name not in [item[0] for item in found]:
                found.append(
                    (
                        name,
                        "def %s(self):\n    return self.open_record(%s)\n" % (name, py_string(which)),
                    )
                )
    return tuple(found)


def _ordered_public(names: Sequence[str]) -> Tuple[str, ...]:
    present = set(names)
    ordered = tuple(name for name in _USER_ORDER if name in present)
    rest = tuple(name for name in names if name not in ordered)
    return ordered + rest


def _summary(filename: str, ui_name: str, names: Sequence[str], helpers: Sequence[str]) -> Tuple[str, ...]:
    third = "Save, Delete and the toolbar buttons will call your methods"
    if "save_record" not in names and "delete_record" not in names:
        third = "The toolbar buttons will call your methods"
    return (
        "Adds %d methods and %d helpers to %s.\n%s" % (len(names), len(helpers), filename, _capped(names)),
        "Removes the data settings from %s" % ui_name,
        third,
    )


def _capped(names: Sequence[str]) -> str:
    shown = list(names[:8])
    extra = len(names) - len(shown)
    text = ", ".join(shown)
    if extra:
        text = "%s, and %d more" % (text, extra)
    return text


def _commands(doc: UiDocument) -> Tuple[Tuple[Command, ...], Tuple[str, ...]]:
    commands: List[Command] = []
    wrappers: List[str] = []
    for node in doc.iter_preorder():
        for key in _CLEARED:
            entry = node.prop(key)
            if entry is None or not isinstance(entry.value, StringValue) or not entry.value.text.strip():
                continue
            commands.append(SetLogic(node.id, key, None))
    for state in read_events(doc):
        steps, changed, made = _rewired(state.steps, state.sender)
        wrappers.extend(made)
        if changed:
            commands.append(SetEventSteps(state.sender, state.signal_name, steps, caption="Eject to code"))
    return tuple(commands), tuple(wrappers)


def _rewired(steps: Sequence[EventStep], sender: str) -> Tuple[Tuple[EventStep, ...], bool, Tuple[str, ...]]:
    changed = False
    out: List[EventStep] = []
    wrappers: List[str] = []
    for index, step in enumerate(steps):
        target, arg_src = _step_call(step)
        if target is None:
            out.append(step)
            continue
        changed = True
        method = target
        if arg_src:
            method = "_call_%s_%s_%d" % (target, _ident(sender), index)
            wrappers.append("def %s(self):\n    return self.%s(%s)\n" % (method, target, arg_src))
        out.append(EventStep("call", method=method, args=0, when="True"))
    return tuple(out), changed, tuple(wrappers)


def _step_call(step: EventStep) -> Tuple[Optional[str], str]:
    if step.verb not in RECORD_VERBS:
        return None, ""
    if step.verb == "openRecord":
        which = _which(step)
        if which == "new":
            return "open_new_record", ""
        if which == "selected":
            return "open_selected_record", ""
        return "open_record", ""
    target = _VERBS.get(step.verb)
    if target is None:
        return None, ""
    if step.verb == "refreshLookups":
        return target, _lookup_args(step)
    return target, ""


def _lookup_args(step: EventStep) -> str:
    raw = step.raw
    value = raw.field("fields") if raw is not None and hasattr(raw, "field") else None
    names = []
    if isinstance(value, tuple):
        for item in value:
            if isinstance(item, str) and item:
                names.append(item)
    if not names:
        return ""
    return "(%s,)" % ", ".join(py_string(name) for name in names)


def _ident(text: str) -> str:
    cleaned = "".join(char if char.isalnum() or char == "_" else "_" for char in text)
    if not cleaned or cleaned[0].isdigit():
        cleaned = "w_" + cleaned
    return cleaned


def _which(step: EventStep) -> str:
    raw = step.raw
    if raw is None:
        return ""
    value = raw.field("which", "") if hasattr(raw, "field") else ""
    return value if isinstance(value, str) else ""


def _window_filename(scope: FormScope) -> str:
    if scope.window_path:
        return os.path.basename(scope.window_path)
    base = os.path.basename(scope.ui_path)
    stem = base[:-3] if base.endswith(".ui") else base
    return stem + "_window.py"


def _window_class(tree: ast.AST) -> Optional[ast.ClassDef]:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and _setup_call(node) is not None:
            return node
    return None


def _setup_call(node: ast.ClassDef) -> Optional[ast.Call]:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call) or not child.args:
            continue
        func = child.func
        if not isinstance(func, ast.Attribute) or func.attr != "setupUi":
            continue
        inner = func.value
        if not isinstance(inner, ast.Attribute) or inner.attr != "ui":
            continue
        if not isinstance(inner.value, ast.Name) or inner.value.id != "self":
            continue
        arg = child.args[0]
        if isinstance(arg, ast.Name) and arg.id == "self":
            return child
    return None


def _class_method_names(node: ast.ClassDef) -> set:
    found = set()
    for child in node.body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.add(child.name)
    return found


def _indent_of(lines: Sequence[str], node: ast.ClassDef) -> str:
    for child in node.body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return _line_indent(lines, child.lineno)
    return "    "


def _line_indent(lines: Sequence[str], lineno: int) -> str:
    if lineno < 1 or lineno > len(lines):
        return "    "
    raw = lines[lineno - 1]
    stripped = raw.lstrip(" \t")
    return raw[: len(raw) - len(stripped)]


def _indented(block: str, indent: str) -> str:
    lines = []
    for line in block.split("\n"):
        lines.append((indent + line) if line else "")
    text = "\n".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    return text


def _offset_after_line(lines: Sequence[str], lineno: int) -> int:
    total = 0
    for index in range(min(lineno, len(lines))):
        total += len(lines[index])
    return total


def _insert_line_after(source: str, lineno: int, addition: str) -> str:
    lines = source.splitlines(keepends=True)
    if lineno < 1 or lineno > len(lines):
        return source
    # The setup call's line number is from the pre-insert parse. Inserting the
    # class block after the class does not move lines above the class end, and
    # the call sits above that end, so the number still addresses the call.
    lines.insert(lineno, addition if addition.endswith("\n") else addition + "\n")
    return "".join(lines)


def _insert_imports(source: str, imports: Sequence[str]) -> str:
    if not imports:
        return source
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    present = set()
    last = 0
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)) and node.end_lineno:
            last = max(last, node.end_lineno)
            present.add(ast.get_source_segment(source, node) or "")
    missing = [line for line in imports if line not in present and not any(line in item for item in present)]
    if not missing:
        return source
    lines = source.splitlines(keepends=True)
    addition = "\n".join(missing) + "\n"
    if last == 0:
        return addition + "\n" + source
    offset = _offset_after_line(lines, last)
    return source[:offset] + addition + source[offset:]
