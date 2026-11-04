"""Arm data-check publishing when a form workbench opens.

The rows themselves live in ``engine/data/publish.py``, which Qt can import.
"""

from __future__ import annotations

from app.features.form_builder.engine.data.publish import (
    SOURCE,
    publish_session,
    warning_rows,
    warnings_of,
)

__all__ = ["SOURCE", "arm", "publish_session", "warning_rows", "warnings_of"]

#: A change that only writes these leaves the data checks' answers the same.
#: Record verbs, bindings, and ``cbcsData`` are not in this set, so those edits
#: still publish.
_BEHAVIOR_ONLY = frozenset(
    {
        "cbcsDefault",
        "cbcsEnabledWhen",
        "cbcsErrorLabel",
        "cbcsErrorSummary",
        "cbcsFormat",
        "cbcsLogic",
        "cbcsReadOnlyWhen",
        "cbcsSplitterSizes",
        "cbcsValidate",
        "cbcsVisibleWhen",
    }
)


def _behavior_only(change: object) -> bool:
    """True when this edit cannot change a data diagnostic."""

    if change is None or getattr(change, "replaced", False) or getattr(change, "renamed", ()):
        return False
    if getattr(change, "added", None) or getattr(change, "removed", None) or getattr(change, "structure_dirty", None):
        return False
    dirty = getattr(change, "property_dirty", ())
    if not dirty:
        return False
    return all(name in _BEHAVIOR_ONLY for _owner, _kind, name in dirty)


def arm(session: object) -> None:
    """Publish now and after each edit. The engine does not import this module."""

    if session is None or getattr(session, "_cbcs_data_checks", False):
        return
    log = getattr(session, "log", None)
    subscribe = getattr(log, "subscribe", None)
    if not callable(subscribe):
        return
    setattr(session, "_cbcs_data_checks", True)
    from app.features.form_builder.engine.events import PRIORITY_DIAGNOSTICS

    def refresh(_change: object = None) -> None:
        if _behavior_only(_change):
            return
        publish_session(session)

    subscribe(refresh, priority=PRIORITY_DIAGNOSTICS)
    publish_session(session)


