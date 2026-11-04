"""Eject writes the form, the generated module, and the window file as one unit.

The three files land together. Open tabs reload from that text, so an editor
undo cannot reach back past the eject. Form undo restores every file unless
one changed since, on disk or in an open tab.
"""

from __future__ import annotations

import os
import weakref
from dataclasses import dataclass, replace
from typing import Any, Optional, Sequence, Tuple, Union

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.codegen.header import is_hand_edited
from app.features.form_builder.engine.codegen.eject import (
    EjectPlan,
    plan_eject,
    window_edit,
    window_objections,
)
from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.project.written_files import note_written_files
from app.persistence.file_unit import (
    bytes_for,
    commit_files,
    restore_file,
    same_bytes,
    same_text,
)
from app.features.form_builder.qtside.data_panel.host import session_of, surface_of
from app.persistence.atomic_write import atomic_write_text


@dataclass(frozen=True)
class _File:
    path: str
    before: Optional[bytes]
    after: bytes


@dataclass(frozen=True)
class _Memo:
    files: Tuple[_File, ...]


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
            changed = _changed(surface, memo, "after")
            if changed:
                _say(surface, _refused(changed))
                return False
            if not original_undo():
                return False
            problem = _apply(memo.files, "before")
            if problem:
                original_redo()
                _say(surface, problem)
                return False
            _reload_files(surface, memo.files, "before")
            _settle(surface)
            return True

        def redo() -> bool:
            pending = log._redo[-1] if getattr(log, "_redo", None) else None
            memo = book.memos.get(pending) if pending is not None else None
            if memo is None:
                return bool(original_redo())
            changed = _changed(surface, memo, "before")
            if changed:
                _say(surface, _refused(changed))
                return False
            if not original_redo():
                return False
            problem = _apply(memo.files, "after")
            if problem:
                original_undo()
                _say(surface, problem)
                return False
            _reload_files(surface, memo.files, "after")
            _settle(surface)
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
    if surface is not None:
        blocked = _blocked(surface, scope)
        if blocked:
            return blocked
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
    blocked = _blocked(surface, scope)
    if blocked:
        return blocked
    saved = _save_dirty_form(surface, session, ui_path)
    if saved:
        return saved
    current = _window_text(surface, path)
    if current is None:
        return "Couldn't read %s." % plan.window_filename
    try:
        edit = window_edit(current, plan)
    except ValueError as exc:
        return str(exc)
    new_py = edit.text
    try:
        with session.log.transaction("Eject to code"):
            for command in plan.commands:
                session.log.execute(command)
    except CommandRejected as exc:
        return str(exc)
    files = _unit(session.document, scope, ui_path, session.text(), path, new_py)
    if isinstance(files, str):
        _abandon(session)
        _say(surface, files)
        return files
    problem = commit_files(
        tuple((item.path, item.after, item.before) for item in files),
        replace=os.replace,
    )
    if problem:
        _abandon(session)
        _say(surface, problem)
        return problem
    note_written_files(tuple(item.path for item in files))
    _reload_files(surface, files, "after")
    entries = session.log.entries()
    if entries:
        _BOOK.note(entries[-1], _Memo(files), surface)
        _BOOK.arm(surface)
    return ""


def _blocked(surface: Any, scope: Any) -> str:
    """A sentence when eject must stop before the dialog. Empty when it may continue."""

    window_path = str(getattr(scope, "window_path", "") or "")
    generated = str(getattr(scope, "generated_path", "") or "")
    for path in (window_path, generated):
        dirty = _unsaved(surface, path)
        if dirty:
            return "Save or discard your changes to %s first." % os.path.basename(dirty)
    return _hand_sentence(generated)


def _hand_sentence(path: str) -> str:
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return ""
    if not is_hand_edited(text):
        return ""
    return "%s has edits made by hand. Saving the form will replace them." % os.path.basename(path)


def _settle(surface: Any) -> None:
    """A clean form stays clean after undo when the text still matches the file."""

    source = getattr(surface, "_source", None)
    session = getattr(surface, "session", None)
    mark = getattr(source, "mark_saved", None)
    if source is None or session is None or not callable(mark) or not source.is_dirty():
        return
    form_path = getattr(surface, "form_path", None)
    path = str(form_path() or "") if callable(form_path) else ""
    if not path:
        path = str(getattr(getattr(session, "scope", None), "ui_path", "") or "")
    disk = _disk_text(path)
    if disk is None or not same_text(session.text(), disk):
        return
    mark(disk)


def _unsaved(surface: Any, path: str) -> str:
    """A path whose open tab differs from disk. Empty when there is nothing to save."""

    if not path:
        return ""
    tab = _tab_text(surface, path)
    if tab is None:
        return ""
    disk = _disk_text(path)
    if disk is None or not same_text(tab, disk):
        return path
    return ""


def _still(surface: Any, path: str, expected: Optional[bytes]) -> bool:
    """True when disk and any open tab still hold the text this step wrote."""

    if not path:
        return True
    found = _disk_bytes(path)
    if not same_bytes(found, expected):
        return False
    tab = _tab_text(surface, path)
    if tab is None or expected is None:
        return True
    return same_text(tab, _text_of(expected))


def _save_dirty_form(surface: Any, session: Any, ui_path: str) -> str:
    """Save the form tab through the normal save path. Empty when it was clean."""

    source = getattr(surface, "_source", None)
    tab_dirty = bool(_unsaved(surface, ui_path))
    source_dirty = bool(source is not None and source.is_dirty())
    if not tab_dirty and not source_dirty:
        return ""
    if source is not None and source_dirty:
        text = source.current_text()
    else:
        text = _tab_text(surface, ui_path) or session.text()
    try:
        atomic_write_text(ui_path, text)
    except OSError:
        return "Couldn't save %s." % os.path.basename(ui_path)
    if source is not None:
        source.mark_saved(text)
        source.after_save()
        notice = getattr(source, "_notice", None)
        if getattr(notice, "error", False):
            return str(getattr(notice, "text", "") or "Couldn't save %s." % os.path.basename(ui_path))
    _reload(surface, ui_path, text)
    return ""


def _unit(
    document: Any,
    scope: Any,
    ui_path: str,
    ui_text: str,
    window_path: str,
    window_text: str,
) -> Union[Tuple[_File, ...], str]:
    files = [
        _File(ui_path, _disk_bytes(ui_path), bytes_for(ui_path, ui_text)),
        _File(window_path, _disk_bytes(window_path), bytes_for(window_path, window_text)),
    ]
    generated = str(getattr(scope, "generated_path", "") or "")
    if not generated:
        return tuple(files)
    result = generate_form_module(document, scope=scope, source_bytes=ui_text.encode("utf-8"))
    if not result.text:
        message = result.diagnostics[0].message if result.diagnostics else "Couldn't write the generated file."
        return message
    files.append(_File(generated, _disk_bytes(generated), bytes_for(generated, result.text)))
    return tuple(files)


def _abandon(session: Any) -> None:
    undo = getattr(session.log, "undo", None)
    if callable(undo):
        undo()
    drop = getattr(session.log, "_drop_redo", None)
    if callable(drop):
        drop()


def _changed(surface: Any, memo: _Memo, field: str) -> str:
    for item in memo.files:
        expected = item.after if field == "after" else item.before
        if not _still(surface, item.path, expected):
            return os.path.basename(item.path)
    return ""


def _apply(files: Sequence[_File], field: str) -> str:
    applied: list[_File] = []
    for item in files:
        payload = item.before if field == "before" else item.after
        sentence = restore_file(item.path, payload, os.replace)
        if sentence:
            other = "after" if field == "before" else "before"
            for earlier in reversed(applied):
                restore_file(
                    earlier.path,
                    earlier.after if other == "after" else earlier.before,
                    os.replace,
                )
            return sentence
        applied.append(item)
    return ""


def _reload_files(surface: Any, files: Sequence[_File], field: str) -> None:
    for item in files:
        payload = item.after if field == "after" else item.before
        if payload is None:
            continue
        _reload(surface, item.path, _text_of(payload).replace("\r\n", "\n").replace("\r", "\n"))


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
