"""Form menu from the command table (UX-SHELL-004).

The shell does not know this menu. It is hidden unless a form tab is active.
Commands whose gesture does not exist yet stay disabled.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.features.form_builder.engine.shell_commands import FormCommand, menu_commands, menu_hint
from app.features.form_builder.integration.surface import FormSurface
from app.shell.menu_action_builder import register_menu_action
from app.shell.menus import register_menu_contributor


def register_form_menu(window: Any) -> None:
    register_menu_contributor(
        "form-builder.menu",
        "shell.menu.view",
        lambda ctx: _build(window, ctx),
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


def _build(window: Any, ctx: Any) -> None:
    if not _qt_alive(window):
        return
    menu = ctx.menu_bar.addMenu("Form")
    menu.setObjectName("formBuilder.menu")
    ctx.menus["formBuilder.menu"] = menu
    actions: Dict[str, Any] = {}
    _fill(window, ctx, menu, menu_commands(), (), actions)
    menu.aboutToShow.connect(lambda: _sync(window, menu, actions))
    tabs = getattr(window, "_editor_tabs_widget", None)
    if tabs is not None and _qt_alive(tabs):
        tabs.currentChanged.connect(lambda _index: _sync(window, menu, actions))
    _sync(window, menu, actions)


def _fill(
    window: Any,
    ctx: Any,
    menu: Any,
    commands: Tuple[FormCommand, ...],
    prefix: Tuple[str, ...],
    actions: Dict[str, Any],
) -> None:
    index = 0
    items = list(commands)
    while index < len(items):
        command = items[index]
        path = command.menu_path
        if path[: len(prefix)] != prefix:
            break
        if len(path) == len(prefix) + 1:
            _add(window, ctx, menu, command, actions)
            index += 1
            continue
        title = path[len(prefix)]
        group: List[FormCommand] = []
        head = prefix + (title,)
        while index < len(items) and items[index].menu_path[: len(head)] == head:
            group.append(items[index])
            index += 1
        submenu = menu.addMenu(title)
        submenu.setObjectName("formBuilder.menu.%s" % title)
        _fill(window, ctx, submenu, tuple(group), head, actions)


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
    actions[command.command_id] = action


def _trigger(window: Any, command_id: str) -> None:
    surface = _active_form(window)
    if surface is None:
        return
    if command_id == "form.action.viewXml":
        surface.toggle_source_view()
        return
    if command_id == "form.action.save":
        workflow = getattr(window, "_save_workflow", None)
        if workflow is not None:
            workflow.handle_save_action()


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


def _sync(window: Any, menu: Any, actions: Dict[str, Any]) -> None:
    visible = _active_form(window) is not None
    menu_action = menu.menuAction()
    menu_action.setVisible(visible)
    by_id = {command.command_id: command for command in menu_commands()}
    for command_id, action in actions.items():
        command = by_id.get(command_id)
        available = command.available if command is not None else False
        action.setEnabled(visible and available)
