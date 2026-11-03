"""Turn a bound form's generated data methods into window-file methods.

The method bodies are the expander text (lookups 380, record 400, rows 420,
listing 430). They stay written for ``self`` as the generated Ui object and are
bound onto ``self.ui`` when the window opens. The window class gets the names
the toolbar calls (``load_record``, ``save_record``, and the rest).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.codegen.api_types import CodegenOptions
from app.features.form_builder.engine.codegen.emit import _Emitter
from app.features.form_builder.engine.codegen.literals import py_string
from app.features.form_builder.engine.codegen.logic_hooks import Contribution, Method, helper_table, load_expanders
from app.features.form_builder.engine.commands.base import Command
from app.features.form_builder.engine.commands.catalog import SetLogic
from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
from app.features.form_builder.engine.logic.events import read_events
from app.features.form_builder.engine.logic.events_codec import EventStep, call_step
from app.features.form_builder.engine.logic.verbs.m8 import RECORD_VERBS
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.engine.codegen.window_template import TextEdit

MARKER = "cbcs-ejected"
EJECTED_KEY = "cbcsEjected"
_DATA_ORDERS = frozenset({380, 400, 420, 430})
_CLEARED = ("cbcsData", "cbcsBind", "cbcsLookup", "cbcsRows")
_BIND = "_cbcs_bind_ejected"
_SETUP = "_cbcs_ejected_setup"

# Generated name -> method on the window class. Helpers stay on self.ui.
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
    """What Eject will do. ``prelude`` is module-level source. ``class_block`` is indented methods."""

    window_filename: str
    ui_filename: str
    first_method: str
    summary: Tuple[str, ...]
    prelude: str
    class_block: str
    commands: Tuple[Command, ...]
    method_names: Tuple[str, ...]


def ejected_method(doc: UiDocument) -> Optional[str]:
    """The first ejected method, when this form's data code lives in the window file."""

    entry = doc.root.prop(EJECTED_KEY)
    if entry is None or not isinstance(entry.value, StringValue):
        return None
    text = entry.value.text.strip()
    return text or None


def method_line(source: str, name: str) -> int:
    """1-based line of ``def name``, or 1 when the method is not in the text."""

    needle = "def %s(" % name
    for number, line in enumerate(source.splitlines(), 1):
        if needle in line:
            return number
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
    setup = emitter._logic_setup(data)
    by_name = {method.name: method for method in methods}
    extra = _extra_methods(doc, by_name)
    names = _ordered_names(by_name, extra)
    if not names:
        raise ValueError("This form has no data settings to eject.")
    first = names[0]
    filename = _window_filename(scope)
    ui_name = os.path.basename(scope.ui_path) or "form.ui"
    return EjectPlan(
        window_filename=filename,
        ui_filename=ui_name,
        first_method=first,
        summary=_summary(filename, ui_name, names),
        prelude=_prelude(doc, data, methods, setup, emitter.form_param, first),
        class_block=_class_block(by_name, extra),
        commands=_commands(doc, first),
        method_names=names,
    )


def splice_window(source: str, plan: EjectPlan) -> str:
    """Insert the ejected prelude, the bind call and the window methods. The rest of the file stays."""

    if ("%s:" % MARKER) in source:
        raise ValueError("This form's data code is already in the window file.")
    lines = source.splitlines(keepends=True)
    setup_at = None
    for index, line in enumerate(lines):
        if "self.ui.setupUi(self)" in line:
            setup_at = index
            break
    if setup_at is None:
        raise ValueError("The window file has no self.ui.setupUi(self).")
    raw = lines[setup_at]
    body_indent = raw[: len(raw) - len(raw.lstrip(" \t"))]
    method_indent = _method_indent(lines, setup_at)
    lines.insert(setup_at + 1, "%s%s(self.ui, self)\n" % (body_indent, _BIND))
    class_at = _class_line(lines, setup_at)
    prelude = plan.prelude
    if not prelude.endswith("\n"):
        prelude += "\n"
    lines.insert(class_at, "\n" + prelude + "\n")
    text = "".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    block = "\n".join(method_indent + line if line else "" for line in plan.class_block.split("\n"))
    return text + "\n" + block + "\n"


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
    # Import every expander so open-hook registration matches a normal generate.
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


def _extra_methods(doc: UiDocument, by_name: Dict[str, Method]) -> Tuple[str, ...]:
    if "cbcs_open_record" not in by_name:
        return ()
    found = []
    for state in read_events(doc):
        for step in state.steps:
            if step.verb != "openRecord":
                continue
            which = _which(step)
            name = "open_new_record" if which == "new" else "open_selected_record" if which == "selected" else ""
            if name and name not in found:
                found.append(name)
    return tuple(found)


def _ordered_names(by_name: Dict[str, Method], extra: Sequence[str]) -> Tuple[str, ...]:
    present = {_USER_OF[name] for name in by_name if name in _USER_OF}
    present.update(extra)
    return tuple(name for name in _USER_ORDER if name in present)


def _summary(filename: str, ui_name: str, names: Sequence[str]) -> Tuple[str, ...]:
    listed = ", ".join(names)
    third = "Save, Delete and the toolbar buttons will call your methods"
    if "save_record" not in names and "delete_record" not in names:
        third = "The toolbar buttons will call your methods"
    return (
        "Adds %d methods to %s: %s" % (len(names), filename, listed),
        "Removes the data settings from %s" % ui_name,
        third,
    )


def _prelude(
    doc: UiDocument,
    contributions: Sequence[Contribution],
    methods: Sequence[Method],
    setup: Sequence[str],
    form_param: str,
    first: str,
) -> str:
    del doc
    chunks: List[str] = ["# %s: %s" % (MARKER, first)]
    imports = _import_lines(contributions)
    if imports:
        chunks.append(imports)
    helpers = _helper_source(contributions)
    if helpers:
        chunks.append(helpers)
    for method in methods:
        chunks.append(_function(method))
    chunks.append(_setup_function(setup, form_param))
    chunks.append(_bind_function(methods))
    return "\n\n".join(chunks) + "\n"


def _import_lines(contributions: Sequence[Contribution]) -> str:
    grouped: Dict[str, List[str]] = {}
    for item in contributions:
        for module, name in item.imports:
            names = grouped.setdefault(module, [])
            if name not in names:
                names.append(name)
    lines = []
    for module in sorted(grouped):
        lines.append("from %s import %s" % (module, ", ".join(sorted(grouped[module]))))
    return "\n".join(lines)


def _helper_source(contributions: Sequence[Contribution]) -> str:
    wanted = {helper_id for item in contributions for helper_id in item.helpers}
    line_plan = "_cbcs_line_plan" in wanted
    if line_plan:
        wanted = wanted - {"_cbcs_line_plan"}
    chunks: List[str] = []
    if wanted:
        table = helper_table()
        for helper_id, source in table:
            if helper_id in wanted:
                chunks.append(source.rstrip())
    if line_plan:
        from app.features.form_builder.engine.data.lines import line_plan_source

        chunks.append(line_plan_source().rstrip())
    return "\n\n".join(chunks)


def _function(method: Method) -> str:
    params = ", " + method.params if method.params else ""
    lines = ["def %s(self%s):" % (method.name, params), "    # %s" % method.source_ref]
    body = method.body.strip("\n")
    if not body:
        lines.append("    pass")
    else:
        for line in body.split("\n"):
            lines.append("    %s" % line if line else "")
    return "\n".join(lines)


def _setup_function(setup: Sequence[str], form_param: str) -> str:
    lines = ["def %s(self, %s):" % (_SETUP, form_param)]
    if not setup:
        lines.append("    self._form = %s" % form_param)
    else:
        for line in setup:
            lines.append("    %s" % line if line else "")
    return "\n".join(lines)


def _bind_function(methods: Sequence[Method]) -> str:
    lines = ["def %s(ui, form):" % _BIND]
    for method in methods:
        lines.append("    ui.%s = %s.__get__(ui, type(ui))" % (method.name, method.name))
    lines.append("    %s(ui, form)" % _SETUP)
    return "\n".join(lines)


def _class_block(by_name: Dict[str, Method], extra: Sequence[str]) -> str:
    blocks: List[str] = []
    produced = set()
    for generated, user in _USER_OF.items():
        method = by_name.get(generated)
        if method is None or user in produced:
            continue
        produced.add(user)
        blocks.append(_forward(user, generated, method.params))
    for name in extra:
        if name in produced:
            continue
        produced.add(name)
        which = "new" if name == "open_new_record" else "selected"
        blocks.append(
            "def %s(self):\n    return self.ui.cbcs_open_record(%s)" % (name, py_string(which))
        )
    ordered = []
    for name in _USER_ORDER:
        for block in blocks:
            if block.startswith("def %s(" % name):
                ordered.append(block)
    return "\n\n".join(ordered)


def _forward(user: str, generated: str, params: str) -> str:
    signature = ", " + params if params else ""
    args = ", ".join(_param_names(params))
    return "def %s(self%s):\n    return self.ui.%s(%s)" % (user, signature, generated, args)


def _param_names(params: str) -> Tuple[str, ...]:
    if not params.strip():
        return ()
    names = []
    for part in params.split(","):
        name = part.split("=", 1)[0].strip()
        if name and name != "self":
            names.append(name.lstrip("*"))
    return tuple(names)


def _commands(doc: UiDocument, first: str) -> Tuple[Command, ...]:
    commands: List[Command] = []
    for node in doc.iter_preorder():
        for key in _CLEARED:
            entry = node.prop(key)
            if entry is None or not isinstance(entry.value, StringValue) or not entry.value.text.strip():
                continue
            commands.append(SetLogic(node.id, key, None))
    for state in read_events(doc):
        steps, changed = _rewired(state.steps)
        if changed:
            commands.append(SetEventSteps(state.sender, state.signal_name, steps, caption="Eject to code"))
    commands.append(SetLogic(doc.root.id, EJECTED_KEY, first))
    return tuple(commands)


def _rewired(steps: Sequence[EventStep]) -> Tuple[Tuple[EventStep, ...], bool]:
    changed = False
    out: List[EventStep] = []
    for step in steps:
        target = _step_method(step)
        if target is None:
            out.append(step)
            continue
        changed = True
        if step.when is None and step.enabled:
            out.append(call_step(target))
        else:
            out.append(replace(step, verb="call", method=target, raw=None))
    return tuple(out), changed


def _step_method(step: EventStep) -> Optional[str]:
    if step.verb not in RECORD_VERBS:
        return None
    if step.verb == "openRecord":
        which = _which(step)
        if which == "new":
            return "open_new_record"
        if which == "selected":
            return "open_selected_record"
        return "open_record"
    return _VERBS.get(step.verb)


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


def _method_indent(lines: Sequence[str], setup_at: int) -> str:
    for index in range(setup_at, -1, -1):
        raw = lines[index]
        stripped = raw.lstrip(" \t")
        if stripped.startswith("def "):
            return raw[: len(raw) - len(stripped)]
    return "    "


def _class_line(lines: Sequence[str], setup_at: int) -> int:
    for index in range(setup_at, -1, -1):
        if lines[index].startswith("class "):
            return index
    return 0
