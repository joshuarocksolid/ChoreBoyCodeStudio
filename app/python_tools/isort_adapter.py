"""isort-backed Python import organization adapter."""

from __future__ import annotations

from pathlib import Path

from app.python_tools.config import resolve_python_tooling_settings
from app.python_tools.models import (
    PYTHON_TOOLING_STATUS_CONFIG_ERROR,
    PYTHON_TOOLING_STATUS_IMPORTS_ORGANIZED,
    PYTHON_TOOLING_STATUS_SYNTAX_ERROR,
    PYTHON_TOOLING_STATUS_TOOL_UNAVAILABLE,
    PYTHON_TOOLING_STATUS_UNCHANGED,
    PythonTextTransformResult,
)
from app.python_tools.vendor_runtime import import_python_tooling_modules


def organize_imports_text(source_text: str, *, file_path: str, project_root: str) -> PythonTextTransformResult:
    """Organize Python imports using vendored isort."""
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
        _black, isort, _tomli = import_python_tooling_modules()
    except Exception as exc:
        return PythonTextTransformResult(
            formatted_text=source_text,
            changed=False,
            status=PYTHON_TOOLING_STATUS_TOOL_UNAVAILABLE,
            settings=settings,
            error_message=str(exc),
        )

    config = isort.Config(
        profile=settings.isort_profile,
        line_length=settings.isort_line_length,
        py_version=str(settings.python_target_minor),
        src_paths=settings.isort_src_paths,
        known_first_party=settings.isort_known_first_party,
        atomic=True,
    )
    try:
        formatted_text = isort.api.sort_code_string(
            source_text,
            config=config,
            file_path=Path(file_path),
        )
    except SyntaxError as exc:
        return PythonTextTransformResult(
            formatted_text=source_text,
            changed=False,
            status=PYTHON_TOOLING_STATUS_SYNTAX_ERROR,
            settings=settings,
            error_message=str(exc),
        )
    except Exception as exc:
        if "syntax error" in str(exc).lower():
            return PythonTextTransformResult(
                formatted_text=source_text,
                changed=False,
                status=PYTHON_TOOLING_STATUS_SYNTAX_ERROR,
                settings=settings,
                error_message=str(exc),
            )
        return PythonTextTransformResult(
            formatted_text=source_text,
            changed=False,
            status=PYTHON_TOOLING_STATUS_TOOL_UNAVAILABLE,
            settings=settings,
            error_message=str(exc),
        )
    if formatted_text == source_text:
        return PythonTextTransformResult(
            formatted_text=source_text,
            changed=False,
            status=PYTHON_TOOLING_STATUS_UNCHANGED,
            settings=settings,
        )
    return PythonTextTransformResult(
        formatted_text=formatted_text,
        changed=True,
        status=PYTHON_TOOLING_STATUS_IMPORTS_ORGANIZED,
        settings=settings,
    )
