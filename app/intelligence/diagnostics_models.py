"""Shared diagnostic datamodels for intelligence lint workflows."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


@dataclass(frozen=True)
class ImportDiagnostic:
    """Unresolved import diagnostic record."""

    file_path: str
    line_number: int
    message: str


@dataclass(frozen=True)
class ImportExplanation:
    """Structured explanation for an unresolved import."""

    module_name: str
    kind: str
    summary: str
    why_it_happened: str
    next_steps: list[str]
    evidence: dict[str, Any]


class DiagnosticSeverity(str, Enum):
    """Severity levels for editor diagnostics."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class CodeDiagnostic:
    """Structured diagnostic used by file linting workflows."""

    code: str
    severity: DiagnosticSeverity
    file_path: str
    line_number: int
    message: str
    col_start: int | None = None
    col_end: int | None = None
