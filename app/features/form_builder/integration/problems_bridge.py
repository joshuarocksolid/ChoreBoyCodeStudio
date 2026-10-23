"""Form diagnostics as ordinary Problems rows (CONTRACTS.md section 7.4)."""

from __future__ import annotations

import os
from typing import List, Sequence

from app.features.form_builder.engine.diagnostics import FormDiagnostic, to_problem_detail
from app.intelligence.diagnostics_models import CodeDiagnostic, DiagnosticSeverity


def code_diagnostics_for_form(
    file_path: str,
    diagnostics: Sequence[FormDiagnostic],
) -> List[CodeDiagnostic]:
    """Map form diagnostics onto the shell row. FB9xx stays hidden unless debug is on."""
    show_internal = os.environ.get("CBCS_FB_DEBUG") == "1"
    rows: List[CodeDiagnostic] = []
    for item in diagnostics:
        if item.code.startswith("FB9") and not show_internal:
            continue
        location = item.location
        obj = location.object_name or ""
        line = location.line if location.line > 0 else 1
        detail = dict(to_problem_detail(item))
        detail["location_label"] = obj if obj else "Ln %d" % line
        detail["source_label"] = "Form"
        message = item.message
        if obj and not message.startswith("%s:" % obj):
            message = "%s: %s" % (obj, message)
        rows.append(
            CodeDiagnostic(
                code=item.code,
                severity=DiagnosticSeverity(item.severity.value),
                file_path=file_path,
                line_number=line,
                message=message,
                detail=detail,
            )
        )
    return rows


__all__ = ["code_diagnostics_for_form"]
