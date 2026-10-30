"""FB406: a step whose name generated code cannot use (D26).

Declared here so M6.1b owns the code. Same severity as FB401. Nothing here
blocks saving. The check matches the Events list lock, including a native
connection, and does not import Qt.
"""

from __future__ import annotations

from typing import List, Tuple

from app.features.form_builder.engine.diagnostics import (
    CODES,
    DiagnosticLocation,
    FormDiagnostic,
    Severity,
    declare,
)
from app.features.form_builder.engine.logic import compat
from app.features.form_builder.engine.logic.events import read_events, signal_property
from app.features.form_builder.engine.logic.events_catalog import event_words
from app.features.form_builder.engine.logic.events_codec import EventStep
from app.features.form_builder.engine.ui4.document import UiDocument

declare("FB406", Severity.ERROR, "A step has a name Code Studio can't use.")

SOURCE = "events"


def _token(step: EventStep) -> str:
    if step.raw is not None:
        return ""
    if step.verb == "slot":
        if not compat.is_name(step.target):
            return step.target
        if not compat.is_signature(step.slot):
            return step.slot
        return ""
    if step.verb == "call" and not compat.is_name(step.method):
        return step.method
    return ""


def name_diagnostics(doc: object) -> Tuple[FormDiagnostic, ...]:
    """One FB406 per event that holds a bad name, including a native connection."""
    assert isinstance(doc, UiDocument)
    info = CODES["FB406"]
    found: List[FormDiagnostic] = []
    for state in read_events(doc):
        names = tuple(token for token in (_token(step) for step in state.steps) if token)
        if not names:
            continue
        owner = doc.by_name(state.sender)
        node_id = owner[0] if owner else None
        key = state.list_property or signal_property(state.signal_name)
        words = event_words(state.signal_name).header
        found.append(
            FormDiagnostic(
                code=info.code,
                severity=info.severity,
                message=(
                    "%s %s has a step whose name Code Studio can't use (%s). "
                    "It is kept as it is and does nothing."
                    % (state.sender, words, names[0])
                ),
                location=DiagnosticLocation(
                    node_id=node_id,
                    object_name=state.sender,
                    property=key,
                ),
                source=SOURCE,
            )
        )
    return tuple(found)
