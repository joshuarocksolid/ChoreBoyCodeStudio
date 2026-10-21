"""Point-range captures through the active tree-sitter binding."""

from __future__ import annotations

from typing import Any

import pytest

from app.treesitter.capture_pipeline import TreeSitterCapturePipelineMixin
from app.treesitter.language_registry import default_tree_sitter_language_registry
from app.treesitter.loader import initialize_tree_sitter_runtime
from app.treesitter.ts_api import captures, compile_query, make_parser

pytestmark = pytest.mark.unit


def _identifier_texts(raw: Any, source: bytes) -> set[str]:
    normalized = TreeSitterCapturePipelineMixin._normalize_captures(
        raw,
        start_line=1,
        end_line=1,
    )
    return {source[node.start_byte : node.end_byte].decode("utf-8") for node, _name in normalized}


def test_captures_limit_to_point_range() -> None:
    # Use the process-wide runtime as-is. Re-initializing it re-imports
    # tree_sitter, and the cached default registry would then hold Language
    # objects from the previous module instance.
    status = initialize_tree_sitter_runtime()
    if not status.is_available:
        pytest.skip(status.message)

    resolved = default_tree_sitter_language_registry().resolve_for_key("python")
    assert resolved is not None
    source = b"alpha = 1\nbeta = 2\n"
    parser = make_parser(resolved.language)
    tree = parser.parse(source)
    query = compile_query(resolved.language, "(identifier) @id")

    ranged = captures(
        query,
        tree.root_node,
        start_point=(1, 0),
        end_point=(2, 0),
    )
    texts = _identifier_texts(ranged, source)
    assert "beta" in texts
    assert "alpha" not in texts
    if not hasattr(query, "captures"):
        raw_texts = set()
        for nodes in ranged.values():
            raw_texts.update(source[node.start_byte : node.end_byte].decode("utf-8") for node in nodes)
        assert "alpha" not in raw_texts
