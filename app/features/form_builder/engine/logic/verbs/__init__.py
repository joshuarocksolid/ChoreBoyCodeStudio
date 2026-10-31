"""Step verbs (CONTRACTS section 18.4 and 18.6).

Qt-free. A module in this package adds verbs with ``register(registry)`` and
``registry.add(VerbSpec(...))``. Modules are discovered in sorted name order
(a name starting with ``_`` is a helper), so M6's ``m6.py`` lists before a
later lane. A lane adds a file here and edits no shared one.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Callable, List, Optional, Tuple

from app.features.form_builder.engine.contributors import run_contributors


@dataclass(frozen=True)
class FieldSpec:
    name: str
    kind: str  # formula, object_name, method, text, enum, signature, int, hints
    required: bool = False


@dataclass(frozen=True)
class VerbSpec:
    """One verb the codec, the generator and the Behavior tab share.

    ``validate`` is the typed-step check (same error strings as the M6 codec).
    ``emit`` returns the statement lines for one step. ``blocks_list`` is True
    when this step keeps the whole list from generating. ``words`` is the
    picker and comment sentence, same signature as ``events_catalog.step_words``.
    """

    name: str
    fields: Tuple[FieldSpec, ...]
    plain: bool
    validate: Callable
    emit: Callable
    blocks_list: Callable
    group_id: str
    words: Callable
    editable: bool = True


class VerbRegistry:
    def __init__(self) -> None:
        self._verbs: List[Tuple[str, VerbSpec]] = []

    def add(self, spec: VerbSpec, *, module: str = "") -> None:
        if any(found.name == spec.name for _module, found in self._verbs):
            raise ValueError("verb %s is already registered" % spec.name)
        self._verbs.append((module, spec))

    def scope(self, module: str) -> "_ModuleScope":
        return _ModuleScope(self, module)

    def all(self) -> Tuple[VerbSpec, ...]:
        return tuple(spec for _module, spec in self._verbs)

    def get(self, name: str) -> Optional[VerbSpec]:
        for _module, spec in self._verbs:
            if spec.name == name:
                return spec
        return None


class _ModuleScope:
    def __init__(self, registry: VerbRegistry, module: str) -> None:
        self._registry = registry
        self._module = module

    def add(self, spec: VerbSpec) -> None:
        self._registry.add(spec, module=self._module)


def load_verbs(*packages: ModuleType) -> VerbRegistry:
    registry = VerbRegistry()
    run_contributors("step verb", packages, "register", lambda module, hook: hook(registry.scope(module.__name__)))
    return registry


_DEFAULT: Optional[VerbRegistry] = None


def default_registry() -> VerbRegistry:
    """This package's verbs, loaded once."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = load_verbs(sys.modules[__name__])
    return _DEFAULT


def require_text(verb: str, names: Tuple[str, ...], taken: Any) -> None:
    """The M6 required-field error, shared by every text-like required field."""
    from app.features.form_builder.engine.logic.codec import _Refused

    for name in names:
        value = taken.get(name)
        if not isinstance(value, str) or not value:
            raise _Refused(1, 'a "%s" step needs "%s" as text' % (verb, name))


__all__ = [
    "FieldSpec",
    "VerbRegistry",
    "VerbSpec",
    "default_registry",
    "load_verbs",
    "require_text",
]
