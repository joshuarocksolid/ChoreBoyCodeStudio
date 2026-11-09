"""Project Find rows for form logic. The shell sees rows, never a Use."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from app.editors.search_service import compile_search_pattern
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.logic.checks import read_checks
from app.features.form_builder.engine.logic.compat import split_signature
from app.features.form_builder.engine.logic.events import read_events
from app.features.form_builder.engine.logic.read_as_text import spoken_display
from app.features.form_builder.engine.logic.refs import FORMULA_JSON_KEYS
from app.features.form_builder.engine.logic.storage import FORMULA_KEYS, signal_property
from app.features.form_builder.engine.logic.uses import WORDS, Use
from app.features.form_builder.engine.project.save import project_ui_files
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.values import CStringValue, StringValue


@dataclass(frozen=True)
class LogicFindRow:
    title: str
    excerpt: str
    column: int
    match_length: int
    token: str


class FormsLogic:
    """claim_chord, rows, and open_row. Installed on the window at startup."""

    def claim_chord(self, window: object) -> bool:
        from app.qt.QtWidgets import QWidget

        from app.features.form_builder.integration.surface import FormSurface

        surface = getattr(window, "_form_undo_surface", None)
        if not isinstance(surface, FormSurface) or not surface.isVisible():
            return False
        text = _selection_text(surface)
        panel = surface.findChild(QWidget, "formBuilder.logic")
        setter = getattr(panel, "set_filter_text", None)
        if callable(setter):
            setter(text)
        workbench = getattr(surface, "_workbench", None)
        focus = getattr(workbench, "focus_section", None)
        if callable(focus):
            focus("logic")
        return True

    def rows(self, project_root: str, query: str, options: object) -> Tuple[LogicFindRow, ...]:
        text = (query or "").strip()
        if not text or not project_root:
            return ()
        pattern = compile_search_pattern(text, options)  # type: ignore[arg-type]
        if pattern is None:
            return ()
        found: List[LogicFindRow] = []
        for path in project_ui_files(project_root):
            document = _read(path)
            if document is None:
                continue
            found.extend(_rows_of(document, path, pattern))
        return tuple(found)

    def open_row(self, window: object, token: str) -> None:
        try:
            data = json.loads(token)
        except (TypeError, ValueError):
            return
        if not isinstance(data, dict):
            return
        path = str(data.get("path") or "")
        if not path:
            return
        factory = getattr(window, "_editor_tab_factory", None)
        opener = getattr(factory, "open_file_in_editor", None)
        if callable(opener):
            opener(path)
        from app.qt.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        registry = getattr(window, "_tab_content_registry", None)
        surface_for = getattr(registry, "surface_for_path", None)
        surface = surface_for(path) if callable(surface_for) else None
        if surface is None:
            return
        use = Use(
            str(data.get("widget") or ""),
            str(data.get("role") or ""),
            str(data.get("kind") or ""),
            str(data.get("widget") or ""),
            "",
            str(data.get("key") or ""),
            int(data.get("index") or 0),
            str(data.get("signal") or ""),
            0,
            path,
            str(data.get("method") or ""),
        )
        open_use = getattr(surface, "open_logic_use", None)
        if callable(open_use):
            open_use(use)


def register(window: object) -> None:
    window._form_builder_forms_logic = FormsLogic()  # type: ignore[attr-defined]


def _selection_text(surface: object) -> str:
    from app.qt.QtWidgets import QApplication

    focus = QApplication.focusWidget()
    if focus is not None:
        cursor_of = getattr(focus, "textCursor", None)
        if callable(cursor_of):
            cursor = cursor_of()
            if cursor.hasSelection():
                return str(cursor.selectedText()).replace("\u2029", "\n")
        selected = getattr(focus, "selectedText", None)
        if callable(selected):
            text = str(selected() or "")
            if text:
                return text
    session = getattr(surface, "session", None)
    selection = getattr(session, "selection", None)
    state = getattr(selection, "state", None)
    ids = getattr(state, "ids", ()) if state is not None else ()
    document = getattr(session, "document", None)
    if len(ids) != 1 or document is None:
        return ""
    node = document.get(ids[0])
    name = str(getattr(node, "object_name", "") or "")
    root = getattr(document, "root", None)
    if not name or name == str(getattr(root, "object_name", "") or ""):
        return ""
    return name


def _read(path: str) -> Optional[UiDocument]:
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        return read_ui(text, allocator=IdAllocator(), source_path=path).document
    except (OSError, UnicodeError, ValueError):
        return None


def _rows_of(doc: UiDocument, path: str, pattern: object) -> List[LogicFindRow]:
    form = os.path.basename(path)
    found: List[LogicFindRow] = []
    for node in doc.iter_preorder():
        if not isinstance(node, WidgetNode) or not node.object_name:
            continue
        display = spoken_display(doc, node.object_name)
        for key in FORMULA_KEYS:
            text = _stored(node, key)
            if text is None or not text.strip():
                continue
            hit = _hit(pattern, (text, display, node.object_name))
            if hit is None:
                continue
            found.append(
                _row(form, display, WORDS.get(key, key), hit, path, "rule", "set", node.object_name, key, 0, "")
            )
        validate = _stored(node, "cbcsValidate")
        if validate:
            read = read_checks(validate)
            for index, check in enumerate(read.checks):
                extras = _strings(check)
                hit = _hit(pattern, (display, node.object_name) + extras)
                if hit is None:
                    continue
                found.append(
                    _row(
                        form,
                        display,
                        _check_label(check),
                        hit,
                        path,
                        "check",
                        "read",
                        node.object_name,
                        "cbcsValidate",
                        index,
                        "",
                    )
                )
    for state in read_events(doc):
        display = spoken_display(doc, state.sender)
        for index, step in enumerate(state.steps):
            method = step.method or (split_signature(step.slot)[0] if step.slot else "")
            texts: List[str] = [display, state.sender]
            if method:
                texts.append(method)
            if step.slot:
                texts.append(step.slot)
            if step.when:
                texts.append(step.when)
            texts.extend(_strings(step.raw) if step.raw is not None else ())
            hit = _hit(pattern, texts)
            if hit is None:
                continue
            words = "Call %s" % method if step.verb == "call" and method else state.signal_name
            found.append(
                _row(
                    form,
                    display,
                    words,
                    hit,
                    path,
                    "step",
                    "call",
                    state.sender,
                    signal_property(state.signal_name),
                    index,
                    state.signal_name,
                    method,
                )
            )
    return found


def _row(
    form: str,
    display: str,
    words: str,
    hit: Tuple[str, int, int],
    path: str,
    kind: str,
    role: str,
    widget: str,
    key: str,
    index: int,
    signal: str,
    method: str = "",
) -> LogicFindRow:
    excerpt, column, length = hit
    token = json.dumps(
        {
            "path": path,
            "kind": kind,
            "role": role,
            "widget": widget,
            "key": key,
            "index": index,
            "signal": signal,
            "method": method,
        },
        sort_keys=True,
    )
    return LogicFindRow("%s · %s · %s" % (form, display, words), excerpt, column, length, token)


def _hit(pattern: object, texts: Sequence[str]) -> Optional[Tuple[str, int, int]]:
    search = getattr(pattern, "search", None)
    if not callable(search):
        return None
    for text in texts:
        if not text:
            continue
        found = search(text)
        if found is None:
            continue
        return text, int(found.start()), int(found.end() - found.start())
    return None


def _check_label(check: object) -> str:
    name = type(check).__name__
    if name == "Required":
        return "Required"
    if name == "Preset":
        return "Email address" if getattr(check, "name", "") == "email" else "Preset"
    return name


def _strings(value: object) -> Tuple[str, ...]:
    found: List[str] = []
    _walk(value, found, 0)
    return tuple(found)


def _walk(value: object, found: List[str], depth: int) -> None:
    if depth > 6:
        return
    if isinstance(value, str):
        if value:
            found.append(value)
        return
    if isinstance(value, (tuple, list)):
        for item in value:
            _walk(item, found, depth + 1)
        return
    pairs = getattr(value, "pairs", None)
    if isinstance(pairs, tuple):
        for key, item in pairs:
            if key in FORMULA_JSON_KEYS or key in ("table", "column", "message", "name"):
                _walk(item, found, depth + 1)
        return
    fields = getattr(value, "__dataclass_fields__", None)
    if isinstance(fields, dict):
        for key in fields:
            _walk(getattr(value, key, None), found, depth + 1)


def _stored(node: object, key: str) -> Optional[str]:
    try:
        value = node.value(key)  # type: ignore[attr-defined]
    except Exception:
        return None
    if isinstance(value, (StringValue, CStringValue)):
        return value.text
    return None


__all__ = ["FormsLogic", "LogicFindRow", "register"]
