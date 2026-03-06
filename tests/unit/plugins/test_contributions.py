"""Unit tests for declarative plugin contribution manager."""

from __future__ import annotations

import pytest

from app.plugins.contributions import DeclarativeContributionManager
from app.plugins.models import DiscoveredPlugin, PluginCompatibility, PluginManifest
from app.shell.events import RunSessionStartedEvent

pytestmark = pytest.mark.unit


def test_apply_registers_commands_and_event_hooks() -> None:
    registered_runtime_commands: list[str] = []
    registered_menu_commands: list[str] = []
    subscribed_events: list[type[object]] = []
    unsubscribed_events: list[type[object]] = []
    runtime_success: list[tuple[str, str]] = []
    runtime_failures: list[tuple[str, str, str]] = []
    executed: list[str] = []

    manager = DeclarativeContributionManager(
        register_runtime_command=lambda command_id, _handler, _replace: registered_runtime_commands.append(command_id),
        register_runtime_menu_command=lambda **kwargs: registered_menu_commands.append(kwargs["command_id"]),
        unregister_runtime_menu_command=lambda _command_id: None,
        execute_runtime_command=lambda command_id: executed.append(command_id),
        subscribe_shell_event=lambda event_type, _handler: subscribed_events.append(event_type),
        unsubscribe_shell_event=lambda event_type, _handler: unsubscribed_events.append(event_type),
        emit_message=lambda _message: None,
        execute_plugin_runtime_command=lambda _command_id, payload: payload,
        on_runtime_command_success=lambda plugin_id, version: runtime_success.append((plugin_id, version)),
        on_runtime_command_failure=lambda plugin_id, version, error: runtime_failures.append((plugin_id, version, error)),
    )

    manifest = PluginManifest(
        plugin_id="acme.demo",
        name="Demo Plugin",
        version="1.0.0",
        api_version=1,
        contributes={
            "commands": [
                {
                    "id": "acme.demo.hello",
                    "title": "Hello",
                    "runtime": True,
                    "runtime_payload": {"value": 1},
                }
            ],
            "event_hooks": [
                {
                    "event_type": "run_start",
                    "command_id": "acme.demo.hello",
                }
            ],
        },
    )
    discovered = DiscoveredPlugin(
        plugin_id="acme.demo",
        version="1.0.0",
        install_path="/tmp/demo",
        manifest_path="/tmp/demo/plugin.json",
        manifest=manifest,
        compatibility=PluginCompatibility(is_compatible=True, reasons=[]),
    )

    manager.apply([discovered], enabled_map={("acme.demo", "1.0.0"): True})

    assert registered_runtime_commands == ["acme.demo.hello"]
    assert registered_menu_commands == ["acme.demo.hello"]
    assert subscribed_events == [RunSessionStartedEvent]
    assert runtime_failures == []
    assert executed == []
    assert runtime_success == []
    assert unsubscribed_events == []


def test_clear_unregisters_commands_and_unsubscribes_handlers() -> None:
    unregistered_commands: list[str] = []
    unsubscribed_events: list[type[object]] = []
    subscriptions: list[tuple[type[object], object]] = []

    manager = DeclarativeContributionManager(
        register_runtime_command=lambda _command_id, _handler, _replace: None,
        register_runtime_menu_command=lambda **_kwargs: None,
        unregister_runtime_menu_command=lambda command_id: unregistered_commands.append(command_id),
        execute_runtime_command=lambda _command_id: None,
        subscribe_shell_event=lambda event_type, handler: subscriptions.append((event_type, handler)),
        unsubscribe_shell_event=lambda event_type, _handler: unsubscribed_events.append(event_type),
        emit_message=lambda _message: None,
        execute_plugin_runtime_command=lambda _command_id, _payload: None,
        on_runtime_command_success=lambda _plugin_id, _version: None,
        on_runtime_command_failure=lambda _plugin_id, _version, _error: None,
    )

    manager._registered_command_ids.add("acme.demo.hello")
    dummy_handler = lambda _event: None
    manager._event_subscriptions.append((RunSessionStartedEvent, dummy_handler))

    manager.clear()

    assert unregistered_commands == ["acme.demo.hello"]
    assert unsubscribed_events == [RunSessionStartedEvent]
