"""Object names inside logic text (CONTRACTS.md section 15.8). Qt-free and pure.

Three kinds of reference follow a rename:

* a *formula* mentions a widget as a NAME token. The text goes through the standard
  library ``tokenize``; only the token's span is replaced, so spacing, strings,
  comments and attribute names are never touched, and text that doesn't tokenize
  is left as it is;
* a *step* names its target in a field (``target`` of a ``slot`` step, and the
  fields other verbs declare in ``NAME_FIELDS``);
* a *label* property (``cbcsErrorLabel``) is one object name.

Every function here is total: a text it can't read is reported as unchanged.
"""

from __future__ import annotations

import io
import keyword
import re
import tokenize
import unicodedata
from typing import Callable, Dict, List, Mapping, Optional, Tuple

from app.features.form_builder.engine.logic.codec import (
    JsonObject,
    JsonValue,
    Step,
    parse_json,
    parse_steps,
    write_json,
    write_steps,
)
from app.features.form_builder.engine.logic.storage import FORMULA_KEYS, LABEL_KEYS, text_kind

#: Keys inside logic JSON whose string value is a formula (CONTRACTS 15.8).
FORMULA_JSON_KEYS: Tuple[str, ...] = ("when", "formula", "default", "min", "max")

#: Step verbs whose fields name objects on the form. ``x`` is one name, ``x[]`` a list of names.
#: ``form`` (a module name) is never here. Later lanes add their verbs with ``declare_name_fields``.
NAME_FIELDS: Dict[str, Tuple[str, ...]] = {
    "slot": ("target",),
    "set": ("field",),
    "clear": ("fields[]",),
    "focus": ("field",),
    "enable": ("field",),
    "disable": ("field",),
    "show": ("field",),
    "hide": ("field",),
    "validate": ("fields[]",),
    "page": ("field", "page"),
    "refreshLookups": ("fields[]",),
    "addRow": ("grid",),
    "deleteRow": ("grid",),
}

#: Longer formula strings are never tokenized (a formula is a line or two).
_MAX_FORMULA_CHARS = 64 * 1024

_SKIP = frozenset(
    {
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.COMMENT,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENDMARKER,
    }
)


def declare_name_fields(verb: str, fields: Tuple[str, ...]) -> None:
    """Say which fields of ``verb`` hold object names (``x`` or ``x[]``)."""
    NAME_FIELDS[verb] = tuple(fields)


# ---------------------------------------------------------------------------
# Formula tokens
# ---------------------------------------------------------------------------


#: Python 3.12+ splits f-strings (3.14 t-strings) into parts with NAME tokens inside. Python
#: 3.9 and 3.11 give one STRING token. Everything from a start to its end is skipped, so a
#: rename never reaches into a string on any version.
_STRING_STARTS = frozenset(
    code for code in (getattr(tokenize, "FSTRING_START", None), getattr(tokenize, "TSTRING_START", None)) if code is not None
)
_STRING_ENDS = frozenset(
    code for code in (getattr(tokenize, "FSTRING_END", None), getattr(tokenize, "TSTRING_END", None)) if code is not None
)


def _same_name(left: str, right: str) -> bool:
    """Python compares identifiers after NFKC normalisation (``\ufb01eld`` is ``field``)."""
    if left == right:
        return True
    if left.isascii() and right.isascii():
        return False
    return unicodedata.normalize("NFKC", left) == unicodedata.normalize("NFKC", right)


def _name_key(name: str) -> str:
    return name if name.isascii() else unicodedata.normalize("NFKC", name)


def _tokens(text: str) -> Optional[List[tokenize.TokenInfo]]:
    if len(text) > _MAX_FORMULA_CHARS:
        return None
    try:
        found: List[tokenize.TokenInfo] = []
        inside = 0
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type == tokenize.ERRORTOKEN:
                return None
            if token.type in _STRING_STARTS:
                inside += 1
                continue
            if token.type in _STRING_ENDS:
                inside -= 1
                continue
            if inside == 0:
                found.append(token)
        return found
    except Exception:  # noqa: BLE001 - text that doesn't tokenize is left alone
        return None


def _name_tokens(text: str) -> List[tokenize.TokenInfo]:
    """NAME tokens that refer to a widget: not after ``.``, not a keyword argument's name."""
    tokens = _tokens(text)
    if tokens is None:
        return []
    significant = [token for token in tokens if token.type not in _SKIP]
    found: List[tokenize.TokenInfo] = []
    stack: List[bool] = []
    previous: Optional[tokenize.TokenInfo] = None
    for index, token in enumerate(significant):
        if token.type == tokenize.OP and token.string in ("(", "[", "{"):
            is_call = (
                token.string == "("
                and previous is not None
                and (
                    (previous.type == tokenize.NAME and not keyword.iskeyword(previous.string))
                    or (previous.type == tokenize.OP and previous.string in (")", "]"))
                )
            )
            stack.append(is_call)
        elif token.type == tokenize.OP and token.string in (")", "]", "}"):
            if stack:
                stack.pop()
        elif token.type == tokenize.NAME:
            after_dot = previous is not None and previous.type == tokenize.OP and previous.string == "."
            following = significant[index + 1] if index + 1 < len(significant) else None
            keyword_argument = (
                bool(stack)
                and stack[-1]
                and following is not None
                and following.type == tokenize.OP
                and following.string == "="
            )
            if not after_dot and not keyword_argument:
                found.append(token)
        previous = token
    return found


_FORMULA_NAMES: Dict[str, Tuple[str, ...]] = {}


def formula_names(text: str) -> Tuple[str, ...]:
    """The names a formula mentions, in order, once each."""
    cached = _FORMULA_NAMES.get(text)
    if cached is not None:
        return cached
    seen: Dict[str, None] = {}
    for token in _name_tokens(text):
        seen.setdefault(token.string, None)
    found = tuple(seen)
    if len(_FORMULA_NAMES) > 512:
        _FORMULA_NAMES.clear()
    _FORMULA_NAMES[text] = found
    return found


def formula_mentions(text: str, name: str) -> bool:
    return any(_same_name(token.string, name) for token in _name_tokens(text))


def rename_formula(text: str, mapping: Mapping[str, str]) -> str:
    """Replace each NAME token that is a key of ``mapping`` (all at once, so no chaining).

    Only the token's span changes. Text that doesn't tokenize comes back as it is."""
    if not mapping:
        return text
    keyed = {_name_key(old): new for old, new in mapping.items()}
    chosen = [token for token in _name_tokens(text) if _name_key(token.string) in keyed]
    if not chosen:
        return text
    starts: List[int] = []
    offset = 0
    for line in text.split("\n"):
        starts.append(offset)
        offset += len(line) + 1
    pieces: List[Tuple[int, int, str]] = []
    for token in chosen:
        row, column = token.start
        end_row, end_column = token.end
        if row != end_row or row - 1 >= len(starts):
            return text
        begin = starts[row - 1] + column
        end = starts[row - 1] + end_column
        if text[begin:end] != token.string:
            return text
        pieces.append((begin, end, keyed[_name_key(token.string)]))
    result = text
    for begin, end, replacement in sorted(pieces, reverse=True):
        result = result[:begin] + replacement + result[end:]
    return result


# ---------------------------------------------------------------------------
# Formulas inside JSON
# ---------------------------------------------------------------------------


def map_json_formulas(value: JsonValue, change: Callable[[str], str]) -> JsonValue:
    """``value`` with ``change`` applied to every string under a ``FORMULA_JSON_KEYS`` key, at any depth."""
    if isinstance(value, JsonObject):
        pairs = []
        for key, item in value.pairs:
            if key in FORMULA_JSON_KEYS and isinstance(item, str):
                pairs.append((key, change(item)))
            else:
                pairs.append((key, map_json_formulas(item, change)))
        return JsonObject(tuple(pairs))
    if isinstance(value, tuple):
        return tuple(map_json_formulas(item, change) for item in value)
    return value


def _map_step_formulas(step: Step, change: Callable[[str], str]) -> Step:
    when = change(step.when) if step.when is not None else None
    fields = tuple(
        (key, change(item) if key in FORMULA_JSON_KEYS and isinstance(item, str) else map_json_formulas(item, change))
        for key, item in step.fields
    )
    unknown = tuple((key, map_json_formulas(item, change)) for key, item in step.unknown)
    return Step(step.verb, when, step.enabled, fields, unknown)


def rename_formulas_in_logic(key: str, text: str, mapping: Mapping[str, str]) -> Optional[str]:
    """New canonical text for ``key`` with formula tokens renamed, or None when nothing changes
    (or the text can't be read, which stays as it is)."""
    kind = text_kind(key)

    def change(formula: str) -> str:
        return rename_formula(formula, mapping)

    if kind == "formula":
        renamed = rename_formula(text, mapping)
        return None if renamed == text else renamed
    if kind == "steps":
        read = parse_steps(text)
        if read.error is not None:
            return None
        steps = tuple(_map_step_formulas(step, change) for step in read.steps)
        if steps == read.steps:
            return None
        return write_steps(steps, read.signal, read.extra)
    if kind == "json":
        got = parse_json(text)
        if got.error is not None:
            return None
        mapped = map_json_formulas(got.value, change)
        if mapped == got.value:
            return None
        return write_json(mapped)
    return None


def formula_mentions_in_logic(key: str, text: str, name: str) -> bool:
    """True when a formula inside ``text`` mentions ``name``."""
    seen = []

    def watch(formula: str) -> str:
        if formula_mentions(formula, name):
            seen.append(formula)
        return formula

    kind = text_kind(key)
    if kind == "formula":
        return formula_mentions(text, name)
    if kind == "steps":
        read = parse_steps(text)
        if read.error is not None:
            return False
        for step in read.steps:
            _map_step_formulas(step, watch)
        return bool(seen)
    if kind == "json":
        got = parse_json(text)
        if got.error is not None:
            return False
        map_json_formulas(got.value, watch)
        return bool(seen)
    return False


# ---------------------------------------------------------------------------
# Step targets
# ---------------------------------------------------------------------------


def _map_step_names(step: Step, mapping: Mapping[str, str]) -> Step:
    declared = NAME_FIELDS.get(step.verb)
    if not declared or not step.fields:
        return step
    scalar = {spec for spec in declared if not spec.endswith("[]")}
    listed = {spec[:-2] for spec in declared if spec.endswith("[]")}
    fields = []
    for key, value in step.fields:
        if key in scalar and isinstance(value, str):
            value = mapping.get(value, value)
        elif key in listed and isinstance(value, tuple):
            value = tuple(mapping.get(item, item) if isinstance(item, str) else item for item in value)
        fields.append((key, value))
    return Step(step.verb, step.when, step.enabled, tuple(fields), step.unknown)


def rename_step_targets(text: str, mapping: Mapping[str, str]) -> Optional[str]:
    """New canonical text of a step list with its object-name fields renamed, or None."""
    read = parse_steps(text)
    if read.error is not None:
        return None
    steps = tuple(_map_step_names(step, mapping) for step in read.steps)
    if steps == read.steps:
        return None
    return write_steps(steps, read.signal, read.extra)


def step_target_names(text: str) -> Tuple[str, ...]:
    """Every object name the steps of ``text`` act on, in order, once each. Empty when unreadable."""
    read = parse_steps(text)
    if read.error is not None:
        return ()
    seen: Dict[str, None] = {}
    for step in read.steps:
        declared = NAME_FIELDS.get(step.verb, ())
        for key, value in step.fields:
            if key in declared and isinstance(value, str):
                seen.setdefault(value, None)
            elif (key + "[]") in declared and isinstance(value, tuple):
                for item in value:
                    if isinstance(item, str):
                        seen.setdefault(item, None)
    return tuple(seen)


# ---------------------------------------------------------------------------
# Any cbcs text, when the structure is not known
# ---------------------------------------------------------------------------


def opaque_mentions(text: str, name: str) -> bool:
    """True when ``name`` occurs in ``text`` as a whole identifier: in a formula, a string, a
    key or a message alike. Used where the structure is unknown: the text of a form saved by a
    newer Code Studio is never interpreted, only searched (CONTRACTS 15.7, UX-LST-001 "any
    ``cbcs*`` text contains"), and it errs towards "mentioned". Linear in ``text``."""
    if not name:
        return False
    key = _name_key(name)
    haystack = text if key == name and text.isascii() else _name_key(text)
    pattern = re.compile(r"(?<![\w])" + re.escape(key) + r"(?![\w])")
    return pattern.search(haystack) is not None


def label_matches(key: str, text: str, name: str) -> bool:
    return key in LABEL_KEYS and text == name


__all__ = [
    "FORMULA_JSON_KEYS",
    "FORMULA_KEYS",
    "NAME_FIELDS",
    "declare_name_fields",
    "formula_mentions",
    "formula_mentions_in_logic",
    "formula_names",
    "label_matches",
    "map_json_formulas",
    "opaque_mentions",
    "rename_formula",
    "rename_formulas_in_logic",
    "rename_step_targets",
    "step_target_names",
]
