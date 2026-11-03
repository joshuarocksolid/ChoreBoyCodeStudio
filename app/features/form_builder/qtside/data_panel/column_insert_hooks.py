"""Hooks a later lane uses when a column is dropped or inserted.

M8.2 calls these and does not decide what a foreign key becomes.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

_CLASS: List[Callable] = []
_LABEL: List[Callable] = []
_AFTER: List[Callable] = []


def register_widget_class(fn: Callable) -> None:
    if fn not in _CLASS:
        _CLASS.append(fn)


def widget_class_override(column: object, engine: str) -> Optional[Tuple[str, object]]:
    for fn in _CLASS:
        decided = fn(column, engine)
        if decided is not None:
            return decided
    return None


def register_insert_label(fn: Callable) -> None:
    if fn not in _LABEL:
        _LABEL.append(fn)


def insert_label(column: object, class_name: str, kind: object) -> str:
    for fn in _LABEL:
        text = fn(column, class_name, kind)
        if text:
            return str(text)
    return ""


def register_after_insert(fn: Callable) -> None:
    if fn not in _AFTER:
        _AFTER.append(fn)


def after_insert(txn: object, session: object, field_id: object, column: object, class_name: str, kind: object) -> None:
    for fn in _AFTER:
        fn(txn, session, field_id, column, class_name, kind)


_SEARCH: List[Callable] = []


def register_search_screen(fn: Callable) -> None:
    """M8.3c registers the command behind "[Use a search screen instead]"."""

    if fn not in _SEARCH:
        _SEARCH.append(fn)


def search_screen_command() -> Optional[Callable]:
    if not _SEARCH:
        return None
    return _SEARCH[-1]
