"""Controller for shell Python tooling status context."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.python_tools.config import resolve_python_tooling_settings
from app.python_tools.vendor_runtime import initialize_python_tooling_runtime
from app.shell.python_tooling_status_copy import (
    PythonToolingRuntimeContext,
    PythonToolingSettingsCopy,
    format_python_tooling_settings_copy,
)


class PythonToolingStatusController:
    """Owns Python tooling runtime/config detection for shell UI copy."""

    def __init__(self, *, current_project_root: Callable[[], str | None]) -> None:
        self._current_project_root = current_project_root

    def current_status_context(self) -> PythonToolingRuntimeContext:
        runtime_status = initialize_python_tooling_runtime()
        project_root = self._current_project_root()
        if project_root is None:
            return PythonToolingRuntimeContext(
                runtime_available=runtime_status.is_available,
                config_state="no_project",
                config_path=None,
                config_error=None,
            )

        settings = resolve_python_tooling_settings(
            project_root=project_root,
            file_path=str(Path(project_root) / "__cbcs_python_tooling_status__.py"),
        )
        if settings.pyproject_path is None:
            return PythonToolingRuntimeContext(
                runtime_available=runtime_status.is_available,
                config_state="defaults",
                config_path=None,
                config_error=None,
            )
        if settings.config_error is not None:
            return PythonToolingRuntimeContext(
                runtime_available=runtime_status.is_available,
                config_state="pyproject_error",
                config_path=str(settings.pyproject_path),
                config_error=settings.config_error,
            )
        return PythonToolingRuntimeContext(
            runtime_available=runtime_status.is_available,
            config_state="pyproject",
            config_path=str(settings.pyproject_path),
            config_error=None,
        )

    def settings_dialog_copy(self) -> PythonToolingSettingsCopy:
        runtime_status = initialize_python_tooling_runtime()
        context = self.current_status_context()
        return format_python_tooling_settings_copy(
            runtime_available=runtime_status.is_available,
            runtime_message=runtime_status.message,
            vendor_root=str(runtime_status.vendor_root),
            config_state=context.config_state,
            config_path=context.config_path,
            config_error=context.config_error,
        )
