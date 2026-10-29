"""Problems fix buttons by FB code (M5.0s).

A lane adds a fix by adding a module here. Modules are discovered in sorted
name order. Each one exposes ``register(registry)`` and calls
``registry.add(ProblemFix(...))``. A module whose name starts with an
underscore is a helper and is not imported. ``problems_bridge`` asks the
registry which fixes a diagnostic offers; the lanes never edit it.

A fix belongs to one FB code. ``offered(diagnostic)`` narrows it (a picture
fix only for a picture property), ``title`` is the button text, either fixed or
made from the diagnostic ("Open {qrc}"), and ``run(context)`` does the work
through the session so it is one undo step. Several fixes may share a code;
they list in module order, then registration order.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
import sys
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from app.features.form_builder.engine.diagnostics import FormDiagnostic

logger = logging.getLogger(__name__)


def _always(_diagnostic: FormDiagnostic) -> bool:
    return True


@dataclass(frozen=True)
class FixContext:
    """What a fix gets. ``surface`` is the form tab (None in a packaging flow)."""

    diagnostic: FormDiagnostic
    session: Any
    project_root: str = ""
    surface: Any = None


@dataclass(frozen=True)
class ProblemFix:
    code: str
    fix_id: str
    title: Union[str, Callable[[FormDiagnostic], str]]
    run: Callable[[FixContext], None]
    offered: Callable[[FormDiagnostic], bool] = _always

    def __post_init__(self) -> None:
        if not (len(self.code) == 5 and self.code.startswith("FB") and self.code[2:].isdigit()):
            raise ValueError("%r is not an FB code" % (self.code,))
        if not self.fix_id:
            raise ValueError("a fix needs an id")

    def title_for(self, diagnostic: FormDiagnostic) -> str:
        return self.title if isinstance(self.title, str) else self.title(diagnostic)


class FixRegistry:
    def __init__(self) -> None:
        self._by_code: Dict[str, List[Tuple[str, ProblemFix]]] = {}

    def add(self, fix: ProblemFix, *, module: str = "") -> None:
        found = self._by_code.setdefault(fix.code, [])
        if any(other.fix_id == fix.fix_id for _module, other in found):
            raise ValueError("fix %s for %s is already registered" % (fix.fix_id, fix.code))
        found.append((module, fix))

    def scope(self, module: str) -> "_ModuleScope":
        return _ModuleScope(self, module)

    def codes(self) -> Tuple[str, ...]:
        return tuple(sorted(self._by_code))

    def for_diagnostic(self, diagnostic: FormDiagnostic) -> Tuple[ProblemFix, ...]:
        """The fixes offered for ``diagnostic``. A fix whose ``offered`` raises is left out."""
        found = []
        for _module, fix in self._by_code.get(diagnostic.code, ()):
            try:
                if fix.offered(diagnostic):
                    found.append(fix)
            except Exception:
                logger.exception("fix %s could not say if it is offered", fix.fix_id)
        return tuple(found)


class _ModuleScope:
    def __init__(self, registry: FixRegistry, module: str) -> None:
        self._registry = registry
        self._module = module

    def add(self, fix: ProblemFix) -> None:
        self._registry.add(fix, module=self._module)


def load_fixes(*packages: ModuleType) -> FixRegistry:
    registry = FixRegistry()
    for package in packages:
        for info in sorted(pkgutil.iter_modules(package.__path__), key=lambda found: found.name):
            if info.name.startswith("_"):
                continue
            try:
                module = importlib.import_module("%s.%s" % (package.__name__, info.name))
                register = getattr(module, "register", None)
                if callable(register):
                    register(registry.scope(module.__name__))
            except Exception:
                logger.exception("problem fix module %s failed", info.name)
    return registry


_DEFAULT: Optional[FixRegistry] = None


def default_registry() -> FixRegistry:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = load_fixes(sys.modules[__name__])
    return _DEFAULT


__all__: Sequence[str] = [
    "FixContext",
    "FixRegistry",
    "ProblemFix",
    "default_registry",
    "load_fixes",
]
