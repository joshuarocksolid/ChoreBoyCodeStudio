"""Explorer letters from a dict. Paint reads the dict and nothing else."""

from __future__ import annotations

from typing import Optional


class ExplorerLetterCache:
    """O(1) letter lookup. ``replace`` is the only writer. ``lookup`` does not touch disk."""

    def __init__(self) -> None:
        self._letters: dict[str, tuple[str, str]] = {}

    def replace(self, letters: dict[str, tuple[str, str]]) -> None:
        self._letters = dict(letters)

    def lookup(self, relative_path: str) -> Optional[tuple[str, str]]:
        return self._letters.get(relative_path)


__all__ = ["ExplorerLetterCache"]
