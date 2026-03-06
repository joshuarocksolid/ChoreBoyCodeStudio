"""Lint-rule profile contracts and helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.core import constants

LINT_SEVERITY_ERROR = "error"
LINT_SEVERITY_WARNING = "warning"
LINT_SEVERITY_INFO = "info"
LINT_SEVERITIES: frozenset[str] = frozenset({
    LINT_SEVERITY_ERROR,
    LINT_SEVERITY_WARNING,
    LINT_SEVERITY_INFO,
})


@dataclass(frozen=True)
class LintRuleDefinition:
    """Definition for one lint rule."""

    code: str
    title: str
    default_enabled: bool
    default_severity: str
    allow_disable: bool = True
    allow_severity_override: bool = True


LINT_RULE_DEFINITIONS: tuple[LintRuleDefinition, ...] = (
    LintRuleDefinition(
        code="PY100",
        title="Syntax error",
        default_enabled=True,
        default_severity=LINT_SEVERITY_ERROR,
        allow_disable=False,
        allow_severity_override=False,
    ),
    LintRuleDefinition(
        code="PY200",
        title="Unresolved import",
        default_enabled=True,
        default_severity=LINT_SEVERITY_ERROR,
    ),
    LintRuleDefinition(
        code="PY210",
        title="Duplicate definition",
        default_enabled=True,
        default_severity=LINT_SEVERITY_WARNING,
    ),
    LintRuleDefinition(
        code="PY220",
        title="Unused import",
        default_enabled=True,
        default_severity=LINT_SEVERITY_WARNING,
    ),
    LintRuleDefinition(
        code="PY221",
        title="Duplicate import",
        default_enabled=True,
        default_severity=LINT_SEVERITY_WARNING,
    ),
    LintRuleDefinition(
        code="PY230",
        title="Unreachable statement",
        default_enabled=True,
        default_severity=LINT_SEVERITY_INFO,
    ),
    LintRuleDefinition(
        code="PY301",
        title="Undefined name (Pyflakes)",
        default_enabled=True,
        default_severity=LINT_SEVERITY_ERROR,
    ),
    LintRuleDefinition(
        code="PY302",
        title="Undefined local (Pyflakes)",
        default_enabled=True,
        default_severity=LINT_SEVERITY_ERROR,
    ),
    LintRuleDefinition(
        code="PY303",
        title="Redefined while unused (Pyflakes)",
        default_enabled=True,
        default_severity=LINT_SEVERITY_WARNING,
    ),
    LintRuleDefinition(
        code="PY304",
        title="Import shadowed by loop variable (Pyflakes)",
        default_enabled=True,
        default_severity=LINT_SEVERITY_WARNING,
    ),
    LintRuleDefinition(
        code="PY305",
        title="Import * used (Pyflakes)",
        default_enabled=True,
        default_severity=LINT_SEVERITY_WARNING,
    ),
    LintRuleDefinition(
        code="PY399",
        title="Other Pyflakes diagnostic",
        default_enabled=True,
        default_severity=LINT_SEVERITY_WARNING,
    ),
)

_DEFINITIONS_BY_CODE: dict[str, LintRuleDefinition] = {
    definition.code: definition for definition in LINT_RULE_DEFINITIONS
}


def lint_rule_definitions() -> tuple[LintRuleDefinition, ...]:
    """Return all lint rule definitions in deterministic order."""
    return LINT_RULE_DEFINITIONS


def parse_lint_rule_overrides(settings_payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Parse persisted lint rule overrides."""
    section = settings_payload.get(constants.UI_LINTER_SETTINGS_KEY, {})
    if not isinstance(section, dict):
        return {}
    raw_overrides = section.get(constants.UI_LINTER_RULE_OVERRIDES_KEY, {})
    if not isinstance(raw_overrides, dict):
        return {}
    parsed: dict[str, dict[str, Any]] = {}
    for code, override in raw_overrides.items():
        if code not in _DEFINITIONS_BY_CODE or not isinstance(override, dict):
            continue
        normalized = _normalize_rule_override(code, override)
        if normalized:
            parsed[code] = normalized
    return parsed


def _normalize_rule_override(code: str, override: Mapping[str, Any]) -> dict[str, Any]:
    definition = _DEFINITIONS_BY_CODE[code]
    normalized: dict[str, Any] = {}
    enabled_value = override.get("enabled")
    if isinstance(enabled_value, bool) and definition.allow_disable:
        normalized["enabled"] = enabled_value
    severity_value = override.get("severity")
    if (
        isinstance(severity_value, str)
        and severity_value in LINT_SEVERITIES
        and definition.allow_severity_override
    ):
        normalized["severity"] = severity_value
    return normalized


def resolve_lint_rule_settings(
    code: str,
    overrides: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[bool, str]:
    """Resolve enabled/severity after applying overrides to defaults."""
    definition = _DEFINITIONS_BY_CODE.get(code)
    if definition is None:
        return (True, LINT_SEVERITY_WARNING)
    enabled = definition.default_enabled
    severity = definition.default_severity
    if overrides is None:
        return (enabled, severity)
    override = overrides.get(code)
    if not isinstance(override, Mapping):
        return (enabled, severity)
    if definition.allow_disable and isinstance(override.get("enabled"), bool):
        enabled = bool(override["enabled"])
    if (
        definition.allow_severity_override
        and isinstance(override.get("severity"), str)
        and override["severity"] in LINT_SEVERITIES
    ):
        severity = str(override["severity"])
    return (enabled, severity)
