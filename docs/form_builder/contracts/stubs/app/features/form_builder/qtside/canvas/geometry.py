"""The Qt implementation of ``engine.query.hit_index.GeometrySource`` and the
invalidation wiring (CONTRACTS.md section 5.5)."""

from __future__ import annotations

from typing import Sequence

from app.features.form_builder.engine.events import ChangeSet
from app.features.form_builder.engine.query.hit_index import GeoEntry, HitIndex
from app.features.form_builder.qtside.realize.api import Realizer


class LiveGeometrySource:
    """Reads ``geometry()`` of realized widgets and ``QLayout.geometry()`` /
    ``itemAt(i).geometry()`` of realized layouts, mapped to root coordinates by
    accumulating parent offsets during one pre-order walk (no ``mapTo`` per
    widget). Pages that are not current are entered with ``visible=False``."""

    def __init__(self, realizer: Realizer) -> None:
        ...

    def settle(self) -> None:
        """Activates the root layout. Never called from paintEvent (CONTRACTS 5.5)."""
        ...

    def entries(self) -> Sequence[GeoEntry]:
        ...


class HitIndexInvalidator:
    """Subscribed at PRIORITY_HIT_INDEX: every ChangeSet -> ``invalidate("changeset")``.
    The canvas calls ``invalidate`` for zoom, root resize, current page change,
    scroll-area scroll, splitter move, text-size preview, style/palette/DPI
    change, realize rebuild and show/hide of any realized widget. Nothing else
    invalidates; nothing reads geometry here."""

    def __init__(self, index: HitIndex) -> None:
        ...

    def on_changeset(self, changeset: ChangeSet) -> None:
        ...
