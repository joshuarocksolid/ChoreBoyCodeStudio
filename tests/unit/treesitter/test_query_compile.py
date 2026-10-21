"""Compile every shipped query against the active tree-sitter."""

from __future__ import annotations

import pytest

from app.treesitter.language_registry import TreeSitterLanguageRegistry
from app.treesitter.language_specs import LANGUAGE_SPECS
from app.treesitter.loader import available_language_keys, initialize_tree_sitter_runtime
from app.treesitter.ts_api import compile_query

pytestmark = pytest.mark.unit


def test_shipped_queries_compile() -> None:
    import app.treesitter.loader as loader

    loader._RUNTIME_INITIALIZED = False
    status = initialize_tree_sitter_runtime()
    if not status.is_available:
        pytest.skip(status.message)

    registry = TreeSitterLanguageRegistry()
    failures: list[str] = []
    available = set(available_language_keys())
    for spec in LANGUAGE_SPECS:
        if spec.key not in available:
            # The loader skips grammars outside the core's language ABI range.
            continue
        resolved = registry.resolve_for_key(spec.key)
        if resolved is None:
            failures.append(f"{spec.key}: language did not resolve")
            continue
        sources = (
            ("highlights", resolved.highlights_query_source),
            ("locals", resolved.locals_query_source),
            ("injections", resolved.injections_query_source),
        )
        for kind, source in sources:
            if not source.strip():
                continue
            try:
                compile_query(resolved.language, source)
            except Exception as exc:
                failures.append(f"{spec.key} {kind}: {exc}")

    assert failures == []
