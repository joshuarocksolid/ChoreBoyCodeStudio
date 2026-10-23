"""Save steps after the ``.ui`` bytes are on disk (CONTRACTS.md section 9.6).

The shell writes the file and then ``mark_saved``. Generation runs here.
A codegen failure is a notice and diagnostics. It does not undo the save.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional, Tuple

from app.features.form_builder.engine.diagnostic_codes import fb5xx as _fb5xx
from app.features.form_builder.engine.diagnostics import (
    CODES,
    DiagnosticLocation,
    FormDiagnostic,
    Severity,
)
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.project.fs import OsFileSystem
from app.features.form_builder.engine.project.save import write_generated
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui
from app.features.form_builder.engine.ui4.writer import write_ui

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SaveNotice:
    """Toolbar text after a save. ``error`` uses the error color. ``files`` lists
    the paths generation created or replaced."""

    kind: str
    text: str
    error: bool
    diagnostics: Tuple[FormDiagnostic, ...] = ()
    files: Tuple[str, ...] = ()


def finish_save(
    scope: Optional[FormScope],
    document: UiDocument,
    saved_text: str,
    fs: Optional[OsFileSystem] = None,
) -> SaveNotice:
    """Step 3. ``saved_text`` is the exact text step 1 wrote."""
    if scope is None or not scope.generates or not scope.generated_path:
        return SaveNotice("saved", "Saved", False)
    ui_name = os.path.basename(scope.ui_path)
    generated_name = os.path.basename(scope.generated_path)
    if not _parses(saved_text):
        return SaveNotice(
            "failed",
            "Saved %s · %s not written" % (ui_name, generated_name),
            True,
        )
    files = fs if fs is not None else OsFileSystem()
    ui_bytes = saved_text.encode("utf-8")
    try:
        result = write_generated(scope, document, ui_bytes, files)
    except Exception:
        _LOGGER.exception("could not write %s", generated_name)
        info = CODES.get("FB509")
        severity = info.severity if info is not None else Severity.ERROR
        diagnostic = FormDiagnostic(
            code="FB509",
            severity=severity,
            message="could not write %s." % generated_name,
            location=DiagnosticLocation(),
            source="codegen",
        )
        return SaveNotice(
            "failed",
            "Saved %s · %s not written" % (ui_name, generated_name),
            True,
            (diagnostic,),
        )
    if result.text_written:
        return SaveNotice(
            "generated",
            "Saved · %s updated" % generated_name,
            False,
            result.diagnostics,
            result.files,
        )
    return SaveNotice(
        "failed",
        "Saved %s · %s not written" % (ui_name, generated_name),
        True,
        result.diagnostics,
    )


def pipeline_bytes(document: UiDocument) -> str:
    """The text step 1 would write from the in-memory document."""
    return write_ui(document).text


def _parses(text: str) -> bool:
    try:
        read_ui(text, allocator=IdAllocator())
    except UiReadError:
        return False
    return True


__all__ = ["SaveNotice", "finish_save", "pipeline_bytes"]
