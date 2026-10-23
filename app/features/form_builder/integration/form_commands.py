"""The form designer's commands as data. No Qt.

``FORM_COMMANDS`` is the only list of form commands. Every other view of them, such as
the shortcut rows from ``form_command_set``, derives from it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from app.shell.shortcut_preferences import ShortcutCommand, ShortcutScope, default_shortcut_map

FORM_CATEGORY = "Form designer"


@dataclass(frozen=True)
class OwnKey:
    """A form-only key, rebindable in Settings once its command is ready."""

    default: str
    scopes: tuple[ShortcutScope, ...]
    shadows: tuple[str, ...] = ()


@dataclass(frozen=True)
class SharedKey:
    """The shell action's own key. The form claims that action and adds no binding."""

    shell_action_id: str
    scopes: tuple[ShortcutScope, ...] = ("form_tab",)


@dataclass(frozen=True)
class InertKeys:
    """Shell keys that do nothing in a form tab. The form claims them while it has focus."""

    shell_action_ids: tuple[str, ...]


Key = Union[OwnKey, SharedKey, InertKeys, None]


@dataclass(frozen=True)
class InFormMenu:
    path: tuple[str, ...] = ()
    checkable: bool = False
    separator_before: bool = False


@dataclass(frozen=True)
class InShellMenu:
    shell_action_id: str


Placement = Union[InFormMenu, InShellMenu, None]


@dataclass(frozen=True)
class FormCommand:
    command_id: str
    label: str
    key: Key
    placement: Placement
    ready: bool


_CANVAS_OUTLINE: tuple[ShortcutScope, ...] = ("canvas", "outline")
_FORM_TAB: tuple[ShortcutScope, ...] = ("form_tab",)
_CANVAS: tuple[ShortcutScope, ...] = ("canvas",)
_OUTLINE: tuple[ShortcutScope, ...] = ("outline",)

_LAYOUT = ("Layout",)
_SIZE = ("Size",)
_OVERLAYS = ("Overlays",)
_PREVIEW_OPTIONS = ("Preview options",)

_GOTO_SYMBOL = "shell.action.tools.gotoSymbolInFile"
_TOGGLE_SOURCE = "shell.action.view.markdownTogglePreview"
_FOCUS_GROUP_1 = "shell.action.view.focusFirstEditorGroup"
_FOCUS_GROUP_2 = "shell.action.view.focusSecondEditorGroup"
_INDENT = "shell.action.edit.indent"
_OUTDENT = "shell.action.edit.outdent"


def _arrow_rows(
    prefix: str,
    label: str,
    modifiers: str,
    scopes: tuple[ShortcutScope, ...],
    directions: tuple[str, ...] = ("Left", "Right", "Up", "Down"),
) -> tuple[FormCommand, ...]:
    return tuple(
        FormCommand(
            f"{prefix}.{direction.lower()}",
            f"{label} {direction.lower()}",
            OwnKey(modifiers + direction, scopes),
            None,
            ready=False,
        )
        for direction in directions
    )


FORM_COMMANDS: tuple[FormCommand, ...] = (
    FormCommand("form.insertWidget", "Insert widget…", OwnKey("/", _CANVAS_OUTLINE), InFormMenu(), ready=False),
    FormCommand("form.goToWidget", "Go to widget…", SharedKey(_GOTO_SYMBOL), InFormMenu(), ready=False),
    FormCommand(
        "form.layout.vertical",
        "Vertical",
        OwnKey("Ctrl+2", _CANVAS_OUTLINE, shadows=(_FOCUS_GROUP_2,)),
        InFormMenu(_LAYOUT, separator_before=True),
        ready=False,
    ),
    FormCommand(
        "form.layout.horizontal",
        "Horizontal",
        OwnKey("Ctrl+1", _CANVAS_OUTLINE, shadows=(_FOCUS_GROUP_1,)),
        InFormMenu(_LAYOUT),
        ready=False,
    ),
    FormCommand("form.layout.grid", "Grid", OwnKey("Ctrl+5", _CANVAS_OUTLINE), InFormMenu(_LAYOUT), ready=False),
    FormCommand("form.layout.form", "Form", OwnKey("Ctrl+6", _CANVAS_OUTLINE), InFormMenu(_LAYOUT), ready=False),
    FormCommand(
        "form.layout.hsplitter",
        "Horizontal splitter",
        OwnKey("Ctrl+3", _CANVAS_OUTLINE),
        InFormMenu(_LAYOUT),
        ready=False,
    ),
    FormCommand(
        "form.layout.vsplitter",
        "Vertical splitter",
        OwnKey("Ctrl+4", _CANVAS_OUTLINE),
        InFormMenu(_LAYOUT),
        ready=False,
    ),
    FormCommand(
        "form.layout.wrap",
        "Wrap in…",
        OwnKey("Ctrl+Shift+G", _CANVAS_OUTLINE),
        InFormMenu(_LAYOUT, separator_before=True),
        ready=False,
    ),
    FormCommand(
        "form.layout.unwrap",
        "Unwrap",
        OwnKey("Ctrl+Shift+B", _CANVAS_OUTLINE),
        InFormMenu(_LAYOUT),
        ready=False,
    ),
    FormCommand("form.layout.remove", "Remove layout…", None, InFormMenu(_LAYOUT), ready=False),
    FormCommand(
        "form.layout.adjustSize",
        "Adjust size",
        OwnKey("Ctrl+J", _CANVAS_OUTLINE),
        InFormMenu(_LAYOUT, separator_before=True),
        ready=False,
    ),
    FormCommand("form.layout.simplifyGrid", "Simplify grid", None, InFormMenu(_LAYOUT), ready=False),
    FormCommand("form.size.widthHug", "Width: Hug", None, InFormMenu(_SIZE), ready=False),
    FormCommand("form.size.widthFill", "Width: Fill", None, InFormMenu(_SIZE), ready=False),
    FormCommand("form.size.widthFixed", "Width: Fixed", None, InFormMenu(_SIZE), ready=False),
    FormCommand("form.size.heightHug", "Height: Hug", None, InFormMenu(_SIZE, separator_before=True), ready=False),
    FormCommand("form.size.heightFill", "Height: Fill", None, InFormMenu(_SIZE), ready=False),
    FormCommand("form.size.heightFixed", "Height: Fixed", None, InFormMenu(_SIZE), ready=False),
    FormCommand("form.size.reset", "Reset size", None, InFormMenu(_SIZE, separator_before=True), ready=False),
    FormCommand(
        "form.overlay.tabOrder",
        "Tab order",
        OwnKey("F8", _FORM_TAB),
        InFormMenu(_OVERLAYS, checkable=True),
        ready=False,
    ),
    FormCommand(
        "form.overlay.buddies",
        "Buddies",
        OwnKey("F7", _FORM_TAB),
        InFormMenu(_OVERLAYS, checkable=True),
        ready=False,
    ),
    FormCommand(
        "form.preview",
        "Preview",
        OwnKey("Ctrl+Shift+R", _FORM_TAB),
        InFormMenu(separator_before=True),
        ready=False,
    ),
    FormCommand("form.preview.textSize", "Text size", None, InFormMenu(_PREVIEW_OPTIONS), ready=False),
    FormCommand("form.preview.screenScale", "Screen scale", None, InFormMenu(_PREVIEW_OPTIONS), ready=False),
    FormCommand(
        "form.viewXml",
        "View XML",
        SharedKey(_TOGGLE_SOURCE),
        InFormMenu(checkable=True, separator_before=True),
        ready=True,
    ),
    FormCommand("form.settings", "Form settings…", None, InFormMenu(), ready=False),
    FormCommand("form.createWindowClass", "Create window class…", None, InFormMenu(), ready=True),
    FormCommand("form.undo", "Undo", SharedKey("shell.action.edit.undo"), None, ready=True),
    FormCommand("form.redo", "Redo", SharedKey("shell.action.edit.redo"), None, ready=True),
    FormCommand(
        "form.cut",
        "Cut",
        OwnKey("Ctrl+X", _CANVAS_OUTLINE),
        InShellMenu("shell.action.edit.cut"),
        ready=False,
    ),
    FormCommand(
        "form.copy",
        "Copy",
        OwnKey("Ctrl+C", _CANVAS_OUTLINE),
        InShellMenu("shell.action.edit.copy"),
        ready=False,
    ),
    FormCommand(
        "form.paste",
        "Paste",
        OwnKey("Ctrl+V", _CANVAS_OUTLINE),
        InShellMenu("shell.action.edit.paste"),
        ready=False,
    ),
    FormCommand(
        "form.delete",
        "Delete",
        OwnKey("Delete", _CANVAS_OUTLINE),
        InShellMenu("shell.action.edit.delete"),
        ready=False,
    ),
    FormCommand(
        "form.selectSiblings",
        "Select all",
        OwnKey("Ctrl+A", _CANVAS_OUTLINE),
        InShellMenu("shell.action.edit.selectAll"),
        ready=False,
    ),
    FormCommand("form.findWidget", "Find widget", SharedKey("shell.action.edit.find"), None, ready=False),
    FormCommand(
        "form.rename",
        "Rename",
        SharedKey("shell.action.edit.renameSymbol", ("canvas", "outline", "inspector")),
        None,
        ready=False,
    ),
    FormCommand("form.zoomIn", "Zoom in", SharedKey("shell.action.view.zoomIn"), None, ready=False),
    FormCommand("form.zoomOut", "Zoom out", SharedKey("shell.action.view.zoomOut"), None, ready=False),
    FormCommand("form.zoomReset", "Zoom 100%", SharedKey("shell.action.view.zoomReset"), None, ready=False),
    FormCommand("form.duplicate", "Duplicate", OwnKey("Ctrl+D", _CANVAS_OUTLINE), None, ready=False),
    FormCommand("form.zoomFit", "Zoom to fit", OwnKey("Ctrl+9", _FORM_TAB), None, ready=False),
    FormCommand("form.editText", "Edit text", OwnKey("Enter", _CANVAS), None, ready=False),
    FormCommand("form.escape", "Close or select parent", OwnKey("Esc", _FORM_TAB), None, ready=True),
    FormCommand("form.nextWidget", "Next widget", OwnKey("Tab", _CANVAS, shadows=(_INDENT,)), None, ready=False),
    FormCommand(
        "form.previousWidget",
        "Previous widget",
        OwnKey("Shift+Tab", _CANVAS, shadows=(_OUTDENT,)),
        None,
        ready=False,
    ),
    FormCommand("form.nest", "Nest", SharedKey(_INDENT, _OUTLINE), None, ready=False),
    FormCommand("form.unnest", "Un-nest", SharedKey(_OUTDENT, _OUTLINE), None, ready=False),
    *_arrow_rows("form.select", "Select nearest", "", _CANVAS),
    *_arrow_rows("form.extend", "Add nearest", "Shift+", _CANVAS),
    *_arrow_rows("form.move", "Move", "Alt+", _CANVAS, ("Left", "Right")),
    *_arrow_rows("form.move", "Move", "Alt+", _CANVAS_OUTLINE, ("Up", "Down")),
    *_arrow_rows("form.nudge", "Nudge 1 px", "Alt+Shift+", _CANVAS),
    *_arrow_rows("form.resize", "Resize", "Ctrl+Shift+", _CANVAS),
    FormCommand("form.leaveOverlay", "Leave overlay", OwnKey("F3", _FORM_TAB), None, ready=False),
    FormCommand("form.overlay.connections", "Connections", OwnKey("F4", _FORM_TAB), None, ready=False),
    FormCommand("form.preview.twoWidths", "Two widths", OwnKey("Ctrl+K, W", _FORM_TAB), None, ready=False),
    FormCommand("form.focus.outline", "Focus outline", OwnKey("Alt+1", _FORM_TAB), None, ready=True),
    FormCommand("form.focus.insert", "Focus insert", OwnKey("Alt+2", _FORM_TAB), None, ready=True),
    FormCommand("form.focus.canvas", "Focus canvas", OwnKey("Alt+3", _FORM_TAB), None, ready=True),
    FormCommand("form.focus.inspector", "Focus inspector", OwnKey("Alt+4", _FORM_TAB), None, ready=True),
    FormCommand(
        "form.inert",
        "Not used in the form designer",
        InertKeys(
            (
                "shell.action.edit.replace",
                "shell.action.edit.goToLine",
                "shell.action.edit.toggleComment",
                "shell.action.edit.pasteReindentedFlatPython",
                "shell.action.edit.signatureHelp",
                "shell.action.run.toggleBreakpoint",
            )
        ),
        None,
        ready=True,
    ),
)


def form_command_set() -> tuple[ShortcutCommand, ...]:
    """Shortcut catalog rows derived from ``FORM_COMMANDS``.

    An own key is one row, reserved until its command is ready. Each inert key is a
    form-tab row on the shell key that shadows the shell action. It is reserved because
    the key keeps its shell binding. A shared key adds no row.
    """
    shell_keys = default_shortcut_map()
    rows: list[ShortcutCommand] = []
    for command in FORM_COMMANDS:
        key = command.key
        if isinstance(key, OwnKey):
            rows.append(
                ShortcutCommand(
                    command.command_id,
                    command.label,
                    key.default,
                    FORM_CATEGORY,
                    scopes=key.scopes,
                    shadows=key.shadows,
                    reserved=not command.ready,
                )
            )
        elif isinstance(key, InertKeys):
            rows.extend(
                ShortcutCommand(
                    f"{command.command_id}:{shell_action_id}",
                    command.label,
                    shell_keys[shell_action_id],
                    FORM_CATEGORY,
                    scopes=_FORM_TAB,
                    shadows=(shell_action_id,),
                    reserved=True,
                )
                for shell_action_id in key.shell_action_ids
            )
    return tuple(rows)


__all__ = [
    "FORM_CATEGORY",
    "FORM_COMMANDS",
    "FormCommand",
    "InFormMenu",
    "InShellMenu",
    "InertKeys",
    "Key",
    "OwnKey",
    "Placement",
    "SharedKey",
    "form_command_set",
]
