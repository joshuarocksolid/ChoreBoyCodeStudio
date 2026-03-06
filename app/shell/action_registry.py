from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide2.QtWidgets import QAction

from app.shell.command_broker import CommandBroker
from app.shell.menus import MenuStubRegistry
from app.shell.shortcut_preferences import normalize_shortcut


class ShellActionRegistry:
    def __init__(self, *, menu_registry: MenuStubRegistry, command_broker: CommandBroker) -> None:
        self._menu_registry = menu_registry
        self._command_broker = command_broker
        self._dynamic_action_menu_ids: dict[str, str] = {}

    def register_menu_action(
        self,
        *,
        action_id: str,
        menu_id: str,
        label: str,
        shortcut: str | None = None,
        enabled: bool = True,
        status_tip: str | None = None,
        tool_tip: str | None = None,
    ) -> QAction:
        existing_action = self._menu_registry.actions.get(action_id)
        if existing_action is not None:
            return existing_action

        target_menu = self._menu_registry.menu(menu_id)
        if target_menu is None:
            raise KeyError(f"menu not found: {menu_id}")

        action = QAction(label, target_menu)
        action.setObjectName(action_id)
        if shortcut:
            normalized_shortcut = normalize_shortcut(shortcut)
            if normalized_shortcut:
                action.setShortcut(normalized_shortcut)
        action.setEnabled(enabled)
        if status_tip:
            action.setStatusTip(status_tip)
        if tool_tip:
            action.setToolTip(tool_tip)
        action.triggered.connect(
            lambda _checked=False, command_id=action_id: self._command_broker.invoke(command_id)
        )
        target_menu.addAction(action)
        self._menu_registry.actions[action_id] = action
        self._dynamic_action_menu_ids[action_id] = menu_id
        return action

    def unregister_menu_action(self, action_id: str) -> None:
        action = self._menu_registry.actions.pop(action_id, None)
        menu_id = self._dynamic_action_menu_ids.pop(action_id, None)
        if action is None:
            return
        if menu_id is not None:
            menu = self._menu_registry.menu(menu_id)
            if menu is not None:
                menu.removeAction(action)
        action.deleteLater()

    def register_command(
        self,
        command_id: str,
        handler: Callable[..., Any],
        *,
        replace: bool = False,
    ) -> None:
        self._command_broker.register(command_id, handler, replace=replace)

    def unregister_command(self, command_id: str) -> None:
        self._command_broker.unregister(command_id)
