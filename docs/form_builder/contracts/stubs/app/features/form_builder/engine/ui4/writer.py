"""Deterministic ``.ui`` writer and the lazy serialization cache
(CONTRACTS.md sections 8.2-8.4).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.spec import Fragment

XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>'
INDENT = " "


@dataclass(frozen=True)
class WriteResult:
    """``text``: the file content (``\\n`` newlines, trailing newline after
    ``</ui>``). ``line_map``: node id -> 1-based line of its start tag in ``text``
    (feeds Problems line numbers)."""

    text: str
    line_map: Dict[NodeId, int]


def write_ui(doc: UiDocument) -> WriteResult:
    """Serialize. A pure function of the document's content (ids excluded):
    no clock, locale, environment, hash seed or set iteration. O(form).
    Budget: 10 ms CPU for a 300-widget form."""
    ...


def write_fragment(fragment: Fragment) -> str:
    """Clipboard text for ``fragment`` (same byte rules as ``write_ui``)."""
    ...


class SerializationCache:
    """Per-session memo: ``text(doc)`` serializes only when ``doc.revision``
    changed since the last call. The ONLY path by which shell-visible XML is
    produced (save, local-history snapshot, draft timer, View XML, preview load).

    ``serialize_count`` is observable so tests can assert that N edits cause
    zero serializations (section 13).
    """

    def __init__(self) -> None:
        ...

    def text(self, doc: UiDocument) -> str:
        ...

    def result(self, doc: UiDocument) -> WriteResult:
        ...

    def last_line_map(self) -> Optional[Dict[NodeId, int]]:
        """Line map from the most recent serialization (may be stale), or None."""
        ...

    @property
    def serialize_count(self) -> int:
        ...
