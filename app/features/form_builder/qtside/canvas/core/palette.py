"""The widgets a drop can insert, read from the Insert catalog (UX-CAT-001).

A thin shim: the canvas, gesture and controller code keep calling ``tile_for``,
``matching_tiles`` and ``fragment_for``. The data lives in ``qtside/insert/catalog``
(Qt-free) and the ranking in ``qtside/insert/catalog/search.py``.
"""

from __future__ import annotations

from typing import Optional, Tuple

from app.features.form_builder.engine.query.drop_target import PayloadKind
from app.features.form_builder.engine.ui4.spec import Fragment
from app.features.form_builder.qtside.insert.catalog import load_catalog
from app.features.form_builder.qtside.insert.catalog._model import WINDOW
from app.features.form_builder.qtside.insert.catalog.search import search

MIME_INSERT = "application/x-cbcs-insert"
MIME_NODE = "application/x-cbcs-node"
MIME_FRAGMENT = "application/x-cbcs-form-fragment"
MIME_DESIGNER_FRAGMENT = "application/x-qt-designer-ui-fragment"

Tile = Tuple[str, PayloadKind, str]


def _all_tiles() -> Tuple[Tile, ...]:
    return tuple((entry.key, entry.payload, entry.friendly) for entry in load_catalog().entries)  # type: ignore[misc]


#: Every widget entry as ``(catalog key, payload kind, friendly name)``, in catalog order.
TILES: Tuple[Tile, ...] = _all_tiles()


def tile_for(key: str) -> Optional[Tile]:
    entry = load_catalog().get(key)
    if entry is None or entry.payload == WINDOW:
        return None
    return (entry.key, entry.payload, entry.friendly)  # type: ignore[return-value]


def matching_tiles(query: str) -> Tuple[Tile, ...]:
    """Widget results for ``query`` (UX-CAT-007). An empty query lists every entry."""
    catalog = load_catalog()
    hits = search(catalog.entries, (), query)
    return tuple((hit.entry.key, hit.entry.payload, hit.entry.friendly) for hit in hits)  # type: ignore[misc]


def fragment_for(key: str) -> Optional[Fragment]:
    entry = load_catalog().get(key)
    if entry is None or entry.build is None:
        return None
    return entry.build()
