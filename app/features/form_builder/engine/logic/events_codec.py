"""The thin adapter between event steps and the logic codec (CONTRACTS section 15.5). Qt-free.

``EventStep`` is what the events engine and the pickers handle. The codec
(``engine/logic/codec.py``) owns the JSON text. This module is the only place
that knows both.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence, Tuple

from app.features.form_builder.engine.logic import codec as _codec


def _verb_spec(name: str) -> object:
    from app.features.form_builder.engine.logic.verbs import default_registry

    return default_registry().get(name)


class _PlainVerbs:
    """Registered verbs with ``plain=True``, in registration order (slot, then call)."""

    def _names(self) -> Tuple[str, ...]:
        from app.features.form_builder.engine.logic.verbs import default_registry

        return tuple(spec.name for spec in default_registry().all() if spec.plain)

    def __contains__(self, item: object) -> bool:
        return item in self._names()

    def __iter__(self) -> object:
        return iter(self._names())

    def __len__(self) -> int:
        return len(self._names())

    def __getitem__(self, index: int) -> str:
        return self._names()[index]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, (tuple, list)):
            return self._names() == tuple(other)
        return NotImplemented


PLAIN_VERBS = _PlainVerbs()


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
    hints: Tuple[Tuple[str, int, int], ...] = ()
    raw: object = None

    @property
    def plain(self) -> bool:
        """Storable as a native ``<connection>``: a ``slot`` or ``call`` with no condition, turned on.

        A valid ``hints`` map is not an unknown key, so it still counts.
        """
        return self.verb in PLAIN_VERBS and self.when is None and self.enabled and self.raw is None


def slot_step(
    target: str,
    slot: str,
    *,
    enabled: bool = True,
    hints: Tuple[Tuple[str, int, int], ...] = (),
) -> EventStep:
    return EventStep("slot", target=target, slot=slot, enabled=enabled, hints=hints)


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


def _hints_of(step: Any) -> Tuple[Tuple[str, int, int], ...]:
    raw = step.field("hints")
    if not isinstance(raw, _codec.JsonObject):
        return ()
    points = []
    for key, item in raw.pairs:
        if isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], int) and isinstance(item[1], int):
            points.append((str(key), item[0], item[1]))
    return tuple(points)


def _from_codec(step: Any) -> EventStep:
    verb = str(step.verb)
    when = step.when if isinstance(step.when, str) else None
    enabled = step.enabled is not False
    spec = _verb_spec(verb)
    if not step.unknown and spec is not None and getattr(spec, "plain", False):
        if spec.name == "slot":
            target, slot = step.field("target"), step.field("slot")
            if isinstance(target, str) and isinstance(slot, str):
                return EventStep(
                    "slot",
                    target=target,
                    slot=slot,
                    when=when,
                    enabled=enabled,
                    hints=_hints_of(step),
                )
        if spec.name == "call":
            method, args = step.field("method"), step.field("args", 0)
            if isinstance(method, str) and isinstance(args, int) and not isinstance(args, bool):
                return EventStep("call", method=method, args=args, when=when, enabled=enabled)
    return EventStep(verb, when=when, enabled=enabled, raw=step)


def _to_codec(step: EventStep) -> Any:
    if step.raw is not None:
        return step.raw
    spec = _verb_spec(step.verb)
    if spec is not None and spec.name == "slot":
        return _codec.slot_step(
            step.target, step.slot, when=step.when, enabled=step.enabled, hints=step.hints
        )
    if spec is not None and spec.name == "call":
        return _codec.call_step(step.method, step.args or None, when=step.when, enabled=step.enabled)
    if spec is None:
        # A step this build does not register still writes the way M6 wrote a non-slot.
        return _codec.call_step(step.method, step.args or None, when=step.when, enabled=step.enabled)
    return _codec.Step(step.verb, step.when, step.enabled, (), ())
