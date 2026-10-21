"""FB diagnostics -> CBCS Problems panel (CONTRACTS.md section 7.4). [M2.3]"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Sequence, Tuple

from app.features.form_builder.engine.diagnostics import FormDiagnostic

if TYPE_CHECKING:  # pragma: no cover
    from app.intelligence.diagnostics_models import CodeDiagnostic


def to_code_diagnostics(file_path: str, diagnostics: Sequence[FormDiagnostic]) -> "Tuple[CodeDiagnostic, ...]":
    """One CodeDiagnostic per FormDiagnostic, same order:

    ``code`` = FB code; ``severity`` = same-valued DiagnosticSeverity;
    ``file_path`` = the ``.ui`` path; ``line_number`` = ``location.line`` or 1;
    ``message`` = ``"<object_name>: <message>"`` when an object name is known,
    else ``message``; ``detail`` = ``engine.diagnostics.to_problem_detail``.
    FB9xx codes are dropped unless ``CBCS_FB_DEBUG=1``.
    """
    ...


class ProblemsBridge:
    """Subscribes to a session's DiagnosticsStore and pushes rows through the
    shell's ``ProblemsController.apply_lint_diagnostics_result(path, rows)``
    (``.ui`` files are never linted, so the form owns that path's slot). Pushes
    are coalesced to one per event-loop turn. On tab close it pushes an empty
    list for the path. Problems double-click lands in ``TabSurface.reveal``."""

    def __init__(self, file_path: str, push: Callable[[str, "Tuple[CodeDiagnostic, ...]"], None]) -> None:
        ...

    def on_diagnostics(self, diagnostics: Tuple[FormDiagnostic, ...]) -> None:
        ...

    def close(self) -> None:
        ...
