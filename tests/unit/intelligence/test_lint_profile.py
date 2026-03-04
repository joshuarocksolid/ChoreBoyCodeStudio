"""Unit tests for lint profile helpers."""

from __future__ import annotations

import pytest

from app.intelligence.lint_profile import (
    LINT_SEVERITY_ERROR,
    LINT_SEVERITY_INFO,
    parse_lint_rule_overrides,
    resolve_lint_rule_settings,
)

pytestmark = pytest.mark.unit


def test_parse_lint_rule_overrides_accepts_supported_codes_only() -> None:
    parsed = parse_lint_rule_overrides(
        {
            "linter": {
                "rule_overrides": {
                    "PY220": {"enabled": False, "severity": "info"},
                    "UNKNOWN": {"enabled": False, "severity": "error"},
                }
            }
        }
    )
    assert parsed == {"PY220": {"enabled": False, "severity": "info"}}


def test_parse_lint_rule_overrides_ignores_non_overridable_fields() -> None:
    parsed = parse_lint_rule_overrides(
        {
            "linter": {
                "rule_overrides": {
                    "PY100": {"enabled": False, "severity": "info"},
                }
            }
        }
    )
    assert parsed == {}


def test_resolve_lint_rule_settings_uses_defaults_without_overrides() -> None:
    enabled, severity = resolve_lint_rule_settings("PY200", overrides=None)
    assert enabled is True
    assert severity == LINT_SEVERITY_ERROR


def test_resolve_lint_rule_settings_applies_valid_overrides() -> None:
    enabled, severity = resolve_lint_rule_settings(
        "PY230",
        overrides={"PY230": {"enabled": False, "severity": "error"}},
    )
    assert enabled is False
    assert severity == LINT_SEVERITY_ERROR


def test_resolve_lint_rule_settings_respects_non_overridable_syntax_rule() -> None:
    enabled, severity = resolve_lint_rule_settings(
        "PY100",
        overrides={"PY100": {"enabled": False, "severity": LINT_SEVERITY_INFO}},
    )
    assert enabled is True
    assert severity == LINT_SEVERITY_ERROR
