"""Where a dragged title, entry, toolbar button or action would land (UX-MAIN-009). Qt-free.

The glue measures every bar, toolbar and open menu into ``HostMap`` values (form
pixels). ``resolve`` picks the one under the pointer and the place in it, and words
the status sentence. The landing place is a line, never a tint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.hit_index import Rect

OUTSIDE = "Drop it on a menu or a toolbar."
LINE = 2


@dataclass(frozen=True)
class EntryBox:
    ref: NodeId
    kind: str  # action, menu, separator
    text: str
    rect: Rect
    #: The action or the menu behind the reference.
    target: Optional[NodeId] = None
    name: str = ""


@dataclass(frozen=True)
class HostMap:
    host: NodeId
    kind: str  # bar, menu, toolbar
    #: ``the File menu`` or ``Main toolbar``: the place in a sentence.
    place: str
    horizontal: bool
    rect: Rect
    entries: Tuple[EntryBox, ...]


@dataclass(frozen=True)
class Source:
    #: title, entry, button (a reference being moved) or action (from the Actions section).
    kind: str
    text: str
    ref: Optional[NodeId] = None
    #: Action names for ``action``; the single name of the moved reference otherwise.
    names: Tuple[str, ...] = ()
    copy: bool = False


@dataclass(frozen=True)
class Landing:
    host: NodeId
    index: int
    line: Rect
    sentence: str
    #: A closed title under the pointer: hovering it opens it.
    open_menu: Optional[NodeId] = None
    place: str = ""


def _inside(rect: Rect, point: Tuple[int, int]) -> bool:
    return rect.x <= point[0] < rect.x + rect.width and rect.y <= point[1] < rect.y + rect.height


def _mid(rect: Rect, horizontal: bool) -> float:
    return rect.x + rect.width / 2.0 if horizontal else rect.y + rect.height / 2.0


def host_at(maps: Sequence[HostMap], point: Tuple[int, int]) -> Optional[HostMap]:
    """The topmost map under ``point``: open menus first (later maps are drawn over earlier ones)."""
    for found in reversed(maps):
        if _inside(found.rect, point):
            return found
    return None


def resolve(maps: Sequence[HostMap], point: Tuple[int, int], source: Source) -> Optional[Landing]:
    found = host_at(maps, point)
    if found is None:
        return None
    axis = point[0] if found.horizontal else point[1]
    index = 0
    for number, entry in enumerate(found.entries):
        if axis >= _mid(entry.rect, found.horizontal):
            index = number + 1
    names = [entry.text for entry in found.entries]
    # A closed menu title under the pointer, with an entry or an action in hand: drop at the end of that menu.
    if found.kind == "bar" and source.kind in ("entry", "action", "button"):
        under = next((entry for entry in found.entries if entry.kind == "menu" and _inside(entry.rect, point)), None)
        if under is not None and under.target is not None:
            line = Rect(under.rect.x, under.rect.y + under.rect.height - LINE, under.rect.width, LINE)
            return Landing(
                under.target,
                -1,
                line,
                "Put %s in the %s menu" % (source.text, under.text),
                open_menu=under.target,
                place="the %s menu" % under.text,
            )
    line = _line(found, index)
    return Landing(found.host, index, line, _sentence(source, found, index, names), place=found.place)


def _line(found: HostMap, index: int) -> Rect:
    entries = found.entries
    if found.horizontal:
        if not entries:
            return Rect(found.rect.x + 2, found.rect.y + 2, LINE, max(4, found.rect.height - 4))
        if index < len(entries):
            x = entries[index].rect.x - 1
            box = entries[index].rect
        else:
            box = entries[-1].rect
            x = box.x + box.width + 1
        return Rect(x, box.y, LINE, box.height)
    if not entries:
        return Rect(found.rect.x + 2, found.rect.y + 2, max(4, found.rect.width - 4), LINE)
    if index < len(entries):
        y = entries[index].rect.y - 1
        box = entries[index].rect
    else:
        box = entries[-1].rect
        y = box.y + box.height - 1
    return Rect(found.rect.x + 2, y, max(4, found.rect.width - 4), LINE)


def _sentence(source: Source, found: HostMap, index: int, names: Sequence[str]) -> str:
    verb = "Add" if source.copy else "Put"
    if not names:
        return "%s %s in %s" % (verb, source.text, found.place)
    if index == 0:
        return "%s %s at the start of %s" % (verb, source.text, found.place)
    after = names[index - 1] or "the separator"
    return "%s %s after %s in %s" % (verb, source.text, after, found.place)
