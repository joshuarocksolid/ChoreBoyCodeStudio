"""Code generation entry points (CONTRACTS.md section 9).

Inputs are a document and options; outputs are text plus diagnostics. The
generator never imports user code, never reads the clock, and never runs
``uic``/``rcc`` (those are test oracles only). Output is Python 3.9-parseable
(``ast.parse(text, feature_version=(3, 9))``) and imports PySide6 directly.
"""

from __future__ import annotations

import hashlib
import os
from typing import Optional

from app.features.form_builder.engine.codegen.api_types import (
    CODEGEN_VERSION,
    CodegenOptions,
    CodegenResult,
    GeneratedHeader,
)
from app.features.form_builder.engine.codegen.emit import emit_module
from app.features.form_builder.engine.codegen.header import (
    is_hand_edited,
    is_stale,
    read_header,
    render_header,
)
from app.features.form_builder.engine.codegen.names import ui_basename_ok
from app.features.form_builder.engine.diagnostic_codes import fb5xx as _fb5xx
from app.features.form_builder.engine.diagnostics import (
    CODES,
    DiagnosticLocation,
    FormDiagnostic,
    Severity,
)
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.document import UiDocument

del _fb5xx

__all__ = (
    "CODEGEN_VERSION",
    "CodegenOptions",
    "CodegenResult",
    "GeneratedHeader",
    "generate_form_module",
    "is_hand_edited",
    "is_stale",
    "read_header",
    "render_header",
)


def _form_diagnostic(code: str, message: str) -> FormDiagnostic:
    info = CODES.get(code)
    severity = info.severity if info is not None else Severity.ERROR
    return FormDiagnostic(
        code=code,
        severity=severity,
        message=message,
        location=DiagnosticLocation(),
        source="codegen",
    )


def generate_form_module(
    doc: UiDocument,
    *,
    scope: FormScope,
    source_bytes: Optional[bytes],
    options: CodegenOptions = CodegenOptions(),
) -> CodegenResult:
    """Generate ``ui_<name>.py`` for a project or adopted form.

    ``source_bytes`` is the exact ``.ui`` bytes just written, or None for a
    preview that omits ``cbcs-source-sha256``. External forms return text None
    with FB506. A stem that is not a Python module name returns text None with
    FB507. An unusable object name returns text None with FB502.
    """
    if not scope.generates:
        return CodegenResult(
            text=None,
            diagnostics=(
                _form_diagnostic(
                    "FB506",
                    "This form is outside the project, so no Python file is written.",
                ),
            ),
            attribute_names=(),
            resource_modules=(),
            uses_freecadgui=False,
            header=None,
        )
    basename = os.path.basename(scope.ui_path)
    stem = basename[:-3] if basename.endswith(".ui") else os.path.splitext(basename)[0]
    if not ui_basename_ok(basename):
        return CodegenResult(
            text=None,
            diagnostics=(
                _form_diagnostic(
                    "FB507",
                    'The file name "%s" can\'t be a Python module.' % basename,
                ),
            ),
            attribute_names=(),
            resource_modules=(),
            uses_freecadgui=False,
            header=None,
        )
    pieces = emit_module(doc, scope, options)
    if pieces.refused:
        return CodegenResult(
            text=None,
            diagnostics=pieces.diagnostics,
            attribute_names=(),
            resource_modules=(),
            uses_freecadgui=False,
            header=None,
        )
    source_hash = None if source_bytes is None else hashlib.sha256(source_bytes).hexdigest()
    body_hash = hashlib.sha256(pieces.body.encode("utf-8")).hexdigest()
    ui_name = basename
    if scope.window_path:
        window_name = os.path.basename(scope.window_path)
    else:
        window_name = stem + "_window.py"
    if "\n" in window_name or "\r" in window_name:
        return CodegenResult(
            text=None,
            diagnostics=(
                _form_diagnostic(
                    "FB507",
                    'The file name "%s" can\'t be a Python module.' % window_name,
                ),
            ),
            attribute_names=(),
            resource_modules=(),
            uses_freecadgui=False,
            header=None,
        )
    header_text = render_header(
        ui_file_name=ui_name,
        window_file_name=window_name,
        has_logic=pieces.has_logic,
        source_sha256=source_hash,
        body_sha256=body_hash,
    )
    text = header_text + pieces.body
    if not text.endswith("\n"):
        text += "\n"
    return CodegenResult(
        text=text,
        diagnostics=pieces.diagnostics,
        attribute_names=pieces.attribute_names,
        resource_modules=pieces.resource_modules,
        uses_freecadgui=pieces.uses_freecadgui,
        header=GeneratedHeader(
            codegen_version=CODEGEN_VERSION,
            source_sha256=source_hash,
            body_sha256=body_hash,
        ),
    )
