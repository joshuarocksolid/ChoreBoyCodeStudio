"""Names, types, blanks, and slots (CONTRACTS.md 17.4 and 17.6).

The tree is trusted once it exists. This pass only fills types and problems.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import List, Optional, Sequence, Set, Tuple

from app.features.form_builder.engine.logic.formula.env import (
    VALUE_SLOTS,
    YESNO_SLOTS,
    FormulaEnv,
    SlotKind,
    WidgetFacts,
    is_reserved_word,
)
from app.features.form_builder.engine.logic.formula.library import (
    FUNCTIONS,
    FunctionSpec,
    accepts_tag,
    result_type,
)
from app.features.form_builder.engine.logic.formula.nodes import (
    Analysis,
    Attr,
    Bin,
    Bool,
    Call,
    Compare,
    Fix,
    FormulaProblem,
    IfElse,
    ListLit,
    Lit,
    Node,
    Ref,
    Span,
    Unary,
    WindowCall,
)
from app.features.form_builder.engine.logic.formula.parse import parse_text
from app.features.form_builder.engine.logic.formula.types import (
    ANY,
    BLANK,
    DATE,
    FKind,
    FType,
    NUMBER,
    TEXT,
    WHOLE,
    YESNO,
    ARITH,
    assignable,
    is_numeric,
    lookup_spec,
    main_type,
    same_or_numeric,
    type_phrase,
    unwrap,
    widen_numeric,
)

_FB103 = "Not available in formulas. Use a method instead."
_EXCEL_IDS = frozenset(
    {
        "blank_compare",
        "excel_if",
        "excel_and",
        "excel_or",
        "excel_not",
        "excel_isblank",
        "join_amp",
        "percent",
        "diamond",
        "amp_amp",
        "pipe_pipe",
        "bang",
        "semicolon",
        "leading_equals",
        "compare_equals",
        "bool_true",
        "bool_false",
        "label",
    }
)
_FB115 = "Connect this form to a table first (coming with data forms)."
_FORM_ATTRS = {"isNew": YESNO, "isDirty": YESNO, "position": WHOLE, "count": WHOLE}
_VERBS = {"+": "add", "-": "subtract", "*": "multiply", "/": "divide"}
_FORMATS = frozenset(
    {
        "",
        "money",
        "date:short",
        "date:long",
        "date:iso",
        "text:upper",
        "text:proper",
    }
)
_RETURN = {
    "bool": YESNO,
    "int": WHOLE,
    "Decimal": NUMBER,
    "float": NUMBER,
    "str": TEXT,
    "date": DATE,
    "datetime": FType(FKind.DATETIME),
    "time": FType(FKind.TIME),
}


@dataclass
class _Ctx:
    aggregate: bool = False
    bare_grid: bool = False


@dataclass
class _State:
    env: FormulaEnv
    text: str
    problems: List[FormulaProblem]
    fixes: List[Fix]
    reads: Set[str]
    calls: List[str]
    wraps: List[Span]
    covered: Tuple[Fix, ...] = ()


def analyze(text: str, env: FormulaEnv, slot: SlotKind) -> Analysis:
    """Parse and check. Any string returns an analysis. Nothing is raised."""
    try:
        return _analyze(text, env, slot)
    except Exception as exc:
        message = "This formula isn't finished: %s" % exc.__class__.__name__
        span = Span(0, len(text) if isinstance(text, str) else 0)
        return Analysis(
            text if isinstance(text, str) else "",
            None,
            None,
            (FormulaProblem("FB108", span, message),),
            (),
            frozenset(),
            (),
            (),
        )


def _analyze(text: str, env: FormulaEnv, slot: SlotKind) -> Analysis:
    parsed = parse_text(text, env)
    problems = list(parsed.problems)
    fixes = list(parsed.fixes)
    _add_fix_problems(problems, fixes)
    if parsed.tree is None:
        return Analysis(text, None, None, _prefer(problems, fixes), tuple(fixes), frozenset(), (), ())
    state = _State(env, text, [], [], set(), [], [], tuple(fixes))
    typed = _check(state, parsed.tree, _Ctx())
    if typed is None:
        problems.extend(state.problems)
        return Analysis(text, None, None, _prefer(problems, fixes), tuple(fixes), frozenset(state.reads), tuple(state.calls), ())
    _apply_slot(state, typed, slot)
    problems.extend(state.problems)
    fixes.extend(state.fixes)
    _add_fix_problems(problems, state.fixes)
    kept = _prefer(problems, fixes)
    reported = typed.type
    if slot.name in YESNO_SLOTS and any(item == typed.span for item in state.wraps):
        reported = YESNO
    return Analysis(
        text,
        typed,
        reported,
        kept,
        tuple(fixes),
        frozenset(state.reads),
        tuple(state.calls),
        tuple(state.wraps),
    )


def _add_fix_problems(problems: List[FormulaProblem], fixes: Sequence[Fix]) -> None:
    have = {(item.code, item.span.start, item.span.end, item.fix_id) for item in problems}
    for fix in fixes:
        if fix.fix_id not in _EXCEL_IDS:
            continue
        key = ("FB107", fix.span.start, fix.span.end, fix.fix_id)
        if key in have:
            continue
        problems.append(FormulaProblem("FB107", fix.span, fix.message, fix.fix_id))
        have.add(key)


def _prefer(problems: Sequence[FormulaProblem], fixes: Sequence[Fix]) -> Tuple[FormulaProblem, ...]:
    excel = [fix for fix in fixes if fix.fix_id in _EXCEL_IDS]
    if not excel:
        return _sorted(problems)
    kept = []
    for problem in problems:
        if problem.code in ("FB101", "FB103") and _inside_fix(problem.span, excel):
            continue
        kept.append(problem)
    return _sorted(kept)


def _inside_fix(span: Span, fixes: Sequence[Fix]) -> bool:
    for fix in fixes:
        if fix.span.start <= span.start and span.end <= fix.span.end:
            return True
    return False


def _sorted(problems: Sequence[FormulaProblem]) -> Tuple[FormulaProblem, ...]:
    return tuple(sorted(problems, key=lambda item: (item.span.start, item.span.end, item.code)))


def _check(state: _State, node: Node, ctx: _Ctx) -> Optional[Node]:
    if isinstance(node, Lit):
        return node
    if isinstance(node, Ref):
        return _check_ref(state, node, ctx)
    if isinstance(node, Attr):
        return _check_attr(state, node, ctx)
    if isinstance(node, Call):
        return _check_call(state, node, ctx)
    if isinstance(node, WindowCall):
        return _check_window(state, node, ctx)
    if isinstance(node, Unary):
        return _check_unary(state, node, ctx)
    if isinstance(node, Bin):
        return _check_bin(state, node, ctx)
    if isinstance(node, Bool):
        return _check_bool(state, node, ctx)
    if isinstance(node, Compare):
        return _check_compare(state, node, ctx)
    if isinstance(node, IfElse):
        return _check_if(state, node, ctx)
    if isinstance(node, ListLit):
        return _check_list(state, node, ctx, None)
    return None


def _check_ref(state: _State, node: Ref, ctx: _Ctx) -> Ref:
    name = node.name
    env = state.env
    if name in ("form", "record", "window"):
        _problem(state, "FB114", node.span, "%s has no value a formula can read" % name)
        return replace(node, type=ANY)
    if name in env.reserved:
        _problem(state, "FB103", node.span, _FB103)
        return replace(node, type=ANY)
    if is_reserved_word(name, env.reserved):
        _problem(state, "FB106", node.span, "That name is reserved.")
        return replace(node, type=ANY)
    facts = env.widgets.get(name)
    if facts is None:
        if name in env.page_names():
            return replace(node, type=FType(FKind.PAGE))
        _unknown(state, node)
        return replace(node, type=ANY)
    matched, spec = _spec_of(env, facts)
    display = facts.display or name
    if spec is None or matched is None:
        _problem(state, "FB114", node.span, "%s has no value a formula can read" % display)
        state.reads.add(name)
        return replace(node, type=ANY)
    value, unknown = main_type(
        spec,
        matched,
        kind=facts.kind,
        prefix=facts.prefix,
        decimals=facts.decimals,
        has_items_data=facts.has_items_data,
    )
    state.reads.add(name)
    if unknown:
        _problem(
            state,
            "FB118",
            node.span,
            "%s has an unknown kind, so this formula reads it as text." % display,
        )
    if value is None:
        if ctx.bare_grid and matched == "QTableView":
            return replace(node, type=ANY)
        _problem(state, "FB114", node.span, "%s has no value a formula can read" % display)
        return replace(node, type=ANY)
    return replace(node, type=value)


def _check_attr(state: _State, node: Attr, ctx: _Ctx) -> Node:
    if not isinstance(node.base, Ref):
        base = _check(state, node.base, ctx)
        _problem(state, "FB103", node.span, _FB103)
        return replace(node, base=base or node.base, type=ANY)
    base_name = node.base.name
    if base_name == "window":
        _problem(state, "FB103", node.span, _FB103)
        return replace(node, type=ANY)
    if base_name == "form":
        return _named_attr(state, node, _FORM_ATTRS, data=True)
    if base_name == "record":
        if node.sub is not None:
            _problem(state, "FB114", node.span, "record has no %s.%s." % (node.name, node.sub))
            return replace(node, type=ANY)
        _data_required(state, node.span)
        return replace(node, type=TEXT)
    facts = state.env.widgets.get(base_name)
    if facts is None:
        typed = _check_ref(state, node.base, ctx)
        return replace(node, base=typed, type=ANY)
    typed = replace(node.base, type=ANY)
    state.reads.add(base_name)
    return _widget_attr(state, node, typed, facts, ctx)


def _named_attr(state: _State, node: Attr, known: dict, data: bool) -> Node:
    if node.sub is not None or node.name not in known:
        label = node.base.name if isinstance(node.base, Ref) else "this"
        extra = node.name if node.sub is None else "%s.%s" % (node.name, node.sub)
        _problem(state, "FB114", node.span, "%s has no %s." % (label, extra))
        return replace(node, type=ANY)
    if data:
        _data_required(state, node.span)
    return replace(node, type=known[node.name])


def _widget_attr(state: _State, node: Attr, base: Ref, facts: WidgetFacts, ctx: _Ctx) -> Node:
    matched, spec = _spec_of(state.env, facts)
    display = facts.display or base.name
    if matched == "QTableView":
        return _grid_attr(state, node, base, display, ctx)
    standard = _standard_attr(matched, node.name)
    if node.sub is None and standard is not None:
        return replace(node, base=base, type=standard)
    if matched == "QComboBox" and node.sub is None and node.name in facts.also:
        _data_required(state, node.span)
        return replace(node, base=base, type=TEXT)
    if spec is None and matched is None:
        _problem(state, "FB114", node.span, "%s has no value a formula can read" % display)
        return replace(node, base=base, type=ANY)
    extra = node.name if node.sub is None else "%s.%s" % (node.name, node.sub)
    _problem(state, "FB114", node.span, "%s has no %s." % (display, extra))
    return replace(node, base=base, type=ANY)


def _grid_attr(state: _State, node: Attr, base: Ref, display: str, ctx: _Ctx) -> Node:
    """A bound grid has no main value. Columns need a data form, and a whole column needs an aggregate."""
    if node.sub is None and node.name in ("enabled", "visible"):
        return replace(node, base=base, type=YESNO)
    if node.sub is None and node.name == "count":
        _data_required(state, node.span)
        return replace(node, base=base, type=WHOLE)
    if node.name == "selected" and node.sub:
        _data_required(state, node.span)
        return replace(node, base=base, type=TEXT)
    if node.sub is None and node.name not in ("text", "enabled", "visible", "checked", "count", "selected"):
        _data_required(state, node.span)
        if state.env.data is not None and not ctx.aggregate:
            _problem(
                state,
                "FB113",
                node.span,
                "%s is a whole column, so it only belongs inside sum, count, avg, min, or max." % node.name,
            )
            return replace(node, base=base, type=ANY)
        if state.env.data is None:
            return replace(node, base=base, type=ANY)
        return replace(node, base=base, type=FType(FKind.COLUMN, TEXT))
    extra = node.name if node.sub is None else "%s.%s" % (node.name, node.sub)
    _problem(state, "FB114", node.span, "%s has no %s." % (display, extra))
    return replace(node, base=base, type=ANY)


def _standard_attr(matched: Optional[str], name: str) -> Optional[FType]:
    if name in ("enabled", "visible") and matched is not None:
        return YESNO
    if name == "text" and matched not in (None, "QTableView"):
        return TEXT
    if name == "checked" and matched in ("QCheckBox", "QRadioButton"):
        return YESNO
    if name == "count" and matched in ("QComboBox", "QListWidget", "QTableView"):
        return WHOLE
    return None


def _check_call(state: _State, node: Call, ctx: _Ctx) -> Node:
    spec = FUNCTIONS.get(node.func)
    child_ctx = _Ctx(aggregate=spec.column if spec is not None else False, bare_grid=node.func == "count")
    args = []
    for arg in node.args:
        checked = _check(state, arg, child_ctx)
        if checked is None:
            return replace(node, type=ANY)
        args.append(checked)
    if spec is None:
        _problem(state, "FB103", node.span, _FB103)
        return replace(node, args=tuple(args), type=ANY)
    column_call = _column_call(spec, args)
    if node.func in ("sum", "avg") and not column_call:
        if len(args) != 1:
            _problem(state, "FB112", node.span, _count_message(node.func, spec, len(args)))
        elif not _has_code(state, args[0].span, "FB115"):
            _problem(state, "FB102", args[0].span, _mismatch("pass", args[0].type, FType(FKind.COLUMN, TEXT), _subject(args[0])))
    elif node.func == "count" and len(args) == 1 and (_is_grid(state, args[0]) or column_call):
        if state.env.data is None and not _has_code(state, args[0].span, "FB115"):
            _problem(state, "FB115", args[0].span, _FB115)
    elif not _count_ok(spec, len(args), column_call):
        _problem(state, "FB112", node.span, _count_message(node.func, spec, len(args)))
    elif not column_call:
        _check_params(state, spec, args)
    if spec.pattern_arg is not None and spec.pattern_arg < len(args):
        _check_pattern(state, args[spec.pattern_arg])
    if node.func == "text" and len(args) == 2:
        _check_format(state, args[1])
    produced = result_type(spec, tuple(arg.type for arg in args))
    if spec.result_rule == "if_blank" and len(args) == 2 and not _blank_pair(args[0].type, args[1].type):
        _problem(state, "FB102", node.span, _mismatch("use", args[0].type, args[1].type, _subject(args[0])))
    return replace(node, args=tuple(args), type=produced)


def _has_code(state: _State, span: Span, code: str) -> bool:
    return any(item.code == code and item.span == span for item in state.problems)


def _column_call(spec: FunctionSpec, args: Sequence[Node]) -> bool:
    if not spec.column or len(args) != 1:
        return False
    return args[0].type.kind == FKind.COLUMN or args[0].type.kind == FKind.ANY


def _count_ok(spec: FunctionSpec, count: int, column_call: bool) -> bool:
    if column_call and spec.column:
        return True
    if count < spec.required:
        return False
    if spec.max_args is not None and count > spec.max_args:
        return False
    if not spec.varargs and spec.max_args is None and count != spec.required:
        return False
    return True


def _count_message(name: str, spec: FunctionSpec, got: int) -> str:
    if spec.max_args is not None and spec.required != spec.max_args:
        return "%s takes %d or %d values, not %d." % (name, spec.required, spec.max_args, got)
    if spec.varargs:
        return "%s takes at least %d values, not %d." % (name, spec.required, got)
    return "%s takes %d values, not %d." % (name, spec.required, got)


def _check_params(state: _State, spec: FunctionSpec, args: Sequence[Node]) -> None:
    for index, arg in enumerate(args):
        if index < len(spec.params):
            tag = spec.params[index]
        elif spec.varargs and spec.params:
            tag = spec.params[-1]
        else:
            tag = "any"
        if not accepts_tag(tag, arg.type):
            expected = _tag_type(tag)
            _problem(state, "FB102", arg.span, _mismatch("pass", arg.type, expected, _subject(arg)))


def _tag_type(tag: str) -> FType:
    return {"text": TEXT, "number": NUMBER, "whole": WHOLE, "date": DATE, "yesno": YESNO}.get(tag, ANY)


def _check_pattern(state: _State, arg: Node) -> None:
    if not isinstance(arg, Lit) or not isinstance(arg.value, str):
        _problem(state, "FB105", arg.span, "The pattern has to be written in quotes.")
        return
    if len(arg.value) > 200:
        _problem(state, "FB105", arg.span, "That pattern is too long.")
        return
    try:
        re.compile(arg.value)
    except re.error:
        _problem(state, "FB105", arg.span, "That pattern isn't one this formula can use.")


def _check_format(state: _State, arg: Node) -> None:
    if not isinstance(arg, Lit) or not isinstance(arg.value, str):
        return
    token = arg.value
    if token in _FORMATS or _numbered_format(token):
        return
    _problem(state, "FB118", arg.span, "%s is an unknown format, so this formula shows the value as text." % token)


def _numbered_format(token: str) -> bool:
    for prefix in ("number:", "percent:"):
        if token.startswith(prefix) and token[len(prefix) :].isdigit():
            return True
    return False


def _check_window(state: _State, node: WindowCall, ctx: _Ctx) -> Node:
    args = []
    for arg in node.args:
        checked = _check(state, arg, ctx)
        if checked is None:
            return replace(node, type=ANY)
        args.append(checked)
    state.calls.append(node.method)
    method = state.env.methods.get(node.method)
    if method is None:
        _problem(
            state,
            "FB109",
            node.span,
            "%s is not in %s (%s)." % (node.method, state.env.class_name, state.env.window_file),
        )
        return replace(node, args=tuple(args), type=ANY)
    got = len(args)
    upper = len(method.params)
    if method.has_varargs:
        bad = got < method.required
    else:
        bad = got < method.required or got > upper
    if bad:
        _problem(
            state,
            "FB112",
            node.span,
            "%s takes %d values, not %d." % (node.method, method.required if not method.has_varargs else method.required, got),
        )
    produced = _RETURN.get(state.env.returns.get(node.method, "").strip(), ANY)
    return replace(node, args=tuple(args), type=produced)


def _check_unary(state: _State, node: Unary, ctx: _Ctx) -> Node:
    child = _check(state, node.x, ctx)
    if child is None:
        return replace(node, type=ANY)
    if node.op == "not":
        _expect_yesno(state, child)
        return replace(node, x=child, type=YESNO)
    kind = unwrap(child.type).kind
    if kind == FKind.BLANK:
        return replace(node, x=child, type=BLANK)
    if kind not in (FKind.WHOLE, FKind.NUMBER, FKind.MONEY, FKind.ANY):
        _problem(state, "FB102", node.span, _mismatch("use", child.type, NUMBER, _subject(child)))
        return replace(node, x=child, type=ANY)
    return replace(node, x=child, type=child.type)


def _check_bin(state: _State, node: Bin, ctx: _Ctx) -> Node:
    left = _check(state, node.a, ctx)
    right = _check(state, node.b, ctx)
    if left is None or right is None:
        return replace(node, type=ANY)
    produced = _arith(node.op, left.type, right.type)
    if produced is None:
        _problem(state, "FB102", node.span, _mismatch(_VERBS[node.op], left.type, right.type, _subject(left)))
        if node.op == "+" and unwrap(left.type).kind == FKind.TEXT and is_numeric(right.type):
            _offer_text(state, right)
        elif node.op == "+" and is_numeric(left.type) and unwrap(right.type).kind == FKind.TEXT:
            _offer_text(state, left)
        produced = ANY
    return replace(node, a=left, b=right, type=produced)


def _arith(op: str, left: FType, right: FType) -> Optional[FType]:
    a = unwrap(left)
    b = unwrap(right)
    if a.kind == FKind.ANY or b.kind == FKind.ANY:
        return ANY
    if a.kind == FKind.BLANK and b.kind == FKind.BLANK:
        return BLANK
    if a.kind == FKind.BLANK:
        return _blank_with(op, b)
    if b.kind == FKind.BLANK:
        return _blank_with(op, a)
    found = ARITH.get((op, a.kind, b.kind))
    if found is None:
        return None
    return FType(found)


def _blank_with(op: str, other: FType) -> Optional[FType]:
    if other.kind == FKind.TEXT and op == "+":
        return TEXT
    if other.kind in (FKind.WHOLE, FKind.NUMBER, FKind.MONEY):
        if op == "/" and other.kind != FKind.MONEY:
            return NUMBER
        return other
    if other.kind == FKind.DATE and op in ("+", "-"):
        return DATE
    return None


def _check_bool(state: _State, node: Bool, ctx: _Ctx) -> Node:
    values = []
    for item in node.values:
        checked = _check(state, item, ctx)
        if checked is None:
            return replace(node, type=YESNO)
        _expect_yesno(state, checked)
        values.append(checked)
    return replace(node, values=tuple(values), type=YESNO)


def _check_compare(state: _State, node: Compare, ctx: _Ctx) -> Node:
    first = _check(state, node.first, ctx)
    if first is None:
        return replace(node, type=YESNO)
    pairs = []
    current = first
    for op, right in node.pairs:
        if op in ("in", "not in") and isinstance(right, ListLit):
            checked_list = _check_list(state, right, ctx, current.type)
            if checked_list is None:
                return replace(node, type=YESNO)
            _list_matches(state, current, checked_list)
            pairs.append((op, checked_list))
            continue
        checked = _check(state, right, ctx)
        if checked is None:
            return replace(node, type=YESNO)
        if not same_or_numeric(current.type, checked.type):
            _problem(state, "FB102", node.span, _mismatch("compare", current.type, checked.type, _subject(current)))
        pairs.append((op, checked))
        current = checked
    return replace(node, first=first, pairs=tuple(pairs), type=YESNO)


def _check_if(state: _State, node: IfElse, ctx: _Ctx) -> Node:
    test = _check(state, node.test, ctx)
    yes = _check(state, node.then, ctx)
    no = _check(state, node.other, ctx)
    if test is None or yes is None or no is None:
        return replace(node, type=ANY)
    _expect_yesno(state, test)
    produced = _unify(yes.type, no.type)
    if produced is None:
        _problem(state, "FB102", node.span, _mismatch("use", yes.type, no.type, _subject(yes)))
        produced = yes.type
    return replace(node, test=test, then=yes, other=no, type=produced)


def _unify(left: FType, right: FType) -> Optional[FType]:
    if _blank_pair(left, right):
        if unwrap(left).kind == FKind.BLANK:
            return right
        if unwrap(right).kind == FKind.BLANK:
            return left
        if is_numeric(left) and is_numeric(right):
            return widen_numeric((left, right))
        if unwrap(left).kind == unwrap(right).kind:
            return unwrap(left)
        if unwrap(left).kind == FKind.ANY:
            return right
        if unwrap(right).kind == FKind.ANY:
            return left
    return None


def _blank_pair(left: FType, right: FType) -> bool:
    a = unwrap(left)
    b = unwrap(right)
    if a.kind in (FKind.BLANK, FKind.ANY) or b.kind in (FKind.BLANK, FKind.ANY):
        return True
    if a.kind == b.kind:
        return True
    return is_numeric(a) and is_numeric(b)


def _check_list(state: _State, node: ListLit, ctx: _Ctx, expected: Optional[FType]) -> Optional[Node]:
    items = []
    for item in node.items:
        checked = _check(state, item, ctx)
        if checked is None:
            return None
        items.append(checked)
    if not items:
        return replace(node, items=(), type=expected or ANY)
    if all(is_numeric(item.type) for item in items):
        produced = widen_numeric(tuple(item.type for item in items))
    else:
        produced = items[0].type
        for item in items[1:]:
            if not same_or_numeric(produced, item.type):
                _problem(state, "FB102", item.span, _mismatch("compare", produced, item.type, _subject(item)))
    return replace(node, items=tuple(items), type=produced)


def _list_matches(state: _State, left: Node, items: ListLit) -> None:
    for item in items.items:
        if not same_or_numeric(left.type, item.type):
            _problem(state, "FB102", item.span, _mismatch("compare", left.type, item.type, _subject(left)))


def _expect_yesno(state: _State, node: Node) -> None:
    kind = unwrap(node.type).kind
    if kind in (FKind.YESNO, FKind.BLANK, FKind.ANY):
        if kind == FKind.ANY and not _blocked_any(state, node):
            _wrap_bool(state, node)
        return
    hint = _bool_hint(node)
    message = _mismatch("use not with", node.type, YESNO, _subject(node)) + hint
    _problem(state, "FB102", node.span, message)


def _bool_hint(node: Node) -> str:
    kind = unwrap(node.type).kind
    name = _subject(node)
    if kind == FKind.TEXT:
        return " Use not is_blank(%s)." % name
    if kind in (FKind.WHOLE, FKind.NUMBER, FKind.MONEY):
        return " Use %s != 0." % name
    return ""


def _apply_slot(state: _State, node: Node, slot: SlotKind) -> None:
    kind = unwrap(node.type).kind
    if slot.name in YESNO_SLOTS:
        if kind == FKind.ANY:
            if not _blocked_any(state, node):
                _wrap_bool(state, node)
            return
        if kind in (FKind.YESNO, FKind.BLANK):
            return
        hint = _bool_hint(node)
        message = _mismatch("use", node.type, YESNO, _subject(node)) + hint
        _problem(state, "FB102", node.span, message)
        return
    target = TEXT if slot.name == "message" else slot.target
    if slot.name == "message":
        target = TEXT
    if target is None or slot.name not in VALUE_SLOTS and slot.name != "message":
        return
    if target is None:
        return
    if assignable(node.type, target):
        return
    message = _mismatch("use", node.type, target, _subject(node))
    fix_id = None
    if unwrap(target).kind == FKind.TEXT:
        fix_id = "wrap_text"
        _offer(state, fix_id, node, message, "text(%s)" % _source(state, node))
    elif is_numeric(target) and unwrap(node.type).kind == FKind.TEXT:
        fix_id = "wrap_number"
        _offer(state, fix_id, node, message, "number(%s)" % _source(state, node))
    _problem(state, "FB102", node.span, message, fix_id)


def _blocked_any(state: _State, node: Node) -> bool:
    """An error or an Excel fix already explains this value, so it is not an untyped window result."""
    codes = ("FB101", "FB102", "FB103", "FB105", "FB109", "FB112", "FB114", "FB115")
    for item in state.problems:
        if item.code not in codes:
            continue
        if node.span.start <= item.span.start and item.span.end <= node.span.end:
            return True
    return any(
        fix.fix_id in _EXCEL_IDS and fix.span.start <= node.span.start and node.span.end <= fix.span.end
        for fix in state.covered
    )


def _wrap_bool(state: _State, node: Node) -> None:
    if node.span in state.wraps:
        return
    state.wraps.append(node.span)
    if isinstance(node, WindowCall):
        message = "%s has no type, so this formula treats it as yes or no." % node.method
    else:
        message = "This value has no type, so this formula treats it as yes or no."
    _problem(state, "FB110", node.span, message)


def _offer_text(state: _State, node: Node) -> None:
    message = _mismatch("add", TEXT, node.type, _subject(node))
    _offer(state, "wrap_text", node, message, "text(%s)" % _source(state, node))


def _offer(state: _State, fix_id: str, node: Node, message: str, replacement: str) -> None:
    state.fixes.append(Fix(fix_id, node.span, message, replacement))


def _unknown(state: _State, node: Ref) -> None:
    if any(
        fix.fix_id in _EXCEL_IDS and fix.span.start <= node.span.start and node.span.end <= fix.span.end
        for fix in state.covered
    ):
        return
    suggestion = _suggest(node.name, state.env)
    if suggestion is None:
        message = "%s is not a field on this form." % node.name
        fix_id = None
    else:
        message = "%s is not a field on this form. Did you mean %s?" % (node.name, suggestion)
        fix_id = "suggest"
        state.fixes.append(Fix("suggest", node.span, message, suggestion))
    _problem(state, "FB101", node.span, message, fix_id)


def _suggest(name: str, env: FormulaEnv) -> Optional[str]:
    folded = name.casefold()
    best: Optional[Tuple[int, int, str, str]] = None
    for obj, facts in env.widgets.items():
        ranked = _rank(name, folded, obj)
        if facts.display:
            ranked = _better(ranked, _rank(name, folded, facts.display))
        if ranked is None:
            continue
        candidate = (ranked[0], ranked[1], obj, obj)
        if best is None or candidate < best:
            best = candidate
    for page in sorted(env.page_names()):
        ranked = _rank(name, folded, page)
        if ranked is None:
            continue
        candidate = (ranked[0], ranked[1], page, page)
        if best is None or candidate < best:
            best = candidate
    if best is None:
        return None
    return best[2]


def _better(
    left: Optional[Tuple[int, int]],
    right: Optional[Tuple[int, int]],
) -> Optional[Tuple[int, int]]:
    if left is None:
        return right
    if right is None:
        return left
    return left if left <= right else right


def _rank(name: str, folded: str, other: str) -> Optional[Tuple[int, int]]:
    if other.casefold() == folded:
        return (0, _distance(name, other))
    distance = _distance(name, other)
    if distance <= 2:
        return (1, distance)
    return None


def _distance(left: str, right: str) -> int:
    if abs(len(left) - len(right)) > 2:
        return 3
    prev = list(range(len(right) + 1))
    for i, char in enumerate(left, 1):
        curr = [i]
        for j, other in enumerate(right, 1):
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + (char != other)))
        prev = curr
    return prev[-1]


def _data_required(state: _State, span: Span) -> None:
    if state.env.data is None:
        _problem(state, "FB115", span, _FB115)


def _spec_of(env: FormulaEnv, facts: WidgetFacts):
    return lookup_spec(facts.class_name, env.class_chain(facts.class_name))


def _is_grid(state: _State, node: Node) -> bool:
    if not isinstance(node, Ref):
        return False
    facts = state.env.widgets.get(node.name)
    if facts is None:
        return False
    matched, _spec = _spec_of(state.env, facts)
    return matched == "QTableView"


def _subject(node: Node) -> str:
    if isinstance(node, Ref):
        return node.name
    if isinstance(node, Attr) and isinstance(node.base, Ref):
        return node.base.name
    if isinstance(node, Unary):
        return _subject(node.x)
    if isinstance(node, Bin):
        return _subject(node.a)
    if isinstance(node, Call):
        return node.func
    if isinstance(node, WindowCall):
        return node.method
    return "this"


def _source(state: _State, node: Node) -> str:
    return state.text[node.span.start : node.span.end]


def _mismatch(verb: str, left: FType, right: FType, name: str) -> str:
    return "Can't %s %s and %s. %s holds %s." % (
        verb,
        type_phrase(unwrap(left)),
        type_phrase(unwrap(right)),
        name,
        type_phrase(unwrap(left)),
    )


def _problem(
    state: _State,
    code: str,
    span: Span,
    message: str,
    fix_id: Optional[str] = None,
) -> None:
    state.problems.append(FormulaProblem(code, span, message, fix_id))
