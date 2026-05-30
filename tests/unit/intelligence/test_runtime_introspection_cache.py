"""Unit tests for runtime introspection session cache."""

from __future__ import annotations

import pytest

from app.intelligence.completion_models import CompletionItem, CompletionKind
from app.intelligence.runtime_introspection_cache import RuntimeIntrospectionCache

pytestmark = pytest.mark.unit


def test_runtime_introspection_cache_stores_and_returns_items() -> None:
    cache = RuntimeIntrospectionCache(max_entries=4)
    items = [
        CompletionItem(label="alpha", insert_text="alpha", kind=CompletionKind.ATTRIBUTE),
    ]

    cache.put(target_path="PySide2.QtCore", include_private=False, items=items)

    cached = cache.get(target_path="PySide2.QtCore", include_private=False)
    assert cached is not None
    assert cached[0].label == "alpha"
