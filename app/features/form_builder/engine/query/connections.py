"""Connection endpoints that do not name a widget on the form (FB014)."""

from __future__ import annotations

from typing import FrozenSet, List, Optional, Tuple

from app.features.form_builder.engine.diagnostic_codes import fb0xx as _fb0xx
from app.features.form_builder.engine.diagnostics import (
    CODES,
    DiagnosticLocation,
    FormDiagnostic,
)
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import Node


def missing_connection_diagnostics(doc: UiDocument) -> Tuple[FormDiagnostic, ...]:
    """One FB014 per connection that names a sender or receiver not on the form."""
    info = CODES["FB014"]
    alive = doc.names()
    found: List[FormDiagnostic] = []
    for index, node in enumerate(doc.connections()):
        missing = _missing_end(node, alive)
        if missing is None:
            continue
        found.append(
            FormDiagnostic(
                code=info.code,
                severity=info.severity,
                message=_connection_sentence(node, missing),
                location=DiagnosticLocation(
                    node_id=node.id,
                    object_name=missing,
                    rule_path=("connections", index),
                ),
                source="connections",
            )
        )
    return tuple(found)


def _connection_sentence(node: Node, missing: str) -> str:
    """Name the connection and say what to do (UX-COPY-003)."""
    sender = _text_field(node, "sender")
    receiver = _text_field(node, "receiver")
    signal = _text_field(node, "signal").replace("()", "")
    slot = _text_field(node, "slot").replace("()", "")
    return (
        "The connection %s.%s → %s.%s points at %s, which isn't in this form. "
        "Add a widget named %s or delete the connection."
        % (sender, signal, receiver, slot, missing, missing)
    )


def _text_field(node: Node, name: str) -> str:
    value = node.field(name)
    return value if isinstance(value, str) else ""


def _missing_end(node: Node, alive: FrozenSet[str]) -> Optional[str]:
    sender = node.field("sender")
    receiver = node.field("receiver")
    if isinstance(sender, str) and sender and sender not in alive:
        return sender
    if isinstance(receiver, str) and receiver and receiver not in alive:
        return receiver
    return None
