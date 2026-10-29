"""The thin adapter between event steps and the logic codec (CONTRACTS section 15.5). Qt-free.

``EventStep`` is what the events engine and the pickers handle. The codec
(``engine/logic/codec.py``) owns the JSON text. This module is the only place
that knows both.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence, Tuple

from app.features.form_builder.engine.logic import codec as _codec

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
    extra: Tuple[Tuple[str, Any], ...] = ()


def read_list(text: str) -> StepList:
    """Parse a ``cbcsOn<Signal>`` text. Total on any string."""
    read = _codec.parse_steps(text)
    if read.error is not None:
        return StepList((), None, (int(read.error[0]), str(read.error[1])))
    return StepList(tuple(_from_codec(step) for step in read.steps), read.signal, None, tuple(read.extra))


def write_list(steps: Sequence[EventStep], signal: Optional[str] = None, extra: Tuple[Tuple[str, Any], ...] = ()) -> str:
    """The canonical text of a step list (CONTRACTS 15.4). Raises ``codec.LogicWriteError``."""
    return str(_codec.write_steps(tuple(_to_codec(step) for step in steps), signal, extra))


WriteError = _codec.LogicWriteError


def _from_codec(step: Any) -> EventStep:
    verb = str(step.verb)
    when = step.when if isinstance(step.when, str) else None
    enabled = step.enabled is not False
    if not step.unknown:
        if verb == "slot":
            target, slot = step.field("target"), step.field("slot")
            if isinstance(target, str) and isinstance(slot, str):
                return EventStep("slot", target=target, slot=slot, when=when, enabled=enabled)
        if verb == "call":
            method, args = step.field("method"), step.field("args", 0)
            if isinstance(method, str) and isinstance(args, int) and not isinstance(args, bool):
                return EventStep("call", method=method, args=args, when=when, enabled=enabled)
    return EventStep(verb, when=when, enabled=enabled, raw=step)


def _to_codec(step: EventStep) -> Any:
    if step.raw is not None:
        return step.raw
    if step.verb == "slot":
        return _codec.slot_step(step.target, step.slot, when=step.when, enabled=step.enabled)
    return _codec.call_step(step.method, step.args or None, when=step.when, enabled=step.enabled)
