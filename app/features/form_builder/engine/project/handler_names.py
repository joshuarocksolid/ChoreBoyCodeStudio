"""Suggested method names (UX-CODE-001). Qt-free.

One function, ``suggest_method_name``, applies the naming rules. The event-word
tables are the copy in UX_SPEC 13.3.8, so the stub docstring and the FB202
sentence use the same words as the Events list will.
"""

from __future__ import annotations

import keyword
from typing import Iterable, Tuple

_MAX_LEN = 40

#: A button or an action with text is named from that text. Other classes use
#: the object-name stem (UX-CODE-001).
_TEXT_CLASSES = frozenset(
    {"QPushButton", "QToolButton", "QCommandLinkButton", "QAction"}
)

#: Longest first, so CheckBox is removed before Check.
_STEM_SUFFIXES = (
    "CheckBox",
    "ComboBox",
    "LineEdit",
    "SpinBox",
    "Button",
    "Check",
    "Radio",
    "Combo",
    "Edit",
    "Spin",
    "Slider",
    "Dial",
    "Tabs",
    "List",
    "View",
    "Action",
    "Date",
    "Box",
    "Btn",
)

_SHORT = {
    "clicked": "clicked",
    "pressed": "pressed",
    "released": "released",
    "toggled": "toggled",
    "editingFinished": "done",
    "returnPressed": "enter",
    "textChanged": "text_changed",
    "textEdited": "typed",
    "currentIndexChanged": "changed",
    "activated": "picked",
    "valueChanged": "changed",
    "dateChanged": "changed",
    "timeChanged": "changed",
    "dateTimeChanged": "changed",
    "currentChanged": "page_changed",
    "itemActivated": "opened",
    "currentRowChanged": "row_changed",
    "accepted": "ok",
    "rejected": "cancel",
    "triggered": "chosen",
    "finished": "closed",
}

_DOC = {
    "clicked": "clicked",
    "pressed": "pressed",
    "released": "released",
    "toggled": "checked or unchecked",
    "editingFinished": "finished editing",
    "returnPressed": "given Enter",
    "textChanged": "changed",
    "textEdited": "changed",
    "currentIndexChanged": "changed",
    "activated": "picked",
    "valueChanged": "changed",
    "dateChanged": "changed",
    "timeChanged": "changed",
    "dateTimeChanged": "changed",
    "currentChanged": "switched to another page",
    "itemActivated": "opened",
    "currentRowChanged": "moved to another row",
    "accepted": "accepted",
    "rejected": "cancelled",
    "triggered": "chosen",
    "finished": "closed",
}

_HEADER = {
    "clicked": "clicked",
    "pressed": "pressed",
    "released": "released",
    "toggled": "checked or unchecked",
    "editingFinished": "editing is finished",
    "returnPressed": "Enter is pressed",
    "textChanged": "the text changes",
    "textEdited": "the text is typed",
    "currentIndexChanged": "the choice changes",
    "activated": "a choice is picked",
    "valueChanged": "the value changes",
    "dateChanged": "the date changes",
    "timeChanged": "the time changes",
    "dateTimeChanged": "the date or time changes",
    "currentChanged": "the page changes",
    "itemActivated": "an item is opened",
    "currentRowChanged": "another row is chosen",
    "accepted": "OK is pressed",
    "rejected": "Cancel is pressed",
    "triggered": "chosen",
    "finished": "it closes",
}

_PARAM = {
    "toggled": "checked",
    "textChanged": "text",
    "textEdited": "text",
    "currentIndexChanged": "index",
    "activated": "index",
    "currentChanged": "index",
    "valueChanged": "value",
    "dateChanged": "date",
    "timeChanged": "time",
    "dateTimeChanged": "date_time",
    "itemActivated": "item",
}


def signal_name(signature: str) -> str:
    """``clicked(bool)`` to ``clicked``."""
    return signature.split("(", 1)[0].strip()


def short_word(signature: str, class_name: str = "") -> str:
    """The method-name word for a signal (UX_SPEC 13.3.8)."""
    name = signal_name(signature)
    if name == "clicked" and class_name == "QDialogButtonBox":
        return "button_clicked"
    found = _SHORT.get(name)
    if found:
        return found
    return _snake(name) or "event"


def docstring_words(signature: str, class_name: str = "") -> str:
    """The words inside ``Runs when {object} is {words}."""
    name = signal_name(signature)
    if name == "clicked" and class_name == "QDialogButtonBox":
        return "clicked"
    found = _DOC.get(name)
    if found:
        return found
    return name or "used"


def header_words(signature: str, class_name: str = "") -> str:
    """The words in problem sentences (``but {event words} sends``)."""
    name = signal_name(signature)
    if name == "clicked" and class_name == "QDialogButtonBox":
        return "any of its buttons is clicked"
    found = _HEADER.get(name)
    if found:
        return found
    return name or "used"


def value_param(signature: str, class_name: str = "") -> str:
    """The parameter name when "My method receives…" is ticked (UX-CODE-004)."""
    name = signal_name(signature)
    if name == "clicked" and class_name == "QDialogButtonBox":
        return "button"
    return _PARAM.get(name, "value")


def form_stem(form_class: str) -> str:
    """``Invoice`` to ``invoice``, ``ShopWindow`` to ``shop``."""
    snake = _snake(form_class)
    for suffix in ("_window", "_dialog", "_form"):
        if snake.endswith(suffix) and snake != suffix:
            snake = snake[: -len(suffix)]
            break
    if not snake or not snake[0].isalpha():
        return "form"
    return snake


def suggest_method_name(
    *,
    class_name: str,
    object_name: str,
    text: str,
    signal: str,
    form_class: str,
    taken: Iterable[str],
    inherited: Iterable[str],
) -> str:
    """The name UX-CODE-001 would put in the method field.

    ``taken`` is the window class's methods plus the form's ``<slots>``.
    ``inherited`` is the public attribute names of the window's stock Qt base.
    """
    used = frozenset(taken)
    shadow = frozenset(inherited)
    stem = form_stem(form_class)
    word = short_word(signal, class_name)
    from_text = ""
    if class_name in _TEXT_CLASSES:
        from_text = _from_label(text)
    if from_text:
        name = from_text
        if "_" not in name:
            name = "%s_%s" % (name, stem)
    else:
        name = _from_object(object_name, word)
    return _finish(name, used, shadow, stem)


def _from_object(object_name: str, word: str) -> str:
    raw = object_name.strip()
    stem = raw
    for suffix in _STEM_SUFFIXES:
        if raw.endswith(suffix) and len(raw) > len(suffix):
            stem = raw[: -len(suffix)]
            break
    snake = _snake(stem)
    usable = bool(snake) and any(ch.isalpha() for ch in snake) and len(snake) > 1
    if not usable:
        snake = _snake(raw)
    if not snake:
        snake = "widget"
    if word:
        return "%s_%s" % (snake, word)
    return snake


def _from_label(text: str) -> str:
    chars = []
    for ch in text:
        if ch == "&":
            continue
        if ch.isascii() and (ch.isalnum() or ch == "_"):
            chars.append(ch)
        else:
            chars.append(" ")
    parts = []
    for word in "".join(chars).split():
        piece = _snake(word)
        if piece:
            parts.append(piece)
    return "_".join(parts)


def _snake(text: str) -> str:
    out: list = []
    chars = list(text)
    for index, ch in enumerate(chars):
        if ch == "_":
            if out and out[-1] != "_":
                out.append("_")
            continue
        if not (ch.isascii() and ch.isalnum()):
            if out and out[-1] != "_":
                out.append("_")
            continue
        prev = chars[index - 1] if index else ""
        nxt = chars[index + 1] if index + 1 < len(chars) else ""
        if ch.isupper() and out and out[-1] != "_":
            new_word = prev.islower() or prev.isdigit() or (prev.isupper() and nxt.islower())
            if new_word:
                out.append("_")
        out.append(ch.lower())
    return "".join(out).strip("_")


def _finish(name: str, taken: frozenset, inherited: frozenset, stem: str) -> str:
    name = name.strip("_")
    if not name:
        name = "handler"
    if name.startswith("cbcs"):
        name = "do_" + name
    if name.startswith("on_"):
        name = "do_" + name
    if not name[0].isalpha():
        name = "do_" + name
    if keyword.iskeyword(name):
        name = name + "_"
    if name in inherited:
        name = "%s_%s" % (name, stem)
        if keyword.iskeyword(name):
            name = name + "_"
    name = _clip(name)
    return _unique(name, taken)


def _clip(name: str) -> str:
    if len(name) <= _MAX_LEN:
        return name
    cut = name.rfind("_", 0, _MAX_LEN + 1)
    if cut > 0:
        return name[:cut]
    return name[:_MAX_LEN]


def _unique(name: str, taken: frozenset) -> str:
    if name not in taken:
        return name
    number = 2
    while True:
        suffix = "_%d" % number
        room = _MAX_LEN - len(suffix)
        base = name if len(name) <= room else _clip(name[:room])
        base = base.rstrip("_")
        if not base or not base[0].isalpha():
            base = "handler"
        candidate = base + suffix
        if candidate not in taken:
            return candidate
        number += 1


def signature_arg_count(signature: str) -> int:
    """How many values ``clicked(bool)`` sends. ``clicked()`` sends none."""
    start = signature.find("(")
    end = signature.rfind(")")
    if start < 0 or end <= start:
        return 0
    inner = signature[start + 1 : end].strip()
    if not inner or inner == "void":
        return 0
    return len([part for part in inner.split(",") if part.strip()])


def arg_names(params: Tuple[str, ...]) -> str:
    """``(checked,)`` to ``checked`` for the FB202 sentence."""
    return ", ".join(params)
