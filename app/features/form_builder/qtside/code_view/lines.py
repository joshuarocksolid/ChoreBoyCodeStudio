"""Which lines of a generated ``ui_<name>.py`` belong to which widget (UX-PREV-004).

Pure text work, no Qt. The generated module names every widget, layout and
spacer as an attribute of the form class (``self.totalLabel = QLabel(Till)``).
The root widget is the ``setupUi`` argument (``Till.resize(480, 320)``). A
widget's lines are every line that names it; its first line is the one that
creates it.
"""

from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

_SETUP = re.compile(r"^\s*def setupUi\(self, (\w+)\)")
_SELF_NAME = re.compile(r"\bself\.([A-Za-z_]\w*)")
_CREATES = re.compile(r"^\s*self\.([A-Za-z_]\w*)\s*=")


class CodeIndex:
    """Lines (0-based) by object name for one generated text."""

    def __init__(self, text: str) -> None:
        self._lines: Dict[str, Tuple[int, ...]] = {}
        self._first: Dict[str, int] = {}
        self._text_lines = text.splitlines()
        self._root = ""
        found: Dict[str, list] = {}
        for number, line in enumerate(self._text_lines):
            setup = _SETUP.match(line)
            if setup is not None and not self._root:
                self._root = setup.group(1)
            for match in _SELF_NAME.finditer(line):
                found.setdefault(match.group(1), []).append(number)
            creates = _CREATES.match(line)
            if creates is not None and creates.group(1) not in self._first:
                self._first[creates.group(1)] = number
        if self._root:
            numbers = [n for n, line in enumerate(self._text_lines) if self._on_root(line)]
            found[self._root] = numbers
            if numbers:
                self._first[self._root] = numbers[0]
        self._lines = {name: tuple(sorted(set(numbers))) for name, numbers in found.items()}

    def lines_of(self, name: str) -> Tuple[int, ...]:
        """Every line that names ``name``, or nothing when the generated text never mentions it."""
        return self._lines.get(name, ())

    def first_line(self, name: str) -> Optional[int]:
        """The line that creates ``name`` (for the root: its first mention)."""
        if name in self._first:
            return self._first[name]
        lines = self._lines.get(name)
        return lines[0] if lines else None

    def name_on(self, line: int) -> Optional[str]:
        """The widget ``line`` names (the first attribute on it that is a known widget), else None."""
        if line < 0 or line >= len(self._text_lines):
            return None
        text = self._text_lines[line]
        for match in _SELF_NAME.finditer(text):
            name = match.group(1)
            if name in self._first:
                return name
        if self._on_root(text):
            return self._root
        return None

    def _on_root(self, text: str) -> bool:
        """True for a line whose receiver is the form itself: ``Till.resize(...)``, not ``QLabel(Till)``."""
        if not self._root:
            return False
        return re.search(r"(?<![\w.])%s\." % re.escape(self._root), text) is not None


__all__ = ["CodeIndex"]
