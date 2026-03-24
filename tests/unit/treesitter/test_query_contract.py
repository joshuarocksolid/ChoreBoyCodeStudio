"""Contract tests for curated highlight/local query assets."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.shell.syntax_color_preferences import SYNTAX_COLOR_TOKENS
from app.treesitter.highlighter import _CAPTURE_TOKEN_MAP

pytestmark = pytest.mark.unit

_QUERY_DIR = Path(__file__).resolve().parents[3] / "app" / "treesitter" / "queries"
_CAPTURE_PATTERN = re.compile(r"@([A-Za-z0-9_.-]+)")
_LOCAL_ROLE_PATTERN = re.compile(r'#set!\s+local\.role\s+"([^"]+)"')


def _highlight_query_paths() -> list[Path]:
    return sorted(
        path
        for path in _QUERY_DIR.glob("*.scm")
        if not path.name.endswith(".locals.scm") and not path.name.endswith(".injections.scm")
    )


def _resolve_capture_token(capture_name: str) -> str | None:
    direct = _CAPTURE_TOKEN_MAP.get(capture_name)
    if direct is not None:
        return direct
    root_name = capture_name.split(".", 1)[0]
    return _CAPTURE_TOKEN_MAP.get(root_name)


def test_highlight_queries_only_emit_mapped_captures() -> None:
    unresolved: list[str] = []
    for query_path in _highlight_query_paths():
        text = query_path.read_text(encoding="utf-8")
        captures = sorted(set(_CAPTURE_PATTERN.findall(text)))
        for capture_name in captures:
            if _resolve_capture_token(capture_name) is None:
                unresolved.append(f"{query_path.name}: @{capture_name}")
    assert unresolved == []


def test_syntax_color_preferences_are_reachable_from_queries() -> None:
    reachable_tokens: set[str] = set()
    for query_path in _highlight_query_paths():
        text = query_path.read_text(encoding="utf-8")
        for capture_name in set(_CAPTURE_PATTERN.findall(text)):
            token_name = _resolve_capture_token(capture_name)
            if token_name is not None:
                reachable_tokens.add(token_name)
    for query_path in sorted(_QUERY_DIR.glob("*.locals.scm")):
        text = query_path.read_text(encoding="utf-8")
        reachable_tokens.update(_LOCAL_ROLE_PATTERN.findall(text))
    reachable_tokens.update({"markdown_emphasis", "markdown_strong"})
    declared_tokens = {token.key for token in SYNTAX_COLOR_TOKENS}
    missing = sorted(declared_tokens - reachable_tokens)
    assert missing == []
