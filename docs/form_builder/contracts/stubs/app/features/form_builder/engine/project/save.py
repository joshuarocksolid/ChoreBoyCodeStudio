"""Save-side generation (CONTRACTS.md section 9.6 step 3). [M1.4]"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from app.features.form_builder.engine.codegen.api_types import CodegenOptions
from app.features.form_builder.engine.diagnostics import FormDiagnostic
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.document import UiDocument


@dataclass(frozen=True)
class WriteResult:
    """``files``: paths created or replaced. ``text_written`` is false when generation was refused."""

    diagnostics: Tuple[FormDiagnostic, ...]
    files: Tuple[str, ...]
    text_written: bool


def opening_diagnostics(scope: FormScope, ui_bytes: bytes, fs: object) -> Tuple[FormDiagnostic, ...]:
    """FB505 when the generated module is out of date with ``ui_bytes``."""
    ...


def write_generated(
    scope: FormScope,
    doc: UiDocument,
    ui_bytes: bytes,
    fs: object,
    *,
    options: CodegenOptions = ...,
) -> WriteResult:
    """Generate, back up a hand edit, and atomically write ``ui_*.py``.

    Also writes ``*_rc.py`` for a changed ``.qrc``, creates ``forms/__init__.py``
    when it is missing, and creates the window class once. A codegen failure
    returns diagnostics and leaves existing files byte-identical.
    """
    ...
