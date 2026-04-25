"""Unit tests for centralized Python tooling UI copy."""

from __future__ import annotations

import pytest

from app.shell.python_tooling_status_copy import (
    UNKNOWN_SETTINGS_COPY,
    format_python_tooling_settings_copy,
    format_python_tooling_status_copy,
)

pytestmark = pytest.mark.unit


def test_unknown_settings_copy_matches_settings_dialog_defaults() -> None:
    assert UNKNOWN_SETTINGS_COPY.runtime_text == "Black/isort/tomli: unknown"
    assert UNKNOWN_SETTINGS_COPY.config_text == "Project pyproject.toml: no project"


def test_format_python_tooling_settings_copy_handles_detected_pyproject() -> None:
    copy = format_python_tooling_settings_copy(
        runtime_available=True,
        runtime_message="Python tooling runtime ready.",
        vendor_root="/workspace/vendor",
        config_state="pyproject",
        config_path="/tmp/project/pyproject.toml",
    )

    assert copy.runtime_text == "Black/isort/tomli: available"
    assert "Vendor root: /workspace/vendor" in copy.runtime_details
    assert copy.config_text == "Project pyproject.toml: detected"
    assert copy.config_details == "Path: /tmp/project/pyproject.toml"


def test_format_python_tooling_status_copy_marks_pyproject_parse_error_as_warning() -> None:
    copy = format_python_tooling_status_copy(
        runtime_available=True,
        config_state="pyproject_error",
        config_path="/tmp/project/pyproject.toml",
        config_error="bad TOML",
    )

    assert copy.severity == "warning"
    assert copy.text == "Python: tools ready | pyproject error"
    assert "bad TOML" in copy.details
