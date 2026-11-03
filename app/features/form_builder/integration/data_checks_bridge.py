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


def arm(session: object) -> None:
    """Publish now and after each edit. The engine does not import this module."""

    if session is None or getattr(session, "_cbcs_data_checks", False):
        return
    log = getattr(session, "log", None)
    subscribe = getattr(log, "subscribe", None)
    if not callable(subscribe):
        return
    setattr(session, "_cbcs_data_checks", True)
    _install_list_probe_secret()
    from app.features.form_builder.engine.events import PRIORITY_DIAGNOSTICS

    def refresh(_change: object = None) -> None:
        publish_session(session)

    subscribe(refresh, priority=PRIORITY_DIAGNOSTICS)
    publish_session(session)


def _install_list_probe_secret() -> None:
    from app.features.form_builder.engine.data.checks.listing import set_list_probe_secret
    from app.features.form_builder.engine.data.schema_cache import installed_root
    from app.features.form_builder.qtside.schema_prompt import ask_connection_secret

    def secret(connection: object) -> str:
        root = installed_root()
        if not root:
            return ""
        return ask_connection_secret(root, connection)  # type: ignore[arg-type]

    set_list_probe_secret(secret)


