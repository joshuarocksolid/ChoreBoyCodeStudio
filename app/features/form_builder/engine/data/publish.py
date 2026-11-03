"""Publish design-time data checks. Qt reads this module. It does not import integration."""

from __future__ import annotations

import weakref
from typing import Dict, Tuple

from app.features.form_builder.engine.data.check import run_checks
from app.features.form_builder.engine.diagnostics import Severity

SOURCE = "data.check"
_WARNINGS: "weakref.WeakKeyDictionary[object, Dict[object, str]]" = weakref.WeakKeyDictionary()


def publish_session(session: object) -> None:
    """Replace the ``data.check`` rows for ``session``."""

    from app.features.form_builder.engine import diagnostic_codes

    if getattr(session, "disposed", False):
        return
    diagnostic_codes.discover()
    document = getattr(session, "document", None)
    diagnostics = getattr(session, "diagnostics", None)
    publish = getattr(diagnostics, "publish", None)
    current = getattr(diagnostics, "rows", None)
    if document is None or not callable(publish) or not callable(current):
        return
    rows = tuple(run_checks(document))
    marks: Dict[object, str] = {}
    for row in rows:
        node_id = row.location.node_id
        if node_id is None or row.severity is Severity.ERROR:
            continue
        marks.setdefault(node_id, row.message)
    try:
        _WARNINGS[document] = marks
    except TypeError:
        pass
    if current(SOURCE) == rows:
        return
    publish(SOURCE, rows)


def warnings_of(document: object) -> Dict[object, str]:
    """Warning text per node, for the bind chip."""

    try:
        return dict(_WARNINGS.get(document, {}))
    except TypeError:
        return {}


def warning_rows(session: object, node_id: object) -> Tuple[object, ...]:
    """Data-check rows that point at ``node_id``."""

    diagnostics = getattr(session, "diagnostics", None)
    rows = getattr(diagnostics, "rows", None)
    if not callable(rows):
        return ()
    found = rows(SOURCE)
    if not isinstance(found, (list, tuple)):
        return ()
    return tuple(
        row
        for row in found
        if getattr(getattr(row, "location", None), "node_id", None) == node_id
    )
