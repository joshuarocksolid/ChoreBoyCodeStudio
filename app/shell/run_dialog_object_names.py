"""Shared object-name constants for run-related shell dialogs."""

from __future__ import annotations

RUN_WITH_ARGUMENTS_DIALOG = "shell.runWithArgumentsDialog"
RUN_CONFIGURATIONS_DIALOG = "shell.runConfigurationsDialog"
RUN_ENV_OVERRIDES_DIALOG = "shell.runEnvOverridesDialog"
RUN_ENV_OVERRIDES_ROW_PREFIX = "shell.runEnvOverridesRow"

RUN_DIALOG_OBJECT_NAMES = (
    RUN_WITH_ARGUMENTS_DIALOG,
    RUN_CONFIGURATIONS_DIALOG,
    RUN_ENV_OVERRIDES_DIALOG,
)


def qss_escape_object_name(object_name: str) -> str:
    """Escape dots for Qt stylesheet object-name selectors."""
    return object_name.replace(".", "\\.")


def qss_dialog_selector(object_name: str) -> str:
    return f"QDialog#{qss_escape_object_name(object_name)}"


def qss_dialog_scope(object_names: tuple[str, ...]) -> str:
    """Comma-join dialog selectors for shared QSS rules."""
    return ",\n".join(qss_dialog_selector(name) for name in object_names)
