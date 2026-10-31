"""Value-table writes shared by refresh and defaults (CONTRACTS §18.2 and §18.3).

The rules expander is the only ``EXPANDER`` at order 200. This module builds
the lines both methods share: the source comment, the write, a blank result,
and the divide-by-zero tooltip.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from app.features.form_builder.engine.codegen.logic_hooks import one_line
from app.features.form_builder.engine.diagnostics import CODES, Severity
from app.features.form_builder.engine.logic.formula import analyze, compile_formula
from app.features.form_builder.engine.logic.formula.env import FormulaEnv, SlotKind, WidgetFacts
from app.features.form_builder.engine.logic.formula.nodes import (
    Analysis,
    Attr,
    Bin,
    Bool,
    Call,
    Compare,
    IfElse,
    ListLit,
    Unary,
    WindowCall,
)
from app.features.form_builder.engine.logic.formula.types import (
    FKind,
    MONEY,
    NUMBER,
    TEXT,
    lookup_spec,
    main_type,
    unwrap,
)
from app.features.form_builder.engine.logic.rules import RuleRecord

_WORDS = {
    "cbcsEnabledWhen": "Enabled when",
    "cbcsVisibleWhen": "Visible when",
    "cbcsReadOnlyWhen": "Read-only when",
    "cbcsValue": "Value",
    "cbcsDefault": "Default",
}
_SETTERS = {
    "cbcsEnabledWhen": "setEnabled",
    "cbcsVisibleWhen": "setVisible",
    "cbcsReadOnlyWhen": "setReadOnly",
}
_STATE = frozenset(_SETTERS)
_VALUE_KEYS = frozenset({"cbcsValue", "cbcsDefault"})
_DIV_ZERO = "Can't divide by zero"


@dataclass(frozen=True)
class Prepared:
    """One rule's lines, helper ids, and the widgets whose change signal should refresh."""

    lines: Tuple[str, ...]
    helpers: Tuple[str, ...]
    imports: Tuple[Tuple[str, str], ...]
    reads: Tuple[str, ...]
    live: bool


def prepare(record: RuleRecord, env: FormulaEnv, trace: bool) -> Prepared:
    """Compile one rule, or the skip comment when the formula has an error."""
    words = _WORDS.get(record.key, record.key)
    facts = env.widgets.get(record.widget)
    if facts is None:
        return _skip(record, words, "FB101")
    chain = env.class_chain(facts.class_name)
    analysis = analyze(record.text, env, _slot(record, facts, chain))
    code = _error_code(analysis)
    if code is not None:
        return _skip(record, words, code)
    try:
        emitted = compile_formula(analysis, env)
    except ValueError:
        return _skip(record, words, "FB108")
    lines, extra_helpers, extra_imports = _body(record, words, facts, chain, analysis, emitted.source, env, trace)
    helpers = tuple(dict.fromkeys(tuple(emitted.helpers) + extra_helpers))
    imports = tuple(dict.fromkeys(tuple(emitted.imports) + extra_imports))
    return Prepared(tuple(lines), helpers, imports, tuple(sorted(analysis.reads)), True)


def _slot(record: RuleRecord, facts: WidgetFacts, chain: Tuple[str, ...]) -> SlotKind:
    if record.key in _STATE:
        return SlotKind.condition()
    target = _target(facts, chain)
    fmt = record.fmt or ""
    if fmt == "money":
        target = MONEY
    elif fmt.startswith("number") or fmt.startswith("percent"):
        target = NUMBER
    if record.key == "cbcsDefault":
        return SlotKind.default(target)
    return SlotKind.value(target)


def _target(facts: WidgetFacts, chain: Tuple[str, ...]):
    matched, spec = lookup_spec(facts.class_name, chain)
    if spec is None or matched is None:
        return TEXT
    found, _unknown = main_type(
        spec,
        matched,
        kind=facts.kind,
        prefix=facts.prefix,
        decimals=facts.decimals,
        has_items_data=facts.has_items_data,
    )
    if found is None:
        return TEXT
    return found


def _error_code(analysis: Analysis) -> Optional[str]:
    for problem in analysis.problems:
        spec = CODES.get(problem.code)
        if spec is None or spec.severity == Severity.ERROR:
            return problem.code
    return None


def _skip(record: RuleRecord, words: str, code: str) -> Prepared:
    text = "%s: %s skipped (%s: see Problems)" % (record.widget, words, code)
    return Prepared(("# " + one_line(text),), (), (), (), False)


def _body(
    record: RuleRecord,
    words: str,
    facts: WidgetFacts,
    chain: Tuple[str, ...],
    analysis: Analysis,
    expr: str,
    env: FormulaEnv,
    trace: bool,
) -> Tuple[List[str], Tuple[str, ...], Tuple[Tuple[str, str], ...]]:
    lines = ["# " + one_line(_describe(record, words))]
    helpers: List[str] = []
    imports: List[Tuple[str, str]] = []
    widget = record.widget
    if record.key in _STATE:
        lines.append("self.%s.%s(%s)" % (widget, _SETTERS[record.key], _condition(expr, analysis)))
        if trace:
            lines.append(_trace(record, expr))
        return lines, (), ()
    denoms = _denominators(analysis, env)
    write, write_helpers, write_imports = _write(widget, facts, chain, record.fmt, expr)
    lines.extend(write)
    helpers.extend(write_helpers)
    imports.extend(write_imports)
    if denoms:
        lines.extend(_div_zero(widget, denoms))
        helpers.append("_cbcs_is_blank")
        imports.append(("decimal", "Decimal"))
    if trace:
        shown = "_cbcs_value" if any("_cbcs_value" in line for line in write) else expr
        lines.append(_trace(record, shown))
    return lines, tuple(helpers), tuple(imports)


def _describe(record: RuleRecord, words: str) -> str:
    if record.key in _VALUE_KEYS:
        text = "%s: %s =  %s" % (record.widget, words, record.text)
        if record.fmt:
            text += "   (format: %s)" % record.fmt
        return text
    return "%s: %s  %s" % (record.widget, words, record.text)


def _condition(expr: str, analysis: Analysis) -> str:
    kind = unwrap(analysis.type).kind if analysis.type is not None else None
    if kind == FKind.YESNO:
        return expr
    return "bool(%s)" % expr


def _trace(record: RuleRecord, expr: str) -> str:
    ref = one_line("%s:%s" % (record.widget, record.key))
    return "self._cbcs_trace(%s, %s, %s)" % (repr("rule"), repr(ref), expr)


def _write(
    widget: str,
    facts: WidgetFacts,
    chain: Tuple[str, ...],
    fmt: str,
    expr: str,
) -> Tuple[List[str], Tuple[str, ...], Tuple[Tuple[str, str], ...]]:
    _matched, spec = lookup_spec(facts.class_name, chain)
    kind = spec.write if spec is not None else ""
    assign = "_cbcs_value = %s" % expr
    if fmt == "money" and kind == "setText(formatted)":
        return (
            [assign, "self.%s.setText(_cbcs_money(_cbcs_value))" % widget],
            ("_cbcs_money",),
            (("decimal", "Decimal"), ("decimal", "ROUND_HALF_UP")),
        )
    if fmt and kind == "setText(formatted)":
        return (
            [assign, "self.%s.setText(_cbcs_text(_cbcs_value, %s) or \"\")" % (widget, repr(fmt))],
            ("_cbcs_text",),
            (("decimal", "Decimal"), ("decimal", "ROUND_HALF_UP")),
        )
    if kind == "setText(formatted)":
        return [assign, 'self.%s.setText("" if _cbcs_value is None else _cbcs_value)' % widget], (), ()
    if kind == "setPlainText":
        return [assign, 'self.%s.setPlainText("" if _cbcs_value is None else _cbcs_value)' % widget], (), ()
    if kind == "setValue":
        return _numeric(widget, "setValue", "int", expr, "minimum"), (), ()
    if kind == "setValue(float(x))":
        return _numeric(widget, "setValue", "float", expr, "minimum"), (), ()
    if kind == "setChecked":
        return [assign, "self.%s.setChecked(bool(_cbcs_value))" % widget], (), ()
    if kind == "setDate":
        return _numeric(widget, "setDate", "", expr, "minimumDate"), (), ()
    if kind == "setTime":
        return _numeric(widget, "setTime", "", expr, "minimumTime"), (), ()
    if kind == "setDateTime":
        return _numeric(widget, "setDateTime", "", expr, "minimumDateTime"), (), ()
    if kind == "select by data, or by text":
        return _combo(widget, expr, facts.has_items_data), (), ()
    if kind == "check the matching button":
        return _radios(widget, expr), (), ()
    if kind == "select the matching item":
        return _list(widget, expr), (), (("PySide6.QtCore", "Qt"),)
    if kind == "setCurrentWidget":
        return [assign, "self.%s.setCurrentWidget(_cbcs_value)" % widget], (), ()
    return [assign, "self.%s.setText('' if _cbcs_value is None else str(_cbcs_value))" % widget], (), ()


def _numeric(widget: str, setter: str, cast: str, expr: str, minimum: str) -> List[str]:
    value = "%s(_cbcs_value)" % cast if cast else "_cbcs_value"
    return [
        "_cbcs_value = %s" % expr,
        "if _cbcs_value is None:",
        "    self.%s.%s(self.%s.%s())" % (widget, setter, widget, minimum),
        "else:",
        "    self.%s.%s(%s)" % (widget, setter, value),
    ]


def _combo(widget: str, expr: str, by_data: bool) -> List[str]:
    lines = [
        "_cbcs_value = %s" % expr,
        "if _cbcs_value is None:",
        "    self.%s.setCurrentIndex(-1)" % widget,
        "else:",
    ]
    if by_data:
        lines.extend(
            [
                "    _cbcs_index = self.%s.findData(_cbcs_value)" % widget,
                "    self.%s.setCurrentIndex(_cbcs_index)" % widget,
            ]
        )
    else:
        lines.append("    self.%s.setCurrentText(str(_cbcs_value))" % widget)
    return lines


def _radios(widget: str, expr: str) -> List[str]:
    return [
        "_cbcs_value = %s" % expr,
        "for _cbcs_button in self.%s.buttons():" % widget,
        "    _cbcs_button.setChecked(_cbcs_button.objectName() == _cbcs_value)",
    ]


def _list(widget: str, expr: str) -> List[str]:
    return [
        "_cbcs_value = %s" % expr,
        "if _cbcs_value is None:",
        "    self.%s.setCurrentRow(-1)" % widget,
        "else:",
        "    _cbcs_matches = self.%s.findItems(str(_cbcs_value), Qt.MatchFlag.MatchExactly)" % widget,
        "    if _cbcs_matches:",
        "        self.%s.setCurrentItem(_cbcs_matches[0])" % widget,
        "    else:",
        "        self.%s.setCurrentRow(-1)" % widget,
    ]


def _div_zero(widget: str, denoms: Sequence[str]) -> List[str]:
    lines = ["_cbcs_div_zero = False"]
    for denom in denoms:
        lines.append("if not _cbcs_is_blank(%s) and Decimal(%s) == 0:" % (denom, denom))
        lines.append("    _cbcs_div_zero = True")
    lines.append("if _cbcs_div_zero:")
    lines.append('    self.%s.setToolTip("%s")' % (widget, _DIV_ZERO))
    lines.append('elif self.%s.toolTip() == "%s":' % (widget, _DIV_ZERO))
    lines.append('    self.%s.setToolTip("")' % widget)
    return lines


def _denominators(analysis: Analysis, env: FormulaEnv) -> Tuple[str, ...]:
    found: List[str] = []

    def walk(node: object) -> None:
        if isinstance(node, Bin) and node.op == "/":
            source = _compile_node(node.b, analysis, env)
            if source:
                found.append(source)
        for child in _children(node):
            walk(child)

    if analysis.tree is not None:
        walk(analysis.tree)
    return tuple(found)


def _compile_node(node: object, analysis: Analysis, env: FormulaEnv) -> str:
    sub = Analysis(
        text=analysis.text,
        tree=node,  # type: ignore[arg-type]
        type=getattr(node, "type", None),
        problems=(),
        fixes=(),
        reads=frozenset(),
        window_calls=(),
        bool_wraps=analysis.bool_wraps,
    )
    try:
        return compile_formula(sub, env).source
    except ValueError:
        return ""


def _children(node: object) -> Tuple[object, ...]:
    if isinstance(node, Bin):
        return (node.a, node.b)
    if isinstance(node, Unary):
        return (node.x,)
    if isinstance(node, Call):
        return tuple(node.args)
    if isinstance(node, WindowCall):
        return tuple(node.args)
    if isinstance(node, Bool):
        return tuple(node.values)
    if isinstance(node, Compare):
        return (node.first,) + tuple(right for _op, right in node.pairs)
    if isinstance(node, IfElse):
        return (node.test, node.then, node.other)
    if isinstance(node, ListLit):
        return tuple(node.items)
    if isinstance(node, Attr):
        return (node.base,)
    return ()
