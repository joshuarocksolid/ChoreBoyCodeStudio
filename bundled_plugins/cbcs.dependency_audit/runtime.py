from __future__ import annotations

from typing import Any, Mapping

from app.packaging.dependency_audit import run_dependency_audit
from app.plugins.runtime_serializers import serialize_dependency_audit_report


def handle_dependency_audit_job(
    _provider_key: str,
    request: Mapping[str, Any],
    emit_event,
    is_cancelled,
) -> dict[str, Any]:
    _ = is_cancelled
    project_root = _require_string(request, "project_root")
    emit_event("job_started", {"project_root": project_root})
    report = run_dependency_audit(
        project_root=project_root,
        known_runtime_modules=_parse_known_runtime_modules(request.get("known_runtime_modules")),
        allow_runtime_import_probe=bool(request.get("allow_runtime_import_probe", True)),
    )
    emit_event(
        "job_finished",
        {
            "highest_severity": report.highest_severity,
            "is_ready": report.is_ready,
            "issue_count": len(report.issues),
        },
    )
    return serialize_dependency_audit_report(report)


def _parse_known_runtime_modules(raw_value: Any) -> frozenset[str] | None:
    if not isinstance(raw_value, list):
        return None
    return frozenset(item for item in raw_value if isinstance(item, str) and item.strip())


def _require_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value
