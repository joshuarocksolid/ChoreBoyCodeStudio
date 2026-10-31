"""The rule graph (CONTRACTS §18.1).

Nodes are ``(widget, key)`` for the five formula properties. An edge runs from
a widget's Value rule to a rule that reads that widget. Defaults are outside
the refresh order. A default that reads a calculated field, and every node of
a cycle, is FB104 and generates nothing.

The graph is cached on ``doc.structure_revision``. A different formula
environment (another window reading, another kind map) is a different cache key.
"""

from __future__ import annotations

import keyword
from dataclasses import dataclass
from types import MappingProxyType
from typing import Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

from app.features.form_builder.engine.diagnostic_codes import fb1xx_formula as _fb1xx
from app.features.form_builder.engine.diagnostics import (
    CODES,
    DiagnosticLocation,
    FormDiagnostic,
    Severity,
)
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.logic.formula import analyze
from app.features.form_builder.engine.logic.formula.env import FormulaEnv, SlotKind
from app.features.form_builder.engine.logic.formula.types import ANY
from app.features.form_builder.engine.logic.storage import FORMULA_KEYS
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import CStringValue, StringValue

del _fb1xx

_VALUE = "cbcsValue"
_DEFAULT = "cbcsDefault"
_STATE = ("cbcsEnabledWhen", "cbcsVisibleWhen", "cbcsReadOnlyWhen")
_ANY_VALUE = SlotKind.value(ANY)


@dataclass(frozen=True)
class RuleId:
    """One formula property on one widget."""

    widget: str
    key: str


@dataclass(frozen=True)
class RuleRecord:
    """The stored formula. Plain values only, so the graph can sit in the memo."""

    widget: str
    key: str
    text: str
    tree_index: int
    node_id: Optional[NodeId]
    fmt: str


@dataclass(frozen=True)
class RuleGraph:
    """Value order, then state order. Cycles and rejected defaults are absent from both."""

    records: Mapping[RuleId, RuleRecord]
    diagnostics: Tuple[FormDiagnostic, ...]
    _value_order: Tuple[RuleId, ...]
    _state_order: Tuple[RuleId, ...]
    _cycles: Tuple[Tuple[RuleId, ...], ...]
    _defaults: Tuple[RuleId, ...]

    def order(self) -> Tuple[RuleId, ...]:
        """Value rules in dependency order, then state rules. Ties follow the widget tree."""
        return self._value_order + self._state_order

    def cycles(self) -> Tuple[Tuple[RuleId, ...], ...]:
        """Strongly connected Value components, each closed circle once."""
        return self._cycles

    def defaults(self) -> Tuple[RuleId, ...]:
        """Defaults that are allowed to run, in widget tree order."""
        return self._defaults


def rule_graph(doc: UiDocument, env: FormulaEnv) -> RuleGraph:
    """Incremental: the same revision and environment return the same graph."""
    key = "m7.2a.rule_graph\0%s" % _env_token(env)
    return doc.structure_memo(key, lambda: _build(doc, env))


def _env_token(env: FormulaEnv) -> str:
    parts = []
    for name in sorted(env.widgets):
        facts = env.widgets[name]
        parts.append("%s:%s:%s:%s:%s" % (name, facts.class_name, facts.kind, facts.decimals, facts.allow_blank))
    return "\n".join(parts)


def _build(doc: UiDocument, env: FormulaEnv) -> RuleGraph:
    records = _collect(doc)
    by_id = {RuleId(item.widget, item.key): item for item in records}
    value_of = {item.widget: RuleId(item.widget, _VALUE) for item in records if item.key == _VALUE}
    reads = {rule_id: _reads(item.text, env) for rule_id, item in by_id.items()}
    edges: List[Tuple[RuleId, RuleId]] = []
    for rule_id, names in reads.items():
        if rule_id.key == _DEFAULT:
            continue
        for name in names:
            src = value_of.get(name)
            if src is None:
                continue
            edges.append((src, rule_id))
    value_ids = tuple(rule_id for rule_id in by_id if rule_id.key == _VALUE)
    cycles = _sccs(value_ids, edges, by_id)
    cyclic = {node for comp in cycles for node in comp}
    diagnostics = _cycle_diagnostics(cycles, by_id)
    rejected_defaults = []
    for rule_id, item in by_id.items():
        if rule_id.key != _DEFAULT:
            continue
        if any(name in value_of for name in reads[rule_id]):
            rejected_defaults.append(rule_id)
            diagnostics.append(_default_diagnostic(item))
    rejected = cyclic.union(rejected_defaults)
    value_order = _topo(
        [rule_id for rule_id in value_ids if rule_id not in rejected],
        edges,
        by_id,
    )
    state_ids = [rule_id for rule_id in by_id if rule_id.key in _STATE and rule_id not in rejected]
    state_order = _topo(state_ids, edges, by_id)
    default_order = tuple(
        sorted(
            (rule_id for rule_id in by_id if rule_id.key == _DEFAULT and rule_id not in rejected),
            key=lambda rule_id: _sort_key(rule_id, by_id),
        )
    )
    return RuleGraph(
        records=MappingProxyType(by_id),
        diagnostics=tuple(diagnostics),
        _value_order=tuple(value_order),
        _state_order=tuple(state_order),
        _cycles=cycles,
        _defaults=default_order,
    )


def _collect(doc: UiDocument) -> Tuple[RuleRecord, ...]:
    found: List[RuleRecord] = []
    try:
        widgets = tuple(doc.iter_widgets())
    except Exception:
        return ()
    for index, node in enumerate(widgets):
        name = node.object_name or ""
        if not name:
            continue
        fmt = _stored(node, "cbcsFormat") or ""
        for key in FORMULA_KEYS:
            text = _stored(node, key)
            if text is None or not text.strip():
                continue
            found.append(
                RuleRecord(
                    widget=name,
                    key=key,
                    text=text,
                    tree_index=index,
                    node_id=getattr(node, "id", None),
                    fmt=fmt,
                )
            )
    return tuple(found)


def _stored(node: object, key: str) -> Optional[str]:
    try:
        value = node.value(key)  # type: ignore[attr-defined]
    except Exception:
        return None
    if isinstance(value, (StringValue, CStringValue)):
        return value.text
    return None


def _reads(text: str, env: FormulaEnv) -> FrozenSet[str]:
    """Widget names a formula reads.

    A bare name is the common rule (``qtySpin``). ``analyze`` treats that as one
    widget read, unless the name is reserved. Doing that lookup here keeps a
    100-rule graph under the 5 ms budget. Anything with an operator still goes
    through ``analyze``, which is the dependency set the checker publishes.
    """
    stripped = text.strip()
    if (
        stripped.isidentifier()
        and not keyword.iskeyword(stripped)
        and stripped not in env.reserved
        and not stripped.startswith("cbcs")
    ):
        if stripped in env.widgets:
            return frozenset((stripped,))
        return frozenset()
    try:
        found = analyze(text, env, _ANY_VALUE)
    except Exception:
        return frozenset()
    return frozenset(found.reads)


def _sccs(
    nodes: Sequence[RuleId],
    edges: Sequence[Tuple[RuleId, RuleId]],
    records: Mapping[RuleId, RuleRecord],
) -> Tuple[Tuple[RuleId, ...], ...]:
    index = {node: pos for pos, node in enumerate(nodes)}
    succ: List[List[int]] = [[] for _ in nodes]
    pred: List[List[int]] = [[] for _ in nodes]
    self_loop = set()
    for src, dst in edges:
        if src not in index or dst not in index:
            continue
        if src == dst:
            self_loop.add(src)
            continue
        succ[index[src]].append(index[dst])
        pred[index[dst]].append(index[src])
    seen = [False] * len(nodes)
    finish: List[int] = []
    for start in range(len(nodes)):
        if seen[start]:
            continue
        stack = [(start, 0)]
        seen[start] = True
        while stack:
            node, cursor = stack[-1]
            kids = succ[node]
            if cursor < len(kids):
                stack[-1] = (node, cursor + 1)
                nxt = kids[cursor]
                if not seen[nxt]:
                    seen[nxt] = True
                    stack.append((nxt, 0))
            else:
                finish.append(node)
                stack.pop()
    seen = [False] * len(nodes)
    comps: List[Tuple[RuleId, ...]] = []
    for start in reversed(finish):
        if seen[start]:
            continue
        seen[start] = True
        stack = [start]
        comp: List[RuleId] = []
        while stack:
            node = stack.pop()
            comp.append(nodes[node])
            for nxt in pred[node]:
                if not seen[nxt]:
                    seen[nxt] = True
                    stack.append(nxt)
        ordered = sorted(comp, key=lambda rule_id: _sort_key(rule_id, records))
        if len(ordered) > 1 or (len(ordered) == 1 and ordered[0] in self_loop):
            comps.append(tuple(ordered))
    return tuple(comps)


def _topo(
    nodes: Sequence[RuleId],
    edges: Sequence[Tuple[RuleId, RuleId]],
    records: Mapping[RuleId, RuleRecord],
) -> List[RuleId]:
    live = set(nodes)
    indeg = {node: 0 for node in nodes}
    succ: Dict[RuleId, List[RuleId]] = {node: [] for node in nodes}
    for src, dst in edges:
        if src in live and dst in live and src != dst:
            succ[src].append(dst)
            indeg[dst] += 1
    ready = sorted((node for node in nodes if indeg[node] == 0), key=lambda rule_id: _sort_key(rule_id, records))
    ordered: List[RuleId] = []
    while ready:
        node = ready.pop(0)
        ordered.append(node)
        for nxt in succ[node]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                ready.append(nxt)
        ready.sort(key=lambda rule_id: _sort_key(rule_id, records))
    return ordered


def _sort_key(rule_id: RuleId, records: Mapping[RuleId, RuleRecord]) -> Tuple[int, int]:
    record = records.get(rule_id)
    tree = record.tree_index if record is not None else 0
    try:
        rank = FORMULA_KEYS.index(rule_id.key)
    except ValueError:
        rank = len(FORMULA_KEYS)
    return (tree, rank)


def _cycle_diagnostics(
    cycles: Sequence[Sequence[RuleId]],
    records: Mapping[RuleId, RuleRecord],
) -> List[FormDiagnostic]:
    found: List[FormDiagnostic] = []
    for comp in cycles:
        names: List[str] = []
        for rule_id in comp:
            if rule_id.widget not in names:
                names.append(rule_id.widget)
        if not names:
            continue
        message = "These values depend on each other in a circle: %s, then %s." % (
            ", then ".join(names),
            names[0],
        )
        for rule_id in comp:
            record = records.get(rule_id)
            found.append(_fb104(message, rule_id, None if record is None else record.node_id))
    return found


def _default_diagnostic(record: RuleRecord) -> FormDiagnostic:
    return _fb104("A default can't read a calculated field", RuleId(record.widget, record.key), record.node_id)


def _fb104(message: str, rule_id: RuleId, node_id: Optional[NodeId]) -> FormDiagnostic:
    info = CODES.get("FB104")
    severity = info.severity if info is not None else Severity.ERROR
    return FormDiagnostic(
        code="FB104",
        severity=severity,
        message=message,
        location=DiagnosticLocation(
            node_id=node_id,
            object_name=rule_id.widget,
            property=rule_id.key,
        ),
        source="logic.rules",
    )
