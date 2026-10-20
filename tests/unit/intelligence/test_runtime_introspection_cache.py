"""Unit tests for the runtime member cache behind the introspection coordinator."""

from __future__ import annotations

from typing import Optional

import pytest

from app.intelligence.completion_models import CompletionKind
from app.intelligence.runtime_introspection import RuntimeIntrospectionCoordinator, RuntimeIntrospectionQuery
from app.intelligence.runtime_members import (
    RuntimeDetailResult,
    RuntimeListingResult,
    RuntimeMember,
    RuntimeMemberListing,
    RuntimeMemberRef,
    RuntimeUnavailable,
)

pytestmark = pytest.mark.unit

_TARGET = "PySide2.QtCore.QObject"


class _ScriptedPort:
    def __init__(self, *results: RuntimeListingResult) -> None:
        self._results = list(results)

    def list_members(self, *, target_path: str) -> RuntimeListingResult:
        return self._results.pop(0)

    def resolve_member(self, ref: RuntimeMemberRef) -> RuntimeDetailResult:
        return RuntimeUnavailable(reason="unused")


def _listing(*names: str) -> RuntimeMemberListing:
    return RuntimeMemberListing.from_members(
        _TARGET,
        [RuntimeMember(name=name, kind=CompletionKind.METHOD) for name in names],
    )


def _cached_labels(
    coordinator: RuntimeIntrospectionCoordinator,
    prefix: str,
    *,
    max_results: Optional[int] = None,
) -> Optional[list[str]]:
    items = coordinator.cached_items(
        RuntimeIntrospectionQuery(target_path=_TARGET, member_prefix=prefix),
        max_results=max_results,
    )
    return None if items is None else [item.label for item in items]


def _primed(listing: RuntimeMemberListing) -> RuntimeIntrospectionCoordinator:
    coordinator = RuntimeIntrospectionCoordinator(runner_port=_ScriptedPort(listing))
    coordinator.fetch_and_cache_from_runner(RuntimeIntrospectionQuery(target_path=_TARGET, member_prefix=""))
    return coordinator


def test_private_names_never_consume_the_public_cap() -> None:
    public = [f"item{index:02d}" for index in range(20)]
    private = [f"_item{index:02d}" for index in range(20)]
    coordinator = _primed(_listing(*private, *public))

    assert _cached_labels(coordinator, "item", max_results=5) == public[:5]
    assert _cached_labels(coordinator, "_item", max_results=5) == private


def test_omitted_max_results_returns_every_matching_public_name() -> None:
    names = [f"name{index:03d}" for index in range(150)]
    coordinator = _primed(_listing(*names))

    assert _cached_labels(coordinator, "name") == names


def test_runtime_unavailable_is_not_cached_and_a_later_listing_is_visible() -> None:
    coordinator = RuntimeIntrospectionCoordinator(
        runner_port=_ScriptedPort(RuntimeUnavailable(reason="repl_unavailable"), _listing("alpha")),
    )
    query = RuntimeIntrospectionQuery(target_path=_TARGET, member_prefix="")

    assert coordinator.fetch_and_cache_from_runner(query) == []
    assert _cached_labels(coordinator, "") is None

    assert [item.label for item in coordinator.fetch_and_cache_from_runner(query)] == ["alpha"]
    assert _cached_labels(coordinator, "") == ["alpha"]
