"""``.qrc`` files open in the resource editor, and forms watch their pictures (UX-RES-004, 005, 007).

``QrcTabProvider`` builds the resource editor tab. ``attach_picture_checks``
publishes FB031 and FB032 for one form session and keeps them current while the
form changes. ``FormTabProvider`` calls both; this module is the only place
that knows how.
"""

from __future__ import annotations

from typing import Callable, Optional

from app.features.form_builder.engine.diagnostics import FormDiagnostic
from app.features.form_builder.engine.project.picture_checks import SOURCE, picture_diagnostics
from app.features.form_builder.engine.project.qrc_edit import QrcEditSource
from app.features.form_builder.engine.session import FormSession
from app.shell.tab_content_providers import ProviderDeclined, TabSurfaceRequest

QRC_SUFFIX = ".qrc"


def is_qrc(file_path: str) -> bool:
    return file_path.lower().endswith(QRC_SUFFIX)


class QrcTabProvider:
    """Creates the resource editor for a ``.qrc`` path. ``FormTabProvider`` delegates to it."""

    def create_surface(self, request: TabSurfaceRequest) -> object:
        from app.features.form_builder.qtside.resources.editor import QrcSurface

        try:
            source = QrcEditSource(request.initial_text, request.file_path, request.project_root or "")
        except Exception as exc:  # a parse failure opens XML, so this is a bug; fall back to text
            raise ProviderDeclined("This pictures file can't be opened as pictures.") from exc
        return QrcSurface(request, source)


def attach_picture_checks(session: FormSession, project_root: str) -> Callable[[], None]:
    """Publish FB031/FB032 now and after each change to the form. Returns a function that stops.

    The rows are computed again only when something that can change them did:
    a property or the include list. An unchanged answer is not published, so
    the Problems panel does not repaint for a keystroke elsewhere.
    """
    from app.features.form_builder.engine.events import PRIORITY_DIAGNOSTICS

    state = {"last": ()}  # type: dict

    def refresh(_change: object = None) -> None:
        if session.disposed:
            return
        found = picture_diagnostics(session.document, session.path, project_root)
        if found == state["last"]:
            return
        state["last"] = found
        session.diagnostics.publish(SOURCE, found)

    refresh()
    subscription = session.log.subscribe(refresh, priority=PRIORITY_DIAGNOSTICS)
    return subscription.close




__all__ = ["QrcTabProvider", "attach_picture_checks", "is_qrc"]
