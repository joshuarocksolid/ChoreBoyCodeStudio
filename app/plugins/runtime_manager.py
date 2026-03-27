from __future__ import annotations

from dataclasses import dataclass
import queue
import threading
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

from app.bootstrap.paths import PathInput, ensure_directory, global_plugins_logs_dir
from app.core.errors import RunLifecycleError
from app.plugins.host_supervisor import PluginHostSupervisor
from app.plugins.rpc_protocol import (
    build_command_request,
    build_provider_job_cancel_request,
    build_provider_job_start_request,
    build_provider_query_request,
    decode_message,
    encode_message,
)
from app.run.process_supervisor import ProcessEvent

_PLUGIN_RUNTIME_LOG_FILENAME = "plugin_host.log"


@dataclass(frozen=True)
class PluginRuntimeJob:
    job_id: str
    provider_key: str


class PluginRuntimeManager:
    def __init__(
        self,
        *,
        state_root: PathInput | None = None,
        runtime_executable: str | None = None,
        host_boot_path: str | None = None,
    ) -> None:
        self._state_root = state_root
        self._stdout_buffer = ""
        self._pending_requests: dict[str, queue.Queue[dict[str, Any]]] = {}
        self._job_result_queues: dict[str, queue.Queue[dict[str, Any]]] = {}
        self._job_event_handlers: dict[str, Callable[[str, Mapping[str, Any]], None]] = {}
        self._pending_lock = threading.RLock()
        self._last_error: str | None = None
        self._log_path = global_plugins_logs_dir(state_root) / _PLUGIN_RUNTIME_LOG_FILENAME
        self._host_supervisor = PluginHostSupervisor(
            on_event=self._handle_event,
            runtime_executable=runtime_executable,
            host_boot_path=host_boot_path,
            state_root=state_root,
        )

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def log_file_path(self) -> str:
        return str(self._log_path)

    def start(self) -> None:
        if self._host_supervisor.is_running():
            return
        self._append_runtime_log("starting plugin host")
        self._host_supervisor.start()

    def stop(self) -> None:
        self._host_supervisor.stop()
        self._append_runtime_log("stopped plugin host")
        with self._pending_lock:
            self._pending_requests.clear()
            self._job_result_queues.clear()
            self._job_event_handlers.clear()

    def is_running(self) -> bool:
        return self._host_supervisor.is_running()

    def reload_plugins(self) -> None:
        self.start()
        self._append_runtime_log("reloading plugin host commands")
        self._host_supervisor.send_input(encode_message({"type": "reload"}))

    def invoke_command(
        self,
        command_id: str,
        payload: Mapping[str, Any] | None = None,
        *,
        timeout_seconds: float = 5.0,
        activation_event: str | None = None,
    ) -> Any:
        message = build_command_request(
            request_id=uuid.uuid4().hex,
            command_id=command_id,
            payload=payload,
        )
        if activation_event is not None:
            message["activation_event"] = activation_event
        return self._invoke_request(
            request_id=message["request_id"],
            message=message,
            timeout_seconds=timeout_seconds,
            failure_label=command_id,
        )

    def invoke_workflow_query(
        self,
        provider_key: str,
        request: Mapping[str, Any] | None = None,
        *,
        timeout_seconds: float = 5.0,
        activation_event: str | None = None,
    ) -> Any:
        message = build_provider_query_request(
            request_id=uuid.uuid4().hex,
            provider_key=provider_key,
            request=request,
            activation_event=activation_event,
        )
        return self._invoke_request(
            request_id=message["request_id"],
            message=message,
            timeout_seconds=timeout_seconds,
            failure_label=provider_key,
        )

    def start_workflow_job(
        self,
        provider_key: str,
        request: Mapping[str, Any] | None = None,
        *,
        on_event: Callable[[str, Mapping[str, Any]], None] | None = None,
        activation_event: str | None = None,
        timeout_seconds: float = 5.0,
    ) -> PluginRuntimeJob:
        self.start()
        request_id = uuid.uuid4().hex
        job_id = uuid.uuid4().hex
        response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        job_result_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending_requests[request_id] = response_queue
            self._job_result_queues[job_id] = job_result_queue
            if on_event is not None:
                self._job_event_handlers[job_id] = on_event
        message = build_provider_job_start_request(
            request_id=request_id,
            job_id=job_id,
            provider_key=provider_key,
            request=request,
            activation_event=activation_event,
        )
        self._host_supervisor.send_input(encode_message(message))
        response = self._wait_for_response(
            request_id=request_id,
            response_queue=response_queue,
            timeout_seconds=timeout_seconds,
            failure_label=provider_key,
        )
        self._unwrap_response(response, failure_label=provider_key)
        return PluginRuntimeJob(job_id=job_id, provider_key=provider_key)

    def wait_for_workflow_job(
        self,
        job: PluginRuntimeJob,
        *,
        timeout_seconds: float | None = None,
    ) -> Any:
        with self._pending_lock:
            result_queue = self._job_result_queues.get(job.job_id)
        if result_queue is None:
            raise RunLifecycleError(f"Plugin workflow job not found: {job.job_id}")
        try:
            response = result_queue.get(timeout=timeout_seconds)
        except queue.Empty as exc:
            self._append_runtime_log(f"workflow job timeout: {job.provider_key}")
            raise RunLifecycleError(
                f"Plugin workflow job timed out: {job.provider_key}"
            ) from exc
        with self._pending_lock:
            self._job_result_queues.pop(job.job_id, None)
            self._job_event_handlers.pop(job.job_id, None)
        message_type = response.get("type")
        if message_type == "job_result":
            return response.get("result")
        error = response.get("error")
        self._append_runtime_log(f"workflow job failed: {job.provider_key}: {error}")
        raise RunLifecycleError(str(error) if error is not None else "Plugin workflow job failed.")

    def cancel_workflow_job(
        self,
        job_id: str,
        *,
        timeout_seconds: float = 5.0,
    ) -> Any:
        message = build_provider_job_cancel_request(
            request_id=uuid.uuid4().hex,
            job_id=job_id,
        )
        return self._invoke_request(
            request_id=message["request_id"],
            message=message,
            timeout_seconds=timeout_seconds,
            failure_label=job_id,
        )

    def _invoke_request(
        self,
        *,
        request_id: str,
        message: Mapping[str, Any],
        timeout_seconds: float,
        failure_label: str,
    ) -> Any:
        self.start()
        response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending_requests[request_id] = response_queue
        self._host_supervisor.send_input(encode_message(message))
        response = self._wait_for_response(
            request_id=request_id,
            response_queue=response_queue,
            timeout_seconds=timeout_seconds,
            failure_label=failure_label,
        )
        return self._unwrap_response(response, failure_label=failure_label)

    def _handle_event(self, event: ProcessEvent) -> None:
        if event.event_type == "output":
            if event.stream == "stderr":
                self._last_error = event.text or ""
                self._append_runtime_log(f"stderr: {(event.text or '').rstrip()}")
                return
            text = event.text or ""
            self._stdout_buffer += text
            lines = self._stdout_buffer.splitlines(keepends=True)
            remaining = ""
            if lines and not lines[-1].endswith("\n"):
                remaining = lines[-1]
                lines = lines[:-1]
            self._stdout_buffer = remaining
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                if not self._consume_message(stripped):
                    self._append_runtime_log(f"stdout: {stripped}")
            return
        if event.event_type == "exit":
            self._append_runtime_log(
                f"host exited return_code={event.return_code} terminated_by_user={event.terminated_by_user}"
            )
            with self._pending_lock:
                pending = list(self._pending_requests.items())
                self._pending_requests.clear()
                job_results = list(self._job_result_queues.items())
                self._job_result_queues.clear()
                self._job_event_handlers.clear()
            for _, response_queue in pending:
                try:
                    response_queue.put_nowait(
                        {"ok": False, "error": "Plugin host process exited before response."}
                    )
                except queue.Full:
                    continue
            for _, result_queue in job_results:
                try:
                    result_queue.put_nowait(
                        {"type": "job_error", "error": "Plugin host process exited before job completion."}
                    )
                except queue.Full:
                    continue

    def _consume_message(self, line: str) -> bool:
        try:
            payload = decode_message(line)
        except Exception:
            return False
        message_type = payload.get("type")
        if message_type == "response":
            request_id = payload.get("request_id")
            if not isinstance(request_id, str):
                return False
            with self._pending_lock:
                response_queue = self._pending_requests.pop(request_id, None)
            if response_queue is None:
                return False
            try:
                response_queue.put_nowait(payload)
            except queue.Full:
                return False
            return True
        if message_type == "job_event":
            job_id = payload.get("job_id")
            provider_key = payload.get("provider_key")
            event_type = payload.get("event_type")
            event_payload = payload.get("payload", {})
            if not isinstance(job_id, str) or not isinstance(event_type, str):
                return False
            if not isinstance(event_payload, dict):
                event_payload = {}
            with self._pending_lock:
                handler = self._job_event_handlers.get(job_id)
                result_queue = self._job_result_queues.get(job_id)
            if handler is not None:
                try:
                    handler(event_type, event_payload)
                except Exception as exc:
                    provider_label = provider_key if isinstance(provider_key, str) and provider_key else "unknown"
                    error_text = (
                        f"Workflow job event handler failed: provider={provider_label} "
                        f"job_id={job_id} event_type={event_type} error={exc.__class__.__name__}: {exc}"
                    )
                    self._append_runtime_log(error_text)
                    if result_queue is not None:
                        try:
                            result_queue.put_nowait(
                                {
                                    "type": "job_error",
                                    "job_id": job_id,
                                    "provider_key": provider_key,
                                    "error": error_text,
                                }
                            )
                        except queue.Full:
                            pass
                    return True
            return True
        if message_type in {"job_result", "job_error"}:
            job_id = payload.get("job_id")
            if not isinstance(job_id, str):
                return False
            with self._pending_lock:
                result_queue = self._job_result_queues.get(job_id)
            if result_queue is None:
                return False
            try:
                result_queue.put_nowait(payload)
            except queue.Full:
                return False
            return True
        return False

    def _wait_for_response(
        self,
        *,
        request_id: str,
        response_queue: queue.Queue[dict[str, Any]],
        timeout_seconds: float,
        failure_label: str,
    ) -> dict[str, Any]:
        try:
            response = response_queue.get(timeout=timeout_seconds)
        except queue.Empty as exc:
            with self._pending_lock:
                self._pending_requests.pop(request_id, None)
            self._append_runtime_log(f"command timeout: {failure_label}")
            raise RunLifecycleError(
                f"Plugin runtime command timed out: {failure_label}"
            ) from exc
        return response

    def _unwrap_response(self, response: dict[str, Any], *, failure_label: str) -> Any:
        ok = bool(response.get("ok", False))
        if ok:
            return response.get("result")
        error = response.get("error")
        self._append_runtime_log(f"command failed: {failure_label}: {error}")
        raise RunLifecycleError(str(error) if error is not None else "Plugin runtime command failed.")

    def _append_runtime_log(self, message: str) -> None:
        try:
            ensure_directory(self._log_path.parent)
            with self._log_path.open("a", encoding="utf-8") as handle:
                handle.write(message.rstrip() + "\n")
        except OSError:
            return
