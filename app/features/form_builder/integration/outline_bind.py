"""Perform one outline effect. The pane owns the widgets. This module owns the switch."""

from __future__ import annotations

from typing import Any, Callable, Dict

from app.qt.QtCore import Qt
from app.qt.QtGui import QKeySequence
from app.qt.qt_compat import enum_value

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import ApplyLayout, MoveNodes, Rename
from app.features.form_builder.engine.commands.placement import InBoxLayout
from app.features.form_builder.engine.query.outline import (
    AskDelete,
    BareNest,
    CloseName,
    Commit,
    DropCue,
    EditName,
    Effect,
    Expand,
    FilterSet,
    Flash,
    KeyGesture,
    NameInvalid,
    Navigate,
    OpenInsert,
    Route,
)
from app.features.form_builder.engine.shell_commands import normalize_form_shortcut, outline_command_for
from app.features.form_builder.engine.ui4.nodes import LayoutNode

_KEY_NAMES = {
    "Key_Up": "up",
    "Key_Down": "down",
    "Key_Left": "left",
    "Key_Right": "right",
    "Key_Tab": "tab",
    "Key_Backtab": "backtab",
    "Key_Delete": "delete",
    "Key_Backspace": "backspace",
    "Key_F2": "f2",
    "Key_Return": "enter",
    "Key_Enter": "enter",
    "Key_Escape": "esc",
    "Key_Home": "home",
    "Key_End": "end",
    "Key_Slash": "slash",
}


def key_gesture(event: object) -> KeyGesture:
    text = str(getattr(event, "text", lambda: "")() or "")
    return KeyGesture(
        command_id=outline_command_for(_portable(event)),
        key=_key_name(event, text),
        shift=_modified(event, "ShiftModifier") or _key_name(event, text) == "backtab",
        alt=_modified(event, "AltModifier"),
        text=text,
    )


def perform(pane: Any, effect: Effect) -> bool:
    """Run ``effect``. False leaves the key for Qt or the shell."""
    handler = _HANDLERS.get(type(effect))
    if handler is None:
        return False
    return handler(pane, effect)


def _commit(pane: Any, effect: Commit) -> bool:
    _run(pane, effect.commands, effect.label)
    pane.note_edited()
    if effect.toast:
        pane.toast(effect.toast)
    pane.focus_tree()
    return True


def _bare(pane: Any, effect: BareNest) -> bool:
    log = pane.session().log
    try:
        with log.transaction("Nest") as txn:
            layout_id = txn.execute(ApplyLayout(effect.container, effect.layout_class))
            layout = pane.session().document.node(layout_id)
            count = len(layout.items) if isinstance(layout, LayoutNode) else 0
            txn.execute(MoveNodes(effect.ids, InBoxLayout(layout_id, count)))
    except CommandRejected as rejected:
        pane.report(str(rejected))
    pane.note_edited()
    pane.focus_tree()
    return True


def _navigate(pane: Any, effect: Navigate) -> bool:
    pane.show_selection(effect.ids, effect.current, effect.anchor)
    pane.focus_tree()
    return True


def _expand(pane: Any, effect: Expand) -> bool:
    pane.apply_expand(effect)
    return True


def _ask(pane: Any, effect: AskDelete) -> bool:
    pane.show_delete(effect.prose, effect.ids)
    return True


def _route(pane: Any, effect: Route) -> bool:
    runner = getattr(pane, "run_command", None)
    if callable(runner):
        runner(effect.action_id)
    return True


def _insert(pane: Any, effect: OpenInsert) -> bool:
    del effect
    pane.show_insert()
    return True


def _edit(pane: Any, effect: EditName) -> bool:
    pane.begin_rename(effect.node)
    return True


def _close(pane: Any, effect: CloseName) -> bool:
    pane.finish_rename()
    if effect.new_name:
        try:
            pane.session().log.execute(Rename(effect.node, effect.new_name))
        except CommandRejected as rejected:
            pane.report(str(rejected))
            if effect.refocus:
                pane.begin_rename(effect.node)
                pane.show_name_error(str(rejected))
            return True
    pane.note_edited()
    if effect.then_node is not None:
        pane.begin_rename(effect.then_node)
    elif effect.refocus:
        pane.focus_tree()
    return True


def _invalid(pane: Any, effect: NameInvalid) -> bool:
    pane.show_name_error(effect.prose)
    pane.focus_editor()
    return True


def _filter(pane: Any, effect: FilterSet) -> bool:
    pane.apply_filter(effect.text, effect.focus_tree, effect.select)
    return True


def _cue(pane: Any, effect: DropCue) -> bool:
    pane.show_cue(effect)
    if effect.prose:
        pane.report(effect.prose)
    return True


def _flash(pane: Any, effect: Flash) -> bool:
    pane.flash_row(effect.node)
    pane.report(effect.prose)
    pane.focus_tree()
    return True


_HANDLERS: Dict[type, Callable[[Any, Any], bool]] = {
    Commit: _commit,
    BareNest: _bare,
    Navigate: _navigate,
    Expand: _expand,
    AskDelete: _ask,
    Route: _route,
    OpenInsert: _insert,
    EditName: _edit,
    CloseName: _close,
    NameInvalid: _invalid,
    FilterSet: _filter,
    DropCue: _cue,
    Flash: _flash,
}


def _run(pane: Any, commands: tuple, label: str) -> None:
    log = pane.session().log
    try:
        with log.transaction(label) as txn:
            for command in commands:
                txn.execute(command)
    except CommandRejected as rejected:
        pane.report(str(rejected))


def _portable(event: object) -> str:
    key = int(getattr(event, "key")())
    mods = getattr(event, "modifiers")()
    shift = getattr(Qt, "ShiftModifier")
    if key == int(getattr(Qt, "Key_Backtab")):
        key = int(getattr(Qt, "Key_Tab"))
        mods = mods | shift
    try:
        sequence = QKeySequence(enum_value(mods) | key)
    except TypeError:
        return ""
    return normalize_form_shortcut(sequence.toString(QKeySequence.SequenceFormat.PortableText))


def _key_name(event: object, text: str) -> str:
    key = int(getattr(event, "key")())
    key_enum = getattr(Qt, "Key", Qt)
    for name, label in _KEY_NAMES.items():
        if key == int(getattr(key_enum, name)):
            return label
    if text == "/":
        return "slash"
    return ""


def _modified(event: object, name: str) -> bool:
    mods = getattr(event, "modifiers")()
    return bool(enum_value(mods) & enum_value(getattr(Qt, name)))
