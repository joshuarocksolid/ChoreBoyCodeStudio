"""Saved form pieces in the global settings store.

The key is ``form_builder.saved_pieces`` on the same JSON file as the rest of
the shell settings. A missing block is an empty list. A row that is not a
named fragment is dropped.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from app.features.form_builder.engine.clipboard import plain_names, selection_fragment
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument, next_object_name
from app.features.form_builder.engine.ui4.reader import UiReadError, read_fragment
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec
from app.features.form_builder.engine.ui4.writer import write_fragment
from app.features.form_builder.integration.memory import SETTINGS_KEY
from app.persistence.settings_service import SettingsService

PIECES_KEY = "saved_pieces"
_FALLBACK_NAME = "piece"


@dataclass(frozen=True)
class SavedPiece:
    name: str
    xml: str


def pieces_from_payload(payload: Mapping[str, Any]) -> Tuple[SavedPiece, ...]:
    section = payload.get(SETTINGS_KEY)
    if not isinstance(section, Mapping):
        return ()
    raw = section.get(PIECES_KEY)
    if not isinstance(raw, list):
        return ()
    found = []
    for item in raw:
        piece = _piece(item)
        if piece is not None:
            found.append(piece)
    return tuple(found)


def payload_with_pieces(payload: Mapping[str, Any], pieces: Sequence[SavedPiece]) -> dict[str, Any]:
    updated = dict(payload)
    section_raw = updated.get(SETTINGS_KEY)
    section = dict(section_raw) if isinstance(section_raw, Mapping) else {}
    section[PIECES_KEY] = [{"name": piece.name, "xml": piece.xml} for piece in pieces]
    updated[SETTINGS_KEY] = section
    return updated


def unique_piece_name(name: str, taken: Sequence[str]) -> str:
    """The engine's object-name suffix. ``email_2`` becomes ``email_3``."""
    return next_object_name(name, taken)


def piece_from_fragment(fragment: Fragment, taken: Sequence[str]) -> Optional[SavedPiece]:
    if not fragment.nodes:
        return None
    base = _visible_base(fragment)
    return SavedPiece(unique_piece_name(base, taken), write_fragment(fragment))


def piece_for_ids(document: UiDocument, ids: Sequence[NodeId], taken: Sequence[str]) -> Optional[SavedPiece]:
    return piece_from_fragment(selection_fragment(document, ids), taken)


def renamed_pieces(pieces: Sequence[SavedPiece], index: int, name: str) -> Tuple[SavedPiece, ...]:
    if index < 0 or index >= len(pieces):
        return tuple(pieces)
    cleaned = name.strip()
    if not cleaned:
        return tuple(pieces)
    current = pieces[index]
    others = [piece.name for slot, piece in enumerate(pieces) if slot != index]
    chosen = cleaned if cleaned == current.name else unique_piece_name(cleaned, others)
    updated = list(pieces)
    updated[index] = SavedPiece(chosen, current.xml)
    return tuple(updated)


def without_piece(pieces: Sequence[SavedPiece], index: int) -> Tuple[SavedPiece, ...]:
    if index < 0 or index >= len(pieces):
        return tuple(pieces)
    return tuple(piece for slot, piece in enumerate(pieces) if slot != index)


_STORES: Dict[str, "SavedPieceStore"] = {}


class SavedPieceStore:
    """One store per settings root. Every open form reads the same list."""

    def __new__(cls, state_root: Optional[str] = None) -> "SavedPieceStore":
        key = "" if state_root is None else state_root
        found = _STORES.get(key)
        if found is not None:
            return found
        created = object.__new__(cls)
        _STORES[key] = created
        return created

    def __init__(self, state_root: Optional[str] = None) -> None:
        if getattr(self, "_ready", False):
            return
        self._ready = True
        self._service = SettingsService(state_root=state_root)
        self._pieces: Optional[Tuple[SavedPiece, ...]] = None
        self._listeners: List[Callable[[], None]] = []

    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Call ``listener`` after every replace. The return value unsubscribes."""
        self._listeners.append(listener)

        def stop() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return stop

    def load(self) -> Tuple[SavedPiece, ...]:
        if self._pieces is None:
            try:
                self._pieces = pieces_from_payload(self._service.load_global())
            except OSError:
                self._pieces = ()
        return self._pieces

    def replace(self, pieces: Sequence[SavedPiece]) -> None:
        stored = tuple(pieces)
        self._pieces = stored
        try:
            self._service.update_global(lambda payload: payload_with_pieces(payload, stored))
        except OSError:
            return
        for listener in tuple(self._listeners):
            listener()


def _visible_base(fragment: Fragment) -> str:
    widget = _first_widget(fragment.nodes[0])
    shown = _visible_text(widget) if widget is not None else ""
    if shown:
        return shown
    lines = [line for line in plain_names(fragment).splitlines() if line]
    return lines[0] if lines else _FALLBACK_NAME


def _first_widget(spec: NodeSpec) -> Optional[NodeSpec]:
    if spec.kind == "widget":
        return spec
    for _slot, kids in spec.slots:
        for child in kids:
            found = _first_widget(child)
            if found is not None:
                return found
    return None


def _visible_text(spec: NodeSpec) -> str:
    for entry in spec.properties:
        if entry.name not in ("text", "title", "windowTitle"):
            continue
        text = getattr(entry.value, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()
    return ""


def _piece(item: object) -> Optional[SavedPiece]:
    if not isinstance(item, Mapping):
        return None
    name = item.get("name")
    xml = item.get("xml")
    if not isinstance(name, str) or not name.strip():
        return None
    if not isinstance(xml, str) or not xml.strip():
        return None
    try:
        fragment = read_fragment(xml)
    except UiReadError:
        return None
    if not fragment.nodes:
        return None
    return SavedPiece(name.strip(), xml)
