"""Shortcut preference contracts and helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.core import constants

_SHORTCUT_ID_CLOSE_TAB = "shell.shortcut.closeTab"


@dataclass(frozen=True)
class ShortcutCommand:
    """Represents one user-configurable command shortcut."""

    action_id: str
    label: str
    default_shortcut: str
    category: str


SHORTCUT_COMMANDS: tuple[ShortcutCommand, ...] = (
    ShortcutCommand("designer.file.new_form", "New Form", "Ctrl+Shift+N", "File"),
    ShortcutCommand("shell.action.file.newProject", "New Project", "Ctrl+N", "File"),
    ShortcutCommand("shell.action.file.openProject", "Open Project", "Ctrl+O", "File"),
    ShortcutCommand("shell.action.file.quickOpen", "Quick Open", "Ctrl+P", "File"),
    ShortcutCommand("shell.action.file.save", "Save", "Ctrl+S", "File"),
    ShortcutCommand("shell.action.file.saveAll", "Save All", "Ctrl+Shift+S", "File"),
    ShortcutCommand("shell.action.file.exit", "Exit", "Ctrl+Q", "File"),
    ShortcutCommand("shell.action.edit.undo", "Undo", "Ctrl+Z", "Edit"),
    ShortcutCommand("shell.action.edit.redo", "Redo", "Ctrl+Shift+Z", "Edit"),
    ShortcutCommand("shell.action.edit.find", "Find", "Ctrl+F", "Edit"),
    ShortcutCommand("shell.action.edit.replace", "Replace", "Ctrl+H", "Edit"),
    ShortcutCommand("shell.action.edit.goToLine", "Go To Line", "Ctrl+G", "Edit"),
    ShortcutCommand("shell.action.edit.findInFiles", "Find in Files", "Ctrl+Shift+F", "Edit"),
    ShortcutCommand("shell.action.edit.findReferences", "Find References", "Shift+F12", "Edit"),
    ShortcutCommand("shell.action.edit.renameSymbol", "Rename Symbol", "F2", "Edit"),
    ShortcutCommand("shell.action.edit.toggleComment", "Toggle Comment", "Ctrl+/", "Edit"),
    ShortcutCommand("shell.action.edit.indent", "Indent", "Tab", "Edit"),
    ShortcutCommand("shell.action.edit.outdent", "Outdent", "Shift+Tab", "Edit"),
    ShortcutCommand("shell.action.edit.goToDefinition", "Go To Definition", "F12", "Edit"),
    ShortcutCommand("shell.action.edit.signatureHelp", "Signature Help", "Ctrl+Shift+Space", "Edit"),
    ShortcutCommand("shell.action.edit.hoverInfo", "Show Hover Info", "Ctrl+K", "Edit"),
    ShortcutCommand("designer.layout.horizontal", "Lay Out Horizontally", "Ctrl+1", "Layout"),
    ShortcutCommand("designer.layout.vertical", "Lay Out Vertically", "Ctrl+2", "Layout"),
    ShortcutCommand("designer.layout.grid", "Lay Out in a Grid", "Ctrl+3", "Layout"),
    ShortcutCommand("designer.layout.break", "Break Layout", "Ctrl+0", "Layout"),
    ShortcutCommand("designer.form.preview", "Preview Form", "Ctrl+R", "Form"),
    ShortcutCommand("designer.form.check_compat", "Run Compatibility Check", "Ctrl+Shift+R", "Form"),
    ShortcutCommand("designer.form.add_resource", "Add Resource (.qrc)", "", "Form"),
    ShortcutCommand("designer.form.promote_widget", "Promote Selected Widget", "", "Form"),
    ShortcutCommand("designer.form.format_ui_xml", "Format UI XML", "Ctrl+Alt+Shift+F", "Form"),
    ShortcutCommand("designer.mode.widget", "Widget Editing Mode", "F3", "Mode"),
    ShortcutCommand("designer.mode.signals_slots", "Signals/Slots Mode", "F4", "Mode"),
    ShortcutCommand("designer.mode.buddy", "Buddy Mode", "F5", "Mode"),
    ShortcutCommand("designer.mode.tab_order", "Tab Order Mode", "F6", "Mode"),
    ShortcutCommand("shell.action.run.run", "Run", "F5", "Run"),
    ShortcutCommand("shell.action.run.debug", "Debug", "Ctrl+F5", "Run"),
    ShortcutCommand("shell.action.run.pytestProject", "Run Project Tests", "Ctrl+Shift+T", "Run"),
    ShortcutCommand("shell.action.run.pytestCurrentFile", "Run Current File Tests", "Ctrl+Alt+T", "Run"),
    ShortcutCommand("shell.action.run.stop", "Stop", "Shift+F5", "Run"),
    ShortcutCommand("shell.action.run.restart", "Restart", "Ctrl+Shift+F5", "Run"),
    ShortcutCommand("shell.action.run.continue", "Continue", "F6", "Run"),
    ShortcutCommand("shell.action.run.pause", "Pause", "Ctrl+F6", "Run"),
    ShortcutCommand("shell.action.run.stepOver", "Step Over", "F10", "Run"),
    ShortcutCommand("shell.action.run.stepInto", "Step Into", "F11", "Run"),
    ShortcutCommand("shell.action.run.stepOut", "Step Out", "Shift+F11", "Run"),
    ShortcutCommand("shell.action.run.toggleBreakpoint", "Toggle Breakpoint", "F9", "Run"),
    ShortcutCommand("shell.action.run.pythonConsole", "Restart Python Console", "Ctrl+`", "Run"),
    ShortcutCommand("shell.action.view.zoomIn", "Zoom In", "Ctrl+=", "View"),
    ShortcutCommand("shell.action.view.zoomOut", "Zoom Out", "Ctrl+-", "View"),
    ShortcutCommand("shell.action.view.zoomReset", "Reset Zoom", "Ctrl+0", "View"),
    ShortcutCommand(_SHORTCUT_ID_CLOSE_TAB, "Close Tab", "Ctrl+W", "Editor"),
)

_KNOWN_SHORTCUT_IDS: frozenset[str] = frozenset(command.action_id for command in SHORTCUT_COMMANDS)


def close_tab_shortcut_id() -> str:
    """Return synthetic action id for close-tab shortcut."""
    return _SHORTCUT_ID_CLOSE_TAB


def default_shortcut_map() -> dict[str, str]:
    """Return default shortcut mapping keyed by action id."""
    return {command.action_id: command.default_shortcut for command in SHORTCUT_COMMANDS}


def parse_shortcut_overrides(settings_payload: Mapping[str, Any]) -> dict[str, str]:
    """Parse and validate persisted keybinding overrides."""
    section = settings_payload.get(constants.UI_KEYBINDINGS_SETTINGS_KEY, {})
    if not isinstance(section, dict):
        return {}
    overrides_payload = section.get(constants.UI_KEYBINDINGS_OVERRIDES_KEY, {})
    if not isinstance(overrides_payload, dict):
        return {}
    overrides: dict[str, str] = {}
    for action_id, shortcut in overrides_payload.items():
        if action_id not in _KNOWN_SHORTCUT_IDS or not isinstance(shortcut, str):
            continue
        normalized = normalize_shortcut(shortcut)
        if normalized:
            overrides[action_id] = normalized
        elif shortcut == "":
            overrides[action_id] = ""
    return overrides


def normalize_shortcut(shortcut: str) -> str:
    """Normalize shortcut text for deterministic persistence."""
    return " ".join(shortcut.strip().split())


def build_effective_shortcut_map(overrides: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return effective shortcut map after applying user overrides."""
    effective = default_shortcut_map()
    if overrides is None:
        return effective
    for action_id, shortcut in overrides.items():
        if action_id not in _KNOWN_SHORTCUT_IDS:
            continue
        normalized = normalize_shortcut(shortcut)
        if normalized:
            effective[action_id] = normalized
        elif shortcut == "":
            effective.pop(action_id, None)
    return effective


def find_shortcut_conflicts(shortcuts_by_action: Mapping[str, str]) -> dict[str, tuple[str, ...]]:
    """Return shortcut -> action-id conflicts for duplicate assignments."""
    grouped: dict[str, list[str]] = {}
    for action_id, shortcut in shortcuts_by_action.items():
        normalized = normalize_shortcut(shortcut)
        if not normalized:
            continue
        grouped.setdefault(normalized, []).append(action_id)
    conflicts: dict[str, tuple[str, ...]] = {}
    for shortcut, action_ids in grouped.items():
        if len(action_ids) > 1:
            conflicts[shortcut] = tuple(sorted(action_ids))
    return conflicts
