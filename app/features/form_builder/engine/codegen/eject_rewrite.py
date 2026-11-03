"""Turn expander text (``self`` is the generated Ui) into window-class methods.

The edit is a span replacement on the parsed function, so comments and string
literals stay as the expander wrote them. Widget attributes become
``self.ui.<name>``. Calls and callback loads of generated methods use the
window method's name.
"""

from __future__ import annotations

import ast
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
    widget_names = frozenset(widgets)
    blocks: List[str] = []
    public: List[str] = []
    helpers: List[str] = []
    emitted: Set[str] = set()
    for method in methods:
        if method.name in skip or method.name in emitted:
            continue
        emitted.add(method.name)
        new = renames.get(method.name, method.name)
        source = _wrap(new, method.params, bodies.get(method.name, method.body), method.source_ref)
        rewritten = rewrite_function(source, widget_names, renames, form_param)
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
            rewritten = rewrite_function(_with_self(function, definition.name, new), widget_names, renames, form_param)
            blocks.append(rewritten)
    setup = _wrap("_setup_ejected", "", "\n".join(setup_lines), "")
    blocks.append(rewrite_function(setup, widget_names, renames, form_param))
    helpers.append("_setup_ejected")
    for wrapper in wrappers:
        blocks.append(wrapper.rstrip() + "\n")
        name = wrapper.split("(", 1)[0].split()[-1]
        if name and name not in helpers:
            helpers.append(name)
    ordered_public = tuple(dict.fromkeys(public))
    ordered_helpers = tuple(dict.fromkeys(helpers))
    return "\n".join(block.rstrip() for block in blocks if block.strip()) + "\n", ordered_public, ordered_helpers


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
            _replace_attr(node, window_names(node.attr, {}), lines, edits)
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


def _wrap(name: str, params: str, body: str, source_ref: str) -> str:
    signature = "def %s(self%s):" % (name, (", " + params) if params else "")
    lines = [signature]
    if source_ref:
        lines.append("    # %s" % source_ref)
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
