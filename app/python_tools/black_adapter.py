"""Black-backed Python formatting adapter."""

from __future__ import annotations

from pathlib import Path

from app.python_tools.config import resolve_python_tooling_settings
from app.python_tools.models import (
    PYTHON_TOOLING_STATUS_CONFIG_ERROR,
    PYTHON_TOOLING_STATUS_FORMATTED,
    PYTHON_TOOLING_STATUS_SYNTAX_ERROR,
    PYTHON_TOOLING_STATUS_TOOL_UNAVAILABLE,
    PYTHON_TOOLING_STATUS_UNCHANGED,
    PythonTextTransformResult,
)
from app.python_tools.vendor_runtime import import_python_tooling_modules


def format_python_text(source_text: str, *, file_path: str, project_root: str) -> PythonTextTransformResult:
    """Format Python source text using vendored Black."""
    settings = resolve_python_tooling_settings(project_root=project_root, file_path=file_path)
    if settings.config_error is not None:
        return PythonTextTransformResult(
            formatted_text=source_text,
            changed=False,
            status=PYTHON_TOOLING_STATUS_CONFIG_ERROR,
            settings=settings,
            error_message=settings.config_error,
        )

    try:
        black, _isort, _tomli = import_python_tooling_modules()
    except Exception as exc:
        return PythonTextTransformResult(
            formatted_text=source_text,
            changed=False,
            status=PYTHON_TOOLING_STATUS_TOOL_UNAVAILABLE,
            settings=settings,
            error_message=str(exc),
        )

    try:
        mode = black.Mode(
            target_versions=_resolve_black_target_versions(black, settings.black_target_versions),
            line_length=settings.black_line_length,
            string_normalization=settings.black_string_normalization,
            magic_trailing_comma=settings.black_magic_trailing_comma,
            is_pyi=Path(file_path).suffix == ".pyi",
            preview=settings.black_preview,
        )
        formatted_text = black.format_file_contents(source_text, fast=False, mode=mode)
    except black.NothingChanged:
        return PythonTextTransformResult(
            formatted_text=source_text,
            changed=False,
            status=PYTHON_TOOLING_STATUS_UNCHANGED,
            settings=settings,
        )
    except black.InvalidInput as exc:
        return PythonTextTransformResult(
            formatted_text=source_text,
            changed=False,
            status=PYTHON_TOOLING_STATUS_SYNTAX_ERROR,
            settings=settings,
            error_message=str(exc),
        )

    return PythonTextTransformResult(
        formatted_text=formatted_text,
        changed=formatted_text != source_text,
        status=PYTHON_TOOLING_STATUS_FORMATTED,
        settings=settings,
    )


def _resolve_black_target_versions(black_module, target_versions: tuple[str, ...]) -> set[object]:
    resolved: set[object] = set()
    for version_name in target_versions:
        normalized = version_name.upper()
        if not normalized.startswith("PY"):
            continue
        target_version = getattr(black_module.TargetVersion, normalized, None)
        if target_version is not None:
            resolved.add(target_version)
    return resolved
