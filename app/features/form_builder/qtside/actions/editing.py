"""Menu editing: the "Type here" grammar of UX-MAIN-004 ... 008 as a state machine.

Qt-free. The canvas glue feeds it ``Key`` values and draws ``view()``; commands
go through an ``Env``, so the same machine runs in tests against a command log.
One key does one thing and commits at most one undo step.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, List, Optional, Protocol, Sequence, Tuple

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog_ext.main_window import (
    AddEntry,
    AddMenu,
    AddSeparator,
    MoveEntry,
    RemoveEntry,
    RenameEntry,
)
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query import actions as q
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode

GRAMMAR = "Left and Right move between menus. Down opens one. Type on Type here to add. Esc leaves."
MNEMONIC_CAPTION = "Put & before a letter to open it with Alt and that letter."
MENU_CLASSES = ("QMenuBar", "QMenu", "QToolBar")
REUSE_LIMIT = 6


@dataclass(frozen=True)
class Key:
    """``name`` is Left, Right, Up, Down, Enter, Escape, Delete, Backspace, Tab or ``""`` for a typed character."""

    name: str = ""
    text: str = ""
    alt: bool = False
    ctrl: bool = False


class Env(Protocol):
    @property
    def document(self) -> UiDocument: ...

    def run(self, command: Any) -> Any: ...

    def group(self, label: str) -> AbstractContextManager[Any]: ...

    def select(self, ids: Sequence[NodeId]) -> None: ...

    def say(self, sentence: str) -> None: ...

    def toast(self, sentence: str) -> None: ...

    def confirm(self, sentence: str, ok: str) -> bool: ...


@dataclass
class Level:
    #: The bar, menu or toolbar. None for a submenu that has not been written yet.
    host: Optional[NodeId]
    slot: int = 0
    #: For an unwritten submenu: the entry reference it will turn into a menu.
    pending: Optional[NodeId] = None


@dataclass
class Editor:
    mode: str  # "new" or "edit"
    text: str = ""
    ref: Optional[NodeId] = None
    #: The text is selected, so the next character replaces it.
    selected: bool = False
    reuse_open: bool = True
    reuse_index: Optional[int] = None


@dataclass(frozen=True)
class ReuseRow:
    kind: str  # "new" or "action"
    label: str
    name: str = ""
    shortcut: str = ""
    has_icon: bool = False


@dataclass(frozen=True)
class RowView:
    kind: str  # action, menu, separator, type_here, add_separator
    text: str
    focused: bool = False
    #: A menu entry that opens (an arrow is drawn).
    opens: bool = False
    shortcut: str = ""


@dataclass(frozen=True)
class LevelView:
    host: Optional[NodeId]
    kind: str  # bar, menu, toolbar
    rows: Tuple[RowView, ...]
    editing: Optional[int] = None
    editor_text: str = ""
    editor_selected: bool = False
    reuse: Tuple[ReuseRow, ...] = ()
    reuse_current: int = 0
    caption: str = ""


@dataclass(frozen=True)
class EditView:
    levels: Tuple[LevelView, ...]


class MenuEditor:
    def __init__(self, env: Env) -> None:
        self._env = env
        self.levels: List[Level] = []
        self.editor: Optional[Editor] = None
        self._caption_shown = False

    # ------------------------------------------------------------ state
    @property
    def active(self) -> bool:
        return bool(self.levels)

    def start(self, node_id: NodeId) -> bool:
        """Enter editing on a selected menu bar, menu or toolbar. False when ``node_id`` is none of them."""
        doc = self._env.document
        node = doc.get(node_id)
        if not isinstance(node, WidgetNode) or node.class_name not in MENU_CLASSES:
            return False
        chain: List[NodeId] = [node_id]
        while True:
            parent = doc.parent(chain[-1])
            if parent is None or not isinstance(parent, WidgetNode) or parent.class_name not in MENU_CLASSES:
                break
            chain.append(parent.id)
        chain.reverse()
        self.levels = []
        for index, host in enumerate(chain):
            level = Level(host, 0)
            if index + 1 < len(chain):
                level.slot = self._slot_of_menu(host, chain[index + 1])
            self.levels.append(level)
        top = self.levels[-1]
        if self._kind(top.host) in ("menu",):
            top.slot = 0
        self.editor = None
        self._focus_selection()
        self._env.say(GRAMMAR)
        return True

    def leave(self) -> None:
        self.levels = []
        self.editor = None

    def _kind(self, host: Optional[NodeId]) -> str:
        if host is None:
            return "menu"
        node = self._env.document.get(host)
        if isinstance(node, WidgetNode):
            return {"QMenuBar": "bar", "QMenu": "menu", "QToolBar": "toolbar"}.get(node.class_name, "toolbar")
        return "toolbar"

    def _entries(self, level: Level) -> Tuple[q.Entry, ...]:
        if level.host is None or not self._env.document.contains(level.host):
            return ()
        return q.entries(self._env.document, level.host)

    def _positions(self, level: Level) -> int:
        count = len(self._entries(level))
        return count + (2 if self._kind(level.host) == "menu" else 1)

    def _slot_of_menu(self, host: NodeId, menu: NodeId) -> int:
        for index, entry in enumerate(q.entries(self._env.document, host)):
            if entry.target == menu:
                return index
        return 0

    def _clamp(self, level: Level) -> None:
        level.slot = max(0, min(level.slot, self._positions(level) - 1))

    # ------------------------------------------------------------ keys
    def handle(self, key: Key) -> bool:
        """Return True when the key was used."""
        if not self.active:
            return False
        try:
            if self.editor is not None:
                return self._editor_key(key)
            return self._navigate_key(key)
        except CommandRejected as refusal:
            self._env.say(str(refusal))
            self.editor = None
            return True

    # ---------------------------------------------------------- navigation
    def _navigate_key(self, key: Key) -> bool:
        level = self.levels[-1]
        kind = self._kind(level.host)
        count = len(self._entries(level))
        name = key.name
        if key.alt and name in ("Left", "Right", "Up", "Down"):
            return self._move_focused(name)
        if name == "Escape":
            self._escape()
            return True
        if kind == "menu":
            if name == "Up":
                level.slot = max(0, level.slot - 1)
            elif name == "Down":
                level.slot = min(self._positions(level) - 1, level.slot + 1)
            elif name == "Right":
                self._open_submenu()
            elif name == "Left":
                self._close_level()
            else:
                return self._common_key(key, level, kind, count)
            self._focus_selection()
            return True
        if name == "Left":
            level.slot = max(0, level.slot - 1)
        elif name == "Right":
            level.slot = min(self._positions(level) - 1, level.slot + 1)
        elif name == "Down" and kind == "bar":
            self._open_menu_below()
        elif name in ("Up", "Down"):
            pass
        else:
            return self._common_key(key, level, kind, count)
        self._focus_selection()
        return True

    def _common_key(self, key: Key, level: Level, kind: str, count: int) -> bool:
        name = key.name
        if name == "Enter":
            if level.slot < count:
                self._edit_focused()
            elif level.slot == count:
                self._begin_new("")
            else:
                self._add_separator(level, count)
            return True
        if name == "Delete":
            self._remove_focused()
            return True
        if name == "" and key.text and key.text.isprintable() and not key.ctrl and not key.alt:
            if level.slot == count:
                self._begin_new(key.text)
                return True
        return name in ("Up", "Down", "Left", "Right", "Tab", "Backspace") or bool(key.text)

    def _escape(self) -> None:
        if len(self.levels) > 1:
            self._close_level()
            self._focus_selection()
        else:
            host = self.levels[0].host
            self.leave()
            if host is not None and self._env.document.contains(host):
                self._env.select((host,))

    def _close_level(self) -> None:
        if len(self.levels) > 1:
            self.levels.pop()
            self._clamp(self.levels[-1])
        elif self._kind(self.levels[0].host) == "menu":
            self.leave()

    def _open_menu_below(self) -> None:
        level = self.levels[-1]
        entries = self._entries(level)
        if level.slot < len(entries) and entries[level.slot].kind == "menu":
            self.levels.append(Level(entries[level.slot].target, 0))
            self._open_focus()

    def _open_focus(self) -> None:
        top = self.levels[-1]
        top.slot = 0

    def _open_submenu(self) -> None:
        level = self.levels[-1]
        entries = self._entries(level)
        if level.slot >= len(entries):
            return
        entry = entries[level.slot]
        if entry.kind == "menu":
            self.levels.append(Level(entry.target, 0))
        elif entry.kind == "action":
            self.levels.append(Level(None, 0, pending=entry.ref))

    def _move_focused(self, name: str) -> bool:
        level = self.levels[-1]
        entries = self._entries(level)
        if level.slot >= len(entries) or level.host is None:
            return True
        delta = -1 if name in ("Left", "Up") else 1
        horizontal = self._kind(level.host) != "menu"
        if horizontal != (name in ("Left", "Right")):
            return True
        target = level.slot + delta
        if target < 0 or target >= len(entries):
            return True
        entry = entries[level.slot]
        index = target + 1 if delta > 0 else target
        self._env.run(MoveEntry(entry.ref, level.host, index, text=entry.text or entry.name))
        level.slot = target
        self._focus_selection()
        return True

    # ------------------------------------------------------------- editing
    def _edit_focused(self) -> None:
        level = self.levels[-1]
        entries = self._entries(level)
        entry = entries[level.slot]
        if entry.kind == "separator":
            return
        self.editor = Editor("edit", entry.text, entry.ref, selected=True, reuse_open=False)
        self._announce_mnemonics()

    def _begin_new(self, text: str) -> None:
        self.editor = Editor("new", text, None, selected=False, reuse_open=bool(text))
        self._refresh_reuse()
        self._announce_mnemonics()

    def _announce_mnemonics(self) -> None:
        if not self._caption_shown:
            self._caption_shown = True
            self._env.say(MNEMONIC_CAPTION)

    def _editor_key(self, key: Key) -> bool:
        editor = self.editor
        assert editor is not None
        level = self.levels[-1]
        kind = self._kind(level.host)
        name = key.name
        if name == "Escape":
            if editor.reuse_open and editor.mode == "new" and self._reuse_rows():
                editor.reuse_open = False
            else:
                self.editor = None
            return True
        if name == "Enter":
            self._commit(then_tab=False)
            return True
        if name == "Tab":
            self._commit(then_tab=True)
            return True
        if name == "Backspace":
            editor.text = "" if editor.selected else editor.text[:-1]
            editor.selected = False
            self._refresh_reuse()
            return True
        if name in ("Up", "Down") and editor.mode == "new" and kind != "bar":
            rows = self._reuse_rows()
            if rows and editor.reuse_open:
                current = editor.reuse_index if editor.reuse_index is not None else self._default_reuse()
                editor.reuse_index = max(0, min(len(rows) - 1, current + (-1 if name == "Up" else 1)))
            return True
        if name == "" and key.text and key.text.isprintable() and not key.ctrl and not key.alt:
            editor.text = key.text if editor.selected else editor.text + key.text
            editor.selected = False
            editor.reuse_open = True
            self._refresh_reuse()
            return True
        return True

    def _reuse_rows(self) -> Tuple[ReuseRow, ...]:
        editor = self.editor
        if editor is None or editor.mode != "new" or not editor.text.strip():
            return ()
        level = self.levels[-1]
        if self._kind(level.host) == "bar":
            return ()
        needle = q.plain_text(editor.text).strip().lower()
        rows: List[ReuseRow] = [ReuseRow("new", "New action “%s”" % q.plain_text(editor.text))]
        for info in q.list_actions(self._env.document):
            text = q.plain_text(info.text)
            if needle in text.lower() or needle in info.name.lower():
                rows.append(ReuseRow("action", text or info.name, info.name, info.shortcut, info.has_icon))
            if len(rows) >= REUSE_LIMIT:
                break
        return tuple(rows)

    def _default_reuse(self) -> int:
        editor = self.editor
        if editor is None:
            return 0
        needle = q.plain_text(editor.text).strip().lower()
        for index, row in enumerate(self._reuse_rows()):
            if row.kind == "action" and row.label.lower() == needle:
                return index
        return 0

    def _refresh_reuse(self) -> None:
        if self.editor is not None:
            self.editor.reuse_index = None

    def _commit(self, then_tab: bool) -> None:
        editor = self.editor
        assert editor is not None
        level = self.levels[-1]
        kind = self._kind(level.host)
        doc = self._env.document
        text = editor.text
        if editor.mode == "edit":
            self.editor = None
            ref = doc.get(editor.ref) if editor.ref is not None else None
            if ref is None or not text.strip():
                return
            entries = self._entries(level)
            entry = entries[level.slot] if level.slot < len(entries) else None
            if entry is None or entry.text == text:
                return
            self._env.run(
                RenameEntry(entry.ref, text, entry.text if entry.kind == "menu" else (entry.name), entry.kind)
            )
            self._focus_selection()
            if then_tab:
                self._tab_on()
            return
        rows = self._reuse_rows() if editor.reuse_open else ()
        pick = editor.reuse_index if editor.reuse_index is not None else self._default_reuse()
        self.editor = None
        if not text.strip():
            return
        if level.host is None:
            self._commit_pending(level, text)
            return
        count = len(self._entries(level))
        where = q.host_phrase(doc, level.host)
        if kind == "bar":
            self._env.run(AddMenu(level.host, count, text))
            level.slot = count
        elif text.strip() == "-" and kind == "menu":
            self._env.run(AddSeparator(level.host, count))
            level.slot = count + 1
        else:
            chosen = rows[pick] if rows and 0 <= pick < len(rows) else None
            if chosen is not None and chosen.kind == "action":
                self._env.run(AddEntry(level.host, count, chosen.label, chosen.name, where))
            else:
                self._env.run(AddEntry(level.host, count, text, None, where))
            level.slot = count + 1
        self._focus_selection()
        if then_tab:
            self._tab_on()

    def _tab_on(self) -> None:
        level = self.levels[-1]
        level.slot = len(self._entries(level))
        self._begin_new("")

    def _commit_pending(self, level: Level, text: str) -> None:
        """First entry typed into an unwritten submenu: the entry becomes a menu."""
        if len(self.levels) < 2 or level.pending is None:
            return
        parent = self.levels[-2]
        doc = self._env.document
        ref = doc.get(level.pending)
        if ref is None or parent.host is None:
            return
        entry = self._entries(parent)[parent.slot]
        title = entry.text
        index = parent.slot
        host = parent.host
        with self._env.group("Add menu %s" % q.plain_text(title)):
            self._env.run(RemoveEntry(entry.ref, title, entry.kind))
            menu = self._env.run(AddMenu(host, index, title))
            self._env.run(AddEntry(menu, 0, text, None, "the %s menu" % q.plain_text(title)))
        parent.slot = index
        self.levels[-1] = Level(menu, 1)
        self._focus_selection()

    def _add_separator(self, level: Level, count: int) -> None:
        if level.host is None:
            return
        self._env.run(AddSeparator(level.host, count))
        level.slot = count + 2
        self._focus_selection()

    def _remove_focused(self) -> None:
        level = self.levels[-1]
        entries = self._entries(level)
        if level.host is None or level.slot >= len(entries):
            return
        entry = entries[level.slot]
        doc = self._env.document
        if entry.kind == "menu" and entry.target is not None:
            inside = len(q.entries(doc, entry.target))
            if inside and not self._env.confirm(
                "Remove the %s menu and its %d entries?" % (q.plain_text(entry.text), inside), "Remove menu"
            ):
                return
        place = q.host_phrase(doc, level.host)
        still = self._env.run(RemoveEntry(entry.ref, entry.text or entry.name, entry.kind))
        if still:
            self._env.toast(
                "Removed %s from %s. It's still on %s. · Undo"
                % (q.plain_text(entry.text), place, " and ".join(still))
            )
        self._clamp(level)
        self._focus_selection()

    # ----------------------------------------------------------- selection
    def _focus_selection(self) -> None:
        """The selection follows the focus: an entry selects its action or menu."""
        level = self.levels[-1]
        self._clamp(level)
        entries = self._entries(level)
        if level.slot < len(entries) and entries[level.slot].target is not None:
            self._env.select((entries[level.slot].target,))  # type: ignore[arg-type]
        elif level.host is not None:
            self._env.select((level.host,))

    # ---------------------------------------------------------------- view
    def view(self) -> EditView:
        doc = self._env.document
        views: List[LevelView] = []
        for number, level in enumerate(self.levels):
            kind = self._kind(level.host)
            entries = self._entries(level)
            rows: List[RowView] = []
            editing: Optional[int] = None
            for index, entry in enumerate(entries):
                info_shortcut = ""
                if entry.kind == "action" and entry.target is not None:
                    node = doc.get(entry.target)
                    if node is not None:
                        value = q.text_of(node, "shortcut")
                        info_shortcut = value
                rows.append(
                    RowView(
                        entry.kind,
                        entry.text or entry.name if entry.kind != "separator" else "",
                        focused=(index == level.slot),
                        opens=entry.kind == "menu",
                        shortcut=info_shortcut,
                    )
                )
            rows.append(RowView("type_here", "Type here", focused=level.slot == len(entries)))
            if kind == "menu":
                rows.append(RowView("add_separator", "Add separator", focused=level.slot == len(entries) + 1))
            last = number == len(self.levels) - 1
            editor = self.editor if last else None
            text = ""
            selected = False
            reuse: Tuple[ReuseRow, ...] = ()
            current = 0
            caption = ""
            if editor is not None:
                editing = level.slot
                text = editor.text
                selected = editor.selected
                if editor.reuse_open:
                    reuse = self._reuse_rows()
                    current = editor.reuse_index if editor.reuse_index is not None else self._default_reuse()
                caption = MNEMONIC_CAPTION
            views.append(LevelView(level.host, kind, tuple(rows), editing, text, selected, reuse, current, caption))
        return EditView(tuple(views))
