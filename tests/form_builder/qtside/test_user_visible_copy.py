# pyright: reportAttributeAccessIssue=false
"""User-visible strings stay free of milestone names and internal ids (UX-COPY-002)."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterable, List, Tuple

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3] / "app" / "features" / "form_builder"
_WORDS = (
    "qtside/canvas/core/words.py",
    "integration/chrome_text.py",
    "qtside/inspector/words.py",
)
_SINKS = {
    "setText",
    "setToolTip",
    "setPlaceholderText",
    "setAccessibleName",
    "setWindowTitle",
    "addAction",
    "addMenu",
    "show_plain",
    "narrate",
    "showMessage",
}
_STUBS = frozenset(
    {
        "Not built yet (M8)",
        "Connect this form to a table",
    }
)
_MILESTONE = re.compile(r"\bM[0-9]+(\.[0-9]+)?[a-z]?\b")
_BANNED = re.compile(r"\bphase\b|later release|coming soon|form\.action\.|formBuilder\.", re.IGNORECASE)


def test_user_visible_strings_hide_milestones_and_internal_ids() -> None:
    """UX-COPY-002. UX-EMPTY-006 is the only stub allowed to name a milestone."""
    hits = list(_scan())
    assert hits == [], "\n".join("%s:%s: %s" % item for item in hits)


def _scan() -> Iterable[Tuple[str, int, str]]:
    for path in sorted(_ROOT.rglob("*.py")):
        relative = path.relative_to(_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        words = relative in _WORDS
        for node in ast.walk(tree):
            if words and isinstance(node, ast.Constant) and isinstance(node.value, str):
                if _banned(node.value):
                    yield relative, node.lineno, node.value
            if isinstance(node, ast.Call) and _is_sink(node):
                for text, line in _literal_args(node):
                    if _banned(text):
                        yield relative, line, text


def _banned(text: str) -> bool:
    if text in _STUBS:
        return False
    return _MILESTONE.search(text) is not None or _BANNED.search(text) is not None


def _is_sink(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr in _SINKS
    return isinstance(func, ast.Name) and func.id == "QLabel"


def _literal_args(node: ast.Call) -> List[Tuple[str, int]]:
    found: List[Tuple[str, int]] = []
    for arg in list(node.args) + [keyword.value for keyword in node.keywords]:
        text = _literal(arg)
        if text is not None:
            found.append((text, getattr(arg, "lineno", node.lineno)))
    return found


def _literal(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            else:
                return None
        return "".join(parts)
    return None
