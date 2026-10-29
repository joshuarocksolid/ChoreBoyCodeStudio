"""Edits to the text of a style sheet that keep everything else as typed (UX-STYLE-010). Qt-free.

The Text colour row writes ``color: #RRGGBB;``: into the widget's own sheet
when that sheet is empty or holds only declarations, and into a
``#objectName { ... }`` rule when the sheet has rules. Every function returns
new text; a sheet Qt cannot read is refused (``StyleEditRefused``) so the row
never rewrites text it did not understand.
"""

from __future__ import annotations

from typing import List, Mapping, Optional, Tuple

from app.features.form_builder.engine.style.colors import Rgb, hex_text, parse_color
from app.features.form_builder.engine.style.sheet import Declaration, Rule, Sheet, parse_sheet
from app.features.form_builder.engine.style.tokenizer import HASH, tokenize

PROPERTY = "color"
INDENT = "    "


class StyleEditRefused(ValueError):
    """The sheet has an error, so an edit would guess."""


def _readable(text: str) -> Sheet:
    sheet = parse_sheet(text)
    if sheet.errors():
        raise StyleEditRefused("the style sheet has an error")
    return sheet


def _own_rule(sheet: Sheet, object_name: str) -> Optional[Rule]:
    wanted = "#" + object_name
    found: Optional[Rule] = None
    for rule in sheet.rules:
        if " ".join(rule.selector.split()) == wanted and rule.close >= 0:
            found = rule
    return found


def _color_declaration(declarations: Tuple[Declaration, ...]) -> Optional[Declaration]:
    found: Optional[Declaration] = None
    for declaration in declarations:
        if declaration.name.lower() == PROPERTY:
            found = declaration
    return found


def _scope(sheet: Sheet, object_name: str) -> Tuple[Optional[Rule], Tuple[Declaration, ...]]:
    """The rule that holds this widget's colour, and the declarations of the place the row writes."""
    if sheet.rules:
        rule = _own_rule(sheet, object_name)
        return rule, (rule.declarations if rule is not None else ())
    return None, sheet.declarations


def read_color(text: str, object_name: str) -> Optional[str]:
    """The text of the ``color`` value the row manages, or None."""
    if not text.strip():
        return None
    sheet = parse_sheet(text)
    if sheet.errors():
        return None
    _rule, declarations = _scope(sheet, object_name)
    found = _color_declaration(declarations)
    return found.value.strip() if found is not None else None


def read_rgb(text: str, object_name: str) -> Optional[Rgb]:
    value = read_color(text, object_name)
    return parse_color(value) if value is not None else None


def set_color(text: str, rgb: Rgb, object_name: str) -> str:
    color = hex_text(*rgb)
    if not text.strip():
        return "%s: %s;" % (PROPERTY, color)
    sheet = _readable(text)
    rule, declarations = _scope(sheet, object_name)
    found = _color_declaration(declarations)
    if found is not None:
        return text[: found.value_start] + color + text[found.value_end :]
    if sheet.rules:
        if rule is None:
            if not object_name:
                raise StyleEditRefused("the widget has no name")
            return text.rstrip() + "\n\n#%s {\n%s%s: %s;\n}\n" % (object_name, INDENT, PROPERTY, color)
        return _add_to_rule(text, rule, color)
    return _add_bare(text, sheet, color)


def _add_bare(text: str, sheet: Sheet, color: str) -> str:
    base = text.rstrip()
    if sheet.declarations:
        last = sheet.declarations[-1]
        tail = text[last.value_end : last.end]
        if ";" not in tail:
            base = text[: last.value_end].rstrip() + ";" + text[last.value_end :].rstrip()
    elif base and not base.endswith(";"):
        base += ";"
    return "%s\n%s: %s;" % (base, PROPERTY, color) if base else "%s: %s;" % (PROPERTY, color)


def _add_to_rule(text: str, rule: Rule, color: str) -> str:
    insert = "%s%s: %s;\n" % (INDENT, PROPERTY, color)
    body = text[rule.open + 1 : rule.close]
    if not body.strip():
        return text[: rule.open + 1] + "\n" + insert + text[rule.close :]
    head = text[: rule.open + 1]
    inner = body.rstrip()
    if rule.declarations:
        last = rule.declarations[-1]
        if ";" not in text[last.value_end : last.end]:
            inner = text[rule.open + 1 : last.value_end].rstrip() + ";" + text[last.value_end : rule.close].rstrip()
    elif not inner.endswith(";"):
        inner += ";"
    return head + inner + "\n" + insert + text[rule.close :]


def remove_color(text: str, object_name: str) -> str:
    """Drop the ``color`` declaration, and the rule or sheet it leaves empty."""
    if not text.strip():
        return ""
    sheet = _readable(text)
    rule, declarations = _scope(sheet, object_name)
    found = _color_declaration(declarations)
    if found is None:
        return text
    start, end = _line_span(text, found.start, found.end)
    result = text[:start] + text[end:]
    if rule is not None and len(rule.declarations) == 1:
        left = parse_sheet(result)
        again = _own_rule(left, object_name)
        if again is not None and not again.declarations:
            first, last = _line_span(result, again.start, again.end)
            result = result[:first] + result[last:]
    return "" if not result.strip() else result


def _line_span(text: str, start: int, end: int) -> Tuple[int, int]:
    first = start
    while first > 0 and text[first - 1] in " \t":
        first -= 1
    if first > 0 and text[first - 1] != "\n":
        first = start
    last = end
    while last < len(text) and text[last] in " \t":
        last += 1
    if last < len(text) and text[last] == "\n" and (first == 0 or text[first - 1] == "\n"):
        last += 1
    return first, last


def rename_selectors(text: str, mapping: Mapping[str, str]) -> str:
    """Rewrite ``#old`` to ``#new`` in every selector (never in a value such as ``#fff``)."""
    if not any("#" + old in text for old in mapping):
        return text
    sheet = parse_sheet(text)
    spans: List[Tuple[int, int]] = [(rule.start, rule.open) for rule in sheet.rules]
    if not spans:
        return text
    tokens, _problems = tokenize(text)
    hits = [
        token
        for token in tokens
        if token.kind == HASH
        and token.text[1:] in mapping
        and any(first <= token.start < last for first, last in spans)
    ]
    for token in reversed(hits):
        text = text[: token.start] + "#" + mapping[token.text[1:]] + text[token.end :]
    return text


def rename_selector(text: str, old: str, new: str) -> str:
    return rename_selectors(text, {old: new})


def mentions_selector(text: str, name: str) -> bool:
    """True when ``#name`` is in a selector of the sheet."""
    return rename_selectors(text, {name: name + "\u0000"}) != text
