from __future__ import annotations

import queue
import threading
import uuid
from pathlib import Path
from typing import Any, Mapping

from app.bootstrap.paths import PathInput, ensure_directory, global_plugins_logs_dir
from app.core.errors import RunLifecycleError
from app.plugins.host_supervisor import PluginHostSupervisor
from app.plugins.rpc_protocol import build_command_request, decode_message, encode_message
from app.run.process_supervisor import ProcessEvent

_PLUGIN_RUNTIME_LOG_FILENAME = "plugin_host.log"


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
            self._append_runtime_log(f"command timeout: {command_id}")
            raise RunLifecycleError(
                f"Plugin runtime command timed out: {command_id}"
            ) from exc
        ok = bool(response.get("ok", False))
        if ok:
            return response.get("result")
        error = response.get("error")
        self._append_runtime_log(f"command failed: {command_id}: {error}")
        raise RunLifecycleError(str(error) if error is not None else "Plugin runtime command failed.")

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
            for _, response_queue in pending:
                try:
                    response_queue.put_nowait(
                        {"ok": False, "error": "Plugin host process exited before response."}
                    )
                except queue.Full:
                    continue

    def _consume_message(self, line: str) -> bool:
        try:
            payload = decode_message(line)
        except Exception:
            return False
        message_type = payload.get("type")
        if message_type != "response":
            return False
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

    def _append_runtime_log(self, message: str) -> None:
        try:
            ensure_directory(self._log_path.parent)
            with self._log_path.open("a", encoding="utf-8") as handle:
                handle.write(message.rstrip() + "\n")
        except OSError:
            return
