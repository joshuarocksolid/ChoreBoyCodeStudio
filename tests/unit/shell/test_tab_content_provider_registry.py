"""Registry matching rules for tab-content providers."""

from __future__ import annotations

import pytest

from app.shell.tab_content_providers import TabContentProviderRegistry, TabMatchContext

pytestmark = pytest.mark.unit


class _Provider:
    def __init__(self, provider_id: str, priority: int, paths: set[str]) -> None:
        self.provider_id = provider_id
        self.priority = priority
        self._paths = paths

    def matches(self, file_path: str, context: TabMatchContext) -> bool:
        del context
        return file_path in self._paths

    def create_surface(self, request: object) -> object:
        raise AssertionError(request)


def test_duplicate_provider_id_is_rejected() -> None:
    registry = TabContentProviderRegistry()
    registry.register(_Provider("markdown", 0, set()))

    with pytest.raises(ValueError, match="duplicate"):
        registry.register(_Provider("markdown", 1, set()))


def test_priority_tie_is_rejected() -> None:
    registry = TabContentProviderRegistry()
    registry.register(_Provider("markdown", 0, set()))

    with pytest.raises(ValueError, match="ties priority"):
        registry.register(_Provider("forms", 0, set()))


def test_higher_priority_provider_wins() -> None:
    registry = TabContentProviderRegistry()
    low = _Provider("markdown", 0, {"/tmp/notes.md"})
    high = _Provider("forms", 10, {"/tmp/notes.md"})
    registry.register(low)
    registry.register(high)

    chosen = registry.provider_for("/tmp/notes.md", TabMatchContext(project_root=None))

    assert chosen is high


def test_bind_rejects_a_path_that_is_already_bound() -> None:
    registry = TabContentProviderRegistry()
    first = object()
    registry.bind("/tmp/notes.md", first, "markdown")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="already bound"):
        registry.bind("/tmp/notes.md", object(), "markdown")  # type: ignore[arg-type]

    assert registry.surface_for_path("/tmp/notes.md") is first
    assert registry.provider_id_for("/tmp/notes.md") == "markdown"


def test_rekey_rejects_a_target_that_is_already_bound() -> None:
    registry = TabContentProviderRegistry()
    moving = object()
    kept = object()
    registry.bind("/tmp/old.md", moving, "markdown")  # type: ignore[arg-type]
    registry.bind("/tmp/new.md", kept, "markdown")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="already bound"):
        registry.rekey("/tmp/old.md", "/tmp/new.md")

    assert registry.surface_for_path("/tmp/old.md") is moving
    assert registry.surface_for_path("/tmp/new.md") is kept


def test_forced_text_skips_matching_providers() -> None:
    registry = TabContentProviderRegistry()
    registry.register(_Provider("markdown", 0, {"/tmp/notes.md"}))

    chosen = registry.provider_for(
        "/tmp/notes.md",
        TabMatchContext(project_root="/tmp", forced_text=True),
    )

    assert chosen is None
