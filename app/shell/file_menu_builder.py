"""File menu construction."""

from __future__ import annotations

from app.shell.menu_action_builder import register_menu_action
from app.shell.menu_build_context import MenuBuildContext


def build_file_menu(ctx: MenuBuildContext) -> object:
    callbacks = ctx.callbacks
    file_menu = ctx.menu_bar.addMenu("&File")
    file_menu.setObjectName("shell.menu.file")
    ctx.menus["shell.menu.file"] = file_menu

    if callbacks.on_file_menu_about_to_show is not None:
        file_menu.aboutToShow.connect(callbacks.on_file_menu_about_to_show)

    register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=file_menu,
        action_lookup=ctx.actions,
        action_id="shell.action.file.newProject",
        label="New Project...",
        shortcut="Ctrl+N",
        enabled=True,
        callback=callbacks.on_new_project,
        shortcut_overrides=ctx.shortcut_overrides,
    )
    register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=file_menu,
        action_lookup=ctx.actions,
        action_id="shell.action.file.newWindow",
        label="New Window",
        shortcut="Ctrl+Shift+N",
        enabled=True,
        callback=callbacks.on_new_window,
        shortcut_overrides=ctx.shortcut_overrides,
    )
    register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=file_menu,
        action_lookup=ctx.actions,
        action_id="shell.action.file.newProjectFromTemplate",
        label="New Project from Template...",
        enabled=True,
        callback=callbacks.on_new_project_from_template,
    )
    file_menu.addSeparator()
    register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=file_menu,
        action_lookup=ctx.actions,
        action_id="shell.action.file.openProject",
        label="Open Project...",
        shortcut="Ctrl+O",
        enabled=True,
        callback=callbacks.on_open_project,
        shortcut_overrides=ctx.shortcut_overrides,
    )
    register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=file_menu,
        action_lookup=ctx.actions,
        action_id="shell.action.file.openFile",
        label="Open File...",
        shortcut="Ctrl+Shift+O",
        enabled=True,
        callback=callbacks.on_open_file,
        shortcut_overrides=ctx.shortcut_overrides,
    )
    open_recent_menu = file_menu.addMenu("Open Recent")
    open_recent_menu.setObjectName("shell.menu.file.openRecent")
    ctx.menus["shell.menu.file.openRecent"] = open_recent_menu

    quick_open_action = register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=file_menu,
        action_lookup=ctx.actions,
        action_id="shell.action.file.quickOpen",
        label="Quick Open...",
        shortcut="Ctrl+P",
        enabled=True,
        callback=callbacks.on_quick_open,
        shortcut_overrides=ctx.shortcut_overrides,
    )
    quick_open_action.setToolTip("Search project files by name and open the selected file.")
    quick_open_action.setStatusTip("Search project files by name and open the selected file.")

    global_history_action = register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=file_menu,
        action_lookup=ctx.actions,
        action_id="shell.action.file.globalHistory",
        label="Open Global History...",
        enabled=True,
        callback=callbacks.on_open_global_history,
    )
    global_history_tip = "Search saved local-history entries across projects, including moved or deleted files."
    global_history_action.setToolTip(global_history_tip)
    global_history_action.setStatusTip(global_history_tip)

    file_menu.addSeparator()
    register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=file_menu,
        action_lookup=ctx.actions,
        action_id="shell.action.file.save",
        label="Save",
        shortcut="Ctrl+S",
        enabled=True,
        callback=callbacks.on_save,
        shortcut_overrides=ctx.shortcut_overrides,
    )
    register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=file_menu,
        action_lookup=ctx.actions,
        action_id="shell.action.file.saveAs",
        label="Save As...",
    )
    register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=file_menu,
        action_lookup=ctx.actions,
        action_id="shell.action.file.saveAll",
        label="Save All",
        shortcut="Ctrl+Shift+S",
        enabled=True,
        callback=callbacks.on_save_all,
        shortcut_overrides=ctx.shortcut_overrides,
    )

    auto_save_action = ctx.qt_widgets.QAction("Auto Save", file_menu)
    auto_save_action.setObjectName("shell.action.file.autoSave")
    auto_save_action.setCheckable(True)
    auto_save_action.setChecked(False)
    auto_save_action.setEnabled(True)
    if callbacks.on_toggle_auto_save is not None:
        auto_save_action.toggled.connect(callbacks.on_toggle_auto_save)
    file_menu.addAction(auto_save_action)
    ctx.actions["shell.action.file.autoSave"] = auto_save_action

    file_menu.addSeparator()
    register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=file_menu,
        action_lookup=ctx.actions,
        action_id="shell.action.file.settings",
        label="Settings...",
        enabled=True,
        callback=callbacks.on_open_settings,
    )
    file_menu.addSeparator()
    register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=file_menu,
        action_lookup=ctx.actions,
        action_id="shell.action.file.exit",
        label="Exit",
        shortcut="Ctrl+Q",
        enabled=True,
        callback=callbacks.on_exit,
        shortcut_overrides=ctx.shortcut_overrides,
    )
    return file_menu
