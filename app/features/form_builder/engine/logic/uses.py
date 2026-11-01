"""Every read, set and call on a form, and the Logic panel's projection of it.

Rules, checks, steps and the window file share one table. The panel and Uses
are filters over that table. FB207 is the code already declared for a setter
that fights a rule; this module produces it and does not declare it.
"""

from __future__ import annotations

import hashlib
import keyword
import re
import weakref
from dataclasses import dataclass
from typing import List, Optional, Tuple

from app.features.form_builder.engine.diagnostic_codes import fb2xx_code as _fb2xx
from app.features.form_builder.engine.diagnostics import (
    CODES,
    DiagnosticLocation,
    FormDiagnostic,
)
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.logic.checks import (
    FormulaCheck,
    Length,
    OneOf,
    Opaque,
    Pattern,
    Preset,
    Range,
    Required,
    Unique,
    read_checks,
)
from app.features.form_builder.engine.logic.compat import split_signature
from app.features.form_builder.engine.logic.events import read_events
from app.features.form_builder.engine.logic.formula.check import analyze
from app.features.form_builder.engine.logic.formula.env import FormulaEnv, SlotKind
from app.features.form_builder.engine.logic.formula.types import ANY
from app.features.form_builder.engine.logic.refs import FORMULA_JSON_KEYS, NAME_FIELDS
from app.features.form_builder.engine.logic.storage import FORMULA_KEYS, signal_property
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import CStringValue, StringValue

del _fb2xx

# Words live here so the engine does not import the inspector.
WORDS = {
    "cbcsEnabledWhen": "Enabled when",
    "cbcsVisibleWhen": "Visible when",
    "cbcsReadOnlyWhen": "Read-only when",
    "cbcsValue": "Value",
    "cbcsDefault": "Default",
}

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# (revision, source digest, relative path) -> book, dropped when the document is.
_CACHE: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


@dataclass(frozen=True)
class Use:
    name: str
    role: str
    kind: str
    widget: str
    summary: str
    property_key: str
    index: int
    signal: str
    line: int
    path: str
    method: str


@dataclass(frozen=True)
class LogicBook:
    uses: Tuple[Use, ...]
    diagnostics: Tuple[FormDiagnostic, ...]


@dataclass(frozen=True)
class PanelQuery:
    text: str = ""
    rules: bool = True
    checks: bool = True
    events: bool = True
    problems: bool = True


@dataclass(frozen=True)
class PanelRow:
    use: Use
    section: str
    words: str
    summary: str
    problem: bool


def collect(doc: UiDocument, env: FormulaEnv, source: str, relative: str) -> LogicBook:
    """Uses and FB207 rows for this document, source text and path.

    Cached on the document's identity, its revision, the source digest and the
    relative path. A later revision replaces the previous entry.
    """
    text = source if isinstance(source, str) else ""
    path = relative if isinstance(relative, str) else ""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    key = (getattr(doc, "revision", 0), digest, path)
    cached = _CACHE.get(doc)
    if cached is not None and cached[0] == key:
        return cached[1]
    book = _build(doc, env, text, path)
    _CACHE[doc] = (key, book)
    return book


def of_name(book: LogicBook, name: str) -> Tuple[Use, ...]:
    return tuple(use for use in book.uses if use.name == name)


def panel_rows(book: LogicBook, query: PanelQuery) -> Tuple[PanelRow, ...]:
    """Anchors the chips and the filter leave visible. Empty sections are omitted by the panel."""
    text = query.text.casefold()
    rows = _anchors(book)
    if query.rules and query.checks and query.events and query.problems:
        return tuple(row for row in rows if _matches(row, text))
    only_problems = query.problems and not query.rules and not query.checks and not query.events
    shown: List[PanelRow] = []
    for row in rows:
        if not _matches(row, text):
            continue
        if only_problems:
            if row.problem:
                shown.append(row)
            continue
        if row.problem:
            # A setter that fights a rule sits in Your code, and also answers the Problems chip alone.
            if query.events:
                shown.append(row)
            continue
        if _section_on(row.section, query):
            shown.append(row)
    return tuple(shown)


def _build(doc: UiDocument, env: FormulaEnv, source: str, relative: str) -> LogicBook:
    from app.features.form_builder.engine.project.code_connections import read_connections

    uses = _rules(doc, env) + _checks(doc, env) + _steps(doc, env)
    try:
        code = read_connections(source, relative)
    except SyntaxError:
        code = ()
    uses.extend(code)
    diagnostics = _fights(doc, code)
    return LogicBook(tuple(uses), diagnostics)


def _rules(doc: UiDocument, env: FormulaEnv) -> List[Use]:
    found: List[Use] = []
    for node in _widgets(doc):
        name = node.object_name or ""
        if not name:
            continue
        for key in FORMULA_KEYS:
            text = _stored(node, key)
            if text is None or not text.strip():
                continue
            found.append(_plain(name, "set", "rule", name, text, key))
            reads, calls = _formula_names(text, env)
            for read in reads:
                found.append(_plain(read, "read", "rule", name, text, key))
            for method in calls:
                found.append(_plain(method, "call", "rule", name, text, key, method=method))
    return found


def _checks(doc: UiDocument, env: FormulaEnv) -> List[Use]:
    found: List[Use] = []
    for node in _widgets(doc):
        name = node.object_name or ""
        if not name:
            continue
        text = _stored(node, "cbcsValidate")
        if text is None or not text.strip():
            continue
        read = read_checks(text)
        for index, check in enumerate(read.checks):
            summary = _check_summary(check)
            found.append(_plain(name, "read", "check", name, summary, "cbcsValidate", index=index))
            for formula in _check_formulas(check):
                reads, _calls = _formula_names(formula, env)
                for other in reads:
                    if other == name:
                        continue
                    found.append(_plain(other, "read", "check", name, formula, "cbcsValidate", index=index))
    return found


def _steps(doc: UiDocument, env: FormulaEnv) -> List[Use]:
    found: List[Use] = []
    try:
        states = read_events(doc)
    except Exception:
        return found
    for state in states:
        key = signal_property(state.signal_name)
        for index, step in enumerate(state.steps):
            # The row the person sees is this anchor. The method name is the
            # summary so "clicked" is not a blank line. The method Use below
            # stays the call of that name.
            if step.verb == "call" and step.method:
                summary = step.method
            elif step.verb == "slot" and step.slot:
                summary = step.slot
            else:
                summary = step.verb or ""
            found.append(
                Use(
                    state.sender,
                    "call",
                    "step",
                    state.sender,
                    summary,
                    key,
                    index,
                    state.signal_name,
                    0,
                    "",
                    "",
                )
            )
            if step.verb == "call":
                if step.method:
                    found.append(
                        Use(
                            step.method,
                            "call",
                            "step",
                            state.sender,
                            "",
                            key,
                            index,
                            state.signal_name,
                            0,
                            "",
                            step.method,
                        )
                    )
                continue
            if step.verb == "slot":
                callable_name = split_signature(step.slot)[0] if step.slot else ""
                if callable_name:
                    found.append(
                        Use(
                            callable_name,
                            "call",
                            "step",
                            step.target or state.sender,
                            step.slot,
                            key,
                            index,
                            state.signal_name,
                            0,
                            "",
                            callable_name,
                        )
                    )
                continue
            found.extend(_other_step(env, state.sender, state.signal_name, key, index, step))
    return found


def _other_step(env: FormulaEnv, sender: str, signal: str, key: str, index: int, step: object) -> List[Use]:
    from app.features.form_builder.engine.logic.codec import Step

    found: List[Use] = []
    raw = getattr(step, "raw", None)
    verb = str(getattr(step, "verb", "") or "")
    if isinstance(raw, Step):
        declared = NAME_FIELDS.get(verb, ())
        scalar = {spec for spec in declared if not spec.endswith("[]")}
        listed = {spec[:-2] for spec in declared if spec.endswith("[]")}
        for field, value in raw.fields:
            names: List[str] = []
            if field in scalar and isinstance(value, str):
                names.append(value)
            elif field in listed and isinstance(value, tuple):
                names.extend(item for item in value if isinstance(item, str))
            for item in names:
                if item:
                    found.append(Use(item, "set", "step", sender, verb, key, index, signal, 0, "", ""))
        formulas: List[str] = []
        when = getattr(step, "when", None)
        if isinstance(when, str) and when.strip():
            formulas.append(when)
        formulas.extend(_json_formulas(raw.fields))
        formulas.extend(_json_formulas(raw.unknown))
        for formula in formulas:
            reads, calls = _formula_names(formula, env)
            for read in reads:
                found.append(Use(read, "read", "step", sender, formula, key, index, signal, 0, "", ""))
            for method in calls:
                found.append(Use(method, "call", "step", sender, formula, key, index, signal, 0, "", method))
    return found


def _json_formulas(pairs: Tuple[Tuple[str, object], ...]) -> List[str]:
    from app.features.form_builder.engine.logic.codec import JsonObject

    found: List[str] = []

    def walk(key: str, item: object) -> None:
        if key in FORMULA_JSON_KEYS and isinstance(item, str):
            if item.strip():
                found.append(item)
            return
        if isinstance(item, JsonObject):
            for name, value in item.pairs:
                walk(name, value)
            return
        if isinstance(item, tuple):
            for value in item:
                walk("", value)

    for key, value in pairs:
        walk(key, value)
    return found


def _fights(doc: UiDocument, uses: List[Use]) -> Tuple[FormDiagnostic, ...]:
    severity = CODES["FB207"].severity
    found: List[FormDiagnostic] = []
    seen = set()
    for use in uses:
        if use.kind != "code" or use.role != "set" or not use.property_key:
            continue
        text = _named_text(doc, use.widget, use.property_key)
        if text is None or not text.strip():
            continue
        identity = (use.widget, use.property_key, use.line)
        if identity in seen:
            continue
        seen.add(identity)
        words = WORDS.get(use.property_key, use.property_key)
        found.append(
            FormDiagnostic(
                code="FB207",
                severity=severity,
                message=(
                    "Your code calls self.ui.%s.%s(...), but an %s rule also controls it. "
                    "The rule wins on every refresh."
                )
                % (use.widget, use.summary, words),
                location=DiagnosticLocation(
                    node_id=_node_id(doc, use.widget),
                    object_name=use.widget,
                    property=use.property_key,
                    code_path=use.path,
                    code_line=use.line,
                ),
                source="logic.code",
            )
        )
    return tuple(found)


def _anchors(book: LogicBook) -> Tuple[PanelRow, ...]:
    flagged = {
        (item.location.object_name or "", item.location.property or "", item.location.code_line)
        for item in book.diagnostics
        if item.code == "FB207"
    }
    rows: List[PanelRow] = []
    code: List[PanelRow] = []
    for use in book.uses:
        if use.kind == "rule" and use.role == "set":
            rows.append(PanelRow(use, "STATE", WORDS.get(use.property_key, use.property_key), use.summary, False))
        elif use.kind == "check" and use.role == "read" and use.name == use.widget:
            rows.append(PanelRow(use, "CHECKS", _check_words(use.summary), use.summary, False))
        elif use.kind == "step" and use.role == "call" and use.name == use.widget and not use.method:
            rows.append(PanelRow(use, "EVENTS", use.signal, use.summary, False))
        elif use.kind == "code" and use.role == "call" and use.method and use.signal and use.name == use.widget:
            code.append(PanelRow(use, "IN YOUR CODE", use.signal, use.method, False))
        elif use.kind == "code" and use.role == "set" and (use.widget, use.property_key, use.line) in flagged:
            code.append(PanelRow(use, "IN YOUR CODE", use.summary, "", True))
    return tuple(rows + code)


def _check_words(summary: str) -> str:
    if summary == "required":
        return "Required"
    if summary == "preset email":
        return "Email address"
    return summary


def _check_summary(check: object) -> str:
    if isinstance(check, Required):
        return "required"
    if isinstance(check, Preset):
        return "preset %s" % check.name
    if isinstance(check, Range):
        return "range"
    if isinstance(check, Length):
        return "length"
    if isinstance(check, Pattern):
        return "pattern"
    if isinstance(check, OneOf):
        return "oneOf"
    if isinstance(check, FormulaCheck):
        return "formula"
    if isinstance(check, Unique):
        return "unique"
    if isinstance(check, Opaque):
        for key, value in check.pairs:
            if key == "check" and isinstance(value, str):
                return value
    return "check"


def _check_formulas(check: object) -> Tuple[str, ...]:
    found: List[str] = []
    if isinstance(check, FormulaCheck) and check.formula.strip():
        found.append(check.formula)
    if isinstance(check, Range):
        for bound in (check.min, check.max):
            if bound is not None and bound.formula and bound.formula.strip():
                found.append(bound.formula)
    return tuple(found)


def _section_on(section: str, query: PanelQuery) -> bool:
    if section == "STATE":
        return query.rules
    if section == "CHECKS":
        return query.checks
    if section in ("EVENTS", "IN YOUR CODE"):
        return query.events
    return False


def _matches(row: PanelRow, text: str) -> bool:
    if not text:
        return True
    hay = " ".join((row.use.widget, row.words, row.summary, row.use.method, row.use.name)).casefold()
    return text in hay


def _formula_names(text: str, env: FormulaEnv) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """Widget reads, then window calls. A bare name uses the same shortcut as the rule graph."""
    stripped = text.strip()
    if (
        stripped.isidentifier()
        and not keyword.iskeyword(stripped)
        and stripped not in env.reserved
        and not stripped.startswith("cbcs")
    ):
        if stripped in env.widgets:
            return (stripped,), ()
        return (), ()
    try:
        found = analyze(text, env, SlotKind.value(ANY))
    except Exception:
        return (), ()
    return _in_order(text, found.reads), tuple(found.window_calls)


def _in_order(text: str, reads: object) -> Tuple[str, ...]:
    wanted = set(reads)  # type: ignore[arg-type]
    if not wanted:
        return ()
    found: List[str] = []
    seen = set()
    for token in _NAME.finditer(text):
        name = token.group(0)
        if name in wanted and name not in seen:
            seen.add(name)
            found.append(name)
    for name in sorted(wanted):
        if name not in seen:
            found.append(name)
    return tuple(found)


def _plain(
    name: str,
    role: str,
    kind: str,
    widget: str,
    summary: str,
    property_key: str,
    index: int = -1,
    method: str = "",
) -> Use:
    return Use(name, role, kind, widget, summary, property_key, index, "", 0, "", method)


def _widgets(doc: UiDocument) -> Tuple[object, ...]:
    try:
        return tuple(doc.iter_widgets())
    except Exception:
        return ()


def _stored(node: object, key: str) -> Optional[str]:
    try:
        value = node.value(key)  # type: ignore[attr-defined]
    except Exception:
        return None
    if isinstance(value, (StringValue, CStringValue)):
        return value.text
    return None


def _named_text(doc: UiDocument, name: str, key: str) -> Optional[str]:
    found = doc.by_name(name)
    if not found:
        return None
    return _stored(doc.node(found[0]), key)


def _node_id(doc: UiDocument, name: str) -> Optional[NodeId]:
    found = doc.by_name(name)
    if not found:
        return None
    return found[0]


def cache_key(doc: object, source: str, relative: str) -> Tuple[int, int, str, str]:
    """The publish key: document identity, revision, source digest, path."""
    text = source if isinstance(source, str) else ""
    return (
        id(doc),
        int(getattr(doc, "revision", 0)),
        hashlib.sha256(text.encode("utf-8")).hexdigest(),
        relative if isinstance(relative, str) else "",
    )


# Re-exported types the panel names without importing diagnostics itself.
__all__ = [
    "LogicBook",
    "PanelQuery",
    "PanelRow",
    "Use",
    "WORDS",
    "cache_key",
    "collect",
    "of_name",
    "panel_rows",
]
