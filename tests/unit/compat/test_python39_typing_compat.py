"""Compatibility guards for Python 3.9 runtime constraints."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_syntax_registry_highlighter_factory_avoids_runtime_pipe_union() -> None:
    """HighlighterFactory alias must stay safe for Python 3.9 runtime evaluation."""
    source_path = Path("app/editors/syntax_registry.py")
    source = source_path.read_text(encoding="utf-8")
    highlighter_line = next(
        line.strip() for line in source.splitlines() if line.strip().startswith("HighlighterFactory = ")
    )
    assert "| None" not in highlighter_line
    assert "Optional[Mapping[str, str]]" in highlighter_line
