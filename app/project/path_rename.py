"""One handler for a path the project tree is about to move.

The project tree calls ``try_move`` before a rename, cut, or drop. The form
builder registers the handler. The shell does not import the form builder.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Tuple, Union


@dataclass(frozen=True)
class MoveRefusal:
    sentence: str


@dataclass(frozen=True)
class MoveDone:
    """``moved`` is ``(old, new)`` for each path the plan moved."""

    moved: Tuple[Tuple[str, str], ...]


MoveOutcome = Union[MoveRefusal, MoveDone]


_handler: Optional[Callable[[str, str], Optional[MoveOutcome]]] = None


def set_path_move_handler(
    handler: Optional[Callable[[str, str], Optional[MoveOutcome]]],
) -> Optional[Callable[[str, str], Optional[MoveOutcome]]]:
    """Replace the handler. Returns the previous one so a test can restore it."""

    global _handler
    previous = _handler
    _handler = handler
    return previous


def try_move(source: str, destination: str) -> Optional[MoveOutcome]:
    """Ask the handler to move ``source``. ``None`` means the shell moves it."""

    handler = _handler
    if handler is None:
        return None
    return handler(source, destination)
