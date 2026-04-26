"""View menu construction."""

from __future__ import annotations

from typing import Any

from app.shell.menu_action_builder import register_menu_action
from app.shell.menu_build_context import MenuBuildContext


def build_view_menu(ctx: MenuBuildContext) -> object:
    callbacks = ctx.callbacks
    view_menu = ctx.menu_bar.addMenu("&View")
    view_menu.setObjectName("shell.menu.view")
    ctx.menus["shell.menu.view"] = view_menu

    register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=view_menu,
        action_lookup=ctx.actions,
        action_id="shell.action.view.resetLayout",
        label="Reset Layout",
        callback=callbacks.on_reset_layout,
    )
    register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=view_menu,
        action_lookup=ctx.actions,
        action_id="shell.action.view.showTestExplorer",
        label="Show Test Explorer",
        shortcut="Ctrl+Shift+X",
        enabled=True,
        callback=callbacks.on_show_test_explorer,
        shortcut_overrides=ctx.shortcut_overrides,
    )
    view_menu.addSeparator()
    _build_theme_submenu(ctx, view_menu)
    view_menu.addSeparator()

    for action_id, label, shortcut, callback in [
        (
            "shell.action.view.markdownTogglePreview",
            "Markdown: Toggle Preview",
            "Ctrl+Shift+V",
            callbacks.on_markdown_toggle_preview,
        ),
        (
            "shell.action.view.markdownShowSource",
            "Markdown: Show Source",
            "",
            callbacks.on_markdown_show_source,
        ),
        (
            "shell.action.view.markdownShowPreview",
            "Markdown: Show Preview",
            "",
            callbacks.on_markdown_show_preview,
        ),
        (
            "shell.action.view.markdownShowSplit",
            "Markdown: Show Split View",
            "Ctrl+K, V",
            callbacks.on_markdown_show_split,
        ),
    ]:
        register_menu_action(
            qt_widgets=ctx.qt_widgets,
            menu=view_menu,
            action_lookup=ctx.actions,
            action_id=action_id,
            label=label,
            shortcut=shortcut,
            enabled=False,
            callback=callback,
            shortcut_overrides=ctx.shortcut_overrides,
        )

    view_menu.addSeparator()

    for action_id, label, shortcut, callback in [
        ("shell.action.view.zoomIn", "Zoom In", "Ctrl+=", callbacks.on_zoom_in),
        ("shell.action.view.zoomOut", "Zoom Out", "Ctrl+-", callbacks.on_zoom_out),
        ("shell.action.view.zoomReset", "Reset Zoom", "Ctrl+0", callbacks.on_zoom_reset),
    ]:
        register_menu_action(
            qt_widgets=ctx.qt_widgets,
            menu=view_menu,
            action_lookup=ctx.actions,
            action_id=action_id,
            label=label,
            shortcut=shortcut,
            enabled=True,
            callback=callback,
            shortcut_overrides=ctx.shortcut_overrides,
        )

    return view_menu


def _build_theme_submenu(ctx: MenuBuildContext, view_menu: Any) -> object:
    callbacks = ctx.callbacks
    theme_menu = view_menu.addMenu("Theme")
    theme_menu.setObjectName("shell.menu.view.theme")
    ctx.menus["shell.menu.view.theme"] = theme_menu

    action_group = ctx.qt_widgets.QActionGroup(theme_menu)
    action_group.setExclusive(True)
    for action_id, label, mode_callback in [
        ("shell.action.view.theme.system", "System", callbacks.on_set_theme_system),
        ("shell.action.view.theme.light", "Light", callbacks.on_set_theme_light),
        ("shell.action.view.theme.dark", "Dark", callbacks.on_set_theme_dark),
    ]:
        action = ctx.qt_widgets.QAction(label, theme_menu)
        action.setObjectName(action_id)
        action.setCheckable(True)
        action.setEnabled(True)
        if mode_callback is not None:
            action.triggered.connect(mode_callback)
        action_group.addAction(action)
        theme_menu.addAction(action)
        ctx.actions[action_id] = action

    return theme_menu
