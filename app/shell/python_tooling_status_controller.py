"""Controller for shell Python tooling status context."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.python_tools.config import resolve_python_tooling_settings
from app.python_tools.vendor_runtime import initialize_python_tooling_runtime
from app.shell.python_tooling_status_copy import format_python_tooling_settings_copy


class PythonToolingStatusController:
    """Owns Python tooling runtime/config detection for shell UI copy."""

    def __init__(self, *, current_project_root: Callable[[], str | None]) -> None:
        self._current_project_root = current_project_root

    def current_status_context(self) -> tuple[bool, str, str | None, str | None]:
        runtime_status = initialize_python_tooling_runtime()
        project_root = self._current_project_root()
        if project_root is None:
            return runtime_status.is_available, "no_project", None, None

        settings = resolve_python_tooling_settings(
            project_root=project_root,
            file_path=str(Path(project_root) / "__cbcs_python_tooling_status__.py"),
        )
        if settings.pyproject_path is None:
            return runtime_status.is_available, "defaults", None, None
        if settings.config_error is not None:
            return runtime_status.is_available, "pyproject_error", str(settings.pyproject_path), settings.config_error
        return runtime_status.is_available, "pyproject", str(settings.pyproject_path), None

    def settings_dialog_copy(self) -> tuple[str, str, str, str]:
        runtime_status = initialize_python_tooling_runtime()
        _runtime_available, config_state, config_path, config_error = self.current_status_context()
        copy = format_python_tooling_settings_copy(
            runtime_available=runtime_status.is_available,
            runtime_message=runtime_status.message,
            vendor_root=str(runtime_status.vendor_root),
            config_state=config_state,
            config_path=config_path,
            config_error=config_error,
        )
        return copy.runtime_text, copy.runtime_details, copy.config_text, copy.config_details
