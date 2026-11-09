"""FB119: add the error label. The diagnostic carries no fix list of its own."""

from __future__ import annotations

from app.features.form_builder.engine.commands.catalog_ext.checks import AddErrorLabel
from app.features.form_builder.engine.diagnostics import FormDiagnostic
from app.features.form_builder.engine.logic.formula_env import env_for
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.integration.problem_fixes import FixContext, ProblemFix


def _offered(diagnostic: FormDiagnostic) -> bool:
    # The engine leaves diagnostic.fixes empty for FB119, so this does not read it.
    return diagnostic.code == "FB119"


def _display(context: FixContext, name: str) -> str:
    document = context.session.document
    try:
        env = env_for(document, None, QtClassTable.shared())
    except Exception:
        return name
    facts = env.widgets.get(name)
    if facts is not None and facts.display:
        return str(facts.display)
    return name


def _run(context: FixContext) -> None:
    name = context.diagnostic.location.object_name or ""
    if not name:
        return
    document = context.session.document
    found = document.by_name(name)
    if not found:
        return
    node = document.node(found[0])
    if not isinstance(node, WidgetNode):
        return
    label = "Add error label for %s" % _display(context, name)
    with context.session.log.transaction(label) as txn:
        txn.execute(AddErrorLabel(node.id))


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if not callable(add):
        return
    add(ProblemFix("FB119", "add-label", "Add label", _run, offered=_offered))
