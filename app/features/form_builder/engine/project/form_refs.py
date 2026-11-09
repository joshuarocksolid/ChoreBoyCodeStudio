"""Cross-form names stored on a form: an openForm step, and a list's Open form.

A rename keeps those names on the new stem. Text the codec cannot read stays
as it was stored. Nothing here writes the filesystem.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import List, Optional, Sequence, Tuple

from app.features.form_builder.engine.data.source import ListSource, read_data, write_data
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.logic.codec import parse_steps, write_steps
from app.features.form_builder.engine.logic.storage import is_signal_property, is_user_logic_key
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.values import StringValue


def missing_form_sentence(stem: str) -> str:
    """The Problems sentence when an open-form step names a form that is not in the project."""

    return "%s isn't in this project's forms folder." % stem


def retarget_ui_text(text: str, old: str, new: str) -> Optional[str]:
    """``.ui`` text with ``old`` form stems pointed at ``new``, or None when nothing changed.

    The edit replaces that property's form name inside its ``<string>`` and
    leaves every other byte alone, including comments and Designer spacing.
    A property that cannot be read is left as it was.
    """

    if not old or old == new or old not in text:
        return None
    document = read_ui(text, allocator=IdAllocator()).document
    keys: List[str] = []
    for node in document.iter_preorder():
        for entry in node.properties():
            if not is_user_logic_key(entry.name) or not isinstance(entry.value, StringValue):
                continue
            updated = _retarget_property(entry.name, entry.value.text, old, new)
            if updated is None or updated == entry.value.text:
                continue
            if entry.name not in keys:
                keys.append(entry.name)
    if not keys:
        return None
    edited = text
    for key in keys:
        edited = _replace_form_in_property(edited, key, old, new)
    if edited == text:
        return None
    return edited


_PROPERTY = re.compile(
    r"(<property\b[^>]*\bname=\"(?P<name>[^\"]+)\"[^>]*>)(?P<body>.*?)(</property>)",
    re.DOTALL,
)


def _replace_form_in_property(text: str, key: str, old: str, new: str) -> str:
    """Swap the form name inside one property. Other properties stay byte for byte."""

    def swap(match: re.Match[str]) -> str:
        if match.group("name") != key:
            return match.group(0)
        body = match.group("body")
        replaced = _swap_form_token(body, old, new)
        if replaced == body:
            return match.group(0)
        return match.group(1) + replaced + match.group(4)

    return _PROPERTY.sub(swap, text)


def _swap_form_token(fragment: str, old: str, new: str) -> str:
    """Replace a JSON ``form`` value. Quoted and XML-escaped quotes both count."""

    patterns = (
        (r'("form"\s*:\s*")' + re.escape(old) + r'(")', r"\g<1>" + new + r"\g<2>"),
        (
            r"(&quot;form&quot;\s*:\s*&quot;)" + re.escape(old) + r"(&quot;)",
            r"\g<1>" + new + r"\g<2>",
        ),
    )
    edited = fragment
    for pattern, repl in patterns:
        edited = re.sub(pattern, repl, edited)
    return edited


def _retarget_property(key: str, text: str, old: str, new: str) -> Optional[str]:
    if is_signal_property(key):
        return _retarget_steps(text, old, new)
    if key == "cbcsData":
        return _retarget_list(text, old, new)
    return None


def _retarget_steps(text: str, old: str, new: str) -> Optional[str]:
    read = parse_steps(text)
    if read.error is not None:
        return None
    steps = []
    changed = False
    for step in read.steps:
        fields, fields_changed = _rename_form_field(step.fields, old, new)
        unknown, unknown_changed = _rename_form_field(step.unknown, old, new)
        if step.verb == "openForm" and (fields_changed or unknown_changed):
            changed = True
            step = replace(step, fields=fields, unknown=unknown)
        steps.append(step)
    if not changed:
        return None
    try:
        return write_steps(tuple(steps), read.signal, read.extra)
    except Exception:
        return None


def _rename_form_field(pairs: Sequence[Tuple[str, object]], old: str, new: str) -> Tuple[Tuple[Tuple[str, object], ...], bool]:
    found = False
    renamed = []
    for key, value in pairs:
        if key == "form" and value == old:
            found = True
            renamed.append((key, new))
        else:
            renamed.append((key, value))
    return tuple(renamed), found


def _retarget_list(text: str, old: str, new: str) -> Optional[str]:
    read = read_data(text)
    value = read.value
    if read.error is not None or not isinstance(value, ListSource) or value.open is None:
        return None
    if value.open.form != old:
        return None
    return write_data(replace(value, open=replace(value.open, form=new)))


__all__ = ["missing_form_sentence", "retarget_ui_text"]
