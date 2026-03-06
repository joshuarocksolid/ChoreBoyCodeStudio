from __future__ import annotations

import queue
import threading
import uuid
from typing import Any, Mapping

from app.bootstrap.paths import PathInput
from app.core.errors import RunLifecycleError
from app.plugins.host_supervisor import PluginHostSupervisor
from app.plugins.rpc_protocol import build_command_request, decode_message, encode_message
from app.run.process_supervisor import ProcessEvent


class PluginRuntimeManager:
    def __init__(
        self,
        *,
        state_root: PathInput | None = None,
        runtime_executable: str | None = None,
        host_boot_path: str | None = None,
    ) -> None:
        self._stdout_buffer = ""
        self._pending_requests: dict[str, queue.Queue[dict[str, Any]]] = {}
        self._pending_lock = threading.RLock()
        self._last_error: str | None = None
        self._host_supervisor = PluginHostSupervisor(
            on_event=self._handle_event,
            runtime_executable=runtime_executable,
            host_boot_path=host_boot_path,
            state_root=state_root,
        )

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def start(self) -> None:
        if self._host_supervisor.is_running():
            return
        self._host_supervisor.start()

    def stop(self) -> None:
        self._host_supervisor.stop()
        with self._pending_lock:
            self._pending_requests.clear()

    def is_running(self) -> bool:
        return self._host_supervisor.is_running()

    def reload_plugins(self) -> None:
        self.start()
        self._host_supervisor.send_input(encode_message({"type": "reload"}))

    def invoke_command(
        self,
        command_id: str,
        payload: Mapping[str, Any] | None = None,
        *,
        timeout_seconds: float = 5.0,
    ) -> Any:
        self.start()
        request_id = uuid.uuid4().hex
        response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending_requests[request_id] = response_queue
        message = build_command_request(
            request_id=request_id,
            command_id=command_id,
            payload=payload,
        )
        self._host_supervisor.send_input(encode_message(message))
        try:
            response = response_queue.get(timeout=timeout_seconds)
        except queue.Empty as exc:
            with self._pending_lock:
                self._pending_requests.pop(request_id, None)
            raise RunLifecycleError(
                f"Plugin runtime command timed out: {command_id}"
            ) from exc
        ok = bool(response.get("ok", False))
        if ok:
            return response.get("result")
        error = response.get("error")
        raise RunLifecycleError(str(error) if error is not None else "Plugin runtime command failed.")

    def _handle_event(self, event: ProcessEvent) -> None:
        if event.event_type == "output":
            if event.stream == "stderr":
                self._last_error = event.text or ""
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
                self._consume_message(stripped)
            return
        if event.event_type == "exit":
            with self._pending_lock:
                pending = list(self._pending_requests.items())
                self._pending_requests.clear()
            for _, response_queue in pending:
                try:
                    response_queue.put_nowait(
                        {"ok": False, "error": "Plugin host process exited before response."}
                    )
                except queue.Full:
                    continue

    def _consume_message(self, line: str) -> None:
        try:
            payload = decode_message(line)
        except Exception:
            return
        message_type = payload.get("type")
        if message_type != "response":
            return
        request_id = payload.get("request_id")
        if not isinstance(request_id, str):
            return
        with self._pending_lock:
            response_queue = self._pending_requests.pop(request_id, None)
        if response_queue is None:
            return
        try:
            response_queue.put_nowait(payload)
        except queue.Full:
            return
