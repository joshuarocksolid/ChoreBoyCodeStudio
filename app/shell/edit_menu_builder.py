"""Edit menu construction."""

from __future__ import annotations

from app.shell.menu_action_builder import register_menu_action
from app.shell.menu_build_context import MenuBuildContext


def build_edit_menu(ctx: MenuBuildContext) -> object:
    callbacks = ctx.callbacks
    edit_menu = ctx.menu_bar.addMenu("&Edit")
    edit_menu.setObjectName("shell.menu.edit")
    edit_menu.setToolTipsVisible(True)
    ctx.menus["shell.menu.edit"] = edit_menu

    register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=edit_menu,
        action_lookup=ctx.actions,
        action_id="shell.action.edit.undo",
        label="Undo",
        shortcut="Ctrl+Z",
        callback=callbacks.on_undo,
        shortcut_overrides=ctx.shortcut_overrides,
    )
    register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=edit_menu,
        action_lookup=ctx.actions,
        action_id="shell.action.edit.redo",
        label="Redo",
        shortcut="Ctrl+Shift+Z",
        callback=callbacks.on_redo,
        shortcut_overrides=ctx.shortcut_overrides,
    )
    edit_menu.addSeparator()

    # Shown only while a tab surface claims them. No shortcut, so native editors keep Ctrl+X/C/V/A and Delete.
    for action_id, label, callback in [
        ("shell.action.edit.cut", "Cut", callbacks.on_cut),
        ("shell.action.edit.copy", "Copy", callbacks.on_copy),
        ("shell.action.edit.paste", "Paste", callbacks.on_paste),
        ("shell.action.edit.delete", "Delete", callbacks.on_delete),
        ("shell.action.edit.selectAll", "Select All", callbacks.on_select_all),
    ]:
        register_menu_action(
            qt_widgets=ctx.qt_widgets,
            menu=edit_menu,
            action_lookup=ctx.actions,
            action_id=action_id,
            label=label,
            callback=callback,
        ).setVisible(False)
    edit_menu.addSeparator()

    for action_id, label, shortcut, callback in [
        ("shell.action.edit.find", "Find", "Ctrl+F", callbacks.on_find),
        ("shell.action.edit.replace", "Replace", "Ctrl+H", callbacks.on_replace),
        ("shell.action.edit.goToLine", "Go To Line", "Ctrl+G", callbacks.on_go_to_line),
        ("shell.action.edit.findInFiles", "Find in Files", "Ctrl+Shift+F", callbacks.on_find_in_files),
        ("shell.action.edit.findReferences", "Find References", "Shift+F12", callbacks.on_find_references),
        ("shell.action.edit.renameSymbol", "Rename Symbol", "F2", callbacks.on_rename_symbol),
        ("shell.action.edit.toggleComment", "Toggle Comment", "Ctrl+/", callbacks.on_toggle_comment),
        ("shell.action.edit.indent", "Indent", "Tab", callbacks.on_indent),
        ("shell.action.edit.outdent", "Outdent", "Shift+Tab", callbacks.on_outdent),
        (
            "shell.action.edit.pasteReindentedFlatPython",
            "Paste and Re-indent Flat Python",
            "Ctrl+Alt+V",
            callbacks.on_paste_reindented_flat_python,
        ),
        ("shell.action.edit.goToDefinition", "Go To Definition", "F12", callbacks.on_go_to_definition),
        ("shell.action.edit.signatureHelp", "Signature Help", "Ctrl+Shift+Space", callbacks.on_signature_help),
        ("shell.action.edit.hoverInfo", "Show Hover Info", "Ctrl+Shift+I", callbacks.on_hover_info),
    ]:
        register_menu_action(
            qt_widgets=ctx.qt_widgets,
            menu=edit_menu,
            action_lookup=ctx.actions,
            action_id=action_id,
            label=label,
            shortcut=shortcut,
            enabled=True,
            callback=callback,
            shortcut_overrides=ctx.shortcut_overrides,
        )

    return edit_menu
