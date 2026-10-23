"""Form command table (UX-KEY-001..004, UX-SHELL-004).

One row feeds the Form menu, the Settings shortcut list, and the collision
test. Shell-owned keys are not registered again. Keys whose gesture does not
exist yet stay in the table with ``available`` false. Inert shell keys are
listed and not registered.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence, Tuple


FORM_SHORTCUT_CATEGORY = "Form designer"

INERT_STATUS = "Not used in the form designer. Ctrl+R goes to a widget."

_WIDGET = frozenset({"canvas", "outline", "inspector"})


@dataclass(frozen=True)
class FormCommand:
    """One form command.

    ``kind`` is ``new`` (registered), ``shell`` (the shell already owns the
    key), ``inert`` (the shell key does nothing here), or ``qt`` (Qt draws
    the menu). ``menu_path`` is empty when the command is not in the Form
    menu. A path of one item is a top-level item. A longer path is a submenu.
    """

    command_id: str
    label: str
    shortcut: str
    contexts: Tuple[str, ...]
    menu_path: Tuple[str, ...]
    available: bool
    kind: str
    shell_action_id: str = ""


def _row(
    command_id: str,
    label: str,
    shortcut: str,
    contexts: Tuple[str, ...],
    *,
    menu: Tuple[str, ...] = (),
    available: bool = False,
    kind: str = "new",
    shell_action_id: str = "",
) -> FormCommand:
    return FormCommand(
        command_id=command_id,
        label=label,
        shortcut=shortcut,
        contexts=contexts,
        menu_path=menu,
        available=available,
        kind=kind,
        shell_action_id=shell_action_id,
    )


def _directions(
    prefix: str,
    label: str,
    chord: str,
    contexts: Tuple[str, ...],
    names: Tuple[str, ...] = ("Up", "Down", "Left", "Right"),
) -> Tuple[FormCommand, ...]:
    rows = []
    for name in names:
        shortcut = name if not chord else "%s+%s" % (chord, name)
        rows.append(
            _row(
                "form.action.%s%s" % (prefix, name),
                "%s %s" % (label, name.lower()),
                shortcut,
                contexts,
            )
        )
    return tuple(rows)


_CANVAS = ("canvas",)
_CANVAS_OUTLINE = ("canvas", "outline")
_FORM = ("form_tab",)

FORM_COMMANDS: Tuple[FormCommand, ...] = (
    _row("form.action.insert", "Insert widget\u2026", "/", _CANVAS_OUTLINE, menu=("Insert widget\u2026",)),
    _row(
        "form.action.goToWidget",
        "Go to widget\u2026",
        "Ctrl+R",
        _FORM,
        menu=("Go to widget\u2026",),
        kind="shell",
        shell_action_id="shell.action.tools.gotoSymbolInFile",
    ),
    _row("form.action.layoutVertical", "Vertical", "Ctrl+2", _CANVAS_OUTLINE, menu=("Layout", "Vertical")),
    _row("form.action.layoutHorizontal", "Horizontal", "Ctrl+1", _CANVAS_OUTLINE, menu=("Layout", "Horizontal")),
    _row("form.action.layoutGrid", "Grid", "Ctrl+5", _CANVAS_OUTLINE, menu=("Layout", "Grid")),
    _row("form.action.layoutForm", "Form", "Ctrl+6", _CANVAS_OUTLINE, menu=("Layout", "Form")),
    _row(
        "form.action.layoutHorizontalSplitter",
        "Horizontal splitter",
        "Ctrl+3",
        _CANVAS_OUTLINE,
        menu=("Layout", "Horizontal splitter"),
    ),
    _row(
        "form.action.layoutVerticalSplitter",
        "Vertical splitter",
        "Ctrl+4",
        _CANVAS_OUTLINE,
        menu=("Layout", "Vertical splitter"),
    ),
    _row("form.action.wrap", "Wrap in\u2026", "Ctrl+Shift+G", _CANVAS_OUTLINE, menu=("Layout", "Wrap in\u2026")),
    _row("form.action.unwrap", "Unwrap", "Ctrl+Shift+B", _CANVAS_OUTLINE, menu=("Layout", "Unwrap")),
    _row("form.action.removeLayout", "Remove layout\u2026", "", _CANVAS_OUTLINE, menu=("Layout", "Remove layout\u2026")),
    _row("form.action.adjustSize", "Adjust size", "Ctrl+J", _CANVAS_OUTLINE, menu=("Layout", "Adjust size")),
    _row("form.action.simplifyGrid", "Simplify grid", "", _CANVAS_OUTLINE, menu=("Layout", "Simplify grid")),
    _row("form.action.sizeHugWidth", "Hug width", "", _CANVAS_OUTLINE, menu=("Size", "Hug width")),
    _row("form.action.sizeHugHeight", "Hug height", "", _CANVAS_OUTLINE, menu=("Size", "Hug height")),
    _row("form.action.sizeFillWidth", "Fill width", "", _CANVAS_OUTLINE, menu=("Size", "Fill width")),
    _row("form.action.sizeFillHeight", "Fill height", "", _CANVAS_OUTLINE, menu=("Size", "Fill height")),
    _row("form.action.sizeFixedWidth", "Fixed width", "", _CANVAS_OUTLINE, menu=("Size", "Fixed width")),
    _row("form.action.sizeFixedHeight", "Fixed height", "", _CANVAS_OUTLINE, menu=("Size", "Fixed height")),
    _row("form.action.sizeReset", "Reset size", "", _CANVAS_OUTLINE, menu=("Size", "Reset size")),
    _row("form.action.tabOrder", "Tab order", "F8", _FORM, menu=("Overlays", "Tab order")),
    _row("form.action.buddies", "Buddies", "F7", _FORM, menu=("Overlays", "Buddies")),
    _row("form.action.connections", "Connections", "F4", _FORM, menu=("Overlays", "Connections")),
    _row("form.action.preview", "Preview", "Ctrl+Shift+R", _FORM, menu=("Preview",)),
    _row("form.action.textSize", "Text size", "", _FORM, menu=("Preview options", "Text size")),
    _row("form.action.screenScale", "Screen scale", "", _FORM, menu=("Preview options", "Screen scale")),
    _row("form.action.twoWidths", "Two widths", "Ctrl+K, W", _FORM, menu=("Preview options", "Two widths")),
    _row(
        "form.action.viewXml",
        "View XML",
        "Ctrl+Shift+V",
        _FORM,
        menu=("View XML",),
        available=True,
        kind="shell",
        shell_action_id="shell.action.view.markdownTogglePreview",
    ),
    _row("form.action.formSettings", "Form settings\u2026", "", _FORM, menu=("Form settings\u2026",)),
    _row("form.action.createWindowClass", "Create window class\u2026", "", _FORM, menu=("Create window class\u2026",)),
    _row("form.action.selectAllSiblings", "Select all siblings", "Ctrl+A", _CANVAS_OUTLINE),
    _row("form.action.duplicate", "Duplicate", "Ctrl+D", _CANVAS_OUTLINE),
    _row("form.action.editText", "Edit text or enter container", "Return", _CANVAS),
    _row("form.action.escape", "Close or select parent", "Esc", ("canvas", "outline", "inspector", "form_tab")),
    _row("form.action.selectNext", "Select next widget", "Tab", _CANVAS),
    _row("form.action.selectPrevious", "Select previous widget", "Shift+Tab", _CANVAS),
    _row("form.action.zoomToFit", "Zoom to fit", "Ctrl+9", _FORM),
    _row("form.action.leaveOverlay", "Leave overlay", "F3", _FORM),
    _row("form.action.focusOutline", "Focus outline", "Alt+1", _FORM),
    _row("form.action.focusInsert", "Focus insert", "Alt+2", _FORM),
    _row("form.action.focusCanvas", "Focus canvas", "Alt+3", _FORM),
    _row("form.action.focusInspector", "Focus inspector", "Alt+4", _FORM),
    _row("form.action.zoomWheel", "Zoom around the pointer", "", _CANVAS),
    *_directions("select", "Select nearest", "", _CANVAS),
    *_directions("outlineMove", "Outline row", "", ("outline",)),
    *_directions("extend", "Add to selection", "Shift", _CANVAS),
    *_directions("moveOrNudge", "Move or nudge", "Alt", _CANVAS_OUTLINE, ("Up", "Down")),
    *_directions("moveOrNudge", "Move or nudge", "Alt", _CANVAS, ("Left", "Right")),
    *_directions("nudgeOne", "Nudge by 1 px", "Alt+Shift", _CANVAS),
    *_directions("resize", "Resize", "Ctrl+Shift", _CANVAS),
    _row(
        "form.action.outlineNest",
        "Nest into previous sibling",
        "Tab",
        ("outline",),
        kind="shell",
        shell_action_id="shell.action.edit.indent",
    ),
    _row(
        "form.action.outlineUnnest",
        "Un-nest",
        "Shift+Tab",
        ("outline",),
        kind="shell",
        shell_action_id="shell.action.edit.outdent",
    ),
    _row(
        "form.action.save",
        "Save",
        "Ctrl+S",
        _FORM,
        kind="shell",
        shell_action_id="shell.action.file.save",
        available=True,
    ),
    _row(
        "form.action.find",
        "Find widget",
        "Ctrl+F",
        _FORM,
        kind="shell",
        shell_action_id="shell.action.edit.find",
    ),
    _row(
        "form.action.rename",
        "Rename",
        "F2",
        ("canvas", "outline", "inspector"),
        kind="shell",
        shell_action_id="shell.action.edit.renameSymbol",
    ),
    _row("form.action.contextMenu", "Context menu", "Shift+F10", _CANVAS_OUTLINE, kind="qt"),
    _row("form.action.contextMenuKey", "Context menu key", "Menu", _CANVAS_OUTLINE, kind="qt"),
    _row(
        "form.action.saveAll",
        "Save all",
        "Ctrl+Shift+S",
        ("any",),
        kind="shell",
        available=True,
        shell_action_id="shell.action.file.saveAll",
    ),
    _row(
        "form.action.closeTab",
        "Close tab",
        "Ctrl+W",
        ("any",),
        kind="shell",
        available=True,
        shell_action_id="shell.shortcut.closeTab",
    ),
    _row(
        "form.action.undo",
        "Undo",
        "Ctrl+Z",
        _FORM,
        kind="shell",
        available=True,
        shell_action_id="shell.action.edit.undo",
    ),
    _row(
        "form.action.redo",
        "Redo",
        "Ctrl+Shift+Z",
        _FORM,
        kind="shell",
        available=True,
        shell_action_id="shell.action.edit.redo",
    ),
    _row("form.action.cut", "Cut", "Ctrl+X", _CANVAS_OUTLINE, kind="shell"),
    _row("form.action.copy", "Copy", "Ctrl+C", _CANVAS_OUTLINE, kind="shell"),
    _row("form.action.paste", "Paste", "Ctrl+V", _CANVAS_OUTLINE, kind="shell"),
    _row("form.action.delete", "Delete", "Delete", _CANVAS_OUTLINE, kind="shell"),
    _row("form.action.backspace", "Backspace", "Backspace", _CANVAS_OUTLINE, kind="shell"),
    _row(
        "form.action.zoomIn",
        "Zoom in",
        "Ctrl+=",
        _FORM,
        kind="shell",
        available=True,
        shell_action_id="shell.action.view.zoomIn",
    ),
    _row(
        "form.action.zoomOut",
        "Zoom out",
        "Ctrl+-",
        _FORM,
        kind="shell",
        available=True,
        shell_action_id="shell.action.view.zoomOut",
    ),
    _row(
        "form.action.zoomReset",
        "Zoom 100%",
        "Ctrl+0",
        _FORM,
        kind="shell",
        available=True,
        shell_action_id="shell.action.view.zoomReset",
    ),
    _row(
        "form.action.run",
        "Run",
        "F5",
        _FORM,
        kind="shell",
        available=True,
        shell_action_id="shell.action.run.run",
    ),
    _row(
        "form.action.runProject",
        "Run project",
        "Shift+F5",
        ("any",),
        kind="shell",
        available=True,
        shell_action_id="shell.action.run.runProject",
    ),
    _row(
        "form.action.debug",
        "Debug the active file",
        "Ctrl+F5",
        ("any",),
        kind="shell",
        available=True,
        shell_action_id="shell.action.run.debug",
    ),
    _row(
        "form.action.debugProject",
        "Debug the project",
        "Ctrl+Shift+F5",
        ("any",),
        kind="shell",
        available=True,
        shell_action_id="shell.action.run.debugProject",
    ),
    _row(
        "form.action.stop",
        "Stop",
        "Shift+F2",
        ("any",),
        kind="shell",
        available=True,
        shell_action_id="shell.action.run.stop",
    ),
    _row(
        "form.action.findInFiles",
        "Find in Files",
        "Ctrl+Shift+F",
        ("any",),
        kind="shell",
        available=True,
        shell_action_id="shell.action.edit.findInFiles",
    ),
)

INERT_SHORTCUTS: Tuple[str, ...] = (
    "Ctrl+H",
    "Ctrl+G",
    "Ctrl+/",
    "Ctrl+Alt+V",
    "Ctrl+Shift+Space",
    "F9",
)

_WM_FORBIDDEN = frozenset(
    ["Ctrl+Alt+Left", "Ctrl+Alt+Right", "Ctrl+Alt+Up", "Ctrl+Alt+Down", "Ctrl+Shift+U"]
    + ["Alt+F%d" % number for number in range(1, 11)]
)

_WINDOW_ONLY = frozenset(
    {
        "shell.action.view.focusFirstEditorGroup",
        "shell.action.view.focusSecondEditorGroup",
        "shell.action.view.splitEditorRight",
        "shell.action.view.closeEditorGroup",
    }
)

_EDITOR_ONLY = frozenset(
    {
        "shell.action.edit.indent",
        "shell.action.edit.outdent",
    }
)


def registered_commands() -> Tuple[FormCommand, ...]:
    """Settings rows. One shortcut text per row.

    Canvas arrows and outline arrows share Up, Down, Left, and Right in
    different focus contexts. The shell category allows one row per key, so
    Settings shows the canvas row. The outline row stays in the command table.
    """
    seen = set()
    chosen = []
    for command in FORM_COMMANDS:
        if command.kind != "new" or not command.shortcut:
            continue
        key = normalize_form_shortcut(command.shortcut)
        if key in seen:
            continue
        seen.add(key)
        chosen.append(command)
    return tuple(chosen)


def menu_commands() -> Tuple[FormCommand, ...]:
    return tuple(command for command in FORM_COMMANDS if command.menu_path)


def is_widget_shortcut(command: FormCommand) -> bool:
    """True when the key belongs only to the canvas, outline, or inspector."""
    if command.kind != "new" or not command.shortcut:
        return False
    return frozenset(command.contexts) <= _WIDGET


def menu_hint(command: FormCommand) -> str:
    """Key text for the menu. These keys are not window shortcuts."""
    if not command.shortcut or not command.menu_path:
        return ""
    if command.kind == "shell" or is_widget_shortcut(command):
        return command.shortcut
    return ""


def shell_command_contexts(action_id: str) -> frozenset[str]:
    """Focus contexts where a shell binding is active.

    Window editor-group keys yield to a canvas or outline widget shortcut.
    Indent stays in the code editor. Explorer keys stay in the project tree.
    """
    if "projectTree" in action_id:
        return frozenset({"explorer"})
    if action_id in _WINDOW_ONLY:
        return frozenset({"window"})
    if action_id in _EDITOR_ONLY:
        return frozenset({"editor"})
    return frozenset({"editor", "form_tab"})


def contexts_overlap(left: Iterable[str], right: Iterable[str]) -> bool:
    """True when both bindings can fire for the same focused widget."""
    a = frozenset(left)
    b = frozenset(right)
    if "any" in a or "any" in b:
        return True
    if a & b:
        return True
    if "window" in a and ({"form_tab", "editor"} & b):
        return True
    if "window" in b and ({"form_tab", "editor"} & a):
        return True
    if "editor" in a and "form_tab" in b:
        return True
    if "editor" in b and "form_tab" in a:
        return True
    return False


def normalize_form_shortcut(shortcut: str) -> str:
    return " ".join(shortcut.strip().split())


def shortcut_collisions(
    shell_shortcuts: Mapping[str, str],
) -> Tuple[str, ...]:
    """Pairs that share a key in overlapping contexts, plus forbidden keys.

    ``shell_shortcuts`` maps a shell action id to its portable key text.
    """
    problems = []
    form_rows = tuple(
        command for command in FORM_COMMANDS if command.kind == "new" and command.shortcut
    )
    for command in FORM_COMMANDS:
        shortcut = normalize_form_shortcut(command.shortcut)
        if shortcut and shortcut in _WM_FORBIDDEN:
            problems.append("%s uses forbidden key %s" % (command.command_id, shortcut))
    for inert in INERT_SHORTCUTS:
        if normalize_form_shortcut(inert) in _WM_FORBIDDEN:
            problems.append("inert key %s is a window-manager key" % inert)
    seen: list[FormCommand] = []
    for command in form_rows:
        shortcut = normalize_form_shortcut(command.shortcut)
        for earlier in seen:
            if normalize_form_shortcut(earlier.shortcut) != shortcut:
                continue
            if contexts_overlap(command.contexts, earlier.contexts):
                problems.append(
                    "%s and %s both use %s" % (earlier.command_id, command.command_id, shortcut)
                )
        for action_id, shell_shortcut in shell_shortcuts.items():
            if normalize_form_shortcut(shell_shortcut) != shortcut:
                continue
            if command.shell_action_id == action_id:
                continue
            if contexts_overlap(command.contexts, shell_command_contexts(action_id)):
                problems.append("%s collides with %s on %s" % (command.command_id, action_id, shortcut))
        seen.append(command)
    return tuple(problems)


def shortcut_rows() -> Tuple[Tuple[str, str, str, str], ...]:
    """``(action id, label, shortcut, category)`` for the shell shortcut list."""
    return tuple(
        (command.command_id, command.label, command.shortcut, FORM_SHORTCUT_CATEGORY)
        for command in registered_commands()
    )


__all__ = [
    "FORM_COMMANDS",
    "FORM_SHORTCUT_CATEGORY",
    "INERT_SHORTCUTS",
    "INERT_STATUS",
    "FormCommand",
    "contexts_overlap",
    "is_widget_shortcut",
    "menu_commands",
    "menu_hint",
    "normalize_form_shortcut",
    "registered_commands",
    "shell_command_contexts",
    "shortcut_collisions",
    "shortcut_rows",
]
