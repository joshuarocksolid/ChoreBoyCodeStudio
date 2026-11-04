"""Turn expander text (``self`` is the generated Ui) into window-class methods.

The edit is a span replacement on the parsed function. Widget attributes
become ``self.ui.<name>``. Calls of generated methods use the window method's
name. A later pass drops the ``u`` prefix, quotes SQL with single quotes, and
removes guards this eject can resolve.
"""

from __future__ import annotations

import ast
import keyword
import re
from typing import Dict, List, Optional, Sequence, Set, Tuple

from app.features.form_builder.engine.codegen.logic_hooks import Method

_FORWARD = re.compile(r"\Areturn self\.([A-Za-z_][A-Za-z0-9_]*)\(\)\Z")
_OWNER_PARAMS = frozenset(("ui", "form"))


def window_names(old: str, public_of: Dict[str, str]) -> str:
    """The window method ``old`` becomes."""

    if old in public_of:
        return public_of[old]
    if old.startswith("_cbcs_"):
        return "_" + old[len("_cbcs_") :]
    if old.startswith("cbcs_"):
        return "_" + old[len("cbcs_") :]
    return old


def render_methods(
    methods: Sequence[Method],
    helper_sources: Sequence[str],
    setup_lines: Sequence[str],
    widgets: Sequence[str],
    form_param: str,
    public_of: Dict[str, str],
    extras: Sequence[Tuple[str, str]],
    wrappers: Sequence[str],
    present: Optional[Set[str]] = None,
    ui_methods: Optional[Set[str]] = None,
) -> Tuple[str, Tuple[str, ...], Tuple[str, ...]]:
    """``(class_block, public_names, helper_names)``."""

    by_name = {method.name: method for method in methods}
    bodies: Dict[str, str] = {}
    skip: Set[str] = set()
    alias: Dict[str, str] = {}
    for method in methods:
        match = _FORWARD.match(method.body.strip())
        private = match.group(1) if match is not None else ""
        if method.name in public_of and private in by_name:
            bodies[method.name] = by_name[private].body
            skip.add(private)
            alias[private] = public_of[method.name]
        else:
            bodies[method.name] = method.body
    renames: Dict[str, str] = {}
    for name in list(by_name) + [helper_id for helper_id in _helper_names(helper_sources)]:
        if name in alias:
            renames[name] = alias[name]
        elif name not in skip:
            renames[name] = window_names(name, public_of)
    for private, public in alias.items():
        renames[private] = public
    planned = _planned(methods, helper_sources, extras, wrappers, skip, renames, public_of)
    known = set(renames.values()) | planned
    widget_names = frozenset(widgets)
    defined = set(present or ())
    setup_raw = rewrite_function(
        _wrap("_setup_ejected", "", "\n".join(setup_lines)), widget_names, renames, form_param
    )
    blob = "\n".join(method.body for method in methods) + "\n".join(helper_sources)
    if "_cbcs_lookup_missing" in blob or "_lookup_missing" in blob:
        setup_raw = _ensure_assign(setup_raw, "_lookup_missing", "None")
    state = _assigned_state(setup_raw)
    on_ui = set(ui_methods or ())
    blocks: List[str] = []
    public: List[str] = []
    helpers: List[str] = []
    emitted: Set[str] = set()
    for method in methods:
        if method.name in skip or method.name in emitted:
            continue
        emitted.add(method.name)
        new = renames.get(method.name, method.name)
        source = _wrap(new, method.params, bodies.get(method.name, method.body))
        rewritten = polish(
            rewrite_function(source, widget_names, renames, form_param),
            planned,
            known,
            state,
            defined,
            on_ui,
        )
        if new in public_of.values() or method.name in public_of:
            public.append(new)
            blocks.append(rewritten)
        else:
            helpers.append(new)
            blocks.append(rewritten)
    for name, body in extras:
        if name in emitted:
            continue
        emitted.add(name)
        public.append(name)
        blocks.append(body.rstrip() + "\n")
    for source in helper_sources:
        for function in _function_texts(source):
            tree = ast.parse(function)
            definition = next(node for node in tree.body if isinstance(node, ast.FunctionDef))
            new = renames.get(definition.name, window_names(definition.name, public_of))
            if new in emitted:
                continue
            emitted.add(new)
            helpers.append(new)
            rewritten = polish(
                rewrite_function(_with_self(function, definition.name, new), widget_names, renames, form_param),
                planned,
                known,
                state,
                defined,
                on_ui,
            )
            blocks.append(rewritten)
    blocks.append(polish(setup_raw, planned, known, state, defined, on_ui))
    helpers.append("_setup_ejected")
    for wrapper in wrappers:
        blocks.append(wrapper.rstrip() + "\n")
        name = wrapper.split("(", 1)[0].split()[-1]
        if name and name not in helpers:
            helpers.append(name)
    ordered_public = tuple(dict.fromkeys(public))
    ordered_helpers = tuple(dict.fromkeys(helpers))
    return "\n\n".join(block.rstrip() for block in blocks if block.strip()) + "\n", ordered_public, ordered_helpers


def rewrite_function(
    source: str,
    widgets: frozenset,
    renames: Dict[str, str],
    form_param: str,
) -> str:
    """One function, rewritten so ``self`` is the window."""

    tree = ast.parse(source)
    parents: Dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    lines = source.splitlines(keepends=True)
    edits: List[Tuple[int, int, str]] = []
    root = next(node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))
    _walk(root, root, True, {root.args.args[0].arg} if root.args.args else set(), widgets, renames, form_param, parents, lines, edits)
    return _apply(source, edits)


def _walk(
    node: ast.AST,
    root: ast.AST,
    in_root_function: bool,
    owners: Set[str],
    widgets: frozenset,
    renames: Dict[str, str],
    form_param: str,
    parents: Dict[int, ast.AST],
    lines: Sequence[str],
    edits: List[Tuple[int, int, str]],
) -> None:
    if isinstance(node, ast.ClassDef):
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                params = {arg.arg for arg in child.args.args}
                nested = {name for name in params if name in _OWNER_PARAMS}
                _walk(child, root, False, nested, widgets, renames, form_param, parents, lines, edits)
            else:
                _walk(child, root, False, set(), widgets, renames, form_param, parents, lines, edits)
        return
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node is not root:
        params = [arg.arg for arg in node.args.args]
        nested = set(owners)
        if params and params[0] == "self":
            nested.discard("self")
        for child in node.body:
            _walk(child, root, False, nested, widgets, renames, form_param, parents, lines, edits)
        return
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in owners:
        if node.attr in renames:
            _replace_attr(node, renames[node.attr], lines, edits)
        elif node.attr.startswith("_cbcs_"):
            parent = parents.get(id(node))
            called = isinstance(parent, ast.Call) and parent.func is node
            renamed = window_names(node.attr, {})
            if called and renamed not in renames.values():
                span = _span(node, lines)
                if span is not None:
                    edits.append((span[0], span[1], "%s.ui.%s" % (node.value.id, node.attr)))
            else:
                _replace_attr(node, renamed, lines, edits)
        elif node.attr.startswith("cbcs_") and isinstance(getattr(node, "ctx", None), ast.Load):
            # A generated method that stayed on the Ui, such as cbcs_refresh.
            span = _span(node, lines)
            if span is not None:
                edits.append((span[0], span[1], "%s.ui.%s" % (node.value.id, node.attr)))
        elif node.attr in widgets:
            span = _span(node, lines)
            if span is not None:
                edits.append((span[0], span[1], "%s.ui.%s" % (node.value.id, node.attr)))
    elif isinstance(node, ast.Attribute) and (
        _receiver_is_owner(node, owners) or _receiver_is_window(node)
    ):
        if node.attr in renames:
            _replace_attr(node, renames[node.attr], lines, edits)
        elif node.attr.startswith("_cbcs_"):
            _replace_attr(node, window_names(node.attr, {}), lines, edits)
    elif isinstance(node, ast.Call):
        _rewrite_lookup(node, owners, renames, widgets, lines, edits)
    elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
        parent = parents.get(id(node))
        if isinstance(parent, ast.Attribute) and parent.value is node:
            pass
        elif node.id in renames:
            span = _span(node, lines)
            if span is not None:
                edits.append((span[0], span[1], "self.%s" % renames[node.id]))
        elif form_param and node.id == form_param:
            span = _span(node, lines)
            if span is not None:
                edits.append((span[0], span[1], "self"))
    for child in ast.iter_child_nodes(node):
        if isinstance(node, ast.ClassDef):
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node is not root and child in node.body:
            continue
        _walk(child, root, in_root_function, owners, widgets, renames, form_param, parents, lines, edits)


def _receiver_is_window(node: ast.Attribute) -> bool:
    """``self.ui.name`` and ``self._ui.name`` name a window method even inside a nested class."""

    value = node.value
    if not isinstance(value, ast.Attribute) or value.attr not in ("ui", "_ui", "_form"):
        return False
    base = value.value
    return isinstance(base, ast.Name) and base.id == "self"


def _rewrite_lookup(
    node: ast.Call,
    owners: Set[str],
    renames: Dict[str, str],
    widgets: frozenset,
    lines: Sequence[str],
    edits: List[Tuple[int, int, str]],
) -> None:
    func = node.func
    if not isinstance(func, ast.Name) or func.id not in ("getattr", "hasattr", "setattr"):
        return
    if len(node.args) < 2 or not isinstance(node.args[0], ast.Name) or node.args[0].id not in owners:
        return
    const = node.args[1]
    if isinstance(const, ast.Name):
        # Lookup helpers take the widget's object name in ``name``. The widget
        # lives on the generated Ui. A constant string is handled below.
        if const.id == "name":
            span = _span(node.args[0], lines)
            if span is not None:
                edits.append((span[0], span[1], "%s.ui" % node.args[0].id))
        return
    if not isinstance(const, ast.Constant) or not isinstance(const.value, str):
        return
    if const.value in renames:
        span = _span(const, lines)
        if span is not None:
            edits.append((span[0], span[1], '"%s"' % renames[const.value]))
        return
    if const.value.startswith("_cbcs_"):
        span = _span(const, lines)
        if span is not None:
            edits.append((span[0], span[1], '"%s"' % window_names(const.value, {})))
        return
    if const.value in widgets or const.value == "cbcs_refresh":
        span = _span(node.args[0], lines)
        if span is not None:
            edits.append((span[0], span[1], "%s.ui" % node.args[0].id))


def _receiver_is_owner(node: ast.Attribute, owners: Set[str]) -> bool:
    value = node.value
    if isinstance(value, ast.Name):
        return value.id in owners
    if isinstance(value, ast.Attribute) and value.attr in ("ui", "_ui", "_form"):
        base = value.value
        return isinstance(base, ast.Name) and base.id in owners
    return False


def _replace_attr(node: ast.Attribute, new: str, lines: Sequence[str], edits: List[Tuple[int, int, str]]) -> None:
    span = _span(node, lines)
    if span is None:
        return
    start, end = span
    width = len(node.attr)
    if end - start < width:
        return
    edits.append((end - width, end, new))


def _span(node: ast.AST, lines: Sequence[str]) -> Optional[Tuple[int, int]]:
    start_line = getattr(node, "lineno", None)
    end_line = getattr(node, "end_lineno", None)
    start_col = getattr(node, "col_offset", None)
    end_col = getattr(node, "end_col_offset", None)
    if None in (start_line, end_line, start_col, end_col):
        return None
    return _offset(lines, int(start_line), int(start_col)), _offset(lines, int(end_line), int(end_col))


def _offset(lines: Sequence[str], lineno: int, col: int) -> int:
    total = 0
    for index in range(lineno - 1):
        total += len(lines[index])
    return total + col


def _apply(source: str, edits: Sequence[Tuple[int, int, str]]) -> str:
    ordered = sorted(edits, key=lambda item: item[0], reverse=True)
    text = source
    last = len(text) + 1
    for start, end, replacement in ordered:
        if end > last or start < 0 or end < start:
            continue
        text = text[:start] + replacement + text[end:]
        last = start
    if not text.endswith("\n"):
        text += "\n"
    return text


def _wrap(name: str, params: str, body: str) -> str:
    signature = "def %s(self%s):" % (name, (", " + params) if params else "")
    lines = [signature]
    stripped = body.strip("\n")
    if not stripped:
        lines.append("    pass")
    else:
        for line in stripped.split("\n"):
            lines.append(("    " + line) if line else "")
    return "\n".join(lines) + "\n"


def _with_self(source: str, old: str, new: str) -> str:
    tree = ast.parse(source)
    definition = next(node for node in tree.body if isinstance(node, ast.FunctionDef))
    names = [arg.arg for arg in definition.args.args]
    if names and names[0] == "self":
        text = source
    elif names:
        text = source.replace("def %s(" % old, "def %s(self, " % old, 1)
    else:
        text = source.replace("def %s(" % old, "def %s(self" % old, 1)
    return text.replace("def %s(" % old, "def %s(" % new, 1)


def _function_texts(source: str) -> List[str]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    found = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        start = _offset(lines, node.lineno, 0)
        end = _offset(lines, node.end_lineno or node.lineno, 0)
        # end_lineno is the last line; include it.
        if node.end_lineno is not None and 1 <= node.end_lineno <= len(lines):
            end = _offset(lines, node.end_lineno, len(lines[node.end_lineno - 1]))
        found.append(source[start:end])
    return found


_LOCALS = (
    ("_conn", "conn"),
    ("_cursor", "cursor"),
    ("_item", "row"),
    ("_row", "row"),
    ("_value", "value"),
    ("_was", "was"),
)
_SQL_WORD = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|FROM|WHERE|VALUES|JOIN|ORDER|SET)\b", re.IGNORECASE)
_SQL_IDENT = re.compile(r'"[A-Za-z_][A-Za-z0-9_]*"')


def _planned(
    methods: Sequence[Method],
    helper_sources: Sequence[str],
    extras: Sequence[Tuple[str, str]],
    wrappers: Sequence[str],
    skip: Set[str],
    renames: Dict[str, str],
    public_of: Dict[str, str],
) -> Set[str]:
    names = set()
    for method in methods:
        if method.name in skip:
            continue
        names.add(renames.get(method.name, method.name))
    for name, _body in extras:
        names.add(name)
    for source in helper_sources:
        for function in _function_texts(source):
            tree = ast.parse(function)
            definition = next(node for node in tree.body if isinstance(node, ast.FunctionDef))
            names.add(renames.get(definition.name, window_names(definition.name, public_of)))
    names.add("_setup_ejected")
    for wrapper in wrappers:
        name = wrapper.split("(", 1)[0].split()[-1]
        if name:
            names.add(name)
    return names


def polish(
    source: str,
    planned: Set[str],
    known: Set[str],
    state: Optional[Set[str]] = None,
    present: Optional[Set[str]] = None,
    ui_methods: Optional[Set[str]] = None,
) -> str:
    """Make one ejected method read like code a person wrote."""

    ready = set(state or ())
    defined = set(present or ())
    text = _simplify(source, planned, known, defined, set(ui_methods or ()))
    text = _plain_reads(text, ready, planned, defined)
    text = _rename_locals(text)
    text = _restyle_strings(text)
    text = _wrap_long_sql(text)
    if not text.endswith("\n"):
        text += "\n"
    ast.parse(text)
    return text


def _simplify(source: str, planned: Set[str], known: Set[str], present: Set[str], ui_methods: Set[str]) -> str:
    tree = ast.parse(source)
    root = next(node for node in tree.body if isinstance(node, ast.FunctionDef))
    lines = source.splitlines(keepends=True)
    edits: List[Tuple[int, int, str]] = []
    _simplify_body(root.body, source, lines, planned, known, present, ui_methods, edits)
    return _apply(source, edits)


def _simplify_body(
    body: Sequence[ast.stmt],
    source: str,
    lines: Sequence[str],
    planned: Set[str],
    known: Set[str],
    present: Set[str],
    ui_methods: Set[str],
    edits: List[Tuple[int, int, str]],
) -> None:
    index = 0
    while index < len(body):
        stmt = body[index]
        nxt = body[index + 1] if index + 1 < len(body) else None
        refresh = _refresh_hedge(stmt, source, lines, "cbcs_refresh" in ui_methods)
        if refresh is not None:
            edits.append(refresh)
            index += 1
            continue
        direct = _direct_hook(stmt, lines)
        if direct is not None:
            edits.append(direct)
            index += 1
            continue
        if nxt is not None and _drop_redundant_write(stmt, nxt, lines, edits):
            index += 2
            continue
        if _drop_missing_call(stmt, lines, planned, present, edits):
            index += 1
            continue
        cancel = _cancel_hook(stmt, nxt) if nxt is not None else None
        if cancel is not None:
            name, _temp = cancel
            edits.append(_cancel_edit(stmt, nxt, lines, name, _kept(name, known, present)))
            index += 2
            continue
        guard = _guard(stmt, nxt) if nxt is not None else None
        if guard is not None:
            name, call_name = guard
            edits.append(
                _guard_edit(stmt, nxt, source, lines, name, call_name, _kept(name, known, present))
            )
            index += 2
            continue
        for child in _nested_bodies(stmt):
            _simplify_body(child, source, lines, planned, known, present, ui_methods, edits)
        index += 1


def _refresh_hedge(
    stmt: ast.stmt,
    source: str,
    lines: Sequence[str],
    keep: bool,
) -> Optional[Tuple[int, int, str]]:
    """``hasattr(self.ui, "cbcs_refresh")`` is known at eject time."""

    if not isinstance(stmt, ast.If) or len(stmt.body) != 1 or stmt.orelse:
        return None
    if not _is_refresh_call(stmt.body[0]):
        return None
    parts = stmt.test.values if isinstance(stmt.test, ast.BoolOp) and isinstance(stmt.test.op, ast.And) else [stmt.test]
    hedge = next((part for part in parts if _is_refresh_hasattr(part)), None)
    if hedge is None:
        return None
    start = _offset(lines, stmt.lineno, 0)
    end_line = stmt.end_lineno or stmt.lineno
    end = _offset(lines, end_line, len(lines[end_line - 1]))
    if not keep:
        return (start, end, "")
    rest = [part for part in parts if part is not hedge]
    indent = lines[stmt.lineno - 1][: stmt.col_offset]
    call = (ast.get_source_segment(source, stmt.body[0]) or "self.ui.cbcs_refresh()").strip()
    if not rest:
        return (start, end, "%s%s\n" % (indent, call))
    test = " and ".join(ast.get_source_segment(source, part) or "" for part in rest)
    return (start, end, "%sif %s:\n%s    %s\n" % (indent, test, indent, call))


def _is_refresh_hasattr(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "hasattr":
        return False
    if len(node.args) < 2 or not isinstance(node.args[1], ast.Constant) or node.args[1].value != "cbcs_refresh":
        return False
    owner = node.args[0]
    return (
        isinstance(owner, ast.Attribute)
        and owner.attr == "ui"
        and isinstance(owner.value, ast.Name)
        and owner.value.id == "self"
    )


def _is_refresh_call(stmt: ast.stmt) -> bool:
    if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
        return False
    func = stmt.value.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "cbcs_refresh"
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "ui"
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "self"
    )


def _ensure_assign(source: str, name: str, value: str) -> str:
    if ("self.%s =" % name) in source:
        return source
    return source + "    self.%s = %s\n" % (name, value)


def _nested_bodies(stmt: ast.stmt) -> List[Sequence[ast.stmt]]:
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return []
    found: List[Sequence[ast.stmt]] = []
    for attr in ("body", "orelse", "finalbody"):
        value = getattr(stmt, attr, None)
        if isinstance(value, list) and value and isinstance(value[0], ast.stmt):
            found.append(value)
    handlers = getattr(stmt, "handlers", None)
    if isinstance(handlers, list):
        for handler in handlers:
            if handler.body:
                found.append(handler.body)
    return found


def _drop_redundant_write(
    stmt: ast.stmt, nxt: ast.stmt, lines: Sequence[str], edits: List[Tuple[int, int, str]]
) -> bool:
    if not isinstance(stmt, ast.If) or not isinstance(nxt, ast.Expr):
        return False
    if len(stmt.body) != 1 or len(stmt.orelse) != 1:
        return False
    if not isinstance(stmt.body[0], ast.Expr) or not isinstance(stmt.orelse[0], ast.Expr):
        return False
    left = stmt.body[0].value
    right = stmt.orelse[0].value
    follow = nxt.value
    if not all(isinstance(node, ast.Call) for node in (left, right, follow)):
        return False
    if ast.dump(left.func) != ast.dump(right.func) or ast.dump(left.func) != ast.dump(follow.func):
        return False
    if len(follow.args) != 1 or not isinstance(follow.args[0], ast.IfExp):
        return False
    choice = follow.args[0]
    if ast.dump(choice.test) != ast.dump(stmt.test):
        return False
    if not left.args or not right.args:
        return False
    if ast.dump(choice.body) != ast.dump(left.args[0]) or ast.dump(choice.orelse) != ast.dump(right.args[0]):
        return False
    start = _offset(lines, stmt.lineno, 0)
    end = _offset(lines, stmt.end_lineno or stmt.lineno, len(lines[(stmt.end_lineno or stmt.lineno) - 1]))
    edits.append((start, end, ""))
    return True


def _guard(stmt: ast.stmt, nxt: ast.stmt) -> Optional[Tuple[str, str]]:
    if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
        return None
    target = stmt.targets[0]
    if not isinstance(target, ast.Name) or not isinstance(stmt.value, ast.Call):
        return None
    call = stmt.value
    if not isinstance(call.func, ast.Name) or call.func.id != "getattr" or len(call.args) < 3:
        return None
    owner, const, default = call.args[0], call.args[1], call.args[2]
    if not isinstance(owner, ast.Name) or owner.id != "self":
        return None
    if not isinstance(const, ast.Constant) or not isinstance(const.value, str):
        return None
    if not isinstance(default, ast.Constant) or default.value is not None:
        return None
    if not isinstance(nxt, ast.If) or nxt.orelse:
        return None
    test = nxt.test
    if not isinstance(test, ast.Compare) or len(test.ops) != 1 or not isinstance(test.ops[0], ast.IsNot):
        return None
    if not isinstance(test.left, ast.Name) or test.left.id != target.id:
        return None
    if len(test.comparators) != 1 or not isinstance(test.comparators[0], ast.Constant):
        return None
    if test.comparators[0].value is not None:
        return None
    return const.value, target.id


def _cancel_edit(
    stmt: ast.stmt, nxt: ast.stmt, lines: Sequence[str], name: str, keep: bool
) -> Tuple[int, int, str]:
    start = _offset(lines, stmt.lineno, 0)
    end_line = nxt.end_lineno or nxt.lineno
    end = _offset(lines, end_line, len(lines[end_line - 1]))
    if not keep:
        return start, end, ""
    indent = _line_indent(lines, nxt.lineno)
    text = "%sif self.%s() is False:\n%s    return False\n" % (indent, name, indent)
    return start, end, text


def _direct_hook(stmt: ast.stmt, lines: Sequence[str]) -> Optional[Tuple[int, int, str]]:
    """A form hook named at eject time is a direct call. A missing refresh call is omitted."""

    if not isinstance(stmt, ast.If) or stmt.orelse:
        return None
    name = _form_hook_name(stmt.test)
    if name:
        indent = _line_indent(lines, stmt.lineno)
        start, end = _stmt_bounds(stmt, lines)
        if _returns_false(stmt):
            return start, end, "%sif self.%s() is False:\n%s    return False\n" % (indent, name, indent)
        return start, end, "%sself.%s()\n" % (indent, name)
    return None


def _form_hook_name(test: ast.AST) -> str:
    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And) and test.values:
        test = test.values[0]
    if not isinstance(test, ast.Call) or not isinstance(test.func, ast.Name) or test.func.id != "hasattr":
        return ""
    if len(test.args) < 2:
        return ""
    owner, const = test.args[0], test.args[1]
    if not isinstance(const, ast.Constant) or not isinstance(const.value, str):
        return ""
    if not isinstance(owner, ast.Attribute) or owner.attr != "_form":
        return ""
    if not isinstance(owner.value, ast.Name) or owner.value.id != "self":
        return ""
    return const.value


def _returns_false(stmt: ast.If) -> bool:
    for node in stmt.body:
        if isinstance(node, ast.Return):
            value = node.value
            return isinstance(value, ast.Constant) and value.value is False
    return False


def _stmt_bounds(stmt: ast.stmt, lines: Sequence[str]) -> Tuple[int, int]:
    start = _offset(lines, stmt.lineno, 0)
    end_line = stmt.end_lineno or stmt.lineno
    return start, _offset(lines, end_line, len(lines[end_line - 1]))


def _line_indent(lines: Sequence[str], lineno: int) -> str:
    if lineno < 1 or lineno > len(lines):
        return ""
    raw = lines[lineno - 1]
    stripped = raw.lstrip(" ")
    return raw[: len(raw) - len(stripped)]


def _drop_missing_call(
    stmt: ast.stmt,
    lines: Sequence[str],
    planned: Set[str],
    present: Set[str],
    edits: List[Tuple[int, int, str]],
) -> bool:
    """A call of ``getattr(self, name, ...)`` goes away when this form has no such method."""

    if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
        return False
    func = stmt.value.func
    if not isinstance(func, ast.Call) or not isinstance(func.func, ast.Name) or func.func.id != "getattr":
        return False
    if len(func.args) < 2:
        return False
    owner, const = func.args[0], func.args[1]
    if not isinstance(owner, ast.Name) or owner.id != "self":
        return False
    if not isinstance(const, ast.Constant) or not isinstance(const.value, str):
        return False
    if const.value in planned or const.value in present:
        return False
    start = _offset(lines, stmt.lineno, 0)
    end_line = stmt.end_lineno or stmt.lineno
    end = _offset(lines, end_line, len(lines[end_line - 1]))
    edits.append((start, end, ""))
    return True


def _kept(name: str, known: Set[str], present: Set[str]) -> bool:
    return name in known or name in present


def _cancel_hook(stmt: ast.stmt, nxt: ast.stmt) -> Optional[Tuple[str, str]]:
    """``temp = getattr(self, name, None)`` then ``if temp is not None and temp() is False``."""

    found = _getattr_assign(stmt)
    if found is None or not isinstance(nxt, ast.If) or nxt.orelse:
        return None
    name, temp = found
    test = nxt.test
    if not isinstance(test, ast.BoolOp) or not isinstance(test.op, ast.And) or len(test.values) != 2:
        return None
    if not _is_not_none(test.values[0], temp) or not _call_is_false(test.values[1], temp):
        return None
    return name, temp


def _getattr_assign(stmt: ast.stmt) -> Optional[Tuple[str, str]]:
    if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
        return None
    target = stmt.targets[0]
    if not isinstance(target, ast.Name):
        return None
    call = _getattr_self(stmt.value)
    if call is None:
        return None
    return call, target.id


def _getattr_self(node: ast.AST) -> Optional[str]:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "getattr":
        return None
    if len(node.args) < 3:
        return None
    owner, const, default = node.args[0], node.args[1], node.args[2]
    if not isinstance(owner, ast.Name) or owner.id != "self":
        return None
    if not isinstance(const, ast.Constant) or not isinstance(const.value, str):
        return None
    if not isinstance(default, ast.Constant) or default.value is not None:
        return None
    return const.value


def _is_not_none(node: ast.AST, temp: str) -> bool:
    if not isinstance(node, ast.Compare) or len(node.ops) != 1 or not isinstance(node.ops[0], ast.IsNot):
        return False
    if not isinstance(node.left, ast.Name) or node.left.id != temp:
        return False
    return (
        len(node.comparators) == 1
        and isinstance(node.comparators[0], ast.Constant)
        and node.comparators[0].value is None
    )


def _call_is_false(node: ast.AST, temp: str) -> bool:
    if not isinstance(node, ast.Compare) or len(node.ops) != 1 or not isinstance(node.ops[0], ast.Is):
        return False
    call = node.left
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name) or call.func.id != temp:
        return False
    return (
        len(node.comparators) == 1
        and isinstance(node.comparators[0], ast.Constant)
        and node.comparators[0].value is False
    )


def _assigned_state(source: str) -> Set[str]:
    """Plain ``self.name = ...`` assignments. Those exist before the first refresh."""

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    root = next((node for node in tree.body if isinstance(node, ast.FunctionDef)), None)
    if root is None:
        return set()
    names = set()
    for stmt in root.body:
        if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
            continue
        target = stmt.targets[0]
        if not isinstance(target, ast.Attribute) or not isinstance(target.value, ast.Name):
            continue
        if target.value.id == "self" and _plain_value(stmt.value):
            names.add(target.attr)
    return names


def _plain_value(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.Name):
        return node.id == "self"
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return isinstance(node.operand, ast.Constant)
    if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
        return all(_plain_value(item) for item in node.elts)
    if isinstance(node, ast.Dict):
        return all(
            (key is None or _plain_value(key)) and _plain_value(value)
            for key, value in zip(node.keys, node.values)
        )
    return False


def _plain_reads(source: str, state: Set[str], planned: Set[str], present: Set[str]) -> str:
    """``getattr(self, name, default)`` becomes ``self.name`` once that name is real."""

    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    edits: List[Tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "getattr":
            continue
        if len(node.args) < 2:
            continue
        owner, const = node.args[0], node.args[1]
        if not isinstance(owner, ast.Name) or owner.id != "self":
            continue
        if not isinstance(const, ast.Constant) or not isinstance(const.value, str):
            continue
        name = const.value
        direct = name in state or name in planned or name in present
        absent = name in ("validate_fields", "cbcs_validate", "cbcsOnBeforeSave") and not direct
        if not direct and not absent:
            continue
        span = _span(node, lines)
        if span is not None:
            edits.append((span[0], span[1], "self.%s" % name if direct else "None"))
    return _apply(source, edits)


def _guard_edit(
    stmt: ast.stmt,
    nxt: ast.stmt,
    source: str,
    lines: Sequence[str],
    name: str,
    temp: str,
    keep: bool,
) -> Tuple[int, int, str]:
    start = _offset(lines, stmt.lineno, 0)
    end_line = nxt.end_lineno or nxt.lineno
    end = _offset(lines, end_line, len(lines[end_line - 1]))
    if not keep or not isinstance(nxt, ast.If):
        return start, end, ""
    first = nxt.body[0]
    last = nxt.body[-1]
    body = source[_offset(lines, first.lineno, 0) : _offset(lines, last.end_lineno or last.lineno, len(lines[(last.end_lineno or last.lineno) - 1]))]
    dedented = []
    for line in body.splitlines():
        dedented.append(line[4:] if line.startswith("    ") else line)
    text = re.sub(r"\b%s\b" % re.escape(temp), "self.%s" % name, "\n".join(dedented))
    return start, end, text + "\n"


def _rename_locals(source: str) -> str:
    tree = ast.parse(source)
    root = next(node for node in tree.body if isinstance(node, ast.FunctionDef))
    used = {node.id for node in ast.walk(root) if isinstance(node, ast.Name)}
    used.update(arg.arg for arg in root.args.args)
    occupied = set(used)
    lines = source.splitlines(keepends=True)
    edits: List[Tuple[int, int, str]] = []
    for old, new in _LOCALS:
        if old not in used or new in occupied:
            continue
        occupied.add(new)
        for node in ast.walk(root):
            if isinstance(node, ast.Name) and node.id == old:
                span = _span(node, lines)
                if span is not None:
                    edits.append((span[0], span[1], new))
            elif isinstance(node, ast.arg) and node.arg == old:
                span = _span(node, lines)
                if span is not None:
                    edits.append((span[0], span[1], new))
    pending: Dict[str, str] = {}
    defined = {
        node.name
        for node in ast.walk(root)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for node in ast.walk(root):
        name = ""
        if isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.arg):
            name = node.arg
        plain = _plain_local(name)
        if not plain or plain in occupied or name in pending or name in defined:
            continue
        pending[name] = plain
        occupied.add(plain)
    for old, new in pending.items():
        for node in ast.walk(root):
            if isinstance(node, ast.Name) and node.id == old:
                span = _span(node, lines)
                if span is not None:
                    edits.append((span[0], span[1], new))
            elif isinstance(node, ast.arg) and node.arg == old:
                span = _span(node, lines)
                if span is not None:
                    edits.append((span[0], span[1], new))
            elif isinstance(node, ast.ExceptHandler) and node.name == old:
                alias = _except_alias_span(node, lines, old)
                if alias is not None:
                    edits.append((alias[0], alias[1], new))
    return _apply(source, edits)


def _except_alias_span(node: ast.ExceptHandler, lines: Sequence[str], name: str) -> Optional[Tuple[int, int]]:
    """The ``as name`` token. The alias is not an ``ast.Name``."""

    if node.lineno < 1 or node.lineno > len(lines):
        return None
    line = lines[node.lineno - 1]
    token = "as %s" % name
    column = line.find(token)
    if column < 0:
        return None
    start = _offset(lines, node.lineno, column + 3)
    return start, start + len(name)


def _plain_local(name: str) -> str:
    """The name without one leading underscore, when that name is free to use."""

    if not name.startswith("_") or name.startswith("__") or name.startswith("_cbcs"):
        return ""
    plain = name[1:]
    if not plain.isidentifier() or keyword.iskeyword(plain):
        return ""
    return plain


def _restyle_strings(source: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    edits: List[Tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        span = _span(node, lines)
        if span is None:
            continue
        start, end = span
        if start > 0 and source[start - 1] in "uUbBrR" and source[start] in "'\"":
            start -= 1
        token = source[start:end]
        if not _is_sql(node.value):
            if token[:1] in ("u", "U"):
                edits.append((start, end, token[1:]))
            continue
        edits.append((start, end, _sql_literal(node.value)))
    return _apply(source, edits)


def _is_sql(value: str) -> bool:
    return '"' in value and (_SQL_WORD.search(value) is not None or _SQL_IDENT.search(value) is not None)


def _sql_literal(value: str) -> str:
    return "'%s'" % value.replace("\\", "\\\\").replace("'", "\\'")


def _wrap_long_sql(source: str) -> str:
    lines = source.splitlines(keepends=True)
    out = []
    for line in lines:
        bare = line.rstrip("\n")
        newline = line[len(bare) :]
        if len(bare) <= 100:
            out.append(line)
            continue
        wrapped = _break_line(bare)
        out.append((wrapped + newline) if wrapped is not None else line)
    return "".join(out)


def _break_line(line: str) -> Optional[str]:
    indent = line[: len(line) - len(line.lstrip(" \t"))]
    dict_text = _break_dict(line, indent)
    if dict_text is not None:
        return dict_text
    found = _longest_sql(line)
    if found is None:
        return None
    start, end, sql = found
    head = line[:start].rstrip()
    tail = line[end:]
    if ".execute(" in head and head.endswith("("):
        return _break_call(head, tail, sql, indent)
    pieces = _sql_pieces(sql)
    parts = [head + " ("]
    for piece in pieces:
        parts.append(indent + "    " + _sql_literal(piece))
    parts.append(indent + ")" + tail)
    return "\n".join(parts)


def _longest_sql(line: str) -> Optional[Tuple[int, int, str]]:
    best = None
    for start, end in _string_spans(line):
        try:
            value = ast.literal_eval(line[start:end])
        except (SyntaxError, ValueError):
            continue
        if not isinstance(value, str) or not _is_sql(value):
            continue
        if best is None or end - start > best[1] - best[0]:
            best = (start, end, value)
    return best


def _break_call(head: str, tail: str, sql: str, indent: str) -> str:
    chunks = _sql_pieces(sql)
    parts = [head]
    if tail.startswith(",") and len(indent + "    " + _sql_literal(chunks[-1]) + tail) > 100:
        for piece in chunks[:-1]:
            parts.append(indent + "    " + _sql_literal(piece))
        parts.append(indent + "    " + _sql_literal(chunks[-1]) + ",")
        parts.append(indent + "    " + tail[1:].lstrip())
        return "\n".join(parts)
    for index, piece in enumerate(chunks):
        row = indent + "    " + _sql_literal(piece)
        if index == len(chunks) - 1:
            row += tail
        parts.append(row)
    return "\n".join(parts)


def _sql_pieces(sql: str) -> List[str]:
    chunks = _sql_chunks(sql, 68)
    pieces = []
    for index, chunk in enumerate(chunks):
        pieces.append(chunk if index == len(chunks) - 1 else chunk + " ")
    return pieces


def _break_dict(line: str, indent: str) -> Optional[str]:
    match = re.match(r"^(\s*[\w.]+\s*=\s*)\{(.*)\}\s*$", line)
    if match is None or len(line) <= 100:
        return None
    body = match.group(2).strip()
    if not body or '"' not in body:
        return None
    try:
        value = ast.literal_eval("{" + body + "}")
    except (SyntaxError, ValueError):
        return None
    if not isinstance(value, dict):
        return None
    rows = [match.group(1).rstrip() + " {"]
    items = list(value.items())
    for index, (key, item) in enumerate(items):
        rendered = _sql_literal(item) if isinstance(item, str) and _is_sql(item) else repr(item)
        comma = "," if index < len(items) - 1 else ""
        rows.append('%s    %s: %s%s' % (indent, repr(key), rendered, comma))
    rows.append(indent + "}")
    return "\n".join(rows)


def _string_spans(line: str) -> List[Tuple[int, int]]:
    spans = []
    index = 0
    while index < len(line):
        if line[index] not in "'\"":
            index += 1
            continue
        quote = line[index]
        start = index
        index += 1
        while index < len(line):
            if line[index] == "\\":
                index += 2
                continue
            if line[index] == quote:
                index += 1
                spans.append((start, index))
                break
            index += 1
    return spans


def _sql_chunks(sql: str, width: int) -> List[str]:
    if len(sql) <= width:
        return [sql]
    # A fragment such as ' WHERE "id" = ?' keeps its leading space. split()
    # yields an empty first word, and an empty current would drop that space.
    lead = sql[: len(sql) - len(sql.lstrip(" "))]
    words = sql.lstrip(" ").split(" ")
    rows: List[str] = []
    current = ""
    for word in words:
        if word == "" and not current:
            continue
        trial = word if not current else current + " " + word
        if current and len(lead) + len(trial) > width and not rows:
            rows.append(lead + current)
            lead = ""
            current = word
        elif current and len(trial) > width:
            rows.append(current)
            current = word
        else:
            current = trial
    if current:
        rows.append(lead + current)
    return rows or [sql]


def _helper_names(sources: Sequence[str]) -> List[str]:
    found = []
    for source in sources:
        if not source.strip():
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                found.append(node.name)
    return found
