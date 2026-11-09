"""The method gesture (CONTRACTS section 16.3).

One form undo step and one edit in the window file's tab. The memo lives on
the log entry, outside the document, so Undo can find the stub after the lines
above it move.
"""

from __future__ import annotations

import os
import weakref
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any, ContextManager, List, Optional, Tuple, cast

from app.features.form_builder.engine.codegen.window_template import (
    TextEdit,
    plan_stub,
    plan_unstub,
    render_window_class,
)
from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.project.handler_names import value_param
from app.features.form_builder.engine.project.window_facts import WindowRead
from app.features.form_builder.engine.project.window_file import file_label, read_window
from app.features.form_builder.integration.handlers import HandlerOutcome, MethodInfo

KEPT = "Removed the step. %s() has your code in it, so it stays in %s."
RENAMED = "Removed the step. %s() was renamed in %s, so the new name stays."
DELETED = "Removed the step. %s() is already gone from %s."
UNREADABLE = "Removed the step. %s can't be read, so %s() was left as it is."
NO_PROJECT = "This form isn't in a project, so it has no window file."
NO_FORMS = "This form isn't in forms/, so Code Studio doesn't write Python for it."


@dataclass(frozen=True)
class HandlerMemo:
    path: str
    relative: str
    method_name: str
    stub_hash: str
    blank_lines: int
    opened_line: bool
    created_file: bool
    params: Tuple[str, ...] = ()
    sender: str = ""
    event_words: str = ""


class GestureBook:
    """Memos live on the log entries, and each form has its own book.

    A discarded redo branch drops its entries. The memos go with them, so a
    later undo cannot fire a toast for a step that is no longer there.
    """

    def __init__(self) -> None:
        self.memos: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
        self.surfaces: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
        self.last_notice = ""

    def arm(self, surface: Any) -> None:
        log = surface.session.log
        self.surfaces[log] = surface
        if getattr(log, "_cbcs_handlers_armed", False):
            return
        original_undo = log.undo
        original_redo = log.redo
        book = self

        def undo() -> bool:
            entries = log.entries()
            tip = entries[-1] if entries else None
            ok = bool(original_undo())
            if ok and tip is not None:
                book.after_undo(log, tip)
            return ok

        def redo() -> bool:
            ok = bool(original_redo())
            if ok:
                entries = log.entries()
                tip = entries[-1] if entries else None
                if tip is not None:
                    book.after_redo(log, tip)
            return ok

        log.undo = undo  # type: ignore[method-assign]
        log.redo = redo  # type: ignore[method-assign]
        log._cbcs_handlers_armed = True

    def note(self, entry: Any, memo: HandlerMemo) -> None:
        self.memos[entry] = memo

    def after_undo(self, log: Any, entry: Any) -> None:
        surface = self.surfaces.get(log)
        memo = self.memos.get(entry)
        if memo is None or surface is None:
            return
        read = _read(surface, memo.path, memo.relative)
        edit = plan_unstub(read, memo.method_name, memo.stub_hash, memo.blank_lines, memo.opened_line)
        if edit is None:
            self.last_notice = _kept_sentence(memo, read)
            _narrate(surface, self.last_notice)
            _publish(surface)
            return
        removed = surface.code_bridge.apply(
            memo.path, edit, base_text=read.source if isinstance(read.source, str) else None
        )
        if removed.ok:
            self.last_notice = ""
        _publish(surface)

    def after_redo(self, log: Any, entry: Any) -> None:
        surface = self.surfaces.get(log)
        memo = self.memos.get(entry)
        if memo is None or surface is None:
            return
        read = _read(surface, memo.path, memo.relative)
        if read.status == "ok" and read.facts.method(memo.method_name) is not None:
            return
        try:
            plan = plan_stub(
                read,
                method_name=memo.method_name,
                params=memo.params,
                sender=memo.sender,
                event_words=memo.event_words,
            )
        except ValueError:
            _publish(surface)
            return
        base = read.source if isinstance(read.source, str) else None
        surface.code_bridge.apply(memo.path, plan.edit, base_text=base)
        _publish(surface)


class CodeHandlers:
    def __init__(self) -> None:
        self.book = GestureBook()

    def _book(self, surface: Any) -> GestureBook:
        book = getattr(surface, "_cbcs_gesture_book", None)
        if not isinstance(book, GestureBook):
            book = GestureBook()
            try:
                surface._cbcs_gesture_book = book
            except (AttributeError, TypeError):
                pass
        self.book = book
        return book

    def make_method(self, surface: Any, request: Any) -> HandlerOutcome:
        # The form step, the window file, and the jump to the new method each
        # ask the status bar for the same text. It is read once at the end.
        with _status_held(surface):
            return self._make_method(surface, request)

    def _make_method(self, surface: Any, request: Any) -> HandlerOutcome:
        book = self._book(surface)
        book.arm(surface)
        waiting = pending_toast(surface)
        if waiting:
            _narrate(surface, waiting)
        method = str(getattr(request, "method", "") or "")
        label = str(getattr(request, "label", "") or "")
        commands = tuple(getattr(request, "commands", ()) or ())
        if not method:
            return _commit(surface, label or "Edit events", commands)
        scope = surface.session.scope
        if not getattr(scope, "generates", False):
            return _fail(surface, _ungenerated(scope))
        path = str(getattr(scope, "window_path", "") or "")
        root = str(getattr(scope, "project_root", "") or "")
        if not path or not root:
            return _fail(surface, _ungenerated(scope))
        relative = os.path.relpath(path, root).replace("\\", "/")
        bridge = surface.code_bridge
        read = _read(surface, path, relative)
        text = read.source if isinstance(read.source, str) else bridge.text_of(path)
        created = False
        if read.status == "missing":
            try:
                rendered = render_window_class(surface.session.document, scope=scope)
            except ValueError as exc:
                return _fail(surface, str(exc))
            made = bridge.apply(path, TextEdit(0, 0, rendered))
            if not made.ok:
                return _fail(surface, made.reason)
            created = True
            text = bridge.text_of(path)
            read = read_window(root, relative, text=text)
        existing = read.facts.method(method) if read.status == "ok" else None
        if existing is not None:
            add_name = _add_label(surface, request, method)
            outcome = _commit(surface, add_name, _relabel(commands, add_name))
            if outcome.ok and getattr(request, "open_code", False):
                self.go_to(surface, method)
            elif outcome.ok:
                _narrate(surface, "Call %s()" % method)
            return outcome
        params = _params_of(request, method)
        sender = str(getattr(request, "sender", "") or "")
        words = str(getattr(request, "event_words", "") or "")
        try:
            plan = plan_stub(
                read,
                method_name=method,
                params=params,
                sender=sender,
                event_words=words,
            )
        except ValueError as exc:
            return _fail(surface, str(exc))
        base = read.source if isinstance(read.source, str) else text
        # Save now, but tell the checks after the form step is stored. Both
        # then see the same text and the same form, and the second reuses
        # the first instead of parsing the window file again.
        notify, pending = _hold_save_notify(bridge)
        replay = False
        try:
            try:
                applied = bridge.apply(path, plan.edit, base_text=base)
            finally:
                bridge.notify_saved = notify  # type: ignore[method-assign]
            if not applied.ok:
                return _fail(surface, applied.reason)
            if read.status == "ok":
                from app.features.form_builder.engine.project.handler_checks import note_inserted_method
                from app.features.form_builder.engine.project.window_file import install_inserted_method

                token_now = bridge.buffer_token(path) if callable(getattr(bridge, "buffer_token", None)) else None
                install_inserted_method(root, relative, read, plan, None if token_now is None else str(token_now))
                note_inserted_method(relative, method)
            replay = True
            before = len(surface.session.log.entries())
            try:
                outcome = _commit(surface, label or _write_label(request), commands)
            except CommandRejected as exc:
                replay = False
                if applied.inverse is not None:
                    bridge.apply(path, applied.inverse)
                return _fail(surface, str(exc))
            if not outcome.ok:
                replay = False
                if applied.inverse is not None:
                    bridge.apply(path, applied.inverse)
                return _fail(surface, outcome.reason)
        finally:
            if replay:
                _notify_when_idle(notify, pending)
        entries = surface.session.log.entries()
        if len(entries) > before:
            book.note(
                entries[-1],
                HandlerMemo(
                    path,
                    relative,
                    method,
                    plan.stub_hash,
                    plan.blank_lines,
                    plan.opened_line,
                    created,
                    params,
                    sender,
                    words,
                ),
            )
        self.go_to(surface, method)
        # The form's save listener already published when the step was stored.
        if not getattr(surface, "_cbcs_handler_checks", False):
            _publish(surface)
        return HandlerOutcome(True, created_method=True)

    def go_to(self, surface: Any, method: str = "") -> bool:
        located = self._located(surface)
        if located is None:
            return False
        path, _root, relative = located
        read = _read(surface, path, relative)
        if read.status != "ok" or not read.facts.class_name:
            line = read.line or 1
            return bool(surface.code_bridge.open_at(path, line))
        if not method:
            return bool(surface.code_bridge.open_at(path, read.facts.line or 1))
        found = read.facts.method(method)
        if found is None:
            return False
        line, select = _caret(read, found.line)
        opened = bool(surface.code_bridge.open_at(path, line, select))
        if opened:
            _back_hint(surface)
        return opened

    def inherited_names(self, class_name: str) -> Tuple[str, ...]:
        from app.features.form_builder.integration.handler_checks_bridge import inherited_names

        return inherited_names(class_name)

    def methods(self, surface: Any) -> Tuple[MethodInfo, ...]:
        read = self.reading(surface)
        if read.status != "ok":
            return ()
        return tuple(
            MethodInfo(item.name, item.line, item.params[: item.required])
            for item in read.facts.methods
            if item.kind == "method"
        )

    def reading(self, surface: Any) -> WindowRead:
        located = self._located(surface)
        if located is None:
            scope = getattr(getattr(surface, "session", None), "scope", None)
            return WindowRead("missing", _ungenerated(scope) if scope is not None else NO_PROJECT)
        path, _root, relative = located
        return _read(surface, path, relative)

    def _located(self, surface: Any) -> Optional[Tuple[str, str, str]]:
        scope = getattr(getattr(surface, "session", None), "scope", None)
        path = str(getattr(scope, "window_path", "") or "")
        root = str(getattr(scope, "project_root", "") or "")
        if not path or not root:
            return None
        return path, root, os.path.relpath(path, root).replace("\\", "/")


SERVICE = CodeHandlers()


def _commit(surface: Any, label: str, commands: Tuple[Any, ...]) -> HandlerOutcome:
    if not commands:
        return HandlerOutcome(True)
    log = surface.session.log
    try:
        with log.transaction(label):
            for command in commands:
                log.execute(command)
    except CommandRejected as exc:
        return HandlerOutcome(False, str(exc))
    return HandlerOutcome(True)


def prewarm_window_read(surface: Any) -> None:
    """Parse the window file on an idle turn so the first double-click does not.

    Does not open a tab. A missing file stays missing until the gesture that
    creates it.
    """
    if getattr(surface, "_cbcs_window_prewarmed", False):
        return
    located = SERVICE._located(surface)
    if located is None:
        return
    path, root, relative = located
    bridge = getattr(surface, "code_bridge", None)
    token = None
    text = None
    if bridge is not None:
        ask = getattr(bridge, "buffer_token", None)
        if callable(ask):
            token = ask(path)
        if token:
            reader = getattr(bridge, "text_of", None)
            if callable(reader):
                got = reader(path)
                if isinstance(got, str):
                    text = got
    if isinstance(text, str):
        read_window(root, relative, text=text, token=str(token) if token else None)
        _warm_first_commit(surface)
        surface._cbcs_window_prewarmed = True
        return
    read = read_window(root, relative)
    if read.status == "ok":
        _warm_first_commit(surface)
        surface._cbcs_window_prewarmed = True


def _warm_first_commit(surface: Any) -> None:
    """Import the first command's helpers and remember the form's events.

    Both are paid once. On the idle turn they stay off the first double-click.
    """
    from app.features.form_builder.engine import diagnostic_codes
    from app.features.form_builder.engine.commands.participants import default_registry
    from app.features.form_builder.engine.logic.events import read_events

    diagnostic_codes.discover()
    default_registry()
    session = getattr(surface, "session", None)
    document = getattr(session, "document", None)
    if document is not None:
        read_events(document)
    # The first double-click opens the code tab. Loading the grammar there is
    # the same work on every form, so the idle turn does it once.
    try:
        from app.treesitter.loader import initialize_tree_sitter_runtime
    except ImportError:
        return
    initialize_tree_sitter_runtime()
    # The tab's highlighter compiles the highlight and locals queries. That is
    # the largest one-time cost in the tab open, and the same for every form.
    located = SERVICE._located(surface)
    if located is None:
        return
    from app.treesitter.highlighter_core import prewarm_queries
    from app.treesitter.language_registry import default_tree_sitter_language_registry

    resolved = default_tree_sitter_language_registry().resolve_for_path(file_path=located[0])
    if resolved is not None:
        prewarm_queries(resolved)


def _read(surface: Any, path: str, relative: str) -> WindowRead:
    scope = surface.session.scope
    root = str(getattr(scope, "project_root", "") or "")
    token = None
    ask = getattr(surface.code_bridge, "buffer_token", None)
    if callable(ask):
        token = ask(path)
    if token:
        from app.features.form_builder.engine.project.window_file import peek_window

        peeked = peek_window(root, relative, str(token))
        if peeked is not None:
            return peeked
    text = surface.code_bridge.text_of(path)
    return read_window(root, relative, text=text, token=token)


def _params_of(request: Any, method: str) -> Tuple[str, ...]:
    raw = str(getattr(request, "params", "") or "").strip()
    if raw:
        return tuple(part.strip() for part in raw.split(",") if part.strip())
    for command in tuple(getattr(request, "commands", ()) or ()):
        for step in tuple(getattr(command, "steps", ()) or ()):
            if getattr(step, "verb", "") == "call" and getattr(step, "method", "") == method:
                if int(getattr(step, "args", 0) or 0) > 0:
                    signal = str(getattr(command, "signal_name", "") or "")
                    return (value_param(signal + "()"),)
    return ()


_BACK_HINT_SHOWN = False


def _back_hint(surface: Any) -> None:
    """One sentence the first time code is opened from the form (UX 13.3.8)."""
    global _BACK_HINT_SHOWN
    if _BACK_HINT_SHOWN:
        return
    narrate = getattr(surface, "narrate", None)
    if not callable(narrate):
        return
    scope = getattr(getattr(surface, "session", None), "scope", None)
    ui = os.path.basename(str(getattr(scope, "ui_path", "") or "")) or "the form"
    _BACK_HINT_SHOWN = True
    narrate("Ctrl+Z in %s takes this back. F12 on the method goes back to the form." % ui)


def _add_label(surface: Any, request: Any, method: str) -> str:
    from app.features.form_builder.engine.query.tab_stops import display_name

    sender = str(getattr(request, "sender", "") or "")
    words = str(getattr(request, "event_words", "") or "")
    shown = sender
    document = getattr(getattr(surface, "session", None), "document", None)
    if document is not None and sender:
        shown = display_name(document, sender)
    if shown and words:
        return "Add Call %s() to %s %s" % (method, shown, words)
    return "Add Call %s()" % method


def _relabel(commands: Tuple[Any, ...], label: str) -> Tuple[Any, ...]:
    from dataclasses import replace

    changed = []
    for command in commands:
        if hasattr(command, "caption"):
            changed.append(replace(command, caption=label))
        else:
            changed.append(command)
    return tuple(changed)


def _write_label(request: Any) -> str:
    sender = str(getattr(request, "sender", "") or "")
    words = str(getattr(request, "event_words", "") or "")
    if sender and words:
        return "Write code for %s %s" % (sender, words)
    return "Write code for %s" % str(getattr(request, "method", "") or "method")


def _ungenerated(scope: Any) -> str:
    if not getattr(scope, "project_root", None):
        return NO_PROJECT
    return NO_FORMS


def _narrate(surface: Any, sentence: str) -> None:
    narrate = getattr(surface, "narrate", None)
    if callable(narrate) and sentence:
        narrate(sentence)


def _fail(surface: Any, reason: str) -> HandlerOutcome:
    _narrate(surface, reason)
    return HandlerOutcome(False, reason)


def _kept_sentence(memo: HandlerMemo, read: WindowRead) -> str:
    label = file_label(memo.relative)
    if read.status != "ok":
        return UNREADABLE % (label, memo.method_name)
    method = read.facts.method(memo.method_name)
    if method is not None:
        return KEPT % (memo.method_name, label)
    for item in read.facts.methods:
        if item.source_hash == memo.stub_hash:
            return RENAMED % (memo.method_name, label)
    return DELETED % (memo.method_name, label)


def _caret(read: WindowRead, def_line: int) -> Tuple[int, Optional[Tuple[int, int]]]:
    """The first body line. A docstring on the next line is skipped. ``pass`` is selected when that line has it."""
    lines = (read.source or "").splitlines()
    index = def_line
    if index < len(lines):
        stripped = lines[index].lstrip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            index += 1
    if index >= len(lines):
        return def_line + 1, None
    text = lines[index]
    at = text.find("pass")
    select = (at, at + 4) if at >= 0 else None
    return index + 1, select


def pending_toast(surface: Any) -> str:
    """The undo sentence, once. The next make narrates it when the UI has not asked yet."""
    book = getattr(surface, "_cbcs_gesture_book", None)
    if not isinstance(book, GestureBook):
        book = SERVICE.book
    sentence = book.last_notice
    book.last_notice = ""
    return sentence


def _hold_save_notify(bridge: Any) -> Tuple[Any, List[str]]:
    """Keep the save's notify until the caller has stored the form step."""
    pending: List[str] = []
    notify = bridge.notify_saved

    def hold(path: str) -> None:
        pending.append(str(path))

    bridge.notify_saved = hold  # type: ignore[method-assign]
    return notify, pending


def _status_held(surface: Any) -> "ContextManager[None]":
    """Hold the shell's status-bar refreshes for the length of a gesture."""
    try:
        workflow = getattr(surface.window(), "_editor_tab_workflow", None)
    except (AttributeError, RuntimeError):
        return nullcontext()
    hold = getattr(workflow, "hold_status_updates", None)
    if not callable(hold):
        return nullcontext()
    return cast("ContextManager[None]", hold())


def _notify_when_idle(notify: Any, saved: List[str]) -> None:
    """Tell the save listeners once the loop is about to block.

    The form step is stored. The checks that follow read the whole window file
    and the form, so they wait for the idle turn the way the editor's own
    after-save work does.
    """
    from app.shell.idle_turn import run_when_idle

    paths = tuple(saved)

    def tell() -> None:
        for path in paths:
            notify(path)

    run_when_idle(tell)


def _publish(surface: Any) -> None:
    from app.features.form_builder.integration.handler_checks_bridge import publish

    publish(surface)
