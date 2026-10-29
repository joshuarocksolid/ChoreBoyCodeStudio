"""The logic codec: JSON text <-> an ordered, frozen model (CONTRACTS.md sections 15.3 to 15.5).

Qt-free and pure. Every ``parse_*`` and ``read_*`` function is total on any ``str``:
no exception escapes, and the work is linear in the input. A text larger than
1 MiB is never parsed. The writers produce the canonical text of section 15.4,
which is also XML 1.0 ``Char`` data.

Key order and unknown keys survive both ways: objects keep their pairs in the
order they were read (``JsonObject.pairs``), a ``Step`` keeps the keys it does not
know in ``unknown``, and a verb this build does not type keeps all its keys in
``fields``.
"""

from __future__ import annotations

import bisect
import json
import re
from dataclasses import dataclass
from typing import Iterator, List, Optional, Sequence, Tuple, Union

from app.features.form_builder.engine.logic.storage import (
    JSON_TOP_SHAPE,
    SUPPORTED_LOGIC_VERSION,
    text_kind,
)
from app.features.form_builder.engine.ui4.spec import PropertyEntry
from app.features.form_builder.engine.ui4.values import (
    LongLongValue,
    NumberValue,
    StringValue,
    UIntValue,
    ULongLongValue,
)

#: Larger texts are FB401 and never parsed (CONTRACTS 15.5).
MAX_TEXT_BYTES = 1024 * 1024

#: Objects and arrays nested deeper than this are FB401.
MAX_DEPTH = 32

#: Digit counts past which a number is refused, so parsing stays linear on every Python.
_MAX_INT_DIGITS = 4300
_MAX_FLOAT_CHARS = 400

#: The verbs this build types, with their fields in written order (CONTRACTS 15.3).
TYPED_VERBS = {
    "slot": ("target", "slot"),
    "call": ("method", "args"),
}
_REQUIRED_FIELDS = {
    "slot": ("target", "slot"),
    "call": ("method",),
}

JsonValue = Union[None, bool, int, float, str, "JsonObject", Tuple["JsonValue", ...]]
Pairs = Tuple[Tuple[str, JsonValue], ...]
ErrorInfo = Tuple[int, str]


class LogicWriteError(ValueError):
    """A model the writer refuses: NaN, an infinity, a non-JSON type or a nesting that is too deep."""


@dataclass(frozen=True)
class JsonObject:
    """An object that keeps its pairs in read order. Duplicate keys are kept as read."""

    pairs: Pairs = ()

    def get(self, key: str, default: JsonValue = None) -> JsonValue:
        """The value of the last pair named ``key``, as ``json`` would read it."""
        found = default
        for name, value in self.pairs:
            if name == key:
                found = value
        return found

    def has(self, key: str) -> bool:
        return any(name == key for name, _ in self.pairs)

    def keys(self) -> Tuple[str, ...]:
        return tuple(name for name, _ in self.pairs)


@dataclass(frozen=True)
class JsonRead:
    value: JsonValue
    error: Optional[ErrorInfo]


@dataclass(frozen=True)
class Step:
    """One step of an event (CONTRACTS 15.3).

    ``enabled`` is True unless the step says ``"enabled": false``. ``fields`` are the
    verb's fields: for ``slot`` and ``call`` in schema order, for any other verb every
    key but ``do``, ``when`` and ``enabled`` in read order. ``unknown`` are the keys
    of a typed verb this build does not know, in read order.
    """

    verb: str
    when: Optional[str] = None
    enabled: bool = True
    fields: Pairs = ()
    unknown: Pairs = ()

    @property
    def is_typed(self) -> bool:
        return self.verb in TYPED_VERBS

    @property
    def is_plain(self) -> bool:
        """A typed step with no ``when`` and not turned off: it can be a native connection."""
        return self.is_typed and self.when is None and self.enabled

    def field(self, name: str, default: JsonValue = None) -> JsonValue:
        for key, value in self.fields:
            if key == name:
                return value
        return default


def slot_step(target: str, slot: str, *, when: Optional[str] = None, enabled: bool = True, unknown: Pairs = ()) -> Step:
    return Step("slot", when, enabled, (("target", target), ("slot", slot)), unknown)


def call_step(
    method: str,
    args: Optional[int] = None,
    *,
    when: Optional[str] = None,
    enabled: bool = True,
    unknown: Pairs = (),
) -> Step:
    fields: Pairs = (("method", method),) if args is None else (("method", method), ("args", args))
    return Step("call", when, enabled, fields, unknown)


@dataclass(frozen=True)
class StepsRead:
    """``steps`` is empty and ``error`` is ``(line, message)`` when the text can't be read.

    ``signal`` is set for the ``{"signal": ..., "steps": [...]}`` form; ``extra`` holds
    that wrapper's other keys.
    """

    steps: Tuple[Step, ...]
    signal: Optional[str]
    error: Optional[ErrorInfo]
    extra: Pairs = ()


@dataclass(frozen=True)
class MarkerRead:
    """``version`` is None when there is no marker or it can't be read (``readable`` False)."""

    version: Optional[int]
    readable: bool


@dataclass(frozen=True)
class Canonical:
    """The canonical text for one logic property. ``text`` None means "remove the property"."""

    text: Optional[str]
    error: Optional[ErrorInfo]


# ---------------------------------------------------------------------------
# Reading JSON
# ---------------------------------------------------------------------------


class _Refused(Exception):
    def __init__(self, line: int, message: str) -> None:
        super().__init__(message)
        self.line = line
        self.message = message


def _refuse_constant(name: str) -> None:
    raise ValueError("%s is not allowed" % (name,))


def _parse_int(text: str) -> int:
    if len(text) > _MAX_INT_DIGITS:
        raise ValueError("number too long")
    return int(text)


def _parse_float(text: str) -> float:
    if len(text) > _MAX_FLOAT_CHARS:
        raise ValueError("number too long")
    value = float(text)
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError("number out of range")
    return value


def _make_object(pairs: List[Tuple[str, object]]) -> JsonObject:
    return JsonObject(tuple(pairs))  # type: ignore[arg-type]


def _freeze(value: object, depth: int) -> JsonValue:
    if depth > MAX_DEPTH:
        raise _Refused(1, "nested too deeply")
    if isinstance(value, JsonObject):
        return JsonObject(tuple((key, _freeze(item, depth + 1)) for key, item in value.pairs))
    if isinstance(value, list):
        return tuple(_freeze(item, depth + 1) for item in value)
    return value  # type: ignore[return-value]


def _too_large(text: str) -> bool:
    if len(text) > MAX_TEXT_BYTES:
        return True
    if len(text) * 4 <= MAX_TEXT_BYTES:
        return False
    return len(text.encode("utf-8", "surrogatepass")) > MAX_TEXT_BYTES


def _decode(text: str) -> JsonValue:
    if not isinstance(text, str):
        raise _Refused(1, "not text")
    if _too_large(text):
        raise _Refused(1, "larger than 1 MB")
    try:
        loaded = json.loads(
            text,
            object_pairs_hook=_make_object,
            parse_constant=_refuse_constant,
            parse_int=_parse_int,
            parse_float=_parse_float,
        )
    except json.JSONDecodeError as exc:
        raise _Refused(max(1, exc.lineno), exc.msg) from exc
    except RecursionError as exc:
        raise _Refused(1, "nested too deeply") from exc
    except (ValueError, TypeError, MemoryError, OverflowError) as exc:
        raise _Refused(1, str(exc) or "not valid JSON") from exc
    return _freeze(loaded, 0)


def parse_json(text: str) -> JsonRead:
    """Parse any JSON text into the ordered model. Never raises."""
    try:
        return JsonRead(_decode(text), None)
    except _Refused as exc:
        return JsonRead(None, (exc.line, exc.message))
    except Exception:  # noqa: BLE001 - total by contract
        return JsonRead(None, (1, "not valid JSON"))


_TOKEN = re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"|[\[\]{},:]')
_NON_SPACE = re.compile(r"\S")


def _element_lines(text: str, wrapper: bool) -> Tuple[int, ...]:
    """Line (1-based) of each element of the top array, or of the ``steps`` array of the wrapper.

    Only called on text that already parsed, so the scan can stay simple."""
    newlines = [match.start() for match in re.finditer("\n", text)]

    def line_at(position: int) -> int:
        return bisect.bisect_left(newlines, position) + 1

    def start_after(position: int) -> int:
        found = _NON_SPACE.search(text, position)
        return found.start() if found is not None else position

    depth_stack: List[str] = []
    lines: List[int] = []
    target = 0
    last_key = ""
    for match in _TOKEN.finditer(text):
        token = match.group()
        if token[0] == '"':
            if wrapper and len(depth_stack) == 1 and depth_stack[0] == "{":
                follow = _NON_SPACE.search(text, match.end())
                if follow is not None and text[follow.start()] == ":":
                    try:
                        last_key = str(json.loads(token))
                    except ValueError:
                        last_key = ""
            continue
        if token in "[{":
            depth_stack.append(token)
            if target == 0 and token == "[":
                top_array = not wrapper and len(depth_stack) == 1
                steps_array = wrapper and len(depth_stack) == 2 and last_key == "steps"
                if top_array or steps_array:
                    target = len(depth_stack)
                    lines.append(line_at(start_after(match.end())))
            continue
        if token in "]}":
            if target and len(depth_stack) == target and token == "]":
                break
            if depth_stack:
                depth_stack.pop()
            continue
        if token == "," and target and len(depth_stack) == target:
            lines.append(line_at(start_after(match.end())))
    return tuple(lines)


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


def _step_error(lines: Sequence[int], index: int, message: str) -> _Refused:
    line = lines[index] if 0 <= index < len(lines) else 1
    return _Refused(line, message)


def _step_from_object(obj: JsonObject) -> Step:
    seen = set()
    for key in obj.keys():
        if key in seen:
            raise _Refused(1, "the key %r is there twice" % (key,))
        seen.add(key)
    verb = obj.get("do")
    if not isinstance(verb, str) or not verb:
        raise _Refused(1, 'a step needs a "do"')
    when: Optional[str] = None
    enabled = True
    rest: List[Tuple[str, JsonValue]] = []
    for key, value in obj.pairs:
        if key == "do":
            continue
        if key == "when" and isinstance(value, str):
            when = value
        elif key == "enabled" and isinstance(value, bool):
            enabled = value
        else:
            rest.append((key, value))
    schema = TYPED_VERBS.get(verb)
    if schema is None:
        return Step(verb, when, enabled, tuple(rest), ())
    taken = {}
    unknown: List[Tuple[str, JsonValue]] = []
    for key, value in rest:
        if key in schema:
            taken[key] = value
        else:
            unknown.append((key, value))
    for name in _REQUIRED_FIELDS[verb]:
        value = taken.get(name)
        if not isinstance(value, str) or not value:
            raise _Refused(1, 'a "%s" step needs "%s" as text' % (verb, name))
    if "args" in taken:
        count = taken["args"]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise _Refused(1, '"args" must be a whole number')
    fields = tuple((name, taken[name]) for name in schema if name in taken)
    return Step(verb, when, enabled, fields, tuple(unknown))


def parse_steps(text: str) -> StepsRead:
    """Read a ``cbcsOn<Signal>`` value. Never raises."""
    try:
        value = _decode(text)
        signal: Optional[str] = None
        extra: List[Tuple[str, JsonValue]] = []
        if isinstance(value, JsonObject):
            keys = value.keys()
            if len(set(keys)) != len(keys):
                raise _Refused(1, "a key is there twice")
            raw_signal = value.get("signal")
            raw_steps = value.get("steps")
            if not isinstance(raw_signal, str) or not raw_signal or not isinstance(raw_steps, tuple):
                raise _Refused(1, 'expected a list of steps, or {"signal": ..., "steps": [...]}')
            signal = raw_signal
            items = raw_steps
            extra = [(key, item) for key, item in value.pairs if key not in ("signal", "steps")]
            wrapper = True
        elif isinstance(value, tuple):
            items = value
            wrapper = False
        else:
            raise _Refused(1, "expected a list of steps")
        steps: List[Step] = []
        lines: Optional[Tuple[int, ...]] = None
        for index, item in enumerate(items):
            try:
                if not isinstance(item, JsonObject):
                    raise _Refused(1, "it is not an object")
                steps.append(_step_from_object(item))
            except _Refused as exc:
                if lines is None:
                    lines = _element_lines(text, wrapper)
                raise _step_error(lines, index, "step %d: %s" % (index + 1, exc.message))
        return StepsRead(tuple(steps), signal, None, tuple(extra))
    except _Refused as exc:
        return StepsRead((), None, (exc.line, exc.message))
    except Exception:  # noqa: BLE001 - total by contract
        return StepsRead((), None, (1, "not a list of steps"))


def _step_object(step: Step) -> JsonObject:
    if not isinstance(step.verb, str) or not step.verb:
        raise LogicWriteError("a step needs a verb")
    pairs: List[Tuple[str, JsonValue]] = [("do", step.verb)]
    if step.when is not None:
        pairs.append(("when", step.when))
    if not step.enabled:
        pairs.append(("enabled", False))
    pairs.extend(step.fields)
    pairs.extend(step.unknown)
    return JsonObject(tuple(pairs))


def write_steps(
    steps: Sequence[Step],
    signal: Optional[str] = None,
    extra: Pairs = (),
) -> str:
    """Canonical text of a step list. "" for no steps: the caller removes the property.

    ``signal`` writes the ``{"signal", "steps"}`` wrapper (UX D24), ``extra`` its other keys.
    Raises ``LogicWriteError`` for a value JSON can't hold.
    """
    if not steps:
        return ""
    items = tuple(_step_object(step) for step in steps)
    if signal is None:
        return _write_block(items, 0, 0)
    pairs: List[Tuple[str, JsonValue]] = [("signal", signal), ("steps", items)]
    pairs.extend(pair for pair in extra if pair[0] not in ("signal", "steps"))
    return _write_block(JsonObject(tuple(pairs)), 0, 0)


# ---------------------------------------------------------------------------
# Writing JSON
# ---------------------------------------------------------------------------

_SHORT_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\b": "\\b",
    "\f": "\\f",
}
_NEEDS_ESCAPE = re.compile('["\\\\\x00-\x1f\x7f-\x9f\ufffe\uffff\ud800-\udfff]')


def _escape_one(match: "re.Match[str]") -> str:
    char = match.group()
    return _SHORT_ESCAPES.get(char) or "\\u%04x" % ord(char)


def quote(text: str) -> str:
    """A JSON string literal that is also XML 1.0 ``Char`` data (CONTRACTS 15.4 rule 4)."""
    return '"' + _NEEDS_ESCAPE.sub(_escape_one, text) + '"'


def _number(value: Union[int, float]) -> str:
    if isinstance(value, int):
        return str(value)
    if value != value or value in (float("inf"), float("-inf")):
        raise LogicWriteError("NaN and infinity can't be written")
    if value == int(value):
        return str(int(value))
    return repr(value)


def _is_object_array(value: object) -> bool:
    return isinstance(value, tuple) and len(value) > 0 and all(isinstance(item, JsonObject) for item in value)


def _check_depth(depth: int) -> None:
    if depth > MAX_DEPTH:
        raise LogicWriteError("nested too deeply")


def _write_inline(value: object, depth: int) -> str:
    _check_depth(depth)
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return _number(value)
    if isinstance(value, str):
        return quote(value)
    if isinstance(value, tuple):
        return "[" + ", ".join(_write_inline(item, depth + 1) for item in value) + "]"
    if isinstance(value, JsonObject):
        return "{" + ", ".join(_write_pair(key, item, depth + 1, None) for key, item in value.pairs) + "}"
    raise LogicWriteError("can't write a %s" % (type(value).__name__,))


def _write_pair(key: object, value: object, depth: int, block: Optional[int]) -> str:
    if not isinstance(key, str):
        raise LogicWriteError("object keys must be text")
    if block is None:
        return quote(key) + ": " + _write_inline(value, depth)
    return quote(key) + ": " + _write_block(value, block, depth)


def _write_block(value: object, indent: int, depth: int) -> str:
    """``value`` as it stands on a line indented ``indent`` levels.

    An object is one line, except that a value that is a non-empty array of objects
    takes one line per item (CONTRACTS 15.4 rules 1 and 2)."""
    _check_depth(depth)
    if isinstance(value, JsonObject):
        return "{" + ", ".join(_write_pair(key, item, depth + 1, indent) for key, item in value.pairs) + "}"
    if _is_object_array(value):
        pad = "  " * (indent + 1)
        body = ",\n".join(pad + _write_block(item, indent + 1, depth + 1) for item in value)  # type: ignore[attr-defined]
        return "[\n" + body + "\n" + "  " * indent + "]"
    return _write_inline(value, depth)


def write_json(value: JsonValue) -> str:
    """Canonical text of any model value. Raises ``LogicWriteError`` for NaN, an infinity or a non-JSON type."""
    return _write_block(value, 0, 0)


# ---------------------------------------------------------------------------
# Whole properties
# ---------------------------------------------------------------------------


def canonical_logic_text(key: str, text: str) -> Canonical:
    """The canonical form of ``text`` for logic property ``key`` (what ``SetLogic`` stores).

    Step lists and the JSON properties are parsed and written again. An empty list
    gives ``text`` None: the property is removed (CONTRACTS 15.4 rule 1). Formulas,
    labels and plain properties are stored as given. Never raises.
    """
    kind = text_kind(key)
    try:
        if kind == "steps":
            read = parse_steps(text)
            if read.error is not None:
                return Canonical(None, read.error)
            if not read.steps:
                return Canonical(None, None)
            return Canonical(write_steps(read.steps, read.signal, read.extra), None)
        if kind == "json":
            got = parse_json(text)
            if got.error is not None:
                return Canonical(None, got.error)
            shape = JSON_TOP_SHAPE.get(key, "any")
            if shape == "array" and not isinstance(got.value, tuple):
                return Canonical(None, (1, "expected a list"))
            if shape == "object" and not isinstance(got.value, JsonObject):
                return Canonical(None, (1, "expected an object"))
            if shape == "any" and not isinstance(got.value, (tuple, JsonObject)):
                return Canonical(None, (1, "expected a list or an object"))
            if isinstance(got.value, tuple) and not got.value:
                return Canonical(None, None)
            return Canonical(write_json(got.value), None)
    except LogicWriteError as exc:
        return Canonical(None, (1, str(exc)))
    except Exception:  # noqa: BLE001 - total by contract
        return Canonical(None, (1, "can't be read"))
    return Canonical(text, None)


def same_logic(key: str, left: str, right: str) -> bool:
    """True when two texts of ``key`` mean the same, whatever their bytes are."""
    if left == right:
        return True
    kind = text_kind(key)
    if kind == "steps":
        a, b = parse_steps(left), parse_steps(right)
        return a.error is None and b.error is None and a == b
    if kind == "json":
        a2, b2 = parse_json(left), parse_json(right)
        return a2.error is None and b2.error is None and a2.value == b2.value
    return False


# ---------------------------------------------------------------------------
# The version marker
# ---------------------------------------------------------------------------

_BARE_INT = re.compile(r"-?[0-9]+")
_INT_VALUES = (NumberValue, UIntValue, LongLongValue, ULongLongValue)


def _marker_from_text(text: str) -> MarkerRead:
    stripped = text.strip(" \t\r\n")
    if _BARE_INT.fullmatch(stripped):
        if len(stripped) > _MAX_INT_DIGITS:
            return MarkerRead(None, False)
        return MarkerRead(int(stripped), True)
    got = parse_json(text)
    if got.error is None and isinstance(got.value, JsonObject):
        version = got.value.get("version")
        if isinstance(version, int) and not isinstance(version, bool):
            return MarkerRead(version, True)
    return MarkerRead(None, False)


def read_marker(entry: Optional[PropertyEntry]) -> MarkerRead:
    """What the root's ``cbcsLogic`` says (CONTRACTS 15.2). No entry: ``MarkerRead(None, True)``."""
    if entry is None:
        return MarkerRead(None, True)
    value = entry.value
    if isinstance(value, _INT_VALUES):
        return MarkerRead(int(value.value), True)  # type: ignore[union-attr]
    if isinstance(value, StringValue):
        return _marker_from_text(value.text)
    return MarkerRead(None, False)


def marker_read_only(entry: Optional[PropertyEntry]) -> bool:
    """True when the form's logic is newer than this build, or its marker can't be read (FB402)."""
    marker = read_marker(entry)
    if not marker.readable:
        return True
    return marker.version is not None and marker.version > SUPPORTED_LOGIC_VERSION


def iter_strings(value: JsonValue) -> Iterator[str]:
    """Every string value in ``value`` (not keys), depth first, in order. Iterative."""
    stack: List[object] = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            yield item
        elif isinstance(item, tuple):
            stack.extend(reversed(item))
        elif isinstance(item, JsonObject):
            stack.extend(reversed([child for _, child in item.pairs]))
