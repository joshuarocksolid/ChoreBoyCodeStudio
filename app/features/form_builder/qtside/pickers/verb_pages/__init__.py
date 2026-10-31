"""One editor page per M7 verb. Formula fields are a plain line until the FX editor lands."""

from __future__ import annotations

import json
from typing import Tuple

from app.qt.QtWidgets import QLineEdit, QWidget

from app.features.form_builder.qtside.pickers.flow import Item, Page


def formula_line(parent: QWidget) -> QLineEdit:
    """The formula field. M7.2b replaces this function with the FX editor."""
    edit = QLineEdit(parent)
    edit.setObjectName("formBuilder.formulaLine")
    edit.setAccessibleName("Formula")
    return edit


_PAIRS = {
    "show-hide": ("Show or hide", (("show", "Show"), ("hide", "Hide"))),
    "enable-disable": ("Enable or disable", (("enable", "Enable"), ("disable", "Disable"))),
}

_FIELDS = {
    "validate": ("Check all fields", (("fields", "Fields, separated by commas", False),)),
    "set": ("Set a field", (("field", "Field", False), ("formula", "Formula", True))),
    "clear": ("Clear fields", (("fields", "Fields, separated by commas", False),)),
    "focus": ("Move focus to", (("field", "Field", False),)),
    "enable": ("Enable", (("field", "Field", False),)),
    "disable": ("Disable", (("field", "Field", False),)),
    "show": ("Show", (("field", "Field", False),)),
    "hide": ("Hide", (("field", "Field", False),)),
    "message": (
        "Show a message",
        (("text", "Message", False), ("level", "Level (info, warning or critical)", False), ("formula", "Formula", True)),
    ),
    "ask": ("Ask yes or no", (("text", "Question", False),)),
    "stop": ("Stop here if\u2026", (("when", "Only if", True), ("message", "Message", False))),
    "page": ("Switch tab or page", (("field", "Tab or stack", False), ("page", "Page", False))),
    "openForm": ("Open another form", (("form", "Form", False), ("mode", "Mode (dialog or window)", False))),
    "close": ("Close this form", (("result", "accept, reject or close", False),)),
}


def page_for(back: Page, verb: str) -> Page:
    """The editor for ``verb``, or a Show/Hide (Enable/Disable) choice."""
    pair = _PAIRS.get(verb)
    if pair is not None:
        title, choices = pair
        rows = tuple(Item("verb", name, label) for name, label in choices)
        return Page(
            kind="step",
            title=title,
            filter="",
            current=0,
            rows=rows,
            check="",
            checked=False,
            field="",
            notice="",
            signal=back.signal,
            intent_id="",
            picked_target="",
            wide=back.wide,
            replace_index=back.replace_index,
            back="step",
        )
    spec = _FIELDS.get(verb)
    title = spec[0] if spec is not None else verb
    fields = spec[1] if spec is not None else ()
    rows = []
    seeded = {}
    defaults = {"level": "info", "mode": "dialog", "result": "close"}
    for name, label, formula in fields:
        faint = defaults.get(name, "")
        if faint:
            seeded[name] = faint
        rows.append(Item("vfield", name, label, faint=faint, note="formula" if formula else ""))
    rows.append(Item("add-verb", verb, "Add this step"))
    return Page(
        kind="verb",
        title=title,
        filter="",
        current=len(rows) - 1,
        rows=tuple(rows),
        check="",
        checked=False,
        field=json.dumps(seeded),
        notice="",
        signal=back.signal,
        intent_id=verb,
        picked_target="",
        wide=back.wide,
        replace_index=back.replace_index,
        back="step",
    )


def values_of(page: Page) -> dict:
    try:
        loaded = json.loads(page.field or "{}")
    except ValueError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def fields_of(verb: str) -> Tuple[Tuple[str, str, bool], ...]:
    spec = _FIELDS.get(verb)
    if spec is None:
        return ()
    return spec[1]
