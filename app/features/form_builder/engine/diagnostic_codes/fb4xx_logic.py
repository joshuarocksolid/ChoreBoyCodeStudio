"""Logic storage diagnostic codes (CONTRACTS.md section 15.9): FB401, FB402, FB403, FB405.

FB404 (an event stored in two places) is declared by M6.1a with its producer, in
``fb40x_events.py``. FB405 is declared here; its producer is M6.1a's too.

``logic_diagnostics(doc)`` is the producer of FB401, FB402 and FB403: pure, O(1) for a
form without logic, and it never blocks saving (CONTRACTS 7.3).
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from app.features.form_builder.engine.commands.refs import identity_name
from app.features.form_builder.engine.diagnostics import (
    DiagnosticLocation,
    FormDiagnostic,
    Severity,
    declare,
)
from app.features.form_builder.engine.logic.codec import parse_json, parse_steps, read_marker
from app.features.form_builder.engine.logic.storage import (
    JSON_KEYS,
    JSON_TOP_SHAPE,
    SUPPORTED_LOGIC_VERSION,
    is_signal_property,
    is_user_logic_key,
    signal_of_property,
)
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import StringValue

SOURCE = "logic.storage"

declare("FB401", Severity.ERROR, "A logic property can't be read.")
declare("FB402", Severity.WARNING, "This form's behavior was saved by a newer version of Code Studio.")
declare("FB403", Severity.ERROR, "A step is from a newer version of Code Studio.")
declare("FB405", Severity.ERROR, "A step acts on something that isn't on the form.")

_WORDS = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")


def event_words(signal_name: str) -> str:
    """``currentIndexChanged`` -> ``current index changed``. M6.1a's catalog has nicer words."""
    return " ".join(part.lower() for part in _WORDS.findall(signal_name)) or signal_name


def unreadable_message(property_name: str, object_name: str, line: int) -> str:
    return "%s on %s can't be read (line %d). It is kept as it is and does nothing." % (property_name, object_name, line)


def newer_message(version: Optional[int]) -> str:
    shown = "unknown" if version is None else str(version)
    return (
        "This form's behavior was saved by a newer version of Code Studio (version %s). "
        "It is shown read-only and kept as it is." % (shown,)
    )


def unknown_step_message(object_name: str, event: str, verb: str) -> str:
    return (
        "%s %s has a step Code Studio can't edit (%s). "
        "The event does nothing until it's edited in a newer version." % (object_name, event, verb)
    )


def logic_diagnostics(doc: UiDocument) -> Tuple[FormDiagnostic, ...]:
    """FB402 for the form, FB401 for each property that can't be read, FB403 for each step list
    that holds a verb this build doesn't type. A read-only form gets FB402 (and FB401 for a
    marker that can't be read) only."""
    root_entry = doc.root.prop("cbcsLogic")
    found: List[FormDiagnostic] = []
    root_label = identity_name(doc.root) or "the form"
    marker = read_marker(root_entry)
    if not marker.readable:
        location = DiagnosticLocation(doc.root.id, root_label, "cbcsLogic", ("cbcsLogic",))
        found.append(FormDiagnostic("FB401", Severity.ERROR, unreadable_message("cbcsLogic", root_label, 1), location, SOURCE))
        found.append(
            FormDiagnostic("FB402", Severity.WARNING, newer_message(None), DiagnosticLocation(doc.root.id, root_label), SOURCE)
        )
    elif marker.version is not None and marker.version > SUPPORTED_LOGIC_VERSION:
        found.append(
            FormDiagnostic(
                "FB402",
                Severity.WARNING,
                newer_message(marker.version),
                DiagnosticLocation(doc.root.id, root_label),
                SOURCE,
            )
        )
    if found or doc.logic_property_count() == 0:
        # Newer logic is never interpreted (CONTRACTS 15.7): its texts may use shapes and verbs
        # this build doesn't know, so FB402 alone speaks for them.
        return tuple(found)
    for node in doc.iter_preorder():
        owner_name = identity_name(node) or "the form"
        for entry in node.properties():
            if not is_user_logic_key(entry.name) or not isinstance(entry.value, StringValue):
                continue
            key = entry.name
            location = DiagnosticLocation(node.id, owner_name, key, (key,))
            if is_signal_property(key):
                read = parse_steps(entry.value.text)
                if read.error is not None:
                    found.append(
                        FormDiagnostic(
                            "FB401", Severity.ERROR, unreadable_message(key, owner_name, read.error[0]), location, SOURCE
                        )
                    )
                    continue
                unknown = next((step.verb for step in read.steps if not step.is_typed), None)
                if unknown is not None:
                    words = event_words(read.signal or signal_of_property(key) or key)
                    found.append(
                        FormDiagnostic(
                            "FB403", Severity.ERROR, unknown_step_message(owner_name, words, unknown), location, SOURCE
                        )
                    )
            elif key in JSON_KEYS:
                got = parse_json(entry.value.text)
                bad: Optional[int] = None
                if got.error is not None:
                    bad = got.error[0]
                else:
                    shape = JSON_TOP_SHAPE.get(key, "any")
                    wrong = (shape == "array" and not isinstance(got.value, tuple)) or (
                        shape == "object" and not hasattr(got.value, "pairs")
                    )
                    if wrong:
                        bad = 1
                if bad is not None:
                    found.append(
                        FormDiagnostic("FB401", Severity.ERROR, unreadable_message(key, owner_name, bad), location, SOURCE)
                    )
    return tuple(found)
