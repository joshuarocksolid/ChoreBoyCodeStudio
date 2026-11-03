"""Rename one method across the open form and its window file."""

from __future__ import annotations

import os
from dataclasses import dataclass, is_dataclass, replace
from typing import List, Optional, Sequence, Tuple

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.project.method_forms import method_rename_commands as _method_rename_commands
from app.features.form_builder.engine.project.handler_checks import shadow_sentence
from app.features.form_builder.qtside.outline.methods import window_methods


@dataclass(frozen=True)
class MethodSeed:
    old_name: str
    window_path: str
    source: str
    cursor: int


@dataclass(frozen=True)
class RenameFollowThrough:
    blocked: bool
    plan: object
    message: str = ""


class MethodRename:
    """seed, refusal, and apply_paired. Menus call ``arm`` before the shell preview."""

    def __init__(self) -> None:
        self._armed: Optional[Tuple[object, str]] = None

    def arm(self, surface: object, method: str) -> None:
        self._armed = (surface, method) if method else None

    def clear(self) -> None:
        self._armed = None

    def seed(self, window: object) -> Optional[MethodSeed]:
        armed = self._armed
        self._armed = None
        if armed is None:
            return None
        surface, method = armed
        path = _window_path(surface)
        source = _read_source(window, path)
        return MethodSeed(method, path, source, _cursor(source, method))

    def refusal(self, window: object, old: str, new: str, file_path: str) -> str:
        del old
        if not new or not file_path:
            return ""
        base = _qt_base_for(window, file_path)
        if not base or new not in window_methods(base):
            return ""
        return shadow_sentence(new, base)

    def apply_paired(self, window: object, seed: MethodSeed, plan: object) -> RenameFollowThrough:
        old = seed.old_name
        new = str(getattr(plan, "new_symbol", "") or "")
        sentence = self.refusal(window, old, new, seed.window_path)
        if sentence:
            return RenameFollowThrough(True, plan, sentence)
        label = "Rename %s to %s" % (old, new)
        done: List[object] = []
        for surface in _surfaces(window):
            if not _same(_window_path(surface), seed.window_path):
                continue
            document = getattr(getattr(surface, "session", None), "document", None)
            log = getattr(getattr(surface, "session", None), "log", None)
            if document is None or log is None:
                continue
            commands = _method_rename_commands(document, old, new)
            if not commands:
                continue
            try:
                with log.transaction(label):
                    for command in commands:
                        log.execute(command)
            except CommandRejected:
                for earlier in done:
                    _undo_if(earlier, label)
                return RenameFollowThrough(True, plan, "The form could not be renamed.")
            done.append(surface)
        try:
            closed = _closed_edits(window, old, new, seed.window_path)
        except CommandRejected:
            for surface in done:
                _undo_if(surface, label)
            return RenameFollowThrough(True, plan, "A form that isn't open could not be renamed.")
        status, updated_plan = _edit_window_file(window, seed.window_path, plan)
        if status == "fail":
            for surface in done:
                _undo_if(surface, label)
            return RenameFollowThrough(True, plan, "The window file could not be edited.")
        written = _write_closed(closed)
        if written is None:
            _restore_window(window, seed)
            for surface in done:
                _undo_if(surface, label)
            return RenameFollowThrough(True, plan, "A form that isn't open could not be renamed.")
        before_text = seed.source
        after_text = ""
        patch = _patch_for(plan, seed.window_path)
        if patch is not None:
            after_text = str(getattr(patch, "updated_content", "") or "")
        if written and not done:
            _mark_closed_anchor(window, seed.window_path, label)
        for surface in done:
            _arm_closed(surface, label, written, window, seed.window_path, before_text, after_text)
        if written and not done:
            _arm_anchor(window, seed.window_path, label, written, before_text, after_text)
        return RenameFollowThrough(False, updated_plan, "")

    def closed_note(self, window: object, seed: MethodSeed, plan: object) -> str:
        """The preview sentence for closed forms this rename will change."""

        new = str(getattr(plan, "new_symbol", "") or "")
        try:
            edits = _closed_edits(window, seed.old_name, new, seed.window_path)
        except CommandRejected:
            return ""
        names = [os.path.basename(edit.path) for edit in edits]
        if not names:
            return ""
        return "Also changes %s (closed)" % ", ".join(names)


def _project_root(window: object) -> str:
    for surface in _surfaces(window):
        request = getattr(surface, "_request", None)
        root = str(getattr(request, "project_root", "") or "")
        if root:
            return root
        scope = getattr(getattr(surface, "session", None), "scope", None)
        root = str(getattr(scope, "project_root", "") or "")
        if root:
            return root
    loaded = getattr(window, "loaded_project", None)
    project = loaded() if callable(loaded) else None
    return str(getattr(project, "project_root", "") or "")


@dataclass(frozen=True)
class _ClosedEdit:
    path: str
    original: bytes
    text: str
    written: bytes = b""


class _ClosedBook:
    def __init__(self) -> None:
        self.memos: dict = {}

    def arm(
        self,
        log: object,
        entry: object,
        edits: Sequence[_ClosedEdit],
        window: object = None,
        path: str = "",
        before: str = "",
        after: str = "",
    ) -> None:
        self.memos[id(entry)] = (entry, edits, window, path, before, after)
        if getattr(log, "_cbcs_closed_armed", False):
            return
        previous_undo = log.undo
        previous_redo = log.redo
        book = self

        def undo() -> bool:
            entries = log.entries()
            tip = entries[-1] if entries else None
            memo = book.memos.get(id(tip)) if tip is not None else None
            if memo is not None:
                sentence = _unchanged(memo[1], written=True) or _window_changed(memo, memo[5])
                if sentence:
                    log._cbcs_rename_notice = sentence
                    return False
            ok = bool(previous_undo())
            if ok and memo is not None:
                _write_bytes(memo[1], restore=True)
                _put_window(memo[2], memo[3], memo[4])
            return ok

        def redo() -> bool:
            pending = log._redo[-1] if getattr(log, "_redo", None) else None
            memo = book.memos.get(id(pending)) if pending is not None else None
            if memo is not None:
                sentence = _unchanged(memo[1], written=False) or _window_changed(memo, memo[4])
                if sentence:
                    log._cbcs_rename_notice = sentence
                    return False
            ok = bool(previous_redo())
            if ok and memo is not None:
                _write_bytes(memo[1], restore=False)
                _put_window(memo[2], memo[3], memo[5])
            return ok

        log.undo = undo  # type: ignore[method-assign]
        log.redo = redo  # type: ignore[method-assign]
        log._cbcs_closed_armed = True


_CLOSED = _ClosedBook()


def _closed_edits(window: object, old: str, new: str, window_path: str) -> List[_ClosedEdit]:
    """Closed forms whose window file is ``window_path``. Nothing is written."""

    if not old or not new or old == new or not window_path:
        return []
    root = _project_root(window)
    if not root:
        return []
    from app.features.form_builder.engine.ids import IdAllocator
    from app.features.form_builder.engine.project.forms import classify_form
    from app.features.form_builder.engine.project.fs import OsFileSystem
    from app.features.form_builder.engine.project.method_forms import rename_method_in_document
    from app.features.form_builder.engine.project.save import project_ui_files
    from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui
    from app.features.form_builder.engine.ui4.writer import write_ui

    opened = set()
    for surface in _surfaces(window):
        form = getattr(surface, "form_path", None)
        path = str(form() or "") if callable(form) else ""
        if path:
            opened.add(os.path.abspath(path))
    wanted = os.path.abspath(window_path)
    files = OsFileSystem()
    found: List[_ClosedEdit] = []
    for path in project_ui_files(root):
        absolute = os.path.abspath(path)
        if absolute in opened:
            continue
        scope = classify_form(absolute, project_root=root)
        if not _same(str(getattr(scope, "window_path", "") or ""), wanted):
            continue
        try:
            current = files.read_bytes(absolute)
            document = read_ui(current.decode("utf-8"), allocator=IdAllocator()).document
        except (OSError, UnicodeError, UiReadError):
            continue
        edited = rename_method_in_document(document, old, new)
        if edited is None:
            continue
        text = write_ui(edited).text
        if text.encode("utf-8") == current:
            continue
        found.append(_ClosedEdit(absolute, current, text))
    return found


def _write_closed(edits: Sequence[_ClosedEdit]) -> Optional[List[_ClosedEdit]]:
    from app.features.form_builder.engine.project.fs import OsFileSystem
    from app.features.form_builder.engine.project.written_files import note_written_files

    files = OsFileSystem()
    written: List[_ClosedEdit] = []
    try:
        for edit in edits:
            files.write_text(edit.path, edit.text)
            payload = files.read_bytes(edit.path)
            written.append(_ClosedEdit(edit.path, edit.original, edit.text, payload))
    except OSError:
        _write_bytes(written, restore=True)
        return None
    if written:
        note_written_files(tuple(edit.path for edit in written))
    return written


def _write_bytes(edits: Sequence[_ClosedEdit], *, restore: bool) -> None:
    for edit in edits:
        payload = edit.original if restore else (edit.written or edit.text.encode("utf-8"))
        try:
            with open(edit.path, "wb") as handle:
                handle.write(payload)
        except OSError:
            continue


def _restore_window(window: object, seed: MethodSeed) -> None:
    from app.features.form_builder.integration.code_bridge import ShellPort

    port = ShellPort(window)
    current = port.open_text(seed.window_path)
    if current is None or current == seed.source:
        return
    port.replace_range(seed.window_path, 0, len(current), seed.source)


def _mark_closed_anchor(window: object, window_path: str, label: str) -> None:
    surface = _anchor_surface(window, window_path)
    log = getattr(getattr(surface, "session", None), "log", None) if surface is not None else None
    mark = getattr(log, "mark", None)
    if log is not None and callable(mark) and log.undo_label() != label:
        mark(label)


def _arm_anchor(
    window: object,
    window_path: str,
    label: str,
    edits: Sequence[_ClosedEdit],
    before: str = "",
    after: str = "",
) -> None:
    surface = _anchor_surface(window, window_path)
    if surface is not None:
        _arm_closed(surface, label, edits, window, window_path, before, after)


def _anchor_surface(window: object, window_path: str) -> object:
    for surface in _surfaces(window):
        if _same(_window_path(surface), window_path):
            return surface
    return None


def _unchanged(edits: Sequence[_ClosedEdit], *, written: bool) -> str:
    """A sentence when a closed file is no longer the bytes this rename left."""

    names = []
    for edit in edits:
        expect = edit.written if written and edit.written else edit.original
        if written and not edit.written:
            expect = edit.text.encode("utf-8")
        try:
            with open(edit.path, "rb") as handle:
                current = handle.read()
        except OSError:
            names.append(os.path.basename(edit.path))
            continue
        if current != expect:
            names.append(os.path.basename(edit.path))
    if not names:
        return ""
    if len(names) == 1:
        return "%s changed after the rename, so the rename can't be undone." % names[0]
    return "%s changed after the rename, so the rename can't be undone." % " and ".join(names)


def _window_changed(memo: tuple, expected: str) -> str:
    window, path = memo[2], memo[3]
    if window is None or not path or expected == "":
        return ""
    from app.features.form_builder.integration.code_bridge import ShellPort

    current = ShellPort(window).open_text(path)
    if current is None or current == expected:
        return ""
    return "%s changed after the rename, so the rename can't be undone." % os.path.basename(path)


def _put_window(window: object, path: str, text: str) -> None:
    if window is None or not path or text == "":
        return
    from app.features.form_builder.integration.code_bridge import ShellPort

    port = ShellPort(window)
    reload = getattr(port, "reload_saved", None)
    if callable(reload) and reload(path, text):
        return
    widget = port._widget(path)
    if widget is not None and hasattr(widget, "setPlainText"):
        widget.setPlainText(text)


def _arm_closed(
    surface: object,
    label: str,
    edits: Sequence[_ClosedEdit],
    window: object = None,
    path: str = "",
    before: str = "",
    after: str = "",
) -> None:
    if not edits:
        return
    log = getattr(getattr(surface, "session", None), "log", None)
    if log is None or log.undo_label() != label:
        return
    entries = log.entries()
    if not entries:
        return
    _CLOSED.arm(log, entries[-1], edits, window, path, before, after)


def register(window: object) -> None:
    window._form_builder_method_rename = MethodRename()  # type: ignore[attr-defined]


def _edit_window_file(window: object, path: str, plan: object) -> Tuple[str, object]:
    patch = _patch_for(plan, path)
    if patch is None:
        return "absent", plan
    updated = str(getattr(patch, "updated_content", "") or "")
    from app.features.form_builder.integration.code_bridge import ShellPort

    port = ShellPort(window)
    current = port.open_text(path)
    if current is None:
        return "absent", plan
    if current != updated:
        if not port.replace_range(path, 0, len(current), updated):
            return "fail", plan
    return "ok", _without(plan, path)


def _patch_for(plan: object, path: str) -> object:
    for patch in getattr(plan, "preview_patches", ()) or ():
        if _same(str(getattr(patch, "file_path", "") or ""), path):
            return patch
    return None


def _without(plan: object, path: str) -> object:
    patches = [
        patch
        for patch in (getattr(plan, "preview_patches", ()) or ())
        if not _same(str(getattr(patch, "file_path", "") or ""), path)
    ]
    if len(patches) == len(list(getattr(plan, "preview_patches", ()) or ())):
        return plan
    if is_dataclass(plan) and not isinstance(plan, type):
        return replace(plan, preview_patches=patches)  # type: ignore[type-var]
    return plan


def _undo_if(surface: object, label: str) -> None:
    log = getattr(getattr(surface, "session", None), "log", None)
    if log is None:
        return
    if log.undo_label() == label and log.can_undo():
        log.undo()


def _surfaces(window: object) -> List[object]:
    found: List[object] = []
    seen = set()
    current = getattr(window, "_form_undo_surface", None)
    if _has_session(current):
        found.append(current)
        seen.add(id(current))
    from app.qt.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return found
    for widget in app.allWidgets():
        if id(widget) in seen or not _has_session(widget):
            continue
        found.append(widget)
        seen.add(id(widget))
    return found


def _has_session(surface: object) -> bool:
    return surface is not None and getattr(surface, "session", None) is not None and callable(
        getattr(surface, "form_path", None)
    )


def _window_path(surface: object) -> str:
    logic = getattr(surface, "logic_window_file", None)
    form = getattr(surface, "form_path", None)
    relative = str(logic() or "") if callable(logic) else ""
    folder = os.path.dirname(str(form() or "")) if callable(form) else ""
    if not relative:
        scope = getattr(getattr(surface, "session", None), "scope", None)
        stored = str(getattr(scope, "window_path", "") or "")
        return os.path.abspath(stored) if stored else ""
    if os.path.isabs(relative):
        return os.path.abspath(relative)
    return os.path.abspath(os.path.join(folder, relative))


def _qt_base_for(window: object, file_path: str) -> str:
    from app.features.form_builder.engine.ui4.defaults import QtClassTable

    classes = QtClassTable.shared()
    for surface in _surfaces(window):
        if not _same(_window_path(surface), file_path):
            continue
        document = getattr(getattr(surface, "session", None), "document", None)
        root = getattr(document, "root", None)
        base = _dialog_base(str(getattr(root, "class_name", "") or ""), classes)
        if base:
            return base
    return ""


def _dialog_base(class_name: str, classes: object) -> str:
    leaf = (class_name or "").rsplit(".", 1)[-1]
    if leaf in ("QDialog", "QMainWindow"):
        return leaf
    chain = getattr(classes, "chain", None)
    names: Sequence[str] = ()
    if callable(chain):
        try:
            raw = chain(leaf)
        except Exception:
            raw = ()
        if isinstance(raw, (list, tuple)):
            names = tuple(str(getattr(info, "name", "") or "") for info in raw)
    for base in ("QDialog", "QMainWindow"):
        if base in names:
            return base
    return ""


def _read_source(window: object, path: str) -> str:
    from app.features.form_builder.integration.code_bridge import ShellPort

    opened = ShellPort(window).open_text(path) if path else None
    if opened is not None:
        return opened
    if path and os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as handle:
                return handle.read()
        except OSError:
            return ""
    return ""


def _cursor(source: str, method: str) -> int:
    import re

    found = re.search(r"^[ \t]*def[ \t]+%s\b" % re.escape(method), source, re.MULTILINE)
    if found is None:
        return 0
    return found.end() - len(method)



def _same(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))


__all__ = ["MethodRename", "MethodSeed", "RenameFollowThrough", "register"]
