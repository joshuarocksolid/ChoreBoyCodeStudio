"""Shortcut preference contracts and helpers."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any, Literal, Mapping, Sequence

from app.core import constants

ShortcutScope = Literal["window", "explorer", "form_tab", "canvas", "outline", "inspector"]

_SCOPE_PARENTS: dict[ShortcutScope, ShortcutScope | None] = {
    "window": None,
    "explorer": "window",
    "form_tab": "window",
    "canvas": "form_tab",
    "outline": "form_tab",
    "inspector": "form_tab",
}

WINDOW_MANAGER_KEYS: frozenset[str] = frozenset(
    {
        "Ctrl+Alt+Left",
        "Ctrl+Alt+Right",
        "Ctrl+Alt+Up",
        "Ctrl+Alt+Down",
        "Alt+F1",
        "Alt+F2",
        "Alt+F3",
        "Alt+F4",
        "Alt+F5",
        "Alt+F6",
        "Alt+F7",
        "Alt+F8",
        "Alt+F9",
        "Alt+F10",
        "Ctrl+Shift+U",
    }
)

_SHORTCUT_ID_CLOSE_TAB = "shell.shortcut.closeTab"
_SHORTCUT_ID_KEEP_PREVIEW_OPEN = "shell.shortcut.keepPreviewOpen"
_SHORTCUT_ID_PROJECT_TREE_RENAME = "shell.shortcut.projectTree.rename"
_SHORTCUT_ID_PROJECT_TREE_COPY = "shell.shortcut.projectTree.copy"
_SHORTCUT_ID_PROJECT_TREE_CUT = "shell.shortcut.projectTree.cut"
_SHORTCUT_ID_PROJECT_TREE_PASTE = "shell.shortcut.projectTree.paste"
_SHORTCUT_ID_PROJECT_TREE_DELETE = "shell.shortcut.projectTree.delete"


@dataclass(frozen=True)
class ShortcutCommand:
    action_id: str
    label: str
    default_shortcut: str
    category: str
    scopes: tuple[ShortcutScope, ...] = ("window",)
    shadows: tuple[str, ...] = ()
    reserved: bool = False


SHORTCUT_COMMANDS: tuple[ShortcutCommand, ...] = (
    ShortcutCommand("shell.action.file.newProject", "New Project", "Ctrl+N", "File"),
    ShortcutCommand("shell.action.file.newWindow", "New Window", "Ctrl+Shift+N", "File"),
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
    ShortcutCommand(
        "shell.action.edit.pasteReindentedFlatPython",
        "Paste and Re-indent Flat Python",
        "Ctrl+Alt+V",
        "Edit",
    ),
    ShortcutCommand("shell.action.edit.goToDefinition", "Go To Definition", "F12", "Edit"),
    ShortcutCommand("shell.action.edit.signatureHelp", "Signature Help", "Ctrl+Shift+Space", "Edit"),
    ShortcutCommand("shell.action.edit.hoverInfo", "Show Hover Info", "Ctrl+Shift+I", "Edit"),
    ShortcutCommand("shell.action.tools.gotoSymbolInFile", "Go to Symbol in File", "Ctrl+R", "Tools"),
    ShortcutCommand(
        "shell.action.tools.reindentFlatPythonSelection",
        "Re-indent Flat Python Selection",
        "",
        "Tools",
    ),
    ShortcutCommand("shell.action.run.run", "Run Active File", "F5", "Run"),
    ShortcutCommand("shell.action.run.debug", "Debug Active File", "Ctrl+F5", "Run"),
    ShortcutCommand("shell.action.run.runProject", "Run Project", "Shift+F5", "Run"),
    ShortcutCommand("shell.action.run.debugProject", "Debug Project", "Ctrl+Shift+F5", "Run"),
    ShortcutCommand("shell.action.run.pytestProject", "Run Project Tests", "Ctrl+Shift+T", "Run"),
    ShortcutCommand("shell.action.run.pytestCurrentFile", "Run Current File Tests", "Ctrl+Alt+T", "Run"),
    ShortcutCommand("shell.action.run.runWithArgs", "Run With Arguments", "Ctrl+Shift+A", "Run"),
    ShortcutCommand("shell.action.run.stop", "Stop", "Shift+F2", "Run"),
    ShortcutCommand("shell.action.run.restart", "Restart", "Ctrl+Shift+F2", "Run"),
    ShortcutCommand("shell.action.run.continue", "Continue", "F6", "Run"),
    ShortcutCommand("shell.action.run.pause", "Pause", "Ctrl+F6", "Run"),
    ShortcutCommand("shell.action.run.stepOver", "Step Over", "F10", "Run"),
    ShortcutCommand("shell.action.run.stepInto", "Step Into", "F11", "Run"),
    ShortcutCommand("shell.action.run.stepOut", "Step Out", "Shift+F11", "Run"),
    ShortcutCommand("shell.action.run.toggleBreakpoint", "Toggle Breakpoint", "F9", "Run"),
    ShortcutCommand("shell.action.run.pythonConsole", "Restart Python Console", "Ctrl+`", "Run"),
    ShortcutCommand("shell.action.view.splitEditorRight", "Split Editor Right", "Ctrl+\\", "View"),
    ShortcutCommand("shell.action.view.closeEditorGroup", "Close Editor Group", "", "View"),
    ShortcutCommand("shell.action.view.focusFirstEditorGroup", "Focus First Editor Group", "Ctrl+1", "View"),
    ShortcutCommand("shell.action.view.focusSecondEditorGroup", "Focus Second Editor Group", "Ctrl+2", "View"),
    ShortcutCommand("shell.action.view.zoomIn", "Zoom In", "Ctrl+=", "View"),
    ShortcutCommand("shell.action.view.zoomOut", "Zoom Out", "Ctrl+-", "View"),
    ShortcutCommand("shell.action.view.zoomReset", "Reset Zoom", "Ctrl+0", "View"),
    ShortcutCommand("shell.action.view.markdownTogglePreview", "Markdown: Toggle Preview", "Ctrl+Shift+V", "View"),
    ShortcutCommand("shell.action.view.markdownShowSource", "Markdown: Show Source", "", "View"),
    ShortcutCommand("shell.action.view.markdownShowPreview", "Markdown: Show Preview", "", "View"),
    ShortcutCommand("shell.action.view.markdownShowSplit", "Markdown: Show Split View", "Ctrl+K, V", "View"),
    ShortcutCommand(
        _SHORTCUT_ID_PROJECT_TREE_RENAME,
        "Rename Project Item",
        "F2",
        "Explorer",
        scopes=("explorer",),
        shadows=("shell.action.edit.renameSymbol",),
    ),
    ShortcutCommand(
        _SHORTCUT_ID_PROJECT_TREE_COPY, "Copy Project Item", "Ctrl+C", "Explorer", scopes=("explorer",)
    ),
    ShortcutCommand(
        _SHORTCUT_ID_PROJECT_TREE_CUT, "Cut Project Item", "Ctrl+X", "Explorer", scopes=("explorer",)
    ),
    ShortcutCommand(
        _SHORTCUT_ID_PROJECT_TREE_PASTE, "Paste Project Item", "Ctrl+V", "Explorer", scopes=("explorer",)
    ),
    ShortcutCommand(
        _SHORTCUT_ID_PROJECT_TREE_DELETE,
        "Move Project Item to Trash",
        "Delete",
        "Explorer",
        scopes=("explorer",),
    ),
    ShortcutCommand(_SHORTCUT_ID_CLOSE_TAB, "Close Tab", "Ctrl+W", "Editor"),
    ShortcutCommand(_SHORTCUT_ID_KEEP_PREVIEW_OPEN, "Keep Preview Tab Open", "Ctrl+K, Enter", "Editor"),
)

_KNOWN_SHORTCUT_IDS: frozenset[str] = frozenset(command.action_id for command in SHORTCUT_COMMANDS)
_CATEGORY_BY_ACTION_ID: dict[str, str] = {
    command.action_id: command.category for command in SHORTCUT_COMMANDS
}
_SHORTCUT_KEY_ALIASES = {
    "Del": "Delete",
}


def close_tab_shortcut_id() -> str:
    """Return synthetic action id for close-tab shortcut."""
    return _SHORTCUT_ID_CLOSE_TAB


def keep_preview_open_shortcut_id() -> str:
    """Return synthetic action id for keep-preview-open shortcut."""
    return _SHORTCUT_ID_KEEP_PREVIEW_OPEN


def project_tree_rename_shortcut_id() -> str:
    return _SHORTCUT_ID_PROJECT_TREE_RENAME


def project_tree_copy_shortcut_id() -> str:
    return _SHORTCUT_ID_PROJECT_TREE_COPY


def project_tree_cut_shortcut_id() -> str:
    return _SHORTCUT_ID_PROJECT_TREE_CUT


def project_tree_paste_shortcut_id() -> str:
    return _SHORTCUT_ID_PROJECT_TREE_PASTE


def project_tree_delete_shortcut_id() -> str:
    return _SHORTCUT_ID_PROJECT_TREE_DELETE


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
    normalized = " ".join(shortcut.strip().split())
    chords: list[str] = []
    for chord in normalized.split(", "):
        keys = [_SHORTCUT_KEY_ALIASES.get(key, key) for key in chord.split("+")]
        chords.append("+".join(keys))
    return ", ".join(chords)


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
    grouped: dict[tuple[str, str], list[str]] = {}
    for action_id, shortcut in shortcuts_by_action.items():
        normalized = normalize_shortcut(shortcut)
        if not normalized:
            continue
        category = _CATEGORY_BY_ACTION_ID.get(action_id, "")
        grouped.setdefault((normalized, category), []).append(action_id)
    conflicts: dict[str, tuple[str, ...]] = {}
    for (shortcut, _category), action_ids in grouped.items():
        if len(action_ids) > 1:
            conflicts[shortcut] = tuple(sorted(action_ids))
    return conflicts


@dataclass(frozen=True)
class ShortcutConflict:
    key: str
    action_ids: tuple[str, ...]
    kind: Literal["overlap", "window_manager"]


@dataclass(frozen=True)
class ShortcutCatalog:
    rows: tuple[ShortcutCommand, ...]

    @classmethod
    def build(
        cls,
        shell_rows: tuple[ShortcutCommand, ...],
        command_sets: Sequence[tuple[ShortcutCommand, ...]] = (),
    ) -> ShortcutCatalog:
        rows = shell_rows + tuple(row for command_set in command_sets for row in command_set)
        seen: set[str] = set()
        for row in rows:
            if row.action_id in seen:
                raise ValueError(f"Duplicate shortcut action id: {row.action_id}")
            seen.add(row.action_id)
        return cls(rows)

    def visible_rows(self) -> tuple[ShortcutCommand, ...]:
        return tuple(row for row in self.rows if not row.reserved)

    def defaults(self) -> dict[str, str]:
        return {row.action_id: row.default_shortcut for row in self.rows}

    def conflicts(
        self,
        shortcuts: Mapping[str, str],
        *,
        include_reserved: bool = False,
    ) -> tuple[ShortcutConflict, ...]:
        bound = [
            (row, _chords(shortcuts.get(row.action_id, "")))
            for row in self.rows
            if include_reserved or not row.reserved
        ]
        found = [
            ShortcutConflict(", ".join(chords), (row.action_id,), "window_manager")
            for row, chords in bound
            if any(chord in WINDOW_MANAGER_KEYS for chord in chords)
        ]
        for (first, first_chords), (second, second_chords) in combinations(bound, 2):
            prefix = _chord_prefix(first_chords, second_chords)
            if prefix and _scopes_collide(first, second):
                found.append(ShortcutConflict(", ".join(prefix), (first.action_id, second.action_id), "overlap"))
        return tuple(found)

    def stale_shadows(self) -> tuple[tuple[str, str], ...]:
        by_id = {row.action_id: row for row in self.rows}
        return tuple(
            (row.action_id, wider_id)
            for row in self.rows
            for wider_id in row.shadows
            if wider_id not in by_id or not _shadow_is_live(row, by_id[wider_id])
        )


def _chords(shortcut: str) -> tuple[str, ...]:
    normalized = normalize_shortcut(shortcut)
    return tuple(normalized.split(", ")) if normalized else ()


def _chord_prefix(first: tuple[str, ...], second: tuple[str, ...]) -> tuple[str, ...]:
    shorter, longer = (first, second) if len(first) <= len(second) else (second, first)
    return shorter if longer[: len(shorter)] == shorter else ()


def _encloses(outer: ShortcutScope, inner: ShortcutScope) -> bool:
    parent = _SCOPE_PARENTS[inner]
    while parent is not None:
        if parent == outer:
            return True
        parent = _SCOPE_PARENTS[parent]
    return False


def _scopes_collide(first: ShortcutCommand, second: ShortcutCommand) -> bool:
    for first_scope in first.scopes:
        for second_scope in second.scopes:
            if first_scope == second_scope:
                return True
            if _encloses(first_scope, second_scope) and first.action_id not in second.shadows:
                return True
            if _encloses(second_scope, first_scope) and second.action_id not in first.shadows:
                return True
    return False


def _shadow_is_live(narrower: ShortcutCommand, wider: ShortcutCommand) -> bool:
    if not _chord_prefix(_chords(narrower.default_shortcut), _chords(wider.default_shortcut)):
        return False
    return any(_encloses(outer, inner) for outer in wider.scopes for inner in narrower.scopes)
