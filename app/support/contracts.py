"""Support-layer DTOs and resolver protocols (downward-facing seams)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class UnresolvedImportDiagnostic:
    """Unresolved import record passed into runtime issue builders."""

    file_path: str
    line_number: int
    message: str


@dataclass(frozen=True)
class ImportExplanationSnapshot:
    """Structured explanation for one unresolved import."""

    module_name: str
    kind: str
    summary: str
    why_it_happened: str
    next_steps: list[str]
    evidence: dict[str, Any]


ImportExplanationResolver = Callable[
    [str, str, Optional[frozenset[str]], bool],
    ImportExplanationSnapshot,
]
"""Resolve one import: (project_root, module_name, known_runtime_modules, allow_probe)."""


def runtime_severity_rank(severity: str) -> int:
    """Return sort rank for runtime issue severities (higher is more severe)."""
    return _RUNTIME_SEVERITY_ORDER.get(severity, 0)


_RUNTIME_SEVERITY_ORDER = {
    "clear": 0,
    "advisory": 1,
    "degraded": 2,
    "blocking": 3,
}
