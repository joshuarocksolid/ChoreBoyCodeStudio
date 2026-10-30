"""Form menu contributors (UX-M5-010).

A lane adds a Form menu item by adding a module here. Modules are discovered
in sorted name order and each exposes ``register(registry)``, which calls
``registry.add(FormMenuItem(...))``. A module whose name starts with an
underscore is a helper and is not imported. Contributors never edit
``form_menu.py``.

Order (deterministic, from UX-M5-010):

* The top-level titles in ``TOP_LEVEL`` come in that order, with a separator
  where the group letter changes. A title not in the table goes after the
  table, sorted by title. Titles are the words on screen, so two modules that
  use ``("Overlays", ...)`` share one submenu.
* Inside a submenu, items sort by ``(rank, module name, registration order)``.
  The command table's own rows have ranks 0, 1, 2 ... so a contributor with
  the default rank (1000) comes after them. Give a smaller rank to go earlier.
* A contributor item whose ``command_id`` is also a Form menu row of the
  command table replaces that row (Form settings, for example). It can never
  replace a shell action: an id in the ``shell.`` namespace is refused here,
  and an id the shell already registered is logged and left out of the menu.

Items a runtime can't offer are absent, not disabled: ``offered(surface)`` is
asked each time the menu opens, and a ``False`` hides the item, its empty
submenu and any separator left with nothing beside it. ``enabled(surface)``
greys an offered item. ``target="help"`` puts the item at the end of the
shell's Help menu instead; its ``offered`` then receives ``None`` when no form
tab is active.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Callable, Dict, Generic, List, Optional, Sequence, Tuple, TypeVar

from app.features.form_builder.engine.contributors import run_contributors

logger = logging.getLogger(__name__)

FORM = "form"
HELP = "help"

#: ``(title, group)``. A separator sits where the group letter changes.
TOP_LEVEL: Tuple[Tuple[str, str], ...] = (
    ("Insert widget…", "a"),
    ("Go to widget…", "a"),
    ("Add event…", "a"),
    ("Go to code", "a"),
    ("Layout", "a"),
    ("Size", "a"),
    ("Main window", "a"),
    ("Overlays", "a"),
    ("Preview", "b"),
    ("Preview options", "b"),
    ("View Python code", "b"),
    ("View XML", "b"),
    ("Style sheet of the form…", "c"),
    ("Form settings…", "c"),
    ("Save as template…", "c"),
    ("Save image…", "c"),
    ("Print…", "c"),
    ("Create window class…", "c"),
    # The editing commands that were in the menu before M5.
    ("Select all", "d"),
    ("Change text", "d"),
    ("Zoom to fit", "d"),
    ("Zoom in", "d"),
    ("Zoom out", "d"),
    ("Zoom 100%", "d"),
)

DEFAULT_RANK = 1000

_SLOT: Dict[str, int] = {title: index for index, (title, _group) in enumerate(TOP_LEVEL)}
_GROUP: Dict[str, str] = dict(TOP_LEVEL)


def _always(_surface: Any) -> bool:
    return True


@dataclass(frozen=True)
class FormMenuItem:
    """One leaf of the Form menu.

    ``path`` is the titles from the top: ``("Main window", "Add toolbar")``.
    ``run`` receives the active ``FormSurface``. ``hint`` is key text shown in
    the item (the key itself is registered through ``keys_ext``).
    """

    command_id: str
    path: Tuple[str, ...]
    run: Callable[[Any], None]
    hint: str = ""
    rank: int = DEFAULT_RANK
    offered: Callable[[Any], bool] = _always
    enabled: Callable[[Any], bool] = _always
    target: str = FORM

    def __post_init__(self) -> None:
        if not self.command_id or self.command_id.startswith("shell."):
            raise ValueError("%r is not a form menu id; shell ids belong to the shell" % (self.command_id,))
        if not self.path or not all(self.path):
            raise ValueError("a menu item needs a path of non-empty titles")
        if self.target not in (FORM, HELP):
            raise ValueError("unknown menu target %r; use %r or %r" % (self.target, FORM, HELP))


class FormMenuRegistry:
    """Contributed items in registration order."""

    def __init__(self) -> None:
        self._items: List[Tuple[str, FormMenuItem]] = []

    def add(self, item: FormMenuItem, *, module: str = "") -> None:
        if any(other.command_id == item.command_id for _name, other in self._items):
            raise ValueError("form menu item %s is already registered" % item.command_id)
        self._items.append((module, item))

    def scope(self, module: str) -> "_ModuleScope":
        return _ModuleScope(self, module)

    def items(self, target: str = FORM) -> Tuple[Tuple[str, FormMenuItem], ...]:
        """``(module name, item)`` pairs for one target, in registration order."""
        return tuple(pair for pair in self._items if pair[1].target == target)


class _ModuleScope:
    def __init__(self, registry: FormMenuRegistry, module: str) -> None:
        self._registry = registry
        self._module = module

    def add(self, item: FormMenuItem) -> None:
        self._registry.add(item, module=self._module)


def load_form_menu_contributors(*packages: ModuleType) -> FormMenuRegistry:
    """Import each public module of ``packages`` in sorted name order and call its ``register``.

    A module that fails to import or register is logged and skipped, so one
    lane's mistake never removes the Form menu.
    """
    registry = FormMenuRegistry()
    run_contributors("form menu", packages, "register", lambda module, hook: hook(registry.scope(module.__name__)))
    return registry


_DEFAULT: Optional[FormMenuRegistry] = None


def default_registry() -> FormMenuRegistry:
    """The registry of this package's contributors, loaded once."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = load_form_menu_contributors(sys.modules[__name__])
    return _DEFAULT


P = TypeVar("P")


@dataclass(frozen=True)
class MenuEntry(Generic[P]):
    """A leaf to place: its path, its rank, who added it and what it is."""

    path: Tuple[str, ...]
    rank: int
    module: str
    payload: P


@dataclass(frozen=True)
class MenuNode(Generic[P]):
    """The planned menu: a ``leaf`` has an ``entry``, a ``submenu`` has ``children``, a ``separator`` neither."""

    kind: str
    title: str = ""
    entry: Optional[MenuEntry[P]] = None
    children: Tuple["MenuNode[P]", ...] = ()


def plan_menu(entries: Sequence[MenuEntry[P]]) -> Tuple[MenuNode[P], ...]:
    """Order ``entries`` into the menu tree described in the module docstring."""
    numbered = [(index, entry) for index, entry in enumerate(entries)]
    titles: List[str] = []
    for _index, entry in numbered:
        if entry.path[0] not in titles:
            titles.append(entry.path[0])
    titles.sort(key=lambda title: (_SLOT.get(title, len(TOP_LEVEL)), title if title not in _SLOT else ""))
    nodes: List[MenuNode[P]] = []
    previous = ""
    for title in titles:
        group = _GROUP.get(title, "z")
        if previous and group != previous:
            nodes.append(MenuNode("separator"))
        previous = group
        mine = [(index, entry) for index, entry in numbered if entry.path[0] == title]
        nodes.append(_node(title, mine, 1))
    return tuple(nodes)


def _node(title: str, mine: Sequence[Tuple[int, MenuEntry[P]]], depth: int) -> MenuNode[P]:
    if len(mine) == 1 and len(mine[0][1].path) == depth:
        return MenuNode("leaf", title, mine[0][1])
    ordered = sorted(mine, key=lambda pair: (pair[1].rank, pair[1].module, pair[0]))
    seen: List[str] = []
    for _index, entry in ordered:
        if len(entry.path) > depth and entry.path[depth] not in seen:
            seen.append(entry.path[depth])
    children = []
    for child in seen:
        group = [pair for pair in ordered if len(pair[1].path) > depth and pair[1].path[depth] == child]
        children.append(_node(child, group, depth + 1))
    return MenuNode("submenu", title, None, tuple(children))


__all__: Sequence[str] = [
    "DEFAULT_RANK",
    "FORM",
    "HELP",
    "TOP_LEVEL",
    "FormMenuItem",
    "FormMenuRegistry",
    "MenuEntry",
    "MenuNode",
    "default_registry",
    "load_form_menu_contributors",
    "plan_menu",
]
