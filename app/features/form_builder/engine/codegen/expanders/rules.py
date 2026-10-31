"""Rules and defaults (CONTRACTS §18.2, order 200).

One contribution carries ``_cbcs_apply_defaults`` and ``cbcs_refresh``, in that
order, so their sequence does not depend on a second expander. Connects name
``cbcs_refresh``. The core looks up the change signal. A form with no formula
properties contributes nothing, so the module stays byte-identical to M6.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from app.features.form_builder.engine.codegen.expanders.defaults import Prepared, prepare
from app.features.form_builder.engine.codegen.logic_hooks import CodegenContext, Contribution, Method
from app.features.form_builder.engine.logic.formula_env import env_for
from app.features.form_builder.engine.logic.rules import rule_graph
from app.features.form_builder.engine.logic.storage import FORMULA_KEYS
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import CStringValue, StringValue

_REFRESH_DOC = "Run every rule on this form again. Safe to call from your own code."


class RulesExpander:
    expander_id = "rules"
    level = 3
    order = 200

    def contribute(self, doc: UiDocument, ctx: CodegenContext) -> Contribution:
        if not _any_formula(doc):
            return Contribution()
        env = env_for(doc, ctx.window, QtClassTable.shared())
        graph = rule_graph(doc, env)
        if not graph.records:
            return Contribution()
        refresh_parts = tuple(prepare(graph.records[rule_id], env, ctx.trace) for rule_id in graph.order())
        default_parts = tuple(prepare(graph.records[rule_id], env, ctx.trace) for rule_id in graph.defaults())
        methods: List[Method] = []
        if default_parts:
            methods.append(_method("_cbcs_apply_defaults", "", "defaults", _plain_body(default_parts)))
        if refresh_parts:
            methods.append(_method("cbcs_refresh", "*args", "rules", _refresh_body(refresh_parts)))
        if not methods and not graph.diagnostics:
            return Contribution()
        setup: List[str] = []
        connects: List[Tuple[str, str]] = []
        if methods:
            if refresh_parts:
                setup.append("self._cbcs_refreshing = False")
            if default_parts:
                setup.append("self._cbcs_apply_defaults()")
            if refresh_parts:
                setup.append("self.cbcs_refresh()")
            connects = _connects(doc, refresh_parts, default_parts)
        helpers: List[str] = []
        imports: List[Tuple[str, str]] = []
        for part in default_parts + refresh_parts:
            for helper in part.helpers:
                if helper not in helpers:
                    helpers.append(helper)
            for pair in part.imports:
                if pair not in imports:
                    imports.append(pair)
        return Contribution(
            imports=tuple(imports),
            setup_lines=tuple(setup),
            methods=tuple(methods),
            helpers=tuple(helpers),
            diagnostics=graph.diagnostics,
            needs_form=bool(methods),
            connects=tuple(connects),
        )


def _method(name: str, params: str, source_ref: str, body: str) -> Method:
    return Method(name=name, body=body, source_ref=source_ref, params=params)


def _plain_body(parts: Sequence[Prepared]) -> str:
    lines: List[str] = []
    for part in parts:
        lines.extend(part.lines)
    if not _has_statement(lines):
        lines.append("pass")
    return "\n".join(lines)


def _refresh_body(parts: Sequence[Prepared]) -> str:
    inner: List[str] = []
    for part in parts:
        for line in part.lines:
            inner.append("    " + line if line else "")
    if not _has_statement(inner):
        inner.append("    pass")
    lines = [
        '"""%s"""' % _REFRESH_DOC,
        "if self._cbcs_refreshing:",
        "    return",
        "self._cbcs_refreshing = True",
        "try:",
    ]
    lines.extend(inner)
    lines.extend(["finally:", "    self._cbcs_refreshing = False"])
    return "\n".join(lines)


def _has_statement(lines: Sequence[str]) -> bool:
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return True
    return False


def _connects(doc: UiDocument, refresh_parts: Sequence[Prepared], default_parts: Sequence[Prepared]) -> List[Tuple[str, str]]:
    wanted = set()
    for part in refresh_parts:
        if part.live:
            wanted.update(part.reads)
    for part in default_parts:
        if part.live:
            wanted.update(part.reads)
    ranked = []
    try:
        widgets = tuple(doc.iter_widgets())
    except Exception:
        widgets = ()
    for node in widgets:
        name = node.object_name or ""
        if name in wanted and name not in ranked:
            ranked.append(name)
    return [(name, "cbcs_refresh") for name in ranked]


def _any_formula(doc: UiDocument) -> bool:
    try:
        widgets = tuple(doc.iter_widgets())
    except Exception:
        return False
    for node in widgets:
        for key in FORMULA_KEYS:
            try:
                value = node.value(key)
            except Exception:
                continue
            if isinstance(value, (StringValue, CStringValue)) and value.text.strip():
                return True
    return False


EXPANDER = RulesExpander()
