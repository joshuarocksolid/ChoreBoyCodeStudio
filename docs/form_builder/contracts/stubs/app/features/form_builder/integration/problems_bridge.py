"""FB diagnostics -> CBCS Problems panel (CONTRACTS.md section 7.4). [M2.3]"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, List, Sequence

from app.features.form_builder.engine.diagnostics import DiagnosticsStore, FormDiagnostic

if TYPE_CHECKING:  # pragma: no cover
    from app.intelligence.diagnostics_models import CodeDiagnostic

Push = Callable[[str, "List[CodeDiagnostic]"], None]


def to_code_diagnostics(file_path: str, diagnostics: Sequence[FormDiagnostic]) -> "List[CodeDiagnostic]":
    """One CodeDiagnostic per FormDiagnostic, same order:

    ``code`` = FB code; ``severity`` = same-valued DiagnosticSeverity;
    ``file_path`` = the ``.ui`` path; ``line_number`` = ``location.line`` or 1;
    ``message`` = the plain message, no object-name prefix; ``source`` = ``"Form"``;
    ``location_label`` = ``location.object_name`` or empty;
    ``detail`` = ``engine.diagnostics.to_problem_detail``.
    FB9xx codes are dropped unless ``CBCS_FB_DEBUG=1``.
    """
    ...


class ProblemsBridge:
    """Subscribes to a session's DiagnosticsStore and pushes the store's full
    ``all()`` through ``push``, which is the shell's
    ``ProblemsController.apply_lint_diagnostics_result(path, rows)`` (``.ui``
    files are never linted, so the form owns that path's slot). Pushes are
    coalesced to one per event-loop turn. Problems clicks land in
    ``TabSurface.reveal``."""

    def __init__(self, file_path: str, store: DiagnosticsStore, push: Push) -> None:
        ...

    def set_path(self, file_path: str) -> None:
        """Rename or move. The next push uses ``file_path``."""
        ...

    def close(self) -> None:
        """Unsubscribe and push an empty list for the path."""
        ...
