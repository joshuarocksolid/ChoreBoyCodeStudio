"""Per-buffer editor state shared by every view of one open file.

Two editor groups can show the same file. Both views use one
``QTextDocument``, so they share the text, the undo stack and the modified
flag. Everything derived from the text belongs here too, so it exists once per
buffer: the syntax highlighter (and its tree-sitter tree), the language
override, breakpoints, the debug execution line, and lint diagnostics. Views
keep only what is about the view: cursor, scroll, selections they draw, and
theme colors.
"""

from __future__ import annotations

from typing import Any, Iterator, Optional

from app.qt.QtGui import QTextDocument
from app.qt.QtWidgets import QPlainTextDocumentLayout, QWidget
from app.qt.qt_compat import wrapper_is_valid


class EditorBuffer:
    """Document plus buffer-level editor state; owned by the views that show it."""

    def __init__(self) -> None:
        # No Qt parent: the document must outlive whichever view created it.
        self.document = QTextDocument()
        self.document.setDocumentLayout(QPlainTextDocumentLayout(self.document))
        self.highlighter: Optional[Any] = None
        self.language_override_key: Optional[str] = None
        self.file_path: Optional[str] = None
        self.breakpoints: set[int] = set()
        self.debug_execution_line: Optional[int] = None
        self.diagnostics: list[Any] = []
        self._views: dict[int, QWidget] = {}

    def attach(self, view: QWidget) -> None:
        key = id(view)
        if key in self._views:
            return
        self._views[key] = view
        view.destroyed.connect(lambda _obj=None, key=key: self._views.pop(key, None))

    def detach(self, view: QWidget) -> None:
        self._views.pop(id(view), None)

    def views(self) -> Iterator[Any]:
        """Views showing this buffer, including the caller."""
        live = [view for view in self._views.values() if wrapper_is_valid(view)]
        return iter(live)

    def view_count(self) -> int:
        return len(list(self.views()))


__all__ = ["EditorBuffer"]
