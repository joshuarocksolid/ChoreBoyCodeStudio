from __future__ import annotations

from typing import Any, Mapping

from app.bootstrap.capability_probe import run_startup_capability_probe
from app.plugins.runtime_serializers import serialize_capability_probe_report


def handle_freecad_helper_job(
    _provider_key: str,
    request: Mapping[str, Any],
    emit_event,
    is_cancelled,
) -> dict[str, Any]:
    _ = request
    _ = is_cancelled
    emit_event("job_started", {"workflow": "capability_probe"})
    report = run_startup_capability_probe()
    emit_event(
        "job_finished",
        {
            "available_count": report.available_count,
            "total_count": report.total_count,
            "all_available": report.all_available,
        },
    )
    return serialize_capability_probe_report(report)
