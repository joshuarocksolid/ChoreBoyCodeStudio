"""Publish FB035 for one open form and keep it current (M5.4, UX-CUST-010)."""

from __future__ import annotations

from typing import Callable

from app.features.form_builder.engine.events import PRIORITY_DIAGNOSTICS
from app.features.form_builder.engine.project.custom_checks import SOURCE, custom_diagnostics
from app.features.form_builder.engine.session import FormSession


def attach_custom_checks(session: FormSession, project_root: str) -> Callable[[], None]:
    """Publish now and after each change to the form. Returns a function that stops.

    An unchanged answer is not published again, so the Problems panel does not
    repaint for a keystroke elsewhere.
    """
    state = {"last": None}  # type: dict

    def refresh(_change: object = None) -> None:
        if session.disposed:
            return
        found = custom_diagnostics(session.document, project_root)
        if found == state["last"]:
            return
        state["last"] = found
        session.diagnostics.publish(SOURCE, found)

    refresh()
    subscription = session.log.subscribe(refresh, priority=PRIORITY_DIAGNOSTICS)

    def stop() -> None:
        subscription.close()

    return stop


__all__ = ["attach_custom_checks"]
