# pyright: reportAttributeAccessIssue=false
"""UX-TOK-001. Builder hex lives in the theme package."""

from __future__ import annotations

import ast
import tokenize
from pathlib import Path
from typing import Iterator, Tuple

import pytest

_ROOT = Path(__file__).resolve().parents[3] / "app" / "features" / "form_builder"
_ALLOWED = frozenset({"Enter a color like #1A2B3C."})


def test_form_builder_hex_literals_stay_in_the_theme_package() -> None:
    offenders = list(_hex_literals())
    assert offenders == [], "hex outside qtside/theme: %s" % offenders


def _hex_literals() -> Iterator[str]:
    for path in sorted(_ROOT.rglob("*.py")):
        if "qtside/theme/" in path.as_posix():
            continue
        source = path.read_text(encoding="utf-8")
        comments = _comment_spans(path)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if node.value in _ALLOWED:
                continue
            if _in_span(node, comments):
                continue
            if _hex_in(node.value):
                yield "%s:%s" % (path.relative_to(_ROOT.parent.parent.parent), node.lineno)


def _hex_in(text: str) -> bool:
    index = 0
    while True:
        found = text.find("#", index)
        if found < 0:
            return False
        rest = text[found + 1 :]
        if _is_hex(rest, 6) or _is_hex(rest, 3):
            return True
        index = found + 1


def _is_hex(text: str, size: int) -> bool:
    if len(text) < size:
        return False
    chunk = text[:size]
    if any(ch not in "0123456789abcdefABCDEF" for ch in chunk):
        return False
    if size == 3 and len(text) > 3 and text[3] in "0123456789abcdefABCDEF":
        return False
    return True


def _comment_spans(path: Path) -> Tuple[Tuple[Tuple[int, int], Tuple[int, int]], ...]:
    spans = []
    with path.open("rb") as handle:
        for token in tokenize.tokenize(handle.readline):
            if token.type == tokenize.COMMENT:
                spans.append((token.start, token.end))
    return tuple(spans)


def _in_span(node: ast.AST, spans: Tuple[Tuple[Tuple[int, int], Tuple[int, int]], ...]) -> bool:
    start = (int(getattr(node, "lineno", 0)), int(getattr(node, "col_offset", 0)))
    for comment_start, comment_end in spans:
        if _pos_le(comment_start, start) and _pos_lt(start, comment_end):
            return True
    return False


def _pos_le(left: Tuple[int, int], right: Tuple[int, int]) -> bool:
    if left[0] != right[0]:
        return left[0] < right[0]
    return left[1] <= right[1]


def _pos_lt(left: Tuple[int, int], right: Tuple[int, int]) -> bool:
    if left[0] != right[0]:
        return left[0] < right[0]
    return left[1] < right[1]


pytestmark = pytest.mark.unit
