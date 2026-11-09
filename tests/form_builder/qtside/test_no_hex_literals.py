# pyright: reportAttributeAccessIssue=false
"""UX-TOK-001. Builder hex lives in the theme package."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterator

import pytest

_ROOT = Path(__file__).resolve().parents[3] / "app" / "features" / "form_builder"
_ALLOWED = frozenset(
    {
        "Enter a color like #1A2B3C.",
        # The form's invalid-field rule. It is stored on the form, not painted as chrome.
        '*[cbcsInvalid="true"] { border: 1px solid #c62828; }',
    }
)


def test_form_builder_hex_literals_stay_in_the_theme_package() -> None:
    offenders = list(_hex_literals())
    assert offenders == [], "hex outside qtside/theme: %s" % offenders


def _hex_literals() -> Iterator[str]:
    for path in sorted(_ROOT.rglob("*.py")):
        if "qtside/theme/" in path.as_posix():
            continue
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if node.value in _ALLOWED:
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


pytestmark = pytest.mark.unit
