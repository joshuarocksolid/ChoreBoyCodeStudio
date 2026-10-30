"""Form diagnostics as ordinary Problems rows (CONTRACTS.md section 7.4)."""

from __future__ import annotations

import json
import logging
import os
from typing import List, Optional, Sequence, Tuple

from app.features.form_builder.engine import diagnostic_codes
from app.features.form_builder.engine.diagnostics import FormDiagnostic, to_problem_detail
from app.features.form_builder.integration.problem_fixes import FixContext, FixRegistry, default_registry
from app.intelligence.diagnostics_models import CodeDiagnostic, DiagnosticSeverity


logger = logging.getLogger(__name__)

# Every module in engine/diagnostic_codes declares its codes, whether or not
# the code that emits them has been imported yet.
diagnostic_codes.discover()


def fixes_for(
    diagnostic: FormDiagnostic,
    registry: Optional[FixRegistry] = None,
) -> Tuple[Tuple[str, str], ...]:
    """``(fix id, button text)`` for each fix registered for the diagnostic's FB code."""
    found = []
    for fix in (registry or default_registry()).for_diagnostic(diagnostic):
        try:
            found.append((fix.fix_id, fix.title_for(diagnostic)))
        except Exception:
            logger.exception("fix %s could not make its title", fix.fix_id)
    return tuple(found)


def run_fix(
    diagnostic: FormDiagnostic,
    fix_id: str,
    context: FixContext,
    registry: Optional[FixRegistry] = None,
) -> bool:
    """Run one fix. False when no such fix is offered for this diagnostic or it raised."""
    for fix in (registry or default_registry()).for_diagnostic(diagnostic):
        if fix.fix_id != fix_id:
            continue
        try:
            fix.run(context)
        except Exception:
            logger.exception("fix %s failed", fix.fix_id)
            return False
        return True
    return False


def code_diagnostics_for_form(
    file_path: str,
    diagnostics: Sequence[FormDiagnostic],
    registry: Optional[FixRegistry] = None,
) -> List[CodeDiagnostic]:
    """Map form diagnostics onto the shell row. FB9xx stays hidden unless debug is on.

    A diagnostic with registered fixes carries them in ``detail["fixes"]``
    as JSON ``[[fix id, button text], ...]``; the shell's Problems panel lists
    them on the row and calls ``FormSurface.run_problem_fix`` with the choice.
    """
    show_internal = os.environ.get("CBCS_FB_DEBUG") == "1"
    rows: List[CodeDiagnostic] = []
    for item in diagnostics:
        if item.code.startswith("FB9") and not show_internal:
            continue
        location = item.location
        obj = location.object_name or ""
        line = location.line if location.line > 0 else 1
        detail = dict(to_problem_detail(item))
        code_path = location.code_path
        if obj:
            detail["location_label"] = obj
        elif code_path:
            detail["location_label"] = "%s:%d" % (os.path.basename(code_path), max(1, location.code_line))
        else:
            detail["location_label"] = "Ln %d" % line
        detail["source_label"] = "Form"
        fixes = fixes_for(item, registry)
        if fixes:
            detail["fixes"] = json.dumps([list(pair) for pair in fixes], ensure_ascii=True)
        message = item.message
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


__all__ = ["code_diagnostics_for_form", "fixes_for", "run_fix"]
