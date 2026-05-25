"""Bounded tail buffer for run output aggregation."""

from __future__ import annotations

from collections import deque


class OutputTailBuffer:
    """Stores only the newest output chunks within configured limits."""

    def __init__(self, *, max_chars: int = 200_000, max_chunks: int = 4_000) -> None:
        self._max_chars = max(1, int(max_chars))
        self._max_chunks = max(1, int(max_chunks))
        self._chunks: deque[str] = deque()
        self._total_chars = 0

    def append(self, text: str) -> None:
        if not text:
            return
        self._chunks.append(text)
        self._total_chars += len(text)
        self._trim()

    def clear(self) -> None:
        self._chunks.clear()
        self._total_chars = 0

    def text(self) -> str:
        return "".join(self._chunks)

    @property
    def total_chars(self) -> int:
        return self._total_chars

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    def _trim(self) -> None:
        while self._chunks and (self._total_chars > self._max_chars or len(self._chunks) > self._max_chunks):
            removed = self._chunks.popleft()
            self._total_chars -= len(removed)
