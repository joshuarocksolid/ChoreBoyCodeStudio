"""Single source of truth for Python tooling UI status copy."""

from __future__ import annotations

from dataclasses import dataclass

PYTHON_TOOLING_CONFIG_NO_PROJECT = "no_project"
PYTHON_TOOLING_CONFIG_DEFAULTS = "defaults"
PYTHON_TOOLING_CONFIG_PYPROJECT = "pyproject"
PYTHON_TOOLING_CONFIG_PYPROJECT_ERROR = "pyproject_error"


@dataclass(frozen=True)
class PythonToolingStatusCopy:
    severity: str
    text: str
    details: str


@dataclass(frozen=True)
class PythonToolingSettingsCopy:
    runtime_text: str
    runtime_details: str
    config_text: str
    config_details: str


UNKNOWN_SETTINGS_COPY = PythonToolingSettingsCopy(
    runtime_text="Black/isort/tomli: unknown",
    runtime_details="",
    config_text="Project pyproject.toml: no project",
    config_details="",
)


def format_python_tooling_status_copy(
    *,
    runtime_available: bool,
    config_state: str,
    config_path: str | None = None,
    config_error: str | None = None,
) -> PythonToolingStatusCopy:
    """Map Python tooling/runtime metadata into concise status-bar copy."""
    if not runtime_available:
        return PythonToolingStatusCopy(
            severity="warning",
            text="Python: tools unavailable",
            details="Vendored Black/isort/tomli tooling is not ready.",
        )

    state_to_copy = {
        PYTHON_TOOLING_CONFIG_NO_PROJECT: (
            "Python: tools ready | no project",
            "Open a project to detect project-local pyproject.toml.",
        ),
        PYTHON_TOOLING_CONFIG_DEFAULTS: (
            "Python: tools ready | defaults",
            "No project-local pyproject.toml detected.",
        ),
        PYTHON_TOOLING_CONFIG_PYPROJECT: (
            "Python: tools ready | pyproject",
            "Project-local pyproject.toml detected.",
        ),
        PYTHON_TOOLING_CONFIG_PYPROJECT_ERROR: (
            "Python: tools ready | pyproject error",
            "Project-local pyproject.toml could not be parsed.",
        ),
    }
    text, details = state_to_copy.get(config_state, state_to_copy[PYTHON_TOOLING_CONFIG_DEFAULTS])
    if config_path:
        details = f"{details} Path: {config_path}."
    if config_error:
        details = f"{details} Error: {config_error}"
    severity = "warning" if config_state == PYTHON_TOOLING_CONFIG_PYPROJECT_ERROR else "ok"
    return PythonToolingStatusCopy(severity=severity, text=text, details=details)


def format_python_tooling_settings_copy(
    *,
    runtime_available: bool,
    runtime_message: str,
    vendor_root: str,
    config_state: str,
    config_path: str | None = None,
    config_error: str | None = None,
) -> PythonToolingSettingsCopy:
    runtime_text = "Black/isort/tomli: available" if runtime_available else "Black/isort/tomli: unavailable"
    runtime_details = f"{runtime_message} Vendor root: {vendor_root}"
    if config_state == PYTHON_TOOLING_CONFIG_NO_PROJECT:
        config_text = "Project pyproject.toml: no project"
        config_details = "Open a project to detect project-local formatter/import settings."
    elif config_state == PYTHON_TOOLING_CONFIG_DEFAULTS:
        config_text = "Project pyproject.toml: not detected"
        config_details = "No project-local pyproject.toml was found for Python tooling."
    elif config_state == PYTHON_TOOLING_CONFIG_PYPROJECT_ERROR:
        config_text = "Project pyproject.toml: parse error"
        config_details = f"Path: {config_path}. Error: {config_error}"
    else:
        config_text = "Project pyproject.toml: detected"
        config_details = f"Path: {config_path}"
    return PythonToolingSettingsCopy(
        runtime_text=runtime_text,
        runtime_details=runtime_details,
        config_text=config_text,
        config_details=config_details,
    )
