from __future__ import annotations

from typing import Any, Mapping

from app.core.models import CapabilityCheckResult, CapabilityProbeReport
from app.intelligence.diagnostics_service import ImportDiagnostic
from app.plugins.runtime_serializers import serialize_runtime_issue_result
from app.support.diagnostics import DiagnosticItem, ProjectHealthReport
from app.support.runtime_explainer import (
    build_import_issue_report,
    build_project_health_issue_report,
    build_startup_issue_report,
    explain_runtime_message,
)


def handle_runtime_query(_provider_key: str, request: Mapping[str, Any]) -> dict[str, Any] | list[dict[str, Any]]:
    mode = _optional_string(request, "mode") or "message"
    if mode == "startup":
        result = build_startup_issue_report(_parse_capability_probe_report(request.get("report")))
    elif mode == "project":
        result = build_project_health_issue_report(_parse_project_health_report(request.get("report")))
    elif mode == "imports":
        result = build_import_issue_report(
            _require_string(request, "project_root"),
            _parse_import_diagnostics(request.get("diagnostics")),
            allow_runtime_import_probe=bool(request.get("allow_runtime_import_probe", False)),
        )
    else:
        result = explain_runtime_message(_require_string(request, "message_text"))
    return serialize_runtime_issue_result(result)


def _parse_capability_probe_report(raw_value: Any) -> CapabilityProbeReport:
    checks_payload = raw_value.get("checks", []) if isinstance(raw_value, dict) else []
    checks: list[CapabilityCheckResult] = []
    for item in checks_payload:
        if not isinstance(item, dict):
            continue
        check_id = item.get("check_id")
        message = item.get("message")
        if not isinstance(check_id, str) or not isinstance(message, str):
            continue
        details = item.get("details", {})
        checks.append(
            CapabilityCheckResult(
                check_id=check_id,
                is_available=bool(item.get("is_available", False)),
                message=message,
                details=dict(details) if isinstance(details, dict) else {},
            )
        )
    return CapabilityProbeReport(checks=checks)


def _parse_project_health_report(raw_value: Any) -> ProjectHealthReport:
    if not isinstance(raw_value, dict):
        return ProjectHealthReport(project_root="", checks=[])
    checks_payload = raw_value.get("checks", [])
    checks: list[DiagnosticItem] = []
    for item in checks_payload:
        if not isinstance(item, dict):
            continue
        check_id = item.get("check_id")
        message = item.get("message")
        if not isinstance(check_id, str) or not isinstance(message, str):
            continue
        details = item.get("details", {})
        checks.append(
            DiagnosticItem(
                check_id=check_id,
                is_ok=bool(item.get("is_ok", False)),
                message=message,
                details=dict(details) if isinstance(details, dict) else {},
            )
        )
    return ProjectHealthReport(
        project_root=_optional_string(raw_value, "project_root") or "",
        checks=checks,
    )


def _parse_import_diagnostics(raw_value: Any) -> list[ImportDiagnostic]:
    if not isinstance(raw_value, list):
        return []
    diagnostics: list[ImportDiagnostic] = []
    for item in raw_value:
        if not isinstance(item, dict):
            continue
        file_path = item.get("file_path")
        line_number = item.get("line_number")
        message = item.get("message")
        if not isinstance(file_path, str) or not isinstance(line_number, int) or not isinstance(message, str):
            continue
        diagnostics.append(
            ImportDiagnostic(
                file_path=file_path,
                line_number=line_number,
                message=message,
            )
        )
    return diagnostics


def _require_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _optional_string(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return None
