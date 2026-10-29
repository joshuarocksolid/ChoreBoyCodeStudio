"""Rows of Form designer keys, built from the registered form commands (UX-MODE-005, UX-MODE-006). Qt-free.

The page cannot drift from the real bindings because it has no key text of its
own: ``build_groups`` reads the commands the form registers and the key each
one is bound to now. The only text kept here is the words for a group, a
context, and the key Qt Designer used for the same job.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

from app.features.form_builder.engine.shell_commands import INERT_SHORTCUTS, INERT_STATUS, FormCommand

COLUMNS = ("Keys", "What it does", "Where", "In Qt Designer")
SEARCH_PLACEHOLDER = "Search keys"
TITLE = "Form designer keys"
DESIGNER_GROUP = "Where Qt Designer's keys went"
INERT_GROUP = "Keys the form leaves alone"

_WHERE: Mapping[str, str] = {
    "form_tab": "Form tab",
    "canvas": "Canvas",
    "outline": "Outline",
    "inspector": "Inspector",
    "any": "Anywhere",
    "window": "Window",
    "editor": "Code editor",
    "tab_order_overlay": "Tab order overlay",
    "buddy_overlay": "Buddies overlay",
}

#: Group order follows UX-KEY-004: file and history, clipboard, selecting, text and find, moving, layout,
#: views, panes, run, overlays. A pattern ending in ``*`` matches by prefix.
_GROUPS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("File and history", ("save", "saveAll", "closeTab", "undo", "redo")),
    ("Clipboard and delete", ("cut", "copy", "paste", "delete", "backspace", "duplicate", "savePiece")),
    (
        "Selecting",
        (
            "select*",
            "extend*",
            "escape",
            "outline*",
            "contextMenu*",
            "showNextPage",
            "showPreviousPage",
        ),
    ),
    ("Insert, rename, text and find", ("insert", "goToWidget", "find", "rename", "editText")),
    ("Moving and sizing", ("moveOrNudge*", "nudgeOne*", "resize*")),
    ("Layout", ("layout*", "wrap", "unwrap", "removeLayout", "adjustSize", "simplifyGrid", "size*", "keepAtContentSize")),
    ("Zoom, preview and views", ("zoom*", "preview", "twoWidths", "viewXml", "textSize", "screenScale")),
    ("Panes", ("focus*",)),
    ("Run", ("run*", "debug*", "stop", "findInFiles")),
    ("Overlays and help", ("tabOrder*", "buddies", "buddyLink", "leaveOverlay", "connections", "widgetHelp")),
    ("Other", ()),
)

_DESIGNER_KEYS: Mapping[str, str] = {
    "save": "Ctrl+S",
    "saveAll": "Ctrl+Shift+S",
    "closeTab": "Ctrl+W",
    "undo": "Ctrl+Z",
    "redo": "Ctrl+Shift+Z",
    "cut": "Ctrl+X",
    "copy": "Ctrl+C",
    "paste": "Ctrl+V",
    "delete": "Delete",
    "backspace": "Delete",
    "find": "Ctrl+F",
    "editText": "F2",
    "preview": "Ctrl+R",
    "adjustSize": "Ctrl+J",
    "widgetHelp": "F1",
    "leaveOverlay": "F3, Esc",
    "connections": "F4",
    "layoutHorizontal": "Ctrl+1",
    "layoutVertical": "Ctrl+2",
    "layoutHorizontalSplitter": "Ctrl+3",
    "layoutVerticalSplitter": "Ctrl+4",
    "layoutGrid": "Ctrl+5",
    "layoutForm": "Ctrl+6",
    "removeLayout": "Ctrl+0",
    "unwrap": "Ctrl+0",
    "zoomReset": "",
}

#: UX-MODE-006: where each Designer key went. ``(R3 rows, Designer, Code Studio)``.
DESIGNER_MOVES: Tuple[Tuple[str, str, str], ...] = (
    ("199", "Ctrl+N new form", "File > New Form… (Ctrl+N is New Project)"),
    ("200", "Ctrl+O open form", "Ctrl+P Quick Open, or the project tree"),
    ("201, 202", "Ctrl+S, Ctrl+Shift+S", "same"),
    ("203, 204", "Ctrl+W, quit", "same (Ctrl+W closes the tab or the Preview; Ctrl+Q quits)"),
    ("205, 206", "Undo, redo, clipboard, Delete", "same"),
    ("207", "Ctrl+R preview", "Ctrl+Shift+R (Ctrl+R is Go to widget)"),
    ("208", "Ctrl+P print", "Form > Print… (Ctrl+P is Quick Open)"),
    ("209", "F1 help for the widget", "F1"),
    ("210", "Ctrl+? Designer help", "Help > Form designer keys"),
    ("211", "F3 or Esc widget mode", "F3 or Esc leaves an overlay"),
    ("212", "F4 signals and slots", "F4 (Connections overlay from M6; until then the status says “Connections are in the Behavior tab. Alt+4 goes there.”)"),
    ("213", "F2 edit text", "Enter (F2 renames)"),
    ("214", "Ctrl+F find in object inspector", "Ctrl+F"),
    ("215", "Ctrl+1 … Ctrl+6 layouts", "same"),
    ("216", "Ctrl+0 break layout", "Form > Layout > Remove layout…, or Ctrl+Shift+B to unwrap (Ctrl+0 is 100% zoom)"),
    ("217", "Ctrl+J adjust size", "same"),
    ("218", "Ctrl-drag clone", "same"),
    ("219", "Arrows snap, Ctrl+arrows 1 px", "Alt+arrow by the grid step, Alt+Shift+arrow 1 px (arrows select)"),
    ("220", "Shift-click selects the parent layout", "Esc"),
    ("221", "Shift+Ctrl+drag moves inside a layout", "a plain drag"),
)


@dataclass(frozen=True)
class KeyRow:
    command_id: str
    keys: str
    what: str
    where: str
    designer: str
    #: True for a key the form binds. False for a Designer row that only says where a key went.
    bound: bool = True


@dataclass(frozen=True)
class KeyGroup:
    title: str
    rows: Tuple[KeyRow, ...]


def _stem(command_id: str) -> str:
    return command_id.rsplit(".", 1)[-1]


def _group_of(command_id: str) -> int:
    stem = _stem(command_id)
    for index, (_title, patterns) in enumerate(_GROUPS):
        for pattern in patterns:
            if stem == pattern or (pattern.endswith("*") and stem.startswith(pattern[:-1])):
                return index
    return len(_GROUPS) - 1


def where_words(contexts: Iterable[str]) -> str:
    return ", ".join(_WHERE.get(name, name) for name in contexts)


def effective_key(command: FormCommand, effective: Mapping[str, str]) -> str:
    """The key the command is bound to now: a Settings rebind, else the shell's key for a shell row, else the table's."""
    return effective.get(command.command_id) or (effective.get(command.shell_action_id) if command.shell_action_id else "") or command.shortcut


def build_groups(commands: Sequence[FormCommand], effective: Mapping[str, str]) -> Tuple[KeyGroup, ...]:
    """The page: one group per ``_GROUPS`` entry that has a key, then the inert keys and where Designer's keys went."""
    buckets: Dict[int, List[KeyRow]] = {}
    seen = set()
    for command in commands:
        keys = effective_key(command, effective)
        if not keys or command.command_id in seen:
            continue
        seen.add(command.command_id)
        row = KeyRow(
            command.command_id,
            keys,
            command.label,
            where_words(command.contexts),
            _DESIGNER_KEYS.get(_stem(command.command_id), ""),
        )
        buckets.setdefault(_group_of(command.command_id), []).append(row)
    groups = [KeyGroup(title, tuple(buckets[index])) for index, (title, _stems) in enumerate(_GROUPS) if index in buckets]
    groups.append(
        KeyGroup(
            INERT_GROUP,
            tuple(KeyRow("inert:" + key, key, INERT_STATUS, "Form tab", "", bound=False) for key in INERT_SHORTCUTS),
        )
    )
    groups.append(
        KeyGroup(
            DESIGNER_GROUP,
            tuple(KeyRow("designer:" + rows, "", now, "", was, bound=False) for rows, was, now in DESIGNER_MOVES),
        )
    )
    return tuple(groups)


def matches(row: KeyRow, needle: str) -> bool:
    text = needle.strip().lower()
    if not text:
        return True
    return text in " ".join((row.keys, row.what, row.where, row.designer)).lower()


def filter_groups(groups: Sequence[KeyGroup], needle: str) -> Tuple[KeyGroup, ...]:
    """Groups with only the rows that contain ``needle`` in any column; a group with none is left out."""
    kept = []
    for group in groups:
        rows = tuple(row for row in group.rows if matches(row, needle))
        if rows:
            kept.append(KeyGroup(group.title, rows))
    return tuple(kept)
