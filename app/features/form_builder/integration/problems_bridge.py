"""Form diagnostics to the shell Problems panel (CONTRACTS.md section 7.4)."""

from __future__ import annotations

import os
from typing import Callable, List, Sequence, Tuple

from app.qt.QtCore import QTimer

from app.features.form_builder.engine.diagnostics import DiagnosticsStore, FormDiagnostic, to_problem_detail
from app.intelligence.diagnostics_models import CodeDiagnostic, DiagnosticSeverity

Push = Callable[[str, List[CodeDiagnostic]], None]


def to_code_diagnostics(file_path: str, diagnostics: Sequence[FormDiagnostic]) -> List[CodeDiagnostic]:
    """One row per diagnostic, same order. FB9xx rows only when ``CBCS_FB_DEBUG=1``."""
    debug = os.environ.get("CBCS_FB_DEBUG") == "1"
    return [
        _row(file_path, diagnostic)
        for diagnostic in diagnostics
        if debug or not diagnostic.code.startswith("FB9")
    ]


def _row(file_path: str, diagnostic: FormDiagnostic) -> CodeDiagnostic:
    location = diagnostic.location
    return CodeDiagnostic(
        code=diagnostic.code,
        severity=DiagnosticSeverity(diagnostic.severity.value),
        file_path=file_path,
        line_number=location.line or 1,
        message=diagnostic.message,
        detail=to_problem_detail(diagnostic),
        source="Form",
        location_label=location.object_name or "",
    )


class ProblemsBridge:
    """Pushes a session's rows for one ``.ui`` path, at most once per event-loop turn.

    ``push`` is ``ProblemsController.apply_lint_diagnostics_result``. ``.ui``
    files are never linted, so the form owns that path's rows.
    """

    def __init__(self, file_path: str, store: DiagnosticsStore, push: Push) -> None:
        self._path = file_path
        self._store = store
        self._push = push
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._flush)
        self._unsubscribe = store.subscribe(self._schedule)
        self._timer.start()

    def set_path(self, file_path: str) -> None:
        self._path = file_path
        self._timer.start()

    def close(self) -> None:
        """Unsubscribe and clear this path's rows."""
        self._unsubscribe()
        self._timer.stop()
        self._push(self._path, [])

    def _schedule(self, _diagnostics: Tuple[FormDiagnostic, ...]) -> None:
        self._timer.start()

    def _flush(self) -> None:
        self._push(self._path, to_code_diagnostics(self._path, self._store.all()))


__all__ = ["ProblemsBridge", "to_code_diagnostics"]
