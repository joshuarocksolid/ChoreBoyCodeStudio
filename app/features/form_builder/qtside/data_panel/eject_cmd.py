"""Eject writes the form file and the window file as one unit.

Both files land on disk together. Open tabs reload from that text, so an
editor undo cannot reach back past the eject. Form undo restores both files
unless either one changed since, on disk or in an open tab.
"""

from __future__ import annotations

import os
import weakref
from dataclasses import dataclass, replace
from typing import Any, Optional, Tuple, Union

from app.features.form_builder.engine.codegen.eject import (
    EjectPlan,
    plan_eject,
    window_edit,
    window_objections,
)
from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.qtside.data_panel.host import session_of, surface_of


@dataclass(frozen=True)
class _Memo:
    path: str
    ui_path: str
    filename: str
    ui_name: str
    before_py: bytes
    after_py: bytes
    before_ui: bytes
    after_ui: bytes


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
            memo = book.memos.get(tip) if tip is not None else None
            if memo is None:
                return bool(original_undo())
            if not _still(surface, memo.path, memo.after_py) or not _still(surface, memo.ui_path, memo.after_ui):
                _say(surface, _refused(memo.filename))
                return False
            if not original_undo():
                return False
            problem = _swap_pair(
                memo.ui_path, memo.before_ui, memo.path, memo.before_py, memo.after_ui, memo.after_py
            )
            if problem:
                original_redo()
                _say(surface, problem)
                return False
            _reload(surface, memo.ui_path, _text_of(memo.before_ui))
            _reload(surface, memo.path, _text_of(memo.before_py))
            return True

        def redo() -> bool:
            pending = log._redo[-1] if getattr(log, "_redo", None) else None
            memo = book.memos.get(pending) if pending is not None else None
            if memo is None:
                return bool(original_redo())
            if not _still(surface, memo.path, memo.before_py) or not _still(surface, memo.ui_path, memo.before_ui):
                _say(surface, _refused(memo.filename))
                return False
            if not original_redo():
                return False
            problem = _swap_pair(
                memo.ui_path, memo.after_ui, memo.path, memo.after_py, memo.before_ui, memo.before_py
            )
            if problem:
                original_undo()
                _say(surface, problem)
                return False
            _reload(surface, memo.ui_path, _text_of(memo.after_ui))
            _reload(surface, memo.path, _text_of(memo.after_py))
            return True

        log.undo = undo  # type: ignore[method-assign]
        log.redo = redo  # type: ignore[method-assign]
        log._cbcs_eject_armed = True

    def note(self, entry: Any, memo: _Memo, surface: Any) -> None:
        self.memos[entry] = memo


_BOOK = EjectBook()


def plan_for(host: Any) -> Union[EjectPlan, str]:
    session = session_of(host)
    surface = surface_of(host)
    if session is None:
        return "Open the form, then eject it."
    scope = session.scope
    window_path = str(getattr(scope, "window_path", "") or "")
    ui_path = str(getattr(scope, "ui_path", "") or "")
    if surface is not None:
        dirty = _unsaved(surface, window_path) or _unsaved(surface, ui_path)
        if dirty:
            return "Save or discard your changes to %s first." % os.path.basename(dirty)
    source = _window_source(host, window_path)
    try:
        plan = plan_eject(session.document, scope, source)
    except ValueError as exc:
        return str(exc)
    if not source:
        return plan
    try:
        notes = window_objections(source, plan)
    except ValueError as exc:
        return str(exc)
    if notes:
        plan = replace(plan, summary=plan.summary + notes)
    return plan


def commit_eject(host: Any, plan: EjectPlan) -> str:
    """Returns a sentence when eject did not finish. Empty when it did."""

    session = session_of(host)
    surface = surface_of(host)
    if session is None or surface is None:
        return "Open the form and its window file, then eject."
    scope = session.scope
    path = str(getattr(scope, "window_path", "") or "")
    ui_path = str(getattr(scope, "ui_path", "") or "")
    if not path or not ui_path:
        return "This form has no window file."
    dirty = _unsaved(surface, path) or _unsaved(surface, ui_path)
    if dirty:
        return "Save or discard your changes to %s first." % os.path.basename(dirty)
    current = _window_text(surface, path)
    if current is None:
        return "Couldn't read %s." % plan.window_filename
    try:
        edit = window_edit(current, plan)
    except ValueError as exc:
        return str(exc)
    new_py = edit.text
    before_py = _disk_bytes(path)
    before_ui = _disk_bytes(ui_path)
    try:
        with session.log.transaction("Eject to code"):
            for command in plan.commands:
                session.log.execute(command)
    except CommandRejected as exc:
        return str(exc)
    new_ui = session.text().encode("utf-8")
    after_py = new_py.encode("utf-8")
    problem = _swap_pair(ui_path, new_ui, path, after_py, before_ui, before_py)
    if problem:
        session.log.undo()
        return problem
    _reload(surface, ui_path, session.text())
    _reload(surface, path, new_py)
    entries = session.log.entries()
    if entries:
        memo = _Memo(
            path,
            ui_path,
            plan.window_filename,
            os.path.basename(ui_path),
            before_py if before_py is not None else b"",
            after_py,
            before_ui if before_ui is not None else b"",
            new_ui,
        )
        _BOOK.note(entries[-1], memo, surface)
        _BOOK.arm(surface)
    return ""


def _unsaved(surface: Any, path: str) -> str:
    """A path whose open tab differs from disk. Empty when there is nothing to save."""

    if not path:
        return ""
    tab = _tab_text(surface, path)
    if tab is None:
        return ""
    disk = _disk_text(path)
    if disk is None or tab != disk:
        return path
    return ""


def _still(surface: Any, path: str, expected: bytes) -> bool:
    """True when disk and any open tab still hold the text eject wrote."""

    if not path:
        return True
    found = _disk_bytes(path)
    if found != expected:
        return False
    tab = _tab_text(surface, path)
    if tab is None:
        return True
    return tab.encode("utf-8") == expected


def _swap_pair(
    ui_path: str,
    ui_new: bytes,
    py_path: str,
    py_new: bytes,
    ui_old: Optional[bytes],
    py_old: Optional[bytes],
) -> str:
    """Write both files. On any failure, put back what was there and say so."""

    jobs: Tuple[Tuple[str, bytes, Optional[bytes]], ...] = (
        (ui_path, ui_new, ui_old),
        (py_path, py_new, py_old),
    )
    temps = []
    done = []
    try:
        for path, data, _old in jobs:
            directory = os.path.dirname(path) or "."
            os.makedirs(directory, exist_ok=True)
            temp = path + ".cbcs-tmp"
            with open(temp, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            temps.append(temp)
        for (path, _data, _old), temp in zip(jobs, temps):
            os.replace(temp, path)
            done.append(path)
    except OSError:
        for path, _data, old in reversed(jobs):
            if path in done:
                _put_back(path, old)
        for temp in temps:
            if os.path.isfile(temp):
                try:
                    os.remove(temp)
                except OSError:
                    pass
        return "Couldn't save %s and %s. Nothing was changed." % (
            os.path.basename(ui_path),
            os.path.basename(py_path),
        )
    return ""


def _put_back(path: str, old: Optional[bytes]) -> None:
    try:
        if old is None:
            if os.path.isfile(path):
                os.remove(path)
            return
        with open(path, "wb") as handle:
            handle.write(old)
    except OSError:
        pass


def _release_other_form(keeper: Any, path: str) -> None:
    """Drop a form tab for ``path`` before a reload subscribes a new one."""

    owners = [keeper]
    window = getattr(keeper, "window", None)
    if callable(window):
        try:
            found = window()
        except RuntimeError:
            found = None
        if found is not None and found is not keeper:
            owners.append(found)
    for owner in owners:
        registry = getattr(owner, "_tab_content_registry", None)
        finder = getattr(registry, "surface_for_path", None)
        if not callable(finder):
            continue
        other = finder(path)
        if other is None or other is keeper:
            continue
        release = getattr(other, "release", None)
        if callable(release):
            release()
        return


def _reload(surface: Any, path: str, text: str) -> None:
    _release_other_form(surface, path)
    bridge = getattr(surface, "code_bridge", None)
    port = getattr(bridge, "_port", None)
    reload = getattr(port, "reload_saved", None)
    if callable(reload):
        reload(path, text)


def _text_of(data: bytes) -> str:
    return data.decode("utf-8")


def _window_source(host: Any, path: str) -> str:
    surface = surface_of(host)
    if surface is None or not path:
        return ""
    found = _tab_text(surface, path)
    if found:
        return found
    return _disk_text(path) or ""


def _window_text(surface: Any, path: str) -> Optional[str]:
    """The open tab, or the file on disk when the tab is closed."""

    found = _tab_text(surface, path)
    if found is not None:
        return found
    return _disk_text(path)


def _tab_text(surface: Any, path: str) -> Optional[str]:
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


def _disk_text(path: str) -> Optional[str]:
    data = _disk_bytes(path)
    if data is None:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeError:
        return None


def _disk_bytes(path: str) -> Optional[bytes]:
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return None


def _refused(filename: str) -> str:
    return "%s changed after Eject, so Eject can't be undone. Undo your edits there first." % filename


def _say(surface: Any, sentence: str) -> None:
    surface._eject_notice = sentence
    narrate = getattr(surface, "narrate", None)
    if callable(narrate):
        narrate(sentence)
