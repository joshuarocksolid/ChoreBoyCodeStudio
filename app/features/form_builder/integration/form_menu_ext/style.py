"""Form > Style sheet of the form… (UX-STYLE-001, UX-M5-010)."""

from __future__ import annotations

from app.features.form_builder.integration.form_menu_ext import FormMenuItem
from app.features.form_builder.qtside.style import gateway

COMMAND_ID = "form.action.styleSheetOfForm"


def run(surface: object) -> None:
    session = getattr(surface, "session", None)
    if session is not None:
        gateway.open_drawer(session, session.document.root.id)


def register(registry: object) -> None:
    registry.add(  # type: ignore[attr-defined]
        FormMenuItem(command_id=COMMAND_ID, path=("Style sheet of the form…",), run=run)
    )
