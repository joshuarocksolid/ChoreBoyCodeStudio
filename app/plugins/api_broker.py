from __future__ import annotations

from typing import Any, Callable, Mapping

from app.plugins.runtime_manager import PluginRuntimeJob, PluginRuntimeManager


class PluginApiBroker:
    def __init__(self, runtime_manager: PluginRuntimeManager) -> None:
        self._runtime_manager = runtime_manager

    def invoke_runtime_command(self, command_id: str, payload: dict[str, object]) -> object:
        return self._runtime_manager.invoke_command(command_id, payload)

    def invoke_runtime_command_for_event(
        self,
        command_id: str,
        payload: dict[str, object],
        *,
        activation_event: str | None,
    ) -> object:
        return self._runtime_manager.invoke_command(
            command_id,
            payload,
            activation_event=activation_event,
        )

    def invoke_workflow_query(
        self,
        provider_key: str,
        request: Mapping[str, Any],
        *,
        activation_event: str | None = None,
    ) -> object:
        return self._runtime_manager.invoke_workflow_query(
            provider_key,
            request,
            activation_event=activation_event,
        )

    def start_workflow_job(
        self,
        provider_key: str,
        request: Mapping[str, Any],
        *,
        on_event: Callable[[str, Mapping[str, Any]], None] | None = None,
        activation_event: str | None = None,
    ) -> PluginRuntimeJob:
        return self._runtime_manager.start_workflow_job(
            provider_key,
            request,
            on_event=on_event,
            activation_event=activation_event,
        )

    def wait_for_workflow_job(
        self,
        job: PluginRuntimeJob,
        *,
        timeout_seconds: float | None = None,
    ) -> object:
        return self._runtime_manager.wait_for_workflow_job(
            job,
            timeout_seconds=timeout_seconds,
        )

    def cancel_workflow_job(self, job_id: str) -> object:
        return self._runtime_manager.cancel_workflow_job(job_id)

    def reload_runtime_plugins(self) -> None:
        self._runtime_manager.reload_plugins()

    def is_runtime_available(self) -> bool:
        return self._runtime_manager.is_running()

    def last_runtime_error(self) -> str | None:
        return self._runtime_manager.last_error

    def coerce_result_payload(self, result: Any) -> object:
        if result is None:
            return {}
        if isinstance(result, (dict, list)):
            return result
        return {"result": result}
