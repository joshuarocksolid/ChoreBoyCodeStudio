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
        closed = _rewrite_closed(window, old, new, label)
        if closed:
            for surface in done:
                _undo_if(surface, label)
            return RenameFollowThrough(True, plan, closed)
        status, updated_plan = _edit_window_file(window, seed.window_path, plan)
        if status == "fail":
            for surface in done:
                _undo_if(surface, label)
            return RenameFollowThrough(True, plan, "The window file could not be edited.")
        return RenameFollowThrough(False, updated_plan, "")


def _rewrite_closed(window: object, old: str, new: str, label: str) -> str:
    """Rewrite closed forms that name ``old``. Empty when there is nothing to do or it worked."""

    if not old or not new or old == new:
        return ""
    root = _project_root(window)
    if not root:
        return ""
    from app.features.form_builder.engine.project.closed_forms import rewrite_forms
    from app.features.form_builder.engine.project.method_forms import rename_method_in_document

    opened = {}
    for surface in _surfaces(window):
        session = getattr(surface, "session", None)
        form = getattr(surface, "form_path", None)
        path = str(form() or "") if callable(form) else ""
        if session is not None and path:
            opened[os.path.abspath(path)] = session
    try:
        rewrite_forms(
            root,
            lambda doc: rename_method_in_document(doc, old, new),
            open_sessions=opened,
            undo_label=label,
            apply_open=False,
        )
    except CommandRejected:
        return "A form that isn't open could not be renamed."
    return ""


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
