"""Unit tests for JediEngine facade behavior."""
from __future__ import annotations

import pytest

from app.intelligence.jedi_engine import JediEngine

pytestmark = pytest.mark.unit


def test_lookup_definition_returns_empty_when_symbol_empty(tmp_path) -> None:
    engine = JediEngine(state_root=str(tmp_path / "state"))
    source = "x = 1\n"

    result = engine.lookup_definition(
        project_root=None,
        current_file_path=str(tmp_path / "module.py"),
        source_text=source,
        cursor_position=len(source),
    )

    assert result.symbol_name == ""
    assert result.locations == []
