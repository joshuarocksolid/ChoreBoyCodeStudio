"""Typed models for Python formatting and import-management tooling."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


PYTHON_TOOLING_CONFIG_SOURCE_DEFAULTS = "defaults"
PYTHON_TOOLING_CONFIG_SOURCE_PROJECT_PYPROJECT = "project_pyproject"

PYTHON_TOOLING_STATUS_UNCHANGED = "unchanged"
PYTHON_TOOLING_STATUS_FORMATTED = "formatted"
PYTHON_TOOLING_STATUS_IMPORTS_ORGANIZED = "imports_organized"
PYTHON_TOOLING_STATUS_SYNTAX_ERROR = "syntax_error"
PYTHON_TOOLING_STATUS_TOOL_UNAVAILABLE = "tool_unavailable"
PYTHON_TOOLING_STATUS_CONFIG_ERROR = "config_error"


@dataclass(frozen=True)
class PythonToolingSettings:
    """Resolved formatter/import settings for one project/file context."""

    project_root: Path
    file_path: Path
    pyproject_path: Path | None
    config_source: str
    config_error: str | None
    python_target_minor: int
    black_line_length: int
    black_target_versions: tuple[str, ...] = field(default_factory=tuple)
    black_string_normalization: bool = True
    black_magic_trailing_comma: bool = True
    black_preview: bool = False
    isort_profile: str = "black"
    isort_line_length: int = 88
    isort_src_paths: tuple[Path, ...] = field(default_factory=tuple)
    isort_known_first_party: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PythonTextTransformResult:
    """Result payload for formatter/import text transforms."""

    formatted_text: str
    changed: bool
    status: str
    settings: PythonToolingSettings
    error_message: str | None = None
