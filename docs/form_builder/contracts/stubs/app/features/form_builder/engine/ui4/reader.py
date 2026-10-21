"""``.ui`` reader (CONTRACTS.md section 8.1).

Parses with ``xml.parsers.expat`` directly (positions for every element, no
ElementTree tree), refuses DOCTYPE and entity declarations, and builds a
``UiDocument`` through ``engine.ui4.mutate``. Never raises anything but
``UiReadError`` for bad input (fuzz contract, section 13).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from app.features.form_builder.engine.diagnostics import FormDiagnostic
from app.features.form_builder.engine.ids import IdAllocator, NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.spec import Fragment

#: Inputs larger than this are refused with FB008 (protects the 30 MB budget).
MAX_INPUT_BYTES = 16 * 1024 * 1024
#: Element nesting deeper than this is refused with FB008.
MAX_DEPTH = 256


class UiReadError(ValueError):
    """Fatal: the text cannot become a document. The visual editor does not open;
    the tab shows View XML with the text unchanged and a banner.

    ``code``: FB001 malformed XML, FB002 not a ``<ui>`` document or no root
    widget, FB004 DOCTYPE or entity declaration, FB008 too large or too deep.
    ``line``/``column``: 1-based, from expat; 0 when unknown.
    """

    def __init__(self, code: str, message: str, line: int = 0, column: int = 0) -> None:
        ...

    code: str
    line: int
    column: int


@dataclass(frozen=True)
class ReadResult:
    """``diagnostics``: non-fatal findings from reading (FB003 newer ui version,
    FB005 value kept as written, FB006 unknown element preserved, FB007
    duplicate property moved to opaque, FB402 newer logic version).
    ``line_map``: node id -> 1-based source line of its start tag."""

    document: UiDocument
    diagnostics: Tuple[FormDiagnostic, ...]
    line_map: Dict[NodeId, int]


def read_ui(text: str, *, allocator: IdAllocator, source_path: Optional[str] = None) -> ReadResult:
    """Parse ``text`` (a leading BOM is ignored; CRLF and CR are accepted).

    Rules:
    * Whitespace-only text between elements is ignored. Text inside value leaf
      elements (``string``, ``cstring``, ``enum``, ``set``...) is kept exactly.
    * Known elements become typed nodes; unknown child elements become
      OpaqueNodes anchored after the preceding known group; unknown attributes
      are kept in input order.
    * A value element that does not parse losslessly becomes OpaqueValue.
    * Ids come from ``allocator`` in pre-order.
    O(input). Budget: 25 ms CPU for a 300-widget form (section 12).
    """
    ...


def read_fragment(text: str, *, source_path: Optional[str] = None) -> Fragment:
    """Parse clipboard text into a ``Fragment`` with ``id=None``
    everywhere. Accepts a full ``<ui>`` document (its root's children become the
    fragment) or the CBCS fragment MIME payload. Raises UiReadError."""
    ...
