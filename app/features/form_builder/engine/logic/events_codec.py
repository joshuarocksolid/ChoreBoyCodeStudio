"""The thin adapter between event steps and the logic codec (CONTRACTS section 15.5). Qt-free.

``EventStep`` is what the events engine and the pickers handle. The codec
(``engine/logic/codec.py``, M6.0b) owns the JSON text. This module is the only
place that knows both. Until M6.0b merges the codec is absent and a minimal
stand-in (``_fallback_*``) that follows CONTRACTS 15.3 and 15.4 for ``slot``
and ``call`` steps takes its place; once ``codec`` imports, it is used and the
stand-in is dead code. TODO(M6.0b): delete the stand-in when the lane merges.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Sequence, Tuple

try:  # M6.0b
    from app.features.form_builder.engine.logic import codec as _codec  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - exercised until M6.0b merges
    _codec = None

MAX_TEXT = 1024 * 1024
PLAIN_VERBS = ("slot", "call")


@dataclass(frozen=True)
class EventStep:
    """One step of an event, in the words of CONTRACTS 15.3.

    ``slot``: ``target`` is an object name (the root's name for the form) and
    ``slot`` a Designer signature (``clear()``). ``call``: ``method`` is a name on
    the window and ``args`` how many of the signal's values it receives. Any
    other verb is kept in ``raw`` (the codec's own step) and written back
    unchanged; this build cannot edit it (FB403).
    """

    verb: str
    target: str = ""
    slot: str = ""
    method: str = ""
    args: int = 0
    when: Optional[str] = None
    enabled: bool = True
    raw: object = None

    @property
    def plain(self) -> bool:
        """Storable as a native ``<connection>``: a ``slot`` or ``call`` with no condition, turned on."""
        return self.verb in PLAIN_VERBS and self.when is None and self.enabled and self.raw is None


def slot_step(target: str, slot: str, *, enabled: bool = True) -> EventStep:
    return EventStep("slot", target=target, slot=slot, enabled=enabled)


def call_step(method: str, args: int = 0, *, enabled: bool = True) -> EventStep:
    return EventStep("call", method=method, args=args, enabled=enabled)


@dataclass(frozen=True)
class StepList:
    """What a ``cbcsOn<Signal>`` text holds. ``error`` is ``(line, message)`` for FB401."""

    steps: Tuple[EventStep, ...]
    signal: Optional[str]
    error: Optional[Tuple[int, str]]


def read_list(text: str) -> StepList:
    """Parse a ``cbcsOn<Signal>`` text. Total on any string."""
    if len(text) > MAX_TEXT:
        return StepList((), None, (1, "The step list is too large to read."))
    if _codec is not None:
        read = _codec.parse_steps(text)
        if read.error is not None:
            return StepList((), None, (int(read.error[0]), str(read.error[1])))
        return StepList(tuple(_from_codec(step) for step in read.steps), read.signal, None)
    return _fallback_parse(text)


def write_list(steps: Sequence[EventStep], signal: Optional[str] = None) -> str:
    """The canonical text of a step list (CONTRACTS 15.4)."""
    if _codec is not None:
        return str(_codec.write_steps(tuple(_to_codec(step) for step in steps), signal))
    return _fallback_write(steps, signal)


# --- the real codec ------------------------------------------------------------------------


def _field(step: Any, name: str, default: Any = None) -> Any:
    fields = getattr(step, "fields", ())
    if isinstance(fields, Mapping):
        return fields.get(name, default)
    for key, value in fields:
        if key == name:
            return value
    return default


def _from_codec(step: Any) -> EventStep:
    verb = str(step.verb)
    when = step.when if isinstance(step.when, str) else None
    enabled = step.enabled is not False
    if verb == "slot":
        target, slot = _field(step, "target"), _field(step, "slot")
        if isinstance(target, str) and isinstance(slot, str) and not getattr(step, "unknown", ()):
            return EventStep("slot", target=target, slot=slot, when=when, enabled=enabled)
    if verb == "call":
        method, args = _field(step, "method"), _field(step, "args", 0)
        if (
            isinstance(method, str)
            and isinstance(args, int)
            and not isinstance(args, bool)
            and not getattr(step, "unknown", ())
        ):
            return EventStep("call", method=method, args=args, when=when, enabled=enabled)
    return EventStep(verb, when=when, enabled=enabled, raw=step)


def _to_codec(step: EventStep) -> Any:
    if step.raw is not None:
        return step.raw
    enabled = None if step.enabled else False
    if step.verb == "slot":
        fields: Tuple[Tuple[str, Any], ...] = (("target", step.target), ("slot", step.slot))
    else:
        fields = (("method", step.method),) + ((("args", step.args),) if step.args else ())
    return _codec.Step(step.verb, step.when, enabled, fields, ())  # type: ignore[union-attr]


# --- stand-in until M6.0b ----------------------------------------------------------------


@dataclass(frozen=True)
class _RawStep:
    """A step this build does not type: every key in read order, kept exactly."""

    pairs: Tuple[Tuple[str, Any], ...]


def _fallback_parse(text: str) -> StepList:
    try:
        value = json.loads(text)
    except ValueError as error:
        line = getattr(error, "lineno", 1)
        return StepList((), None, (int(line) if isinstance(line, int) else 1, "Not valid JSON."))
    signal: Optional[str] = None
    items = value
    if isinstance(value, dict):
        wrapped = value.get("steps")
        signal_text = value.get("signal")
        if not isinstance(wrapped, list) or not isinstance(signal_text, str):
            return StepList((), None, (1, "Expected a list of steps."))
        signal, items = signal_text, wrapped
    if not isinstance(items, list):
        return StepList((), None, (1, "Expected a list of steps."))
    steps: List[EventStep] = []
    for number, item in enumerate(items, 1):
        if not isinstance(item, dict) or not isinstance(item.get("do"), str):
            return StepList((), None, (number + 1, "A step needs a \"do\" key."))
        steps.append(_fallback_step(item))
    return StepList(tuple(steps), signal, None)


def _fallback_step(item: Mapping[str, Any]) -> EventStep:
    verb = item["do"]
    when = item.get("when") if isinstance(item.get("when"), str) else None
    enabled = item.get("enabled") is not False
    keys = tuple(item.keys())
    if verb == "slot" and set(keys) <= {"do", "when", "enabled", "target", "slot"}:
        if isinstance(item.get("target"), str) and isinstance(item.get("slot"), str):
            return EventStep("slot", target=item["target"], slot=item["slot"], when=when, enabled=enabled)
    if verb == "call" and set(keys) <= {"do", "when", "enabled", "method", "args"}:
        args = item.get("args", 0)
        if isinstance(item.get("method"), str) and isinstance(args, int) and not isinstance(args, bool):
            return EventStep("call", method=item["method"], args=args, when=when, enabled=enabled)
    return EventStep(str(verb), when=when, enabled=enabled, raw=_RawStep(tuple(item.items())))


def _fallback_write(steps: Sequence[EventStep], signal: Optional[str]) -> str:
    lines = ["  " + _fallback_object(step) for step in steps]
    body = "[\n" + ",\n".join(lines) + "\n]"
    if signal is None:
        return body
    return '{"signal": %s, "steps": %s}' % (json.dumps(signal, ensure_ascii=False), body)


def _fallback_object(step: EventStep) -> str:
    if isinstance(step.raw, _RawStep):
        pairs: List[Tuple[str, Any]] = list(step.raw.pairs)
    else:
        pairs = [("do", step.verb)]
        if step.when is not None:
            pairs.append(("when", step.when))
        if not step.enabled:
            pairs.append(("enabled", False))
        if step.verb == "slot":
            pairs.extend((("target", step.target), ("slot", step.slot)))
        else:
            pairs.append(("method", step.method))
            if step.args:
                pairs.append(("args", step.args))
    return "{" + ", ".join("%s: %s" % (json.dumps(key, ensure_ascii=False), _fallback_value(value)) for key, value in pairs) + "}"


def _fallback_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)
