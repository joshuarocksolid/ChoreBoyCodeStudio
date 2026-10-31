"""Compile a typed formula tree to one Python expression."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Set

from app.features.form_builder.engine.diagnostic_codes import fb1xx_formula as _formula_codes
from app.features.form_builder.engine.diagnostics import CODES, Severity

# Importing the code module registers FB1xx severities. Keep the name live.
_ = _formula_codes
from app.features.form_builder.engine.logic.formula.library import FUNCTIONS
from app.features.form_builder.engine.logic.formula.runtime import HELPERS

_NEVER_BLANK_FUNCS = {
    "is_blank",
    "contains",
    "starts_with",
    "ends_with",
    "matches",
    "is_email",
    "is_phone",
    "is_zip",
    "sum",
    "count",
    "today",
    "now",
}

_CMP_HELPER = {
    "<": "_cbcs_lt",
    "<=": "_cbcs_le",
    ">": "_cbcs_gt",
    ">=": "_cbcs_ge",
    "==": "_cbcs_eq",
    "!=": "_cbcs_ne",
    "in": "_cbcs_in",
    "not in": "_cbcs_not_in",
}

_ARITH_HELPER = {"+": "_cbcs_add", "-": "_cbcs_sub", "*": "_cbcs_mul"}

_DATE_TYPES = {"DATE", "DATETIME"}
_ACCESSOR_KINDS = ("money", "whole", "percent", "date", "time")

# Higher binds tighter.
PREC_IF = 1
PREC_OR = 2
PREC_AND = 3
PREC_NOT = 4
PREC_CMP = 5
PREC_ADD = 6
PREC_MUL = 7
PREC_UNARY = 8
PREC_ATOM = 9

_LEFT_ASSOC = {PREC_ADD, PREC_MUL, PREC_AND, PREC_OR}
_HELPER_RE = re.compile(r"\b(_cbcs_[A-Za-z0-9_]*)\b")
_HELPER_ORDER = [helper_id for helper_id, _source in HELPERS]
_HELPER_SET = set(_HELPER_ORDER)
_IMPORT_NAMES = {
    "Decimal": ("decimal", "Decimal"),
    "ROUND_HALF_UP": ("decimal", "ROUND_HALF_UP"),
    "date": ("datetime", "date"),
    "datetime": ("datetime", "datetime"),
    "time": ("datetime", "time"),
}


@dataclass(frozen=True)
class Emitted:
    source: str
    helpers: tuple
    imports: tuple


@dataclass(frozen=True)
class _Piece:
    source: str
    prec: int
    blank: bool


def compile_formula(analysis: Any, env: Any, *, self_name: str = "self") -> Emitted:
    if getattr(analysis, "tree", None) is None:
        raise ValueError("formula has no tree")
    for problem in getattr(analysis, "problems", ()) or ():
        spec = CODES.get(getattr(problem, "code", ""))
        if spec is None or spec.severity == Severity.ERROR:
            raise ValueError("formula has an error")
    wraps = set(getattr(analysis, "bool_wraps", ()) or ())
    piece = _emit(analysis.tree, env, self_name, wraps)
    direct = _helpers_in(piece.source)
    # A pasted helper can call another helper. The generator emits this tuple
    # and nothing else, so the callees have to be in it.
    helpers = tuple(_closure(direct))
    imports = _imports_for(piece.source, helpers)
    return Emitted(piece.source, helpers, imports)


def _emit(node: Any, env: Any, self_name: str, wraps: Set[Any]) -> _Piece:
    kind = _node_kind(node)
    if kind == "lit":
        piece = _emit_lit(node)
    elif kind == "ref":
        piece = _emit_ref(node, env, self_name)
    elif kind == "attr":
        piece = _emit_attr(node, self_name)
    elif kind == "call":
        piece = _emit_call(node, env, self_name, wraps)
    elif kind == "window":
        piece = _emit_window(node, env, self_name, wraps)
    elif kind == "unary":
        piece = _emit_unary(node, env, self_name, wraps)
    elif kind == "bin":
        piece = _emit_bin(node, env, self_name, wraps)
    elif kind == "bool":
        piece = _emit_bool(node, env, self_name, wraps)
    elif kind == "compare":
        piece = _emit_compare(node, env, self_name, wraps)
    elif kind == "if":
        piece = _emit_if(node, env, self_name, wraps)
    elif kind == "list":
        piece = _emit_list(node, env, self_name, wraps)
    else:
        raise ValueError("unknown formula node")
    span = getattr(node, "span", None)
    if span is not None and span in wraps:
        return _Piece("_cbcs_bool(%s)" % piece.source, PREC_ATOM, False)
    return piece


def _node_kind(node: Any) -> str:
    if hasattr(node, "pairs") and hasattr(node, "first"):
        return "compare"
    if hasattr(node, "test") and hasattr(node, "then") and hasattr(node, "other"):
        return "if"
    if hasattr(node, "method") and hasattr(node, "args"):
        return "window"
    if hasattr(node, "func") and hasattr(node, "args"):
        return "call"
    if hasattr(node, "items") and hasattr(node, "span"):
        return "list"
    if hasattr(node, "values") and hasattr(node, "op"):
        return "bool"
    if hasattr(node, "op") and hasattr(node, "a") and hasattr(node, "b"):
        return "bin"
    if hasattr(node, "op") and hasattr(node, "x"):
        return "unary"
    if hasattr(node, "base") and hasattr(node, "sub"):
        return "attr"
    if hasattr(node, "name") and hasattr(node, "type") and not hasattr(node, "args"):
        return "ref"
    if hasattr(node, "value") and hasattr(node, "type"):
        return "lit"
    raise ValueError("unknown formula node")


def _type_name(node: Any) -> str:
    ftype = getattr(node, "type", None)
    kind = getattr(ftype, "kind", None)
    name = getattr(kind, "name", None)
    if isinstance(name, str) and name != "":
        return name
    return "ANY"


def _reject_hidden_name(name: str) -> None:
    if name.startswith("_"):
        raise ValueError("widget name %s starts with _" % name)


def _emit_lit(node: Any) -> _Piece:
    value = node.value
    if value is None:
        return _Piece("None", PREC_ATOM, True)
    if type(value) is bool:
        return _Piece("True" if value else "False", PREC_ATOM, False)
    if type(value) is int:
        if value < 0:
            return _Piece(str(value), PREC_UNARY, False)
        return _Piece(str(value), PREC_ATOM, False)
    if type(value).__name__ == "Decimal":
        return _Piece(_decimal_source(value), PREC_ATOM, False)
    if isinstance(value, str):
        return _Piece(repr(value), PREC_ATOM, False)
    raise ValueError("unsupported literal")


def _decimal_source(value: Any) -> str:
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and 0 <= exponent <= 6:
        body = format(value, "f")
    else:
        body = str(value)
    return 'Decimal("%s")' % body


def _emit_ref(node: Any, env: Any, self_name: str) -> _Piece:
    name = node.name
    _reject_hidden_name(name)
    facts = env.widgets.get(name)
    if facts is None:
        pages = env.page_names() if hasattr(env, "page_names") else ()
        if name in pages and _type_name(node) == "PAGE":
            return _Piece("%s.%s" % (self_name, name), PREC_ATOM, False)
        raise ValueError("unknown widget %s" % name)
    # A page name is the widget object. A tab or stack still reads currentWidget().
    if _type_name(node) == "PAGE" and _class_key(facts) not in ("QTabWidget", "QStackedWidget"):
        return _Piece("%s.%s" % (self_name, name), PREC_ATOM, False)
    return _emit_widget(name, facts, self_name)


def _class_key(facts: Any) -> str:
    raw = getattr(facts, "widget_class", None)
    if not raw:
        raw = getattr(facts, "class_name", None)
    if not isinstance(raw, str) or raw == "":
        raise ValueError("widget class is missing")
    if "." in raw:
        return raw.rsplit(".", 1)[-1]
    return raw


def _kind_key(kind: Any) -> str:
    if not isinstance(kind, str) or kind == "" or kind == "text":
        return "text"
    if kind in _ACCESSOR_KINDS:
        return kind
    if kind.startswith("number:"):
        tail = kind.split(":", 1)[1]
        if tail.isdigit():
            return "number"
    return "text"


def _number_places(facts: Any) -> int:
    kind = getattr(facts, "kind", None)
    if isinstance(kind, str) and kind.startswith("number:"):
        tail = kind.split(":", 1)[1]
        if tail.isdigit():
            return int(tail)
    decimals = getattr(facts, "decimals", 2)
    if decimals is None:
        return 2
    return int(decimals)


def _emit_widget(name: str, facts: Any, self_name: str) -> _Piece:
    cls = _class_key(facts)
    target = "%s.%s" % (self_name, name)
    allow_blank = bool(getattr(facts, "allow_blank", False))
    kind = _kind_key(getattr(facts, "kind", None))
    if cls in ("QSlider", "QDial", "QProgressBar"):
        return _Piece("%s.value()" % target, PREC_ATOM, False)
    if cls == "QSpinBox":
        if allow_blank:
            return _Piece("_cbcs_read_spin(%s)" % target, PREC_ATOM, True)
        return _Piece("%s.value()" % target, PREC_ATOM, False)
    if cls == "QDoubleSpinBox":
        decimals = getattr(facts, "decimals", 2)
        if decimals is None:
            decimals = 2
        places = int(decimals)
        if allow_blank:
            return _Piece("_cbcs_read_double(%s, %s)" % (target, places), PREC_ATOM, True)
        return _Piece("_cbcs_dec(%s.value(), %s)" % (target, places), PREC_ATOM, False)
    if cls == "QLineEdit":
        return _emit_textish(target, "line", kind, facts, True)
    if cls == "QLabel":
        return _emit_textish(target, "label", kind, facts, True)
    if cls == "QPlainTextEdit":
        return _emit_textish(target, "plain", kind, facts, True)
    if cls == "QTextEdit":
        # The value table types every text edit as text. kind does not apply.
        return _emit_textish(target, "plain", "text", facts, True)
    if cls == "QCheckBox":
        if bool(getattr(facts, "tristate", False)):
            return _Piece("_cbcs_read_check(%s)" % target, PREC_ATOM, True)
        return _Piece("%s.isChecked()" % target, PREC_ATOM, False)
    if cls == "QRadioButton":
        return _Piece("%s.isChecked()" % target, PREC_ATOM, False)
    if cls == "QButtonGroup":
        return _Piece("_cbcs_read_radio(%s)" % target, PREC_ATOM, True)
    if cls == "QComboBox":
        if bool(getattr(facts, "has_items_data", False)):
            return _Piece("%s.currentData()" % target, PREC_ATOM, True)
        return _Piece("%s.currentText()" % target, PREC_ATOM, True)
    if cls == "QDateEdit":
        return _Piece("_cbcs_read_dateedit(%s)" % target, PREC_ATOM, allow_blank)
    if cls == "QTimeEdit":
        return _Piece("_cbcs_read_timeedit(%s)" % target, PREC_ATOM, allow_blank)
    if cls == "QDateTimeEdit":
        return _Piece("_cbcs_read_datetime(%s)" % target, PREC_ATOM, allow_blank)
    if cls == "QListWidget":
        return _Piece("_cbcs_read_list(%s)" % target, PREC_ATOM, True)
    if cls in ("QTabWidget", "QStackedWidget"):
        return _Piece("%s.currentWidget()" % target, PREC_ATOM, False)
    raise ValueError("no formula read for %s" % cls)


def _emit_textish(target: str, style: str, kind: str, facts: Any, blank: bool) -> _Piece:
    if kind == "text":
        if style == "label":
            return _Piece("%s.text()" % target, PREC_ATOM, blank)
        if style == "plain":
            return _Piece("_cbcs_read_plain(%s)" % target, PREC_ATOM, blank)
        return _Piece("_cbcs_read_line(%s)" % target, PREC_ATOM, blank)
    places = _number_places(facts)
    prefix = {
        "line": "",
        "label": "label_",
        "plain": "plain_",
    }[style]
    if kind == "number":
        return _Piece(
            "_cbcs_read_%snumber(%s, %s)" % (prefix, target, places),
            PREC_ATOM,
            blank,
        )
    return _Piece("_cbcs_read_%s%s(%s)" % (prefix, kind, target), PREC_ATOM, blank)


def _emit_attr(node: Any, self_name: str) -> _Piece:
    if getattr(node, "sub", None) is not None:
        raise ValueError("attribute subscript is not a formula read")
    base = node.base
    if isinstance(base, str):
        widget = base
    elif hasattr(base, "name"):
        widget = base.name
    else:
        raise ValueError("attribute base is not a widget")
    _reject_hidden_name(widget)
    target = "%s.%s" % (self_name, widget)
    name = node.name
    table = {
        "text": ("_cbcs_read_shown", True),
        "enabled": ("_cbcs_read_enabled", False),
        "visible": ("_cbcs_read_visible", False),
        "checked": ("_cbcs_read_checked", False),
        "count": ("_cbcs_read_count", False),
    }
    if name not in table:
        raise ValueError("unknown attribute %s" % name)
    helper, blank = table[name]
    return _Piece("%s(%s)" % (helper, target), PREC_ATOM, blank)


def _emit_call(node: Any, env: Any, self_name: str, wraps: Set[Any]) -> _Piece:
    spec = FUNCTIONS.get(node.func)
    if spec is None:
        raise ValueError("unknown function %s" % node.func)
    helper = spec.helper_id
    args = [_emit(arg, env, self_name, wraps) for arg in node.args]
    src = "%s(%s)" % (helper, ", ".join(arg.source for arg in args))
    blank = node.func not in _NEVER_BLANK_FUNCS
    return _Piece(src, PREC_ATOM, blank)


def _emit_window(node: Any, env: Any, self_name: str, wraps: Set[Any]) -> _Piece:
    args = [_emit(arg, env, self_name, wraps) for arg in node.args]
    src = "%s._form.%s(%s)" % (self_name, node.method, ", ".join(arg.source for arg in args))
    blank = _type_name(node) not in ("YESNO", "PAGE")
    return _Piece(src, PREC_ATOM, blank)


def _emit_unary(node: Any, env: Any, self_name: str, wraps: Set[Any]) -> _Piece:
    inner = _emit(node.x, env, self_name, wraps)
    op = node.op
    if op == "not":
        if inner.blank:
            return _Piece("_cbcs_not(%s)" % inner.source, PREC_ATOM, False)
        return _Piece("not %s" % _paren(inner, PREC_NOT, "unary"), PREC_NOT, False)
    if op == "-":
        if inner.blank:
            return _Piece("_cbcs_neg(%s)" % inner.source, PREC_ATOM, True)
        return _Piece("-%s" % _paren(inner, PREC_UNARY, "unary"), PREC_UNARY, False)
    if op == "+":
        # No positive helper: blankable +x is add-zero so None stays None.
        if inner.blank:
            return _Piece("_cbcs_add(%s, 0)" % inner.source, PREC_ATOM, True)
        return _Piece("+%s" % _paren(inner, PREC_UNARY, "unary"), PREC_UNARY, False)
    raise ValueError("unknown unary %s" % op)


def _emit_bin(node: Any, env: Any, self_name: str, wraps: Set[Any]) -> _Piece:
    left = _emit(node.a, env, self_name, wraps)
    right = _emit(node.b, env, self_name, wraps)
    op = node.op
    left_type = _type_name(node.a)
    right_type = _type_name(node.b)
    if op == "/":
        return _Piece("_cbcs_div(%s, %s)" % (left.source, right.source), PREC_ATOM, True)
    if op == "+" and _date_plus_whole(left_type, right_type):
        if left_type in _DATE_TYPES:
            date_piece, whole_piece = left, right
        else:
            date_piece, whole_piece = right, left
        src = "_cbcs_add_days(%s, %s)" % (date_piece.source, whole_piece.source)
        return _Piece(src, PREC_ATOM, date_piece.blank or whole_piece.blank)
    if op == "-" and left_type in _DATE_TYPES and right_type == "WHOLE":
        if right.blank:
            whole_src = "_cbcs_neg(%s)" % right.source
        else:
            whole_src = "-" + _paren(right, PREC_UNARY, "unary")
        src = "_cbcs_add_days(%s, %s)" % (left.source, whole_src)
        return _Piece(src, PREC_ATOM, left.blank or right.blank)
    if op == "-" and left_type in _DATE_TYPES and right_type in _DATE_TYPES:
        src = "_cbcs_date_diff(%s, %s)" % (left.source, right.source)
        return _Piece(src, PREC_ATOM, left.blank or right.blank)
    if op == "+" and (left_type == "TEXT" or right_type == "TEXT"):
        if left.blank or right.blank:
            # Concat always returns str, so a later plain + must not treat it as None.
            return _Piece(
                "_cbcs_concat(%s, %s)" % (left.source, right.source),
                PREC_ATOM,
                False,
            )
        return _join_plain("+", left, right, PREC_ADD, False)
    if op in _ARITH_HELPER:
        if left.blank or right.blank:
            src = "%s(%s, %s)" % (_ARITH_HELPER[op], left.source, right.source)
            return _Piece(src, PREC_ATOM, True)
        prec = PREC_MUL if op == "*" else PREC_ADD
        return _join_plain(op, left, right, prec, False)
    raise ValueError("unknown operator %s" % op)


def _date_plus_whole(left_type: str, right_type: str) -> bool:
    return (left_type in _DATE_TYPES and right_type == "WHOLE") or (
        right_type in _DATE_TYPES and left_type == "WHOLE"
    )


def _emit_bool(node: Any, env: Any, self_name: str, wraps: Set[Any]) -> _Piece:
    values = list(node.values)
    if len(values) < 2:
        raise ValueError("boolean formula needs two values")
    parts = [_emit(value, env, self_name, wraps) for value in values]
    if any(part.blank for part in parts):
        helper = "_cbcs_and" if node.op == "and" else "_cbcs_or"
        src = parts[0].source
        for part in parts[1:]:
            src = "%s(%s, %s)" % (helper, src, part.source)
        return _Piece(src, PREC_ATOM, False)
    prec = PREC_AND if node.op == "and" else PREC_OR
    src = _paren(parts[0], prec, "left")
    for part in parts[1:]:
        src = "%s %s %s" % (src, node.op, _paren(part, prec, "right"))
    return _Piece(src, prec, False)


def _emit_compare(node: Any, env: Any, self_name: str, wraps: Set[Any]) -> _Piece:
    pairs = list(node.pairs)
    if not pairs:
        raise ValueError("comparison needs an operator")
    operands = [node.first] + [pair[1] for pair in pairs]
    ops = [pair[0] for pair in pairs]
    if len(ops) == 1 and ops[0] in ("==", "!="):
        rewritten = _blank_compare(operands[0], operands[1], ops[0], env, self_name, wraps)
        if rewritten is not None:
            return rewritten
    parts = [_emit(operand, env, self_name, wraps) for operand in operands]
    needs_helper = False
    for operand, part in zip(operands, parts):
        if part.blank or _is_null_lit(operand):
            needs_helper = True
            break
    if not needs_helper:
        text = _paren(parts[0], PREC_CMP, "unary")
        for op, part in zip(ops, parts[1:]):
            text = "%s %s %s" % (text, op, _paren(part, PREC_CMP, "unary"))
        return _Piece(text, PREC_CMP, False)
    pieces = []  # type: List[str]
    for index, op in enumerate(ops):
        helper = _CMP_HELPER[op]
        pieces.append("%s(%s, %s)" % (helper, parts[index].source, parts[index + 1].source))
    src = pieces[0]
    for piece in pieces[1:]:
        src = "_cbcs_and(%s, %s)" % (src, piece)
    return _Piece(src, PREC_ATOM, False)


def _blank_compare(
    left: Any,
    right: Any,
    op: str,
    env: Any,
    self_name: str,
    wraps: Set[Any],
) -> Optional[_Piece]:
    negate = op == "!="
    if _is_null_lit(right):
        other = _emit(left, env, self_name, wraps)
        return _Piece(_is_blank_call(other.source, negate), PREC_ATOM, False)
    if _is_null_lit(left):
        other = _emit(right, env, self_name, wraps)
        return _Piece(_is_blank_call(other.source, negate), PREC_ATOM, False)
    return None


def _is_blank_call(source: str, negate: bool) -> str:
    call = "_cbcs_is_blank(%s)" % source
    if negate:
        return "_cbcs_not(%s)" % call
    return call


def _is_null_lit(node: Any) -> bool:
    if _node_kind(node) != "lit":
        return False
    return node.value is None or node.value == ""


def _emit_if(node: Any, env: Any, self_name: str, wraps: Set[Any]) -> _Piece:
    test = _emit(node.test, env, self_name, wraps)
    then = _emit(node.then, env, self_name, wraps)
    other = _emit(node.other, env, self_name, wraps)
    src = "(%s if %s else %s)" % (then.source, test.source, other.source)
    return _Piece(src, PREC_ATOM, then.blank or other.blank)


def _emit_list(node: Any, env: Any, self_name: str, wraps: Set[Any]) -> _Piece:
    parts = [_emit(item, env, self_name, wraps) for item in node.items]
    src = "[%s]" % ", ".join(part.source for part in parts)
    return _Piece(src, PREC_ATOM, False)


def _paren(piece: _Piece, parent_prec: int, side: str) -> str:
    if piece.prec > parent_prec:
        return piece.source
    if piece.prec == parent_prec:
        if side == "right" and parent_prec in _LEFT_ASSOC:
            return "(%s)" % piece.source
        if side == "unary":
            return "(%s)" % piece.source
        return piece.source
    return "(%s)" % piece.source


def _join_plain(op: str, left: _Piece, right: _Piece, prec: int, blank: bool) -> _Piece:
    src = "%s %s %s" % (_paren(left, prec, "left"), op, _paren(right, prec, "right"))
    return _Piece(src, prec, blank)


def _helpers_in(source: str) -> tuple:
    found = set(_HELPER_RE.findall(source))
    unknown = found - _HELPER_SET
    if unknown:
        raise ValueError("unknown helper %s" % ", ".join(sorted(unknown)))
    return tuple(helper_id for helper_id in _HELPER_ORDER if helper_id in found)


def _closure(helper_ids: Sequence[str]) -> List[str]:
    sources = {helper_id: source for helper_id, source in HELPERS}
    needed = set(helper_ids)  # type: Set[str]
    changed = True
    while changed:
        changed = False
        for helper_id in list(needed):
            for found in _HELPER_RE.findall(sources[helper_id]):
                if found in sources and found not in needed:
                    needed.add(found)
                    changed = True
    return [helper_id for helper_id in _HELPER_ORDER if helper_id in needed]


def _imports_for(source: str, helper_ids: Sequence[str]) -> tuple:
    names = set()  # type: Set[str]
    names.update(_load_names(source, mode="exec"))
    sources = {helper_id: text for helper_id, text in HELPERS}
    for helper_id in _closure(helper_ids):
        names.update(_load_names(sources[helper_id], mode="exec"))
    found = []
    for name in names:
        pair = _IMPORT_NAMES.get(name)
        if pair is not None:
            found.append(pair)
    return tuple(sorted(set(found)))


def _load_names(source: str, mode: str) -> Set[str]:
    try:
        tree = ast.parse(source, mode=mode)
    except SyntaxError:
        return set()
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
