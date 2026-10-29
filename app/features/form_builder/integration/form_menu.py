"""Form menu from the command table and the contributor registry (UX-SHELL-004, UX-M5-010).

The shell does not know this menu. It is hidden unless a form tab is active.
Commands whose gesture does not exist yet stay disabled. Items that lanes add
come from ``form_menu_ext``; see that package for the order and the
absent-not-disabled rule.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Sequence, Tuple

from app.qt.QtCore import QObject, Qt, QTimer
from app.qt.QtGui import QKeySequence

from app.features.form_builder.engine.layout_actions import gate, request_for
from app.features.form_builder.engine.shell_commands import FormCommand, menu_commands, menu_hint
from app.features.form_builder.engine.clipboard import command_enabled
from app.features.form_builder.integration.clipboard_actions import (
    CLIPBOARD_COMMAND_IDS,
    clipboard_has_fragment,
)
from app.features.form_builder.integration.form_menu_ext import (
    FORM,
    HELP,
    FormMenuItem,
    FormMenuRegistry,
    MenuEntry,
    MenuNode,
    default_registry,
    plan_menu,
)
from app.features.form_builder.integration.surface import FormSurface
from app.shell.menu_action_builder import register_menu_action
from app.shell.menus import register_menu_contributor

logger = logging.getLogger(__name__)


def register_form_menu(window: Any, registry: Optional[FormMenuRegistry] = None) -> None:
    """Add the Form menu. ``registry`` is for tests; the product uses ``form_menu_ext``'s own."""
    register_menu_contributor(
        "form-builder.menu",
        "shell.menu.view",
        lambda ctx: _build(window, ctx, registry or default_registry()),
    )


def _qt_alive(obj: Any) -> bool:
    probe = getattr(obj, "objectName", None)
    if not callable(probe):
        return True
    try:
        probe()
    except RuntimeError:
        return False
    return True


class _State:
    """What ``_sync`` needs: every action by id, the contributed items, the Help hook."""

    def __init__(self, ctx: Any, registry: FormMenuRegistry) -> None:
        self.actions: Dict[str, Any] = {}
        self.items: Dict[str, FormMenuItem] = {}
        self.help_items = tuple(item for _module, item in registry.items(HELP))
        self.ctx = ctx
        self.menus = ctx.menus
        self.help_attached = False
        self.help_actions: Dict[str, Any] = {}


def _build(window: Any, ctx: Any, registry: FormMenuRegistry) -> None:
    if not _qt_alive(window):
        return
    menu = ctx.menu_bar.addMenu("F&orm")
    menu.setObjectName("formBuilder.menu")
    ctx.menus["formBuilder.menu"] = menu
    state = _State(ctx, registry)
    contributed = tuple(pair for pair in registry.items(FORM) if _free(ctx, pair[1]))
    claimed = {item.command_id for _module, item in contributed}
    entries: list = [
        MenuEntry(command.menu_path, index, "", command)
        for index, command in enumerate(menu_commands())
        if command.command_id not in claimed
    ]
    entries.extend(MenuEntry(item.path, item.rank, module, item) for module, item in contributed)
    _fill(window, ctx, menu, plan_menu(entries), state)
    menu.aboutToShow.connect(lambda: _sync(window, menu, state))
    tabs = getattr(window, "_editor_tabs_widget", None)
    if tabs is not None and _qt_alive(tabs):
        # A receiver owned by the menu drops this connection when the menu
        # goes, so a tab change during window teardown never reaches a
        # deleted menu.
        watcher = _TabWatcher(window, menu, state)
        tabs.currentChanged.connect(watcher.on_current_changed)
    _sync(window, menu, state)
    if state.help_items:
        # The shell builds Help after this menu, so its items join on the next turn.
        QTimer.singleShot(0, lambda: _qt_alive(menu) and _sync(window, menu, state))


def _free(ctx: Any, item: FormMenuItem) -> bool:
    """False, and logged, when another menu already registered this action id."""
    if item.command_id in ctx.actions:
        logger.error("form menu item %s left out: the id is already a menu action", item.command_id)
        return False
    return True


class _TabWatcher(QObject):
    def __init__(self, window: Any, menu: Any, state: _State) -> None:
        super().__init__(menu)
        self._window = window
        self._menu = menu
        self._state = state

    def on_current_changed(self, _index: int) -> None:
        if _qt_alive(self._menu):
            _sync(self._window, self._menu, self._state)


def _fill(window: Any, ctx: Any, menu: Any, nodes: Sequence[MenuNode], state: _State) -> None:
    for node in nodes:
        if node.kind == "separator":
            menu.addSeparator()
        elif node.kind == "submenu":
            submenu = menu.addMenu(node.title)
            submenu.setObjectName("formBuilder.menu.%s" % node.title)
            _fill(window, ctx, submenu, node.children, state)
        elif node.entry is not None and isinstance(node.entry.payload, FormMenuItem):
            _add_item(window, ctx, menu, node.entry.payload, state)
        elif node.entry is not None:
            _add(window, ctx, menu, node.entry.payload, state.actions)


def _add_item(window: Any, ctx: Any, menu: Any, item: FormMenuItem, state: _State) -> None:
    label = item.path[-1]
    hint = item.hint or _key_hint(item.command_id)
    if hint:
        label = "%s\t%s" % (label, hint)
    action = register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=menu,
        action_lookup=ctx.actions,
        action_id=item.command_id,
        label=label,
        shortcut=None,
        enabled=False,
        callback=lambda _checked=False, found=item: _run_item(window, found),
        shortcut_overrides=ctx.shortcut_overrides,
    )
    # A contributed item's key is a keys_ext row the form tab binds. Settings
    # re-applies keys to actions by id, so keep this one off the window.
    action.setShortcut(QKeySequence())
    action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
    state.actions[item.command_id] = action
    state.items[item.command_id] = item


def _key_hint(command_id: str) -> str:
    """The key of the keys_ext row with this id, shown in the menu."""
    from app.features.form_builder.integration.keys_ext import extra_commands

    for command in extra_commands():
        if command.command_id == command_id:
            return command.shortcut
    return ""


def _run_item(window: Any, item: FormMenuItem) -> None:
    surface = _active_form(window)
    if surface is None and item.target == FORM:
        return
    try:
        item.run(surface)
    except Exception:
        logger.exception("form menu item %s failed", item.command_id)


def _add(window: Any, ctx: Any, menu: Any, command: FormCommand, actions: Dict[str, Any]) -> None:
    hint = menu_hint(command)
    label = command.menu_path[-1]
    if hint:
        label = "%s\t%s" % (label, hint)
    shortcut = None if hint or command.kind != "new" else command.shortcut
    action = register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=menu,
        action_lookup=ctx.actions,
        action_id=command.command_id,
        label=label,
        shortcut=shortcut,
        enabled=False,
        callback=lambda _checked=False, command_id=command.command_id: _trigger(window, command_id),
        shortcut_overrides=ctx.shortcut_overrides,
    )
    if hint:
        # The key lives on a canvas or outline QShortcut, or on the shell
        # action. ``register_menu_action`` applied the effective map, which
        # holds the form rows, so clear it. Settings re-applies every menu
        # key later; a widget-scope context keeps that key off the window.
        action.setShortcut(QKeySequence())
        action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
    actions[command.command_id] = action


def _trigger(window: Any, command_id: str) -> None:
    surface = _active_form(window)
    if surface is None:
        return
    if request_for(command_id) is not None or command_id in CLIPBOARD_COMMAND_IDS:
        surface.dispatch(command_id)
        return
    if command_id == "form.action.viewXml":
        surface.toggle_source_view()
        return
    if command_id == "form.action.save":
        workflow = getattr(window, "_save_workflow", None)
        if workflow is not None:
            workflow.handle_save_action()
        return
    if command_id == "form.action.zoomIn":
        surface.zoom_in()
        return
    if command_id == "form.action.zoomOut":
        surface.zoom_out()
        return
    if command_id == "form.action.zoomReset":
        surface.zoom_to(1.0)
        return
    if command_id == "form.action.zoomToFit":
        surface.zoom_fit()
        return
    if command_id == "form.action.editText":
        surface.edit_text()


def _active_form(window: Any) -> Any:
    if not _qt_alive(window):
        return None
    manager = getattr(window, "_editor_manager", None)
    registry = getattr(window, "_tab_content_registry", None)
    if manager is None or registry is None:
        return None
    active = manager.active_tab()
    if active is None:
        return None
    surface = registry.surface_for_path(active.file_path)
    if isinstance(surface, FormSurface):
        return surface
    return None


def _sync(window: Any, menu: Any, state: _State) -> None:
    actions = state.actions
    surface = _active_form(window)
    visible = surface is not None
    sheet = surface.layout_offers() if surface is not None else None
    editable = bool(surface.can_edit_text()) if surface is not None else False
    menu_action = menu.menuAction()
    menu_action.setVisible(visible)
    by_id = {command.command_id: command for command in menu_commands()}
    for command_id, action in actions.items():
        item = state.items.get(command_id)
        if item is not None:
            _sync_item(action, item, surface)
            continue
        command = by_id.get(command_id)
        available = command.available if command is not None else False
        request = request_for(command_id)
        reason = ""
        if sheet is not None and request is not None:
            offer = gate(sheet, request)
            available = available and offer.enabled
            reason = offer.reason
        if surface is not None and command_id in CLIPBOARD_COMMAND_IDS:
            available = command_enabled(
                surface._session.document,
                surface._session.selection.state.ids,
                command_id,
                clipboard_has_fragment(),
            )
        text_block = command_id == "form.action.editText" and not editable
        action.setEnabled(visible and available and not text_block)
        action.setToolTip(reason)
    _tidy(menu)
    _sync_help(window, state, surface)


def _sync_item(action: Any, item: FormMenuItem, surface: Any) -> None:
    """A contributed item is absent, not disabled, when its runtime can't offer it."""
    offered = surface is not None and _asked(item.offered, item, surface, False)
    action.setVisible(offered)
    action.setEnabled(offered and _asked(item.enabled, item, surface, False))


def _asked(question: Any, item: FormMenuItem, surface: Any, otherwise: bool) -> bool:
    try:
        return bool(question(surface))
    except Exception:
        logger.exception("form menu item %s could not answer", item.command_id)
        return otherwise


def _tidy(menu: Any) -> bool:
    """Hide empty submenus and separators with nothing beside them. True when something shows."""
    shown = False
    waiting = None
    for action in menu.actions():
        if action.isSeparator():
            action.setVisible(False)
            waiting = action if shown else None
            continue
        submenu = action.menu()
        if submenu is not None:
            action.setVisible(_tidy(submenu))
        if not action.isVisible():
            continue
        if waiting is not None:
            waiting.setVisible(True)
            waiting = None
        shown = True
    return shown


def _sync_help(window: Any, state: _State, surface: Any) -> None:
    """Help items join the shell's Help menu the first time that menu exists."""
    if not state.help_items:
        return
    help_menu = state.menus.get("shell.menu.help")
    if help_menu is None:
        return
    if not state.help_attached:
        state.help_attached = True
        ctx = state.ctx
        for item in state.help_items:
            action = register_menu_action(
                qt_widgets=ctx.qt_widgets,
                menu=help_menu,
                action_lookup=ctx.actions,
                action_id=item.command_id,
                label=item.path[-1],
                shortcut=None,
                enabled=True,
                callback=lambda _checked=False, found=item: _run_item(window, found),
                shortcut_overrides=ctx.shortcut_overrides,
            )
            state.help_actions[item.command_id] = action
    for item in state.help_items:
        action = state.help_actions[item.command_id]
        action.setVisible(_asked(item.offered, item, surface, False))
        action.setEnabled(_asked(item.enabled, item, surface, False))
