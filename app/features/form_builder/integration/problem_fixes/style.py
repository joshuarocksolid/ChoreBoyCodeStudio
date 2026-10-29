"""Problems fix buttons for the style sheet codes (FB033, FB034)."""

from __future__ import annotations

from app.features.form_builder.integration.problem_fixes import FixContext, ProblemFix
from app.features.form_builder.qtside.style import gateway

TITLE = "Edit style sheet"


def edit_style_sheet(context: FixContext) -> None:
    gateway.open_drawer(context.session, context.diagnostic.location.node_id)


def register(registry: object) -> None:
    for code in ("FB033", "FB034"):
        registry.add(ProblemFix(code, "edit-style-sheet", TITLE, edit_style_sheet))  # type: ignore[attr-defined]
