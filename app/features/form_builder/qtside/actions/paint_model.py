"""What the menu-edit canvas layer draws, in form pixels. Qt-free and hashable."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

#: Item kinds. ``hint`` is a "Type here" box, ``box`` an open menu's panel, ``row`` an entry,
#: ``separator`` a rule, ``edit`` the in-place editor, ``reuse`` a row of the reuse list,
#: ``caption`` the mnemonic caption under the editor, ``drop`` the landing line of a drag (``ov.menu_drop``).
KINDS = ("hint", "box", "row", "separator", "edit", "reuse", "caption", "drop")

ROW_HEIGHT = 24
MIN_MENU_WIDTH = 180
HINT_MIN_WIDTH = 64
HINT_MIN_HEIGHT = 20


@dataclass(frozen=True)
class PaintItem:
    kind: str
    x: int
    y: int
    width: int
    height: int
    text: str = ""
    extra: str = ""
    focused: bool = False
    opens: bool = False
    current: bool = False
    selected: bool = False


@dataclass(frozen=True)
class PaintState:
    items: Tuple[PaintItem, ...] = ()
