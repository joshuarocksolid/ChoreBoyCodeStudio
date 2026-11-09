"""Fix buttons for the picture problems (UX-RES-005, UX-RES-007).

FB031 offers "Add to project pictures": the file joins the project's pictures
and the property points at it, in one undo step on the form. FB032 offers
"Open {qrc}". The fixes use the open form's session; the packaging flow has no
session and uses ``engine.project.packaging.adopt_pictures_now`` instead.
"""

from __future__ import annotations

import os
from typing import Optional

from app.features.form_builder.engine.diagnostics import FormDiagnostic
from app.features.form_builder.engine.project.fs import ProjectOpError
from app.features.form_builder.engine.project.picture_adopt import adopt_raw_picture
from app.features.form_builder.engine.project.pictures import raw_pictures
from app.features.form_builder.integration.problem_fixes import FixContext, ProblemFix
from app.features.form_builder.qtside.resources import notices
from app.features.form_builder.qtside.resources.opening import open_linked_file

ADD_TO_PICTURES = "Add to project pictures"


def _tell(context: FixContext, sentence: str) -> None:
    show = getattr(context.surface, "show_plain", None)
    if callable(show):
        show(sentence)


def _add_to_pictures(context: FixContext) -> None:
    session = context.session
    diagnostic = context.diagnostic
    location = diagnostic.location
    if session is None or not context.project_root:
        return
    state = location.rule_path[0] if location.rule_path else ""
    for raw in raw_pictures(session.document):
        if raw.node_id == location.node_id and raw.property_name == location.property and raw.state == state:
            break
    else:
        _tell(context, "That picture is no longer on the form.")
        return
    try:
        plan = adopt_raw_picture(session.document, session.path, context.project_root, raw)
    except ProjectOpError as exc:
        _tell(context, str(exc))
        return
    with session.log.transaction(plan.label) as txn:
        for command in plan.commands:
            txn.execute(command)
    notices.remember(plan.label, plan.notice)
    _tell(context, plan.notice)


def _open_title(diagnostic: FormDiagnostic) -> str:
    return "Open %s" % (diagnostic.location.property or "the pictures file")


def _open_qrc(context: FixContext) -> None:
    label = context.diagnostic.location.property or ""
    if not label or not context.project_root:
        return
    path = os.path.join(context.project_root, *label.split("/"))
    open_linked_file(context.surface, path)


def _is_picture_row(diagnostic: FormDiagnostic) -> Optional[bool]:
    return bool(diagnostic.location.property)


def register(registry: object) -> None:
    registry.add(  # type: ignore[attr-defined]
        ProblemFix("FB031", "add-to-project-pictures", ADD_TO_PICTURES, _add_to_pictures, offered=_is_picture_row)  # type: ignore[arg-type]
    )
    registry.add(ProblemFix("FB032", "open-pictures-file", _open_title, _open_qrc, offered=_is_picture_row))  # type: ignore[attr-defined,arg-type]
