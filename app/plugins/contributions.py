from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.plugins.models import DiscoveredPlugin
from app.shell.events import (
    ProjectOpenFailedEvent,
    ProjectOpenedEvent,
    RunProcessExitEvent,
    RunProcessOutputEvent,
    RunSessionStartedEvent,
)

EVENT_TYPE_MAP: dict[str, type[object]] = {
    "run_start": RunSessionStartedEvent,
    "run_output": RunProcessOutputEvent,
    "run_exit": RunProcessExitEvent,
    "project_opened": ProjectOpenedEvent,
    "project_open_failed": ProjectOpenFailedEvent,
}


class DeclarativeContributionManager:
    def __init__(
        self,
        *,
        register_runtime_command: Callable[[str, Callable[[], object], bool], None],
        register_runtime_menu_command: Callable[..., None],
        unregister_runtime_menu_command: Callable[[str], None],
        execute_runtime_command: Callable[[str], object],
        subscribe_shell_event: Callable[[type[object], Callable[[object], None]], None],
        unsubscribe_shell_event: Callable[[type[object], Callable[[object], None]], None],
        emit_message: Callable[[str], None],
        execute_plugin_runtime_command: Callable[[str, dict[str, Any]], Any],
    ) -> None:
        self._register_runtime_command = register_runtime_command
        self._register_runtime_menu_command = register_runtime_menu_command
        self._unregister_runtime_menu_command = unregister_runtime_menu_command
        self._execute_runtime_command = execute_runtime_command
        self._subscribe_shell_event = subscribe_shell_event
        self._unsubscribe_shell_event = unsubscribe_shell_event
        self._emit_message = emit_message
        self._execute_plugin_runtime_command = execute_plugin_runtime_command
        self._registered_command_ids: set[str] = set()
        self._event_subscriptions: list[tuple[type[object], Callable[[object], None]]] = []

    def clear(self) -> None:
        for command_id in list(self._registered_command_ids):
            self._unregister_runtime_menu_command(command_id)
        self._registered_command_ids.clear()
        for event_type, handler in self._event_subscriptions:
            self._unsubscribe_shell_event(event_type, handler)
        self._event_subscriptions.clear()

    def apply(self, discovered_plugins: list[DiscoveredPlugin], *, enabled_map: dict[tuple[str, str], bool]) -> None:
        self.clear()
        for discovered in discovered_plugins:
            if discovered.manifest is None:
                continue
            if discovered.compatibility is not None and not discovered.compatibility.is_compatible:
                continue
            if not enabled_map.get((discovered.plugin_id, discovered.version), True):
                continue
            contributes = discovered.manifest.contributes
            commands_payload = contributes.get("commands", [])
            if isinstance(commands_payload, list):
                self._apply_commands(discovered.plugin_id, commands_payload)
            hooks_payload = contributes.get("event_hooks", [])
            if isinstance(hooks_payload, list):
                self._apply_event_hooks(hooks_payload)

    def _apply_commands(self, plugin_id: str, commands_payload: list[Any]) -> None:
        for command_payload in commands_payload:
            if not isinstance(command_payload, dict):
                continue
            command_id = command_payload.get("id")
            title = command_payload.get("title")
            if not isinstance(command_id, str) or not command_id.strip():
                continue
            if not isinstance(title, str) or not title.strip():
                continue
            menu_id = command_payload.get("menu_id")
            if not isinstance(menu_id, str) or not menu_id.strip():
                menu_id = "shell.menu.tools"
            shortcut = command_payload.get("shortcut")
            if not isinstance(shortcut, str):
                shortcut = None
            status_tip = command_payload.get("status_tip")
            if not isinstance(status_tip, str):
                status_tip = None
            tool_tip = command_payload.get("tool_tip")
            if not isinstance(tool_tip, str):
                tool_tip = None
            message = command_payload.get("message")
            if not isinstance(message, str) or not message.strip():
                message = f"{plugin_id}: {command_id}"
            runtime_flag = bool(command_payload.get("runtime", False))
            runtime_payload = command_payload.get("runtime_payload", {})
            if not isinstance(runtime_payload, dict):
                runtime_payload = {}
            normalized_command_id = command_id.strip()

            if runtime_flag:
                self._register_runtime_command(
                    normalized_command_id,
                    lambda cid=normalized_command_id, payload=dict(runtime_payload): self._execute_plugin_runtime_command(
                        cid,
                        payload,
                    ),
                    True,
                )
            else:
                self._register_runtime_command(
                    normalized_command_id,
                    lambda text=message: self._emit_message(text),
                    True,
                )

            self._register_runtime_menu_command(
                command_id=normalized_command_id,
                menu_id=menu_id.strip(),
                label=title.strip(),
                handler=lambda cid=normalized_command_id: self._execute_runtime_command(cid),
                shortcut=shortcut,
                enabled=True,
                status_tip=status_tip,
                tool_tip=tool_tip,
                replace=True,
            )
            self._registered_command_ids.add(normalized_command_id)

    def _apply_event_hooks(self, hooks_payload: list[Any]) -> None:
        for hook_payload in hooks_payload:
            if not isinstance(hook_payload, dict):
                continue
            event_type_name = hook_payload.get("event_type")
            command_id = hook_payload.get("command_id")
            if not isinstance(event_type_name, str) or not isinstance(command_id, str):
                continue
            event_type = EVENT_TYPE_MAP.get(event_type_name.strip())
            if event_type is None:
                continue
            normalized_command_id = command_id.strip()
            if not normalized_command_id:
                continue

            def _handler(_event: object, cid: str = normalized_command_id) -> None:
                try:
                    self._execute_runtime_command(cid)
                except Exception:
                    return

            self._subscribe_shell_event(event_type, _handler)
            self._event_subscriptions.append((event_type, _handler))
