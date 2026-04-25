from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any

from app.plugins.models import DiscoveredPlugin, PluginCommandContribution
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
_LOGGER = logging.getLogger(__name__)


class DeclarativeContributionManager:
    def __init__(
        self,
        *,
        register_runtime_command: Callable[[str, Callable[..., object], bool], None],
        register_runtime_menu_command: Callable[..., None],
        unregister_runtime_menu_command: Callable[[str], None],
        execute_runtime_command: Callable[[str, dict[str, Any] | None, str | None], object],
        subscribe_shell_event: Callable[[type[object], Callable[[object], None]], None],
        unsubscribe_shell_event: Callable[[type[object], Callable[[object], None]], None],
        emit_message: Callable[[str], None],
        execute_plugin_runtime_command: Callable[[str, dict[str, Any], str | None], Any],
        on_runtime_command_success: Callable[[str, str], None],
        on_runtime_command_failure: Callable[[str, str, str], None],
    ) -> None:
        self._register_runtime_command = register_runtime_command
        self._register_runtime_menu_command = register_runtime_menu_command
        self._unregister_runtime_menu_command = unregister_runtime_menu_command
        self._execute_runtime_command = execute_runtime_command
        self._subscribe_shell_event = subscribe_shell_event
        self._unsubscribe_shell_event = unsubscribe_shell_event
        self._emit_message = emit_message
        self._execute_plugin_runtime_command = execute_plugin_runtime_command
        self._on_runtime_command_success = on_runtime_command_success
        self._on_runtime_command_failure = on_runtime_command_failure
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
            self._apply_commands(
                discovered.plugin_id,
                discovered.version,
                discovered.manifest.command_contributions,
            )
            hooks_payload = contributes.get("event_hooks", [])
            if isinstance(hooks_payload, list):
                self._apply_event_hooks(
                    plugin_id=discovered.plugin_id,
                    version=discovered.version,
                    hooks_payload=hooks_payload,
                )

    def _apply_commands(
        self,
        plugin_id: str,
        version: str,
        commands: list[PluginCommandContribution],
    ) -> None:
        for command in commands:
            command_id = command.command_id
            message = command.message or f"{plugin_id}: {command_id}"
            runtime_payload = dict(command.runtime_payload)
            try:
                if command.runtime:
                    self._register_runtime_command(
                        command_id,
                        lambda extra_payload=None, activation_event=None, cid=command_id, payload=runtime_payload, pid=plugin_id, ver=version: self._execute_runtime_command_with_quarantine(
                            plugin_id=pid,
                            version=ver,
                            command_id=cid,
                            payload=_merge_runtime_payload(payload, extra_payload),
                            activation_event=activation_event,
                        ),
                        True,
                    )
                else:
                    self._register_runtime_command(
                        command_id,
                        lambda text=message: self._emit_message(text),
                        True,
                    )

                self._register_runtime_menu_command(
                    command_id=command_id,
                    menu_id=command.menu_id,
                    label=command.title,
                    handler=lambda cid=command_id: self._execute_runtime_command(
                        cid,
                        None,
                        None,
                    ),
                    shortcut=command.shortcut,
                    enabled=True,
                    status_tip=command.status_tip,
                    tool_tip=command.tool_tip,
                    replace=True,
                )
                self._registered_command_ids.add(command_id)
            except Exception as exc:
                _LOGGER.warning(
                    "Failed to register declarative command '%s' from plugin %s@%s: %s",
                    command_id,
                    plugin_id,
                    version,
                    exc,
                )
                continue

    def _execute_runtime_command_with_quarantine(
        self,
        *,
        plugin_id: str,
        version: str,
        command_id: str,
        payload: dict[str, Any],
        activation_event: str | None,
    ) -> Any:
        try:
            result = self._execute_plugin_runtime_command(command_id, payload, activation_event)
        except Exception as exc:
            self._on_runtime_command_failure(plugin_id, version, str(exc))
            raise
        self._on_runtime_command_success(plugin_id, version)
        return result

    def _apply_event_hooks(
        self,
        *,
        plugin_id: str,
        version: str,
        hooks_payload: list[Any],
    ) -> None:
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
            normalized_event_type_name = event_type_name.strip()
            hook_id = f"{normalized_event_type_name}:{normalized_command_id}"

            def _handler(
                _event: object,
                cid: str = normalized_command_id,
                event_name: str = normalized_event_type_name,
                hook_name: str = hook_id,
            ) -> None:
                try:
                    event_payload = _event_to_payload(_event)
                    self._execute_runtime_command(
                        cid,
                        event_payload,
                        f"on_event:{event_name}",
                    )
                except Exception as exc:
                    _LOGGER.warning(
                        "Plugin event hook %s failed for %s@%s: %s",
                        hook_name,
                        plugin_id,
                        version,
                        exc,
                        exc_info=True,
                    )

            self._subscribe_shell_event(event_type, _handler)
            self._event_subscriptions.append((event_type, _handler))


def _event_to_payload(event: object) -> dict[str, Any]:
    if hasattr(event, "__dict__"):
        return {
            key: value
            for key, value in vars(event).items()
            if not key.startswith("_")
        }
    return {}


def _merge_runtime_payload(
    base_payload: dict[str, Any],
    extra_payload: object,
) -> dict[str, Any]:
    merged = dict(base_payload)
    if isinstance(extra_payload, dict):
        merged.update(extra_payload)
    return merged
