"""Apply eject as one form undo step and one window-file edit.

Form undo applies the window inverse while the form tab is still open.
The memo is keyed by the log entry, not by id(doc).
"""

from __future__ import annotations

import os
import weakref
from dataclasses import dataclass
from typing import Any, Union

from app.features.form_builder.engine.codegen.eject import EjectPlan, plan_eject, window_edit
from app.features.form_builder.engine.codegen.window_template import TextEdit
from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.qtside.data_panel.host import session_of, surface_of


@dataclass(frozen=True)
class _Memo:
    path: str
    inverse: TextEdit
    forward: TextEdit


class EjectBook:
    def __init__(self) -> None:
        self.memos: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
        self.surfaces: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()

    def arm(self, surface: Any) -> None:
        log = surface.session.log
        self.surfaces[log] = surface
        if getattr(log, "_cbcs_eject_armed", False):
            return
        original_undo = log.undo
        original_redo = log.redo
        book = self

        def undo() -> bool:
            entries = log.entries()
            tip = entries[-1] if entries else None
            ok = bool(original_undo())
            if ok and tip is not None:
                book._apply(log, tip, undo=True)
            return ok

        def redo() -> bool:
            ok = bool(original_redo())
            if ok:
                entries = log.entries()
                tip = entries[-1] if entries else None
                if tip is not None:
                    book._apply(log, tip, undo=False)
            return ok

        log.undo = undo  # type: ignore[method-assign]
        log.redo = redo  # type: ignore[method-assign]
        log._cbcs_eject_armed = True

    def note(self, entry: Any, memo: _Memo) -> None:
        self.memos[entry] = memo

    def _apply(self, log: Any, entry: Any, *, undo: bool) -> None:
        memo = self.memos.get(entry)
        surface = self.surfaces.get(log)
        if memo is None or surface is None:
            return
        bridge = getattr(surface, "code_bridge", None)
        if bridge is None:
            return
        edit = memo.inverse if undo else memo.forward
        bridge.apply(memo.path, edit)


_BOOK = EjectBook()


def plan_for(host: Any) -> Union[EjectPlan, str]:
    session = session_of(host)
    if session is None:
        return "Open the form, then eject it."
    scope = session.scope
    try:
        return plan_eject(session.document, scope)
    except ValueError as exc:
        return str(exc)


def commit_eject(host: Any, plan: EjectPlan) -> str:
    """Returns a sentence when eject did not finish. Empty when it did."""

    session = session_of(host)
    surface = surface_of(host)
    if session is None or surface is None:
        return "Open the form and its window file, then eject."
    scope = session.scope
    path = str(getattr(scope, "window_path", "") or "")
    if not path:
        return "This form has no window file."
    bridge = surface.code_bridge
    current = bridge.open_text(path)
    if current is None and os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as handle:
                current = handle.read()
        except OSError:
            current = None
    if current is None:
        return "Open %s, then eject, so Undo can restore it." % plan.window_filename
    try:
        edit = window_edit(current, plan)
    except ValueError as exc:
        return str(exc)
    result = bridge.apply(path, edit, base_text=current)
    if not result.ok or result.inverse is None:
        return result.reason or "The window file could not be edited."
    try:
        with session.log.transaction("Eject to code"):
            for command in plan.commands:
                session.log.execute(command)
    except CommandRejected as exc:
        bridge.apply(path, result.inverse)
        return str(exc)
    entries = session.log.entries()
    if entries:
        inverse = result.inverse
        forward = TextEdit(0, len(current), edit.text)
        _BOOK.note(
            entries[-1],
            _Memo(path, TextEdit(int(inverse.start), int(inverse.end), str(inverse.text)), forward),
        )
        _BOOK.arm(surface)
    return ""
