"""Fix button for FB035: "Use my own class…" opens the popover for a widget of that class (UX-CUST-010)."""

from __future__ import annotations

from app.features.form_builder.engine.diagnostics import FormDiagnostic
from app.features.form_builder.integration.custom_registry import registry_of
from app.features.form_builder.integration.problem_fixes import FixContext, ProblemFix
from app.features.form_builder.qtside.dialogs.promote import open_popover

TITLE = "Use my own class…"


def _has_widget(diagnostic: FormDiagnostic) -> bool:
    return diagnostic.location.node_id is not None


def _open(context: FixContext) -> None:
    session = context.session
    node_id = context.diagnostic.location.node_id
    if session is None or node_id is None or not session.document.contains(node_id):
        return
    surface = context.surface
    parent = surface if hasattr(surface, "isVisible") else None
    open_popover(session, (node_id,), registry_of(session), parent)


def register(registry: object) -> None:
    registry.add(ProblemFix("FB035", "use-my-own-class", TITLE, _open, offered=_has_widget))  # type: ignore[attr-defined]
