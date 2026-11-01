"""Rename one method across the open form and its window file."""

from __future__ import annotations

import io
import os
import tokenize
from dataclasses import dataclass, is_dataclass, replace
from typing import List, Optional, Sequence, Tuple

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import SetFormSlots, SetLogic
from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
from app.features.form_builder.engine.logic.codec import parse_json, write_json
from app.features.form_builder.engine.logic.compat import signature_text, split_signature
from app.features.form_builder.engine.logic.events import read_events
from app.features.form_builder.engine.logic.events_codec import EventStep
from app.features.form_builder.engine.logic.refs import map_json_formulas
from app.features.form_builder.engine.logic.storage import FORMULA_KEYS
from app.features.form_builder.engine.project.handler_checks import shadow_sentence
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.schema import SlotsDecl
from app.features.form_builder.engine.ui4.values import CStringValue, StringValue
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
        # A closed form on disk is left alone. Saving it would write a file the person has not opened.
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
        status, updated_plan = _edit_window_file(window, seed.window_path, plan)
        if status == "fail":
            for surface in done:
                _undo_if(surface, label)
            return RenameFollowThrough(True, plan, "The window file could not be edited.")
        return RenameFollowThrough(False, updated_plan, "")


def register(window: object) -> None:
    window._form_builder_method_rename = MethodRename()  # type: ignore[attr-defined]


def _method_rename_commands(doc: UiDocument, old: str, new: str) -> Tuple[object, ...]:
    """One form's commands. Private to this module. The transaction label is applied by the caller."""
    commands: List[object] = []
    for node in doc.iter_preorder():
        if not isinstance(node, WidgetNode):
            continue
        for key in FORMULA_KEYS:
            text = _stored(node, key)
            if not text:
                continue
            updated = _window_call(text, old, new)
            if updated != text:
                commands.append(SetLogic(node.id, key, updated))
        validate = _stored(node, "cbcsValidate")
        if validate:
            updated_json = _rewrite_json(validate, old, new)
            if updated_json != validate:
                commands.append(SetLogic(node.id, "cbcsValidate", updated_json))
    for state in read_events(doc):
        steps = tuple(_rename_step(step, old, new) for step in state.steps)
        if steps != state.steps:
            commands.append(SetEventSteps(state.sender, state.signal_name, steps))
    declared = doc.ui.field("form_slots")
    if isinstance(declared, SlotsDecl):
        slots: List[str] = []
        changed = False
        for signature in declared.slots:
            name, params = split_signature(signature)
            if name == old:
                signature = signature_text(new, params)
                changed = True
            slots.append(signature)
        if changed:
            commands.append(SetFormSlots(tuple(declared.signals), tuple(slots)))
    return tuple(commands)


def _rename_step(step: EventStep, old: str, new: str) -> EventStep:
    method = step.method
    slot = step.slot
    when = step.when
    raw = step.raw
    changed = False
    if step.verb == "call" and method == old:
        method = new
        changed = True
    if slot:
        name, params = split_signature(slot)
        if name == old:
            slot = signature_text(new, params)
            changed = True
    if isinstance(when, str):
        updated = _window_call(when, old, new)
        if updated != when:
            when = updated
            changed = True
    if raw is not None:
        renamed = _rename_raw(raw, old, new)
        if renamed is not raw:
            raw = renamed
            changed = True
    if not changed:
        return step
    return replace(step, method=method, slot=slot, when=when, raw=raw)


def _rename_raw(raw: object, old: str, new: str) -> object:
    fields = getattr(raw, "fields", None)
    when = getattr(raw, "when", None)
    if not isinstance(fields, tuple):
        return raw
    updated_fields = []
    changed = False
    for key, value in fields:
        if key == "method" and value == old:
            value = new
            changed = True
        elif isinstance(value, str) and key in ("when", "formula"):
            rewritten = _window_call(value, old, new)
            if rewritten != value:
                value = rewritten
                changed = True
        updated_fields.append((key, value))
    new_when = _window_call(when, old, new) if isinstance(when, str) else when
    if new_when != when:
        changed = True
    if not changed:
        return raw
    if is_dataclass(raw):
        try:
            return replace(raw, fields=tuple(updated_fields), when=new_when)  # type: ignore[type-var]
        except TypeError:
            return raw
    return raw


def _window_call(text: str, old: str, new: str) -> str:
    """Replace ``window.old`` name tokens. ``rename_formula`` skips a name after a dot."""
    if not text or not old or old == new or "window" not in text:
        return text
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError, IndentationError):
        return text
    older = None
    previous = None
    chosen = []
    for token in tokens:
        if (
            token.type == tokenize.NAME
            and token.string == old
            and previous is not None
            and previous.type == tokenize.OP
            and previous.string == "."
            and older is not None
            and older.type == tokenize.NAME
            and older.string == "window"
        ):
            chosen.append(token)
        older = previous
        previous = token
    if not chosen:
        return text
    starts: List[int] = []
    offset = 0
    for line in text.split("\n"):
        starts.append(offset)
        offset += len(line) + 1
    pieces: List[Tuple[int, int]] = []
    for token in chosen:
        row, column = token.start
        end_row, end_column = token.end
        if row != end_row or row - 1 >= len(starts):
            return text
        begin = starts[row - 1] + column
        end = starts[row - 1] + end_column
        if text[begin:end] != token.string:
            return text
        pieces.append((begin, end))
    result = text
    for begin, end in sorted(pieces, reverse=True):
        result = result[:begin] + new + result[end:]
    return result


def _rewrite_json(text: str, old: str, new: str) -> str:
    parsed = parse_json(text)
    if parsed.error is not None or parsed.value is None:
        return text
    mapped = map_json_formulas(parsed.value, lambda formula: _window_call(formula, old, new))
    if mapped == parsed.value:
        return text
    return write_json(mapped)


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


def _stored(node: object, key: str) -> Optional[str]:
    try:
        value = node.value(key)  # type: ignore[attr-defined]
    except Exception:
        return None
    if isinstance(value, (StringValue, CStringValue)):
        return value.text
    return None


def _same(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))


__all__ = ["MethodRename", "MethodSeed", "RenameFollowThrough", "register"]
