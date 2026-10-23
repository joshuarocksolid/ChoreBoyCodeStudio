"""Registrations become one frozen Catalog. The conflict rule lives here and nowhere else."""

from __future__ import annotations

from typing import Dict, FrozenSet, Generic, Hashable, Mapping, Optional, Tuple, TypeVar

from app.features.form_builder.qtside.inspector.api import (
    EditorFactory,
    EditorKey,
    GroupBodyFactory,
    GroupId,
    Registrar,
    RowSpec,
)

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


class RegistryConflict(RuntimeError):
    """Two baselines, or two overrides, of one key. The message names both modules."""


class _Slots(Generic[K, V]):
    """Per key, at most one baseline and one override. The override wins in the baseline's place."""

    def __init__(self, kind: str) -> None:
        self._kind = kind
        self._baselines: Dict[K, Tuple[V, str]] = {}
        self._overrides: Dict[K, Tuple[V, str]] = {}

    def add(self, key: K, value: V, module: str, baseline: bool) -> None:
        bucket = self._baselines if baseline else self._overrides
        held = bucket.get(key)
        if held is not None:
            raise RegistryConflict(
                "%s %r is registered %sby both %s and %s"
                % (self._kind, key, "as a baseline " if baseline else "", held[1], module)
            )
        bucket[key] = (value, module)

    def resolve(self) -> Dict[K, V]:
        merged = {key: value for key, (value, _module) in self._baselines.items()}
        for key, (value, _module) in self._overrides.items():
            merged[key] = value
        return merged


class Registrations:
    """Collects registrations in load order. Freeze once."""

    def __init__(self) -> None:
        self.editors: _Slots[EditorKey, EditorFactory] = _Slots("editor")
        self.rows: _Slots[str, RowSpec] = _Slots("row")
        self.bodies: _Slots[GroupId, GroupBodyFactory] = _Slots("group body")

    def scope(self, module: str) -> Registrar:
        """A Registrar that stamps each registration with ``module``."""
        return _Scope(self, module)

    def freeze(self) -> Catalog:
        return Catalog(tuple(self.rows.resolve().values()), self.editors.resolve(), self.bodies.resolve())


class _Scope:
    def __init__(self, found: Registrations, module: str) -> None:
        self._found = found
        self._module = module

    def editor(self, key: EditorKey, factory: EditorFactory, *, baseline: bool = False) -> None:
        self._found.editors.add(key, factory, self._module, baseline)

    def row(self, spec: RowSpec, *, baseline: bool = False) -> None:
        self._found.rows.add(spec.key, spec, self._module, baseline)

    def group_body(self, group: GroupId, factory: GroupBodyFactory, *, baseline: bool = False) -> None:
        self._found.bodies.add(group, factory, self._module, baseline)


class Catalog:
    """Frozen. Registrations.freeze builds one."""

    def __init__(
        self,
        rows: Tuple[RowSpec, ...],
        editors: Mapping[EditorKey, EditorFactory],
        bodies: Mapping[GroupId, GroupBodyFactory],
    ) -> None:
        self._rows = rows
        self._editors = dict(editors)
        self._bodies = dict(bodies)
        self._editor_keys = frozenset(self._editors)

    def rows(self) -> Tuple[RowSpec, ...]:
        """Curated rows in resolved order."""
        return self._rows

    def editor(self, key: EditorKey) -> Optional[EditorFactory]:
        return self._editors.get(key)

    def editor_keys(self) -> FrozenSet[EditorKey]:
        return self._editor_keys

    def group_body(self, group: GroupId) -> Optional[GroupBodyFactory]:
        return self._bodies.get(group)
