"""Shell chrome that follows the active tab.

``ActiveSurfaceChrome`` is the only writer of a tab menu's visibility and of
the text, enabled state, visibility and tooltip of the routed Edit actions.
The markdown toggle is routed for triggers only. The markdown workflow keeps
writing its state and asks ``claims`` instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

from app.qt.QtCore import Qt
from app.qt.QtWidgets import QAction, QMenu, QMenuBar, QWidget

from app.shell.menus import MenuStubRegistry
from app.shell.tab_content_providers import (
    CommandState,
    SurfaceShellState,
    TabContentProviderRegistry,
    TabMenu,
    TabMenuItem,
    TabSurface,
)

_ROUTED_STATE_IDS = (
    "shell.action.edit.undo",
    "shell.action.edit.redo",
    "shell.action.edit.cut",
    "shell.action.edit.copy",
    "shell.action.edit.paste",
    "shell.action.edit.delete",
    "shell.action.edit.selectAll",
)


@dataclass(frozen=True)
class _BaseState:
    text: str
    enabled: bool
    visible: bool


_MenuItems = Dict[str, Tuple[QAction, TabMenuItem]]


def _nothing() -> None:
    return None


class ActiveSurfaceChrome:
    def __init__(self, registry: TabContentProviderRegistry) -> None:
        self._registry = registry
        self._surface: Optional[TabSurface] = None
        self._provider_id: Optional[str] = None
        self._unsubscribe: Callable[[], None] = _nothing
        self._state = SurfaceShellState()
        self._routed: Dict[str, Tuple[QAction, _BaseState]] = {}
        self._menus: Dict[str, Tuple[QMenu, _MenuItems]] = {}
        self._on_sentence_changed: Callable[[], None] = _nothing

    def route(self, action_id: str, fallback: Optional[Callable[[], object]] = None) -> Callable[[], None]:
        """The trigger for a shell action. The active surface runs it when it claims ``action_id``."""

        def trigger() -> None:
            surface = self._surface
            if surface is not None and action_id in self._state.commands:
                surface.run_command(action_id)
            elif fallback is not None:
                fallback()

        return trigger

    def bind(
        self,
        menu_registry: MenuStubRegistry,
        menu_bar: QMenuBar,
        *,
        before_menu_id: str,
        on_sentence_changed: Callable[[], None],
    ) -> None:
        """Build each provider's tab menu before ``before_menu_id`` and record the routed actions' base state."""
        for action_id in _ROUTED_STATE_IDS:
            action = menu_registry.action(action_id)
            self._routed[action_id] = (action, _BaseState(action.text(), action.isEnabled(), action.isVisible()))
        before = menu_registry.menu(before_menu_id).menuAction()
        for provider_id, tab_menu in self._registry.menus():
            menu, items = _build_menu(tab_menu, menu_bar, self._run_item)
            menu_bar.insertMenu(before, menu)
            menu_registry.menus[tab_menu.menu_id] = menu
            self._menus[provider_id] = (menu, items)
        self._on_sentence_changed = on_sentence_changed
        self._apply(self._current_state())

    def follow(self, file_path: Optional[str]) -> None:
        """The active tab changed. None: no tab is active."""
        surface = None if file_path is None else self._registry.surface_for_path(file_path)
        if surface is not self._surface:
            self._unsubscribe()
            self._surface = surface
            self._unsubscribe = _nothing if surface is None else surface.subscribe_shell_state(self._on_state_changed)
        self._provider_id = None if file_path is None or surface is None else self._registry.provider_id_for(file_path)
        self._apply(self._current_state())

    def claims(self, action_id: str) -> bool:
        return action_id in self._state.commands

    def _current_state(self) -> SurfaceShellState:
        surface = self._surface
        if surface is None:
            return SurfaceShellState()
        return surface.shell_state()

    def _on_state_changed(self) -> None:
        state = self._current_state()
        if state != self._state:
            self._apply(state)

    def _apply(self, state: SurfaceShellState) -> None:
        sentence_changed = state.sentence != self._state.sentence
        self._state = state
        for provider_id, (menu, items) in self._menus.items():
            active = provider_id == self._provider_id
            menu.menuAction().setVisible(active)
            if active:
                for command_id, (action, item) in items.items():
                    _write_item(action, item, state.commands.get(command_id))
        for action_id, (action, base) in self._routed.items():
            _write_routed(action, base, state.commands.get(action_id))
        if sentence_changed:
            self._on_sentence_changed()

    def _run_item(self, command_id: str) -> None:
        surface = self._surface
        if surface is not None:
            surface.run_command(command_id)


def _new_menu(title: str, parent: QWidget) -> QMenu:
    menu = QMenu(title, parent)
    menu.setToolTipsVisible(True)
    menu.setAttribute(Qt.WA_TranslucentBackground)
    return menu


def _item_text(label: str, key_text: str) -> str:
    if not key_text:
        return label
    return "%s\t%s" % (label, key_text)


def _build_menu(
    tab_menu: TabMenu,
    parent: QWidget,
    run: Callable[[str], None],
) -> Tuple[QMenu, _MenuItems]:
    root = _new_menu(tab_menu.title, parent)
    root.setObjectName(tab_menu.menu_id)
    submenus: Dict[Tuple[str, ...], QMenu] = {(): root}
    items: _MenuItems = {}
    for item in tab_menu.items:
        menu = submenus.get(item.path)
        if menu is None:
            owner = submenus[item.path[:-1]]
            if item.separator_before:
                owner.addSeparator()
            menu = _new_menu(item.path[-1], owner)
            owner.addMenu(menu)
            submenus[item.path] = menu
        elif item.separator_before:
            menu.addSeparator()
        action = QAction(_item_text(item.label, item.key_text), menu)
        action.setObjectName(item.command_id)
        action.setCheckable(item.checkable)
        action.setEnabled(False)
        action.triggered.connect(lambda _checked=False, command_id=item.command_id: run(command_id))
        menu.addAction(action)
        items[item.command_id] = (action, item)
    return root, items


def _write_item(action: QAction, item: TabMenuItem, state: Optional[CommandState]) -> None:
    if state is None:
        action.setEnabled(False)
        return
    action.setText(_item_text(state.label or item.label, item.key_text))
    action.setEnabled(state.enabled)
    action.setToolTip(state.tooltip)
    if state.checked is not None:
        action.setChecked(state.checked)


def _write_routed(action: QAction, base: _BaseState, state: Optional[CommandState]) -> None:
    if state is None:
        action.setText(base.text)
        action.setEnabled(base.enabled)
        action.setVisible(base.visible)
        action.setToolTip("")
        return
    action.setText(state.label or base.text)
    action.setEnabled(state.enabled)
    action.setToolTip(state.tooltip)
    action.setVisible(True)


__all__ = ["ActiveSurfaceChrome"]
