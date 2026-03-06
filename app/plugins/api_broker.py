from __future__ import annotations

from typing import Any

from app.plugins.runtime_manager import PluginRuntimeManager


class PluginApiBroker:
    def __init__(self, runtime_manager: PluginRuntimeManager) -> None:
        self._runtime_manager = runtime_manager

    def invoke_runtime_command(self, command_id: str, payload: dict[str, object]) -> object:
        return self._runtime_manager.invoke_command(command_id, payload)

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
