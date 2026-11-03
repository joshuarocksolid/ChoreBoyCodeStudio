"""Apply eject as one form undo step and one window-file edit.

Neither file is saved. Form undo restores the window while the form tab is open.
If the window text changed after eject, undo of both files is refused.
The memo is keyed by the log entry, not by id(doc).
"""

from __future__ import annotations

import weakref
from dataclasses import dataclass
from typing import Any, Optional, Union

from app.features.form_builder.engine.codegen.eject import EjectPlan, plan_eject, window_edit
from app.features.form_builder.engine.codegen.window_template import TextEdit
from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.qtside.data_panel.host import session_of, surface_of


@dataclass(frozen=True)
class _Memo:
    path: str
    filename: str
    before: str
    after: str
    inverse: TextEdit
    forward: TextEdit


class EjectBook:
    def __init__(self) -> None:
        self.memos: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
        self.surfaces: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
        self.latest: dict = {}
        self.busy = False

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
            memo = book.memos.get(tip) if tip is not None else None
            if memo is None:
                return bool(original_undo())
            current = _window_text(surface, memo.path)
            if current != memo.after and current != memo.before:
                _say(surface, _refused(memo.filename))
                return False
            book.busy = True
            try:
                ok = bool(original_undo())
                if ok and current == memo.after:
                    if not book._restore(surface, memo, memo.inverse, memo.after):
                        original_redo()
                        return False
                return ok
            finally:
                book.busy = False

        def redo() -> bool:
            pending = log._redo[-1] if getattr(log, "_redo", None) else None
            memo = book.memos.get(pending) if pending is not None else None
            if memo is None:
                return bool(original_redo())
            current = _window_text(surface, memo.path)
            if current != memo.before and current != memo.after:
                _say(surface, _refused(memo.filename))
                return False
            book.busy = True
            try:
                ok = bool(original_redo())
                if ok and current == memo.before:
                    if not book._restore(surface, memo, memo.forward, memo.before):
                        original_undo()
                        return False
                return ok
            finally:
                book.busy = False

        log.undo = undo  # type: ignore[method-assign]
        log.redo = redo  # type: ignore[method-assign]
        log._cbcs_eject_armed = True

    def note(self, entry: Any, memo: _Memo, surface: Any) -> None:
        self.memos[entry] = memo
        self.latest[memo.path] = memo
        self._watch(surface, memo.path)

    def _restore(self, surface: Any, memo: _Memo, edit: TextEdit, base: str) -> bool:
        bridge = getattr(surface, "code_bridge", None)
        if bridge is None:
            return False
        result = bridge.apply(memo.path, edit, base_text=base, keep_dirty=True)
        if not result.ok:
            _say(surface, _refused(memo.filename))
        return bool(result.ok)

    def _watch(self, surface: Any, path: str) -> None:
        document = _document(surface, path)
        if document is None or getattr(document, "_cbcs_eject_watch", False):
            return
        book = self

        def changed() -> None:
            if book.busy:
                return
            memo = book.latest.get(path)
            log = getattr(getattr(surface, "session", None), "log", None)
            if memo is None or log is None:
                return
            current = _window_text(surface, path)
            book.busy = True
            try:
                if current == memo.before and log.undo_label() == "Eject to code":
                    log.undo()
                elif current == memo.after and log.redo_label() == "Eject to code":
                    log.redo()
            finally:
                book.busy = False

        document.contentsChanged.connect(changed)
        document._cbcs_eject_watch = True


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
    current = _window_text(surface, path)
    if current is None:
        bridge.open_at(path, 1)
        current = _window_text(surface, path)
    if current is None:
        return "Couldn't open %s." % plan.window_filename
    try:
        edit = window_edit(current, plan)
    except ValueError as exc:
        return str(exc)
    result = bridge.apply(path, edit, base_text=current, keep_dirty=True)
    if not result.ok or result.inverse is None:
        return result.reason or "The window file could not be edited."
    try:
        with session.log.transaction("Eject to code"):
            for command in plan.commands:
                session.log.execute(command)
    except CommandRejected as exc:
        bridge.apply(path, result.inverse, base_text=edit.text, keep_dirty=True)
        return str(exc)
    entries = session.log.entries()
    if entries:
        inverse = result.inverse
        memo = _Memo(
            path,
            plan.window_filename,
            current,
            edit.text,
            TextEdit(int(inverse.start), int(inverse.end), str(inverse.text)),
            TextEdit(0, len(current), edit.text),
        )
        _BOOK.note(entries[-1], memo, surface)
        _BOOK.arm(surface)
    return ""


def _window_text(surface: Any, path: str) -> Optional[str]:
    bridge = getattr(surface, "code_bridge", None)
    if bridge is None:
        return None
    reader = getattr(bridge, "text_of", None)
    if callable(reader):
        found = reader(path)
        return None if found is None else str(found)
    reader = getattr(bridge, "open_text", None)
    if callable(reader):
        found = reader(path)
        return None if found is None else str(found)
    return None


def _document(surface: Any, path: str) -> Any:
    bridge = getattr(surface, "code_bridge", None)
    port = getattr(bridge, "_port", None)
    manager = getattr(port, "_editors", None)
    if manager is None or not hasattr(manager, "find_by_path"):
        return None
    editor = manager.find_by_path(path)
    widget = getattr(editor, "widget", None) if editor is not None else None
    if widget is None or not hasattr(widget, "document"):
        return None
    return widget.document()


def _refused(filename: str) -> str:
    return "%s changed after Eject, so Eject can't be undone. Undo your edits there first." % filename


def _say(surface: Any, sentence: str) -> None:
    surface._eject_notice = sentence
    narrate = getattr(surface, "narrate", None)
    if callable(narrate):
        narrate(sentence)
