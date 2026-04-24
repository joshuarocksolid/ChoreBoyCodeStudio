"""Unit tests for workflow broker provider metrics."""

from __future__ import annotations

import pytest

from app.core import constants
from app.plugins.workflow_broker import WorkflowBroker

pytestmark = pytest.mark.unit


class _UnusedPluginApiBroker:
    def invoke_workflow_query(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("builtin provider should handle query")

    def start_workflow_job(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("builtin provider should handle job")

    def wait_for_workflow_job(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("builtin provider should handle job")


def test_workflow_broker_records_success_metrics_for_builtin_query_provider() -> None:
    broker = WorkflowBroker(_UnusedPluginApiBroker())
    broker.register_builtin_query_provider(
        provider_key="builtin:formatter",
        kind=constants.WORKFLOW_PROVIDER_KIND_FORMATTER,
        title="Builtin Formatter",
        handler=lambda request: {"status": "ok", "request": dict(request)},
    )

    descriptor, result = broker.invoke_query(
        kind=constants.WORKFLOW_PROVIDER_KIND_FORMATTER,
        request={"source_text": "x=1\n"},
    )

    metrics = broker.list_provider_metrics()

    assert descriptor.provider_key == "builtin:formatter"
    assert result["status"] == "ok"
    assert len(metrics) == 1
    metric = metrics[0]
    assert metric["provider_key"] == "builtin:formatter"
    assert metric["invocation_count"] == 1
    assert metric["success_count"] == 1
    assert metric["failure_count"] == 0
    assert metric["timeout_count"] == 0
    assert metric["last_error"] is None
    assert metric["last_elapsed_ms"] >= 0
    assert metric["max_elapsed_ms"] >= metric["last_elapsed_ms"]


def test_workflow_broker_records_failure_and_timeout_metrics() -> None:
    broker = WorkflowBroker(_UnusedPluginApiBroker())

    def _failing_job(_request, _emit_event, _is_cancelled):  # type: ignore[no-untyped-def]
        raise RuntimeError("workflow job timed out waiting for plugin")

    broker.register_builtin_job_provider(
        provider_key="builtin:pytest",
        kind=constants.WORKFLOW_PROVIDER_KIND_TEST,
        title="Builtin Pytest",
        handler=_failing_job,
    )

    with pytest.raises(RuntimeError, match="timed out"):
        broker.run_job(
            kind=constants.WORKFLOW_PROVIDER_KIND_TEST,
            request={"project_root": "/tmp/project"},
        )

    metrics = broker.list_provider_metrics()

    assert metrics[0]["provider_key"] == "builtin:pytest"
    assert metrics[0]["invocation_count"] == 1
    assert metrics[0]["success_count"] == 0
    assert metrics[0]["failure_count"] == 1
    assert metrics[0]["timeout_count"] == 1
    assert metrics[0]["last_error"] == "workflow job timed out waiting for plugin"
