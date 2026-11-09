"""Step intents: the plain-language choices of the step picker (CONTRACTS.md section 1.4, UX-PICK-004).

Qt-free. A module in this package adds intents with ``register(registry)``
and ``registry.add(Intent(...))``. Modules are discovered in sorted name order
(a name starting with ``_`` is a helper), so M6's ``m6.py`` lists before M7's
rule intents, and the picker shows intents in registration order. A lane adds a
file here and edits no shared one.

An ``Intent`` says who offers it (``sender_classes``: Qt class names the sender
must derive from, or any when empty; matched with the class table by the
caller), the signal it picks (``event``, ``""`` when it uses the event being
edited), the picker text (``words``), whether it opens the target page
(``needs_target``) and ``steps``. ``steps(sender, target)`` returns the steps to
add as plain JSON-shaped mappings of the logic schema (the ``slot`` and ``call``
verbs of CONTRACTS 15.3), each mapping also carrying its ``event`` when an
intent adds steps to two events. It is pure and total on its input.

Routing keys of a mapping (never stored; CONTRACTS 15.6 "Intents"): ``event`` is
the signal the step goes on; ``sender`` is the object whose event it goes on,
present only when that is not the picker's sender (the second half of "Keep a
and b in step"); a ``slot`` step without ``target`` acts on the form.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Callable, List, Mapping, Optional, Sequence, Tuple

from app.features.form_builder.engine.contributors import run_contributors

IntentStep = Mapping[str, Any]
StepsFor = Callable[[str, Optional[str]], Tuple[IntentStep, ...]]


@dataclass(frozen=True)
class Intent:
    intent_id: str
    words: str
    steps: StepsFor
    sender_classes: Tuple[str, ...] = ()
    event: str = ""
    needs_target: bool = False

    def __post_init__(self) -> None:
        if not self.intent_id or not self.words:
            raise ValueError("an intent needs an id and words")


class IntentRegistry:
    def __init__(self) -> None:
        self._intents: List[Tuple[str, Intent]] = []

    def add(self, intent: Intent, *, module: str = "") -> None:
        if any(found.intent_id == intent.intent_id for _module, found in self._intents):
            raise ValueError("intent %s is already registered" % intent.intent_id)
        self._intents.append((module, intent))

    def scope(self, module: str) -> "_ModuleScope":
        return _ModuleScope(self, module)

    def all(self) -> Tuple[Intent, ...]:
        return tuple(intent for _module, intent in self._intents)

    def get(self, intent_id: str) -> Optional[Intent]:
        for _module, intent in self._intents:
            if intent.intent_id == intent_id:
                return intent
        return None

    def for_classes(self, classes: Sequence[str], event: Optional[str] = None) -> Tuple[Intent, ...]:
        """Intents a sender with these class names (itself and its bases) is offered.

        ``event`` set keeps only intents of that event or of the event being
        edited (``event == ""``): the "+ Then..." list of UX-PICK-004.
        """
        known = set(classes)
        found = []
        for intent in self.all():
            if intent.sender_classes and not known.intersection(intent.sender_classes):
                continue
            if event is not None and intent.event not in ("", event):
                continue
            found.append(intent)
        return tuple(found)


class _ModuleScope:
    def __init__(self, registry: IntentRegistry, module: str) -> None:
        self._registry = registry
        self._module = module

    def add(self, intent: Intent) -> None:
        self._registry.add(intent, module=self._module)


def load_intents(*packages: ModuleType) -> IntentRegistry:
    registry = IntentRegistry()
    run_contributors("step intent", packages, "register", lambda module, hook: hook(registry.scope(module.__name__)))
    return registry


_DEFAULT: Optional[IntentRegistry] = None


def default_registry() -> IntentRegistry:
    """This package's intents, loaded once."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = load_intents(sys.modules[__name__])
    return _DEFAULT


__all__ = ["Intent", "IntentRegistry", "IntentStep", "StepsFor", "default_registry", "load_intents"]
