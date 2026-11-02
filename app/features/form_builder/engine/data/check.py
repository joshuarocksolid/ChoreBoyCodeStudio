"""Design-time data checks (CONTRACTS.md section 19.8).

``register(registry)`` in this module adds the checks that need no schema.
A later lane adds a module under ``engine/data/checks/`` and edits nothing here.
Checks run in ``(order, check_id)`` order. Each receives ``(doc, connections, schema)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.contributors import run_contributors
from app.features.form_builder.engine.diagnostics import (
    CODES,
    DiagnosticLocation,
    FormDiagnostic,
)
from app.features.form_builder.engine.logic.codec import parse_steps
from app.features.form_builder.engine.logic.storage import is_signal_property
from app.features.form_builder.engine.ui4.values import StringValue

# Import for the declaration side effect.
import app.features.form_builder.engine.diagnostic_codes.fb3xx_data  # noqa: F401

CheckFn = Callable[[object, object, object], Iterable[FormDiagnostic]]


@dataclass(frozen=True)
class DataCheck:
    check_id: str
    run: CheckFn
    order: int = 100


class CheckRegistry:
    def __init__(self) -> None:
        self._checks: List[DataCheck] = []

    def add(self, check: DataCheck) -> None:
        if any(found.check_id == check.check_id for found in self._checks):
            raise ValueError("data check %s is already registered" % check.check_id)
        self._checks.append(check)

    def checks(self) -> Tuple[DataCheck, ...]:
        return tuple(sorted(self._checks, key=lambda item: (item.order, item.check_id)))


def register(registry: CheckRegistry) -> None:
    """FB318 and FB320. They read the form only."""

    registry.add(DataCheck("records-without-source", _records_without_source, 10))
    registry.add(DataCheck("one-lines-grid", _one_lines_grid, 20))


def load_checks(*packages: ModuleType) -> CheckRegistry:
    """Built-in checks, then ``register`` in each package's modules, sorted by module name."""

    registry = CheckRegistry()
    register(registry)
    found: Tuple[ModuleType, ...] = packages
    if not found:
        import app.features.form_builder.engine.data.checks as checks

        found = (checks,)
    run_contributors("data check", found, "register", lambda _module, hook: hook(registry))
    return registry


_DEFAULT: Optional[CheckRegistry] = None


def default_registry() -> CheckRegistry:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = load_checks()
    return _DEFAULT


def reset_default_registry() -> None:
    """Tests that swap the process registry call this when they finish."""

    global _DEFAULT
    _DEFAULT = None


def run_checks(
    doc: object,
    connections: object = None,
    schema: object = None,
    registry: Optional[CheckRegistry] = None,
) -> Tuple[FormDiagnostic, ...]:
    chosen = registry if registry is not None else default_registry()
    found: List[FormDiagnostic] = []
    for check in chosen.checks():
        found.extend(check.run(doc, connections, schema))
    return tuple(found)


def _records_without_source(doc: object, connections: object, schema: object) -> Iterable[FormDiagnostic]:
    del connections, schema
    from app.features.form_builder.engine.data.source import has_data_source
    from app.features.form_builder.engine.logic.verbs.m8 import RECORD_VERBS

    if has_data_source(doc):
        return ()
    info = CODES["FB318"]
    found = []
    for node in _nodes(doc):
        name = _node_name(node)
        for entry in _properties(node):
            if not is_signal_property(entry.name) or not isinstance(entry.value, StringValue):
                continue
            read = parse_steps(entry.value.text)
            if read.error is not None or not any(step.verb in RECORD_VERBS for step in read.steps):
                continue
            found.append(
                FormDiagnostic(
                    info.code,
                    info.severity,
                    info.title,
                    DiagnosticLocation(getattr(node, "id", 0), name, entry.name, (entry.name,)),
                    "data.check",
                )
            )
    return tuple(found)


def _one_lines_grid(doc: object, connections: object, schema: object) -> Iterable[FormDiagnostic]:
    del connections, schema
    owners = []
    for node in _nodes(doc):
        for entry in _properties(node):
            if entry.name == "cbcsRows" and isinstance(entry.value, StringValue) and entry.value.text.strip():
                owners.append(node)
                break
    if len(owners) < 2:
        return ()
    info = CODES["FB320"]
    node = owners[1]
    return (
        FormDiagnostic(
            info.code,
            info.severity,
            info.title,
            DiagnosticLocation(getattr(node, "id", 0), _node_name(node), "cbcsRows", ("cbcsRows",)),
            "data.check",
        ),
    )


def _nodes(doc: object) -> Sequence[object]:
    walk = getattr(doc, "iter_preorder", None)
    if not callable(walk):
        return ()
    try:
        return tuple(walk())
    except Exception:
        return ()


def _properties(node: object) -> Sequence[object]:
    props = getattr(node, "properties", None)
    if not callable(props):
        return ()
    try:
        return tuple(props())
    except Exception:
        return ()


def _node_name(node: object) -> str:
    for field in ("object_name", "name"):
        value = getattr(node, field, "")
        if isinstance(value, str) and value:
            return value
    return "the form"


__all__ = [
    "CheckRegistry",
    "DataCheck",
    "default_registry",
    "load_checks",
    "register",
    "reset_default_registry",
    "run_checks",
]
