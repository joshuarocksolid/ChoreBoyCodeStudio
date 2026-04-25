from __future__ import annotations

from typing import Any, Mapping

from app.plugins.runtime_serializers import serialize_pytest_run_result
from app.run.pytest_runner_service import run_pytest_project, run_pytest_target


def handle_pytest_job(
    _provider_key: str,
    request: Mapping[str, Any],
    emit_event,
    is_cancelled,
) -> dict[str, Any]:
    _ = is_cancelled
    project_root = _require_string(request, "project_root")
    target_path = _optional_string(request, "target_path")
    timeout_seconds = int(request.get("timeout_seconds", 300))
    emit_event("job_started", {"project_root": project_root, "target_path": target_path})
    result = (
        run_pytest_target(project_root, target_path, timeout_seconds=timeout_seconds)
        if target_path
        else run_pytest_project(project_root, timeout_seconds=timeout_seconds)
    )
    emit_event(
        "job_finished",
        {
            "return_code": result.return_code,
            "failure_count": len(result.failures),
            "elapsed_ms": result.elapsed_ms,
        },
    )
    return serialize_pytest_run_result(result)


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
