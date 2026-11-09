"""Picture problems for the Problems panel: FB031 and FB032 (UX-RES-005, UX-RES-007).

Qt-free. ``picture_diagnostics`` reads the form's document and, for FB032, the
``.qrc`` files the form includes (through the mtime cache in ``pictures``). It
writes nothing.
"""

from __future__ import annotations

import os
from typing import List, Tuple

from app.features.form_builder.engine.diagnostic_codes import fb03x_resources as _codes
from app.features.form_builder.engine.diagnostics import (
    CODES,
    DiagnosticLocation,
    FormDiagnostic,
)
from app.features.form_builder.engine.project.fs import inside_project
from app.features.form_builder.engine.project.picture_adopt import included_qrcs
from app.features.form_builder.engine.project.pictures import missing_listed, raw_pictures

del _codes

SOURCE = "pictures"


def raw_picture_message(name: str, path: str) -> str:
    """The FB031 sentence (UX_SPEC 13.2.10), used by Problems and by packaging."""
    return "%s uses a picture from a file path (%s). A packaged app may not find it." % (name, path)


def missing_file_message(qrc: str, file_name: str) -> str:
    """The FB032 sentence."""
    return "%s lists %s, but the file is missing." % (qrc, file_name)


def qrc_label(qrc_path: str, project_root: str) -> str:
    """The ``.qrc`` as the sentences show it: relative to the project, else the file name."""
    if project_root and inside_project(qrc_path, project_root):
        return os.path.relpath(os.path.abspath(qrc_path), os.path.abspath(project_root)).replace(os.sep, "/")
    return os.path.basename(qrc_path)


def picture_diagnostics(document: object, ui_path: str, project_root: str) -> Tuple[FormDiagnostic, ...]:
    found: List[FormDiagnostic] = []
    raw_info = CODES["FB031"]
    for item in raw_pictures(document):
        found.append(
            FormDiagnostic(
                code=raw_info.code,
                severity=raw_info.severity,
                message=raw_picture_message(item.object_name or "A widget", item.path),
                location=DiagnosticLocation(
                    node_id=item.node_id,  # type: ignore[arg-type]
                    object_name=item.object_name or None,
                    property=item.property_name,
                    rule_path=(item.state,) if item.state else (),
                ),
                source=SOURCE,
            )
        )
    gone_info = CODES["FB032"]
    for qrc in included_qrcs(document, ui_path):
        if not qrc.lower().endswith(".qrc") or (project_root and not inside_project(qrc, project_root)):
            continue
        label = qrc_label(qrc, project_root)
        for file_name in missing_listed(qrc):
            found.append(
                FormDiagnostic(
                    code=gone_info.code,
                    severity=gone_info.severity,
                    message=missing_file_message(label, file_name),
                    location=DiagnosticLocation(property=label, rule_path=(file_name,)),
                    source=SOURCE,
                )
            )
    return tuple(found)


__all__ = ["SOURCE", "missing_file_message", "picture_diagnostics", "qrc_label", "raw_picture_message"]
