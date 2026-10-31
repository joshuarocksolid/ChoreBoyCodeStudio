"""M6 picker groups: DO THIS (order 10) and YOUR CODE (order 20).

The row helpers moved here unchanged. They still take ``(ctx, signal)``; the
registered callables read the page signal so the step page can ask ``rows(ctx)``.
"""

from __future__ import annotations

from typing import Optional

from app.features.form_builder.engine.logic import compat
from app.features.form_builder.qtside.pickers.groups_ext import PickerGroup, page_signal


def _intent_rows(ctx: object, event: Optional[str]) -> list:
    from app.features.form_builder.engine.logic.intents.m6 import intents_for
    from app.features.form_builder.qtside.pickers.flow import Item, _intent_search

    specs = intents_for(ctx.doc, ctx.classes, ctx.source.sender, event)  # type: ignore[attr-defined]
    rows = []
    if specs:
        rows.append(Item("header", "", "DO THIS", header=True))
        for spec in specs:
            rows.append(Item("intent", spec.intent_id, spec.words, search=_intent_search(ctx, spec)))
    return rows


def _code_rows(ctx: object, signal: str) -> list:
    from app.features.form_builder.qtside.pickers.flow import Item, _other_event_method, _sends, _used_methods
    from app.features.form_builder.qtside.pickers.method_page import _fitting

    rows = [Item("header", "", "YOUR CODE", header=True), Item("new-method", "", "Call a new method\u2026")]
    if not ctx.window_file and not ctx.methods and not ctx.method_infos:  # type: ignore[attr-defined]
        rows.append(Item("header", "", "This form isn't in a project, so it has no window file.", header=True))
        return rows
    rows.append(Item("header", "", ctx.window_file, header=True))  # type: ignore[attr-defined]
    used = _used_methods(ctx, signal)
    sends = len(_sends(ctx, signal))
    for info in _fitting(ctx, sends):
        name = str(getattr(info, "name", info) or "")
        if not name or not compat.is_name(name) or _other_event_method(ctx, name, signal):
            continue
        mark = " already here" if name in used else ""
        rows.append(Item("method", name, "Call %s()%s" % (name, mark)))
    return rows


def _do_this(ctx: object) -> list:
    return _intent_rows(ctx, page_signal())


def _your_code(ctx: object) -> list:
    return _code_rows(ctx, page_signal())


def register(registry: object) -> None:
    add = getattr(registry, "add")
    add(PickerGroup("do-this", 10, "DO THIS", _do_this))
    add(PickerGroup("your-code", 20, "YOUR CODE", _your_code))
