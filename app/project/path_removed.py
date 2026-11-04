"""One listener for a path that is no longer at its old place.

The project tree calls ``notify_path_removed`` after a delete or a move that
leaves the old path. The form builder registers the listener. The shell does
not import the form builder.
"""

from __future__ import annotations

from typing import Callable, Optional


_listener: Optional[Callable[[str], None]] = None


def set_path_removed_listener(listener: Optional[Callable[[str], None]]) -> Optional[Callable[[str], None]]:
    """Replace the listener. Returns the previous one so a test can restore it."""

    global _listener
    previous = _listener
    _listener = listener
    return previous


def notify_path_removed(path: str) -> None:
    listener = _listener
    if listener is None or not path:
        return
    listener(path)
