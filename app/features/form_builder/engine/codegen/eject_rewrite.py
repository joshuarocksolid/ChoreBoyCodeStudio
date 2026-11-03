"""Turn expander text (``self`` is the generated Ui) into window-class methods.

The edit is a span replacement on the parsed function. Widget attributes
become ``self.ui.<name>``. Calls of generated methods use the window method's
name. A later pass drops the ``u`` prefix, quotes SQL with single quotes, and
removes guards this eject can resolve.
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
    planned = _planned(methods, helper_sources, extras, wrappers, skip, renames, public_of)
    known = set(renames.values()) | planned
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
        source = _wrap(new, method.params, bodies.get(method.name, method.body))
        rewritten = polish(rewrite_function(source, widget_names, renames, form_param), planned, known)
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
            )
            blocks.append(rewritten)
    setup = _wrap("_setup_ejected", "", "\n".join(setup_lines))
    blocks.append(polish(rewrite_function(setup, widget_names, renames, form_param), planned, known))
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


_LOCALS = (("_conn", "conn"), ("_cursor", "cursor"), ("_item", "row"))
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


def polish(source: str, planned: Set[str], known: Set[str]) -> str:
    """Make one ejected method read like code a person wrote."""

    text = _simplify(source, planned, known)
    text = _rename_locals(text)
    text = _restyle_strings(text)
    text = _wrap_long_sql(text)
    if not text.endswith("\n"):
        text += "\n"
    ast.parse(text)
    return text


def _simplify(source: str, planned: Set[str], known: Set[str]) -> str:
    tree = ast.parse(source)
    root = next(node for node in tree.body if isinstance(node, ast.FunctionDef))
    lines = source.splitlines(keepends=True)
    edits: List[Tuple[int, int, str]] = []
    _simplify_body(root.body, source, lines, planned, known, edits)
    return _apply(source, edits)


def _simplify_body(
    body: Sequence[ast.stmt],
    source: str,
    lines: Sequence[str],
    planned: Set[str],
    known: Set[str],
    edits: List[Tuple[int, int, str]],
) -> None:
    index = 0
    while index < len(body):
        stmt = body[index]
        nxt = body[index + 1] if index + 1 < len(body) else None
        if nxt is not None and _drop_redundant_write(stmt, nxt, lines, edits):
            index += 2
            continue
        guard = _guard(stmt, nxt) if nxt is not None else None
        if guard is not None:
            name, call_name = guard
            if name in planned or (name in known) or name.startswith("_"):
                edits.append(_guard_edit(stmt, nxt, source, lines, name, call_name, name in planned))
                index += 2
                continue
        for child in _nested_bodies(stmt):
            _simplify_body(child, source, lines, planned, known, edits)
        index += 1


def _nested_bodies(stmt: ast.stmt) -> List[Sequence[ast.stmt]]:
    found: List[Sequence[ast.stmt]] = []
    for node in ast.iter_child_nodes(stmt):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = getattr(node, "body", None)
        if isinstance(body, list):
            found.append(body)
        orelse = getattr(node, "orelse", None)
        if isinstance(orelse, list) and orelse and isinstance(orelse[0], ast.stmt):
            found.append(orelse)
        handlers = getattr(node, "handlers", None)
        if isinstance(handlers, list):
            for handler in handlers:
                found.append(handler.body)
        final = getattr(node, "finalbody", None)
        if isinstance(final, list):
            found.append(final)
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
    lines = source.splitlines(keepends=True)
    edits: List[Tuple[int, int, str]] = []
    for old, new in _LOCALS:
        if old not in used or new in used:
            continue
        for node in ast.walk(root):
            if isinstance(node, ast.Name) and node.id == old:
                span = _span(node, lines)
                if span is not None:
                    edits.append((span[0], span[1], new))
            elif isinstance(node, ast.arg) and node.arg == old:
                span = _span(node, lines)
                if span is not None:
                    edits.append((span[0], span[1], new))
    return _apply(source, edits)


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
