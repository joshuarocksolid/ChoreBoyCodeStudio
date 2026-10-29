"""Event storage diagnostics: FB404 and the producers of FB404 and FB405 (CONTRACTS section 15.9).

FB404 is declared here. FB405 (a step whose target is not on the form) is declared
with FB401 to FB403 in ``fb4xx_logic.py`` (M6.0b); this module only produces it, and
reads its severity at call time so the order modules load in does not matter.
Nothing here blocks saving (CONTRACTS 7.3).
"""

from __future__ import annotations

from typing import List, Tuple

from app.features.form_builder.engine.diagnostics import (
    CODES,
    DiagnosticLocation,
    FormDiagnostic,
    QuickFix,
    Severity,
    declare,
)

declare("FB404", Severity.WARNING, "An event is stored in two places.")

SOURCE = "events"


def event_diagnostics(doc: object) -> Tuple[FormDiagnostic, ...]:
    """FB404 per event with native connections and a step list, FB405 per step that acts on a missing object."""
    # Imported here: these modules import the diagnostics registry and must not load while it fills.
    from app.features.form_builder.engine.commands.catalog_ext.events import MergeEventStorage
    from app.features.form_builder.engine.logic.events import read_events, signal_property
    from app.features.form_builder.engine.logic.events_catalog import class_chain, event_words
    from app.features.form_builder.engine.logic.compat import node_class
    from app.features.form_builder.engine.ui4.defaults import QtClassTable
    from app.features.form_builder.engine.ui4.document import UiDocument

    assert isinstance(doc, UiDocument)
    classes = QtClassTable.shared()
    names = doc.names()
    found: List[FormDiagnostic] = []
    for state in read_events(doc):
        owner = doc.by_name(state.sender)
        node = doc.node(owner[0]) if owner else None
        chain = class_chain(classes, node_class(doc, classes, node)[0]) if node is not None else ()
        words = event_words(state.signal_name, chain).header
        key = signal_property(state.signal_name)
        location = DiagnosticLocation(
            node_id=node.id if node is not None else None,
            object_name=state.sender,
            property=key,
            rule_path=(key,),
        )
        if state.stored_twice:
            info = CODES["FB404"]
            found.append(
                FormDiagnostic(
                    code=info.code,
                    severity=info.severity,
                    message=(
                        "%s %s is stored in two places: Qt Designer connections and a Code Studio step list."
                        % (state.sender, words)
                    ),
                    location=location,
                    source=SOURCE,
                    fixes=(
                        QuickFix(
                            "merge-event",
                            "Merge",
                            command=MergeEventStorage(
                                state.sender, state.signal_name, caption="Merge the %s event" % words
                            ),
                        ),
                    ),
                )
            )
        for number, step in enumerate(state.list_steps, 1):
            if step.verb != "slot" or not step.target or step.target in names:
                continue
            info405 = CODES.get("FB405")
            found.append(
                FormDiagnostic(
                    code="FB405",
                    severity=info405.severity if info405 is not None else Severity.ERROR,
                    message=(
                        "Step %d of %s %s acts on %s, which isn't on this form."
                        % (number, state.sender, words, step.target)
                    ),
                    location=DiagnosticLocation(
                        node_id=location.node_id,
                        object_name=state.sender,
                        property=key,
                        rule_path=(key, number - 1),
                    ),
                    source=SOURCE,
                )
            )
    return tuple(found)
