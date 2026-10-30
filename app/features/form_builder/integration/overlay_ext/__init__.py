"""Overlay kinds (UX-OVL-001 .. 003, UX-ARR-006 .. 008, CONTRACTS.md section 1.4, M6.0s).

Tab order and Buddies keep their code in ``integration/overlays.py``. Any
other overlay is a kind registered here: a lane adds a module, discovered in
sorted name order (a name starting with ``_`` is a helper), that exposes
``register(registry)`` and calls ``registry.add(OverlayKind(...))``. It edits
no shared file. The overlay host (``OverlayModes``) then gives the kind the
same life as the built-in two: one overlay open at a time, the banner with
its Done button, Esc, F3, close on a structural change or a tab switch, and
the toolbar toggle.

An ``OverlayKind`` has:

* ``kind``: the id passed to ``open_overlay`` / ``toggle_overlay`` (``"connections"``).
* ``title`` and ``banner_text``: the banner's name and sentence; ``glyph`` is the
  banner glyph key (default: the kind id).
* ``layer``: the canvas layer name (``qtside/canvas/layers/``, M5.0s) shown while the
  overlay is open. ``state(view)`` builds the layer's (hashable) state from a
  ``LinkView``; the default passes the view itself.
* ``toggle``: ``ToggleSpec(label, tooltip)`` for a toolbar button after Buddies,
  or None. The button shows ``glyph`` beside its text, and the glyph alone when
  the toolbar is compact. An unknown glyph name leaves the text in place.
* ``banner_action``: ``(label, run(surface))`` for the banner's extra button, or None.
* ``link``: a ``LinkGesture``, or None for an overlay with no link.

The **link gesture** is the generic "from a widget to a widget or the form".
Press-drag: a left press on a widget (``can_start``) and a drag to another
widget; the widget under the pointer is the candidate; releasing on the page
background means the form; a release on a layout or a spacer means its owning
widget (UX D23); releasing on the sender itself means the sender. Esc during
the drag cancels. Keyboard (UX-ARR-008): Enter on the selected widget starts a
link from it; arrows and Tab select the receiver as usual; Home selects the
form; Enter ends the link; Esc cancels it (a second Esc closes the overlay). Both
end in ``link.link(surface, source, target)`` with two node ids (``target`` is
the root widget's id for the form). Nothing is written before that call, so
cancelling leaves bytes and the undo stack alone. ``link.start_status(name)`` and
``link.hover_status(name)`` are the status sentences; both are optional.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Callable, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.contributors import run_contributors
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LinkView:
    """The link gesture's state, for the layer: ``source`` is None while no link is started."""

    source: Optional[NodeId] = None
    candidate: Optional[NodeId] = None
    pointer: Optional[Tuple[int, int]] = None
    dragging: bool = False


@dataclass(frozen=True)
class ToggleSpec:
    label: str
    tooltip: str


def starts_link(document: UiDocument, node: Optional[NodeId]) -> bool:
    """A press on a widget starts a link; a press on a spacer, a layout, the page background or nothing starts none."""
    return node is not None and node != document.root.id and isinstance(document.get(node), WidgetNode)


def owning_widget(document: UiDocument, node: Optional[NodeId]) -> NodeId:
    """The widget a drop on ``node`` means: the node itself when it is a widget, the widget that
    owns a layout or spacer (UX D23), and the form for the page background."""
    root = document.root.id
    current = node
    while current is not None:
        found = document.get(current)
        if isinstance(found, WidgetNode):
            return current
        parent = document.parent(current)
        current = None if parent is None else parent.id
    return root


def _same(view: LinkView) -> LinkView:
    return view


@dataclass(frozen=True)
class LinkGesture:
    link: Callable[[Any, NodeId, NodeId], None]
    can_start: Callable[[UiDocument, Optional[NodeId]], bool] = starts_link
    target_of: Callable[[UiDocument, Optional[NodeId]], NodeId] = owning_widget
    start_status: Optional[Callable[[str], str]] = None
    hover_status: Optional[Callable[[str], str]] = None


@dataclass(frozen=True)
class OverlayKind:
    kind: str
    title: str
    banner_text: str
    layer: str
    glyph: str = ""
    state: Callable[[LinkView], Any] = _same
    toggle: Optional[ToggleSpec] = None
    banner_action: Optional[Tuple[str, Callable[[Any], None]]] = None
    link: Optional[LinkGesture] = None

    def __post_init__(self) -> None:
        if not self.kind or not self.layer:
            raise ValueError("an overlay kind needs an id and a layer")
        if self.kind in ("tab_order", "buddies"):
            raise ValueError("%s is a built-in overlay" % self.kind)


class OverlayRegistry:
    def __init__(self) -> None:
        self._kinds: List[Tuple[str, OverlayKind]] = []

    def add(self, kind: OverlayKind, *, module: str = "") -> None:
        if any(found.kind == kind.kind for _module, found in self._kinds):
            raise ValueError("overlay kind %s is already registered" % kind.kind)
        self._kinds.append((module, kind))

    def scope(self, module: str) -> "_ModuleScope":
        return _ModuleScope(self, module)

    def kinds(self) -> Tuple[OverlayKind, ...]:
        return tuple(kind for _module, kind in self._kinds)

    def get(self, kind: str) -> Optional[OverlayKind]:
        for _module, found in self._kinds:
            if found.kind == kind:
                return found
        return None


class _ModuleScope:
    def __init__(self, registry: OverlayRegistry, module: str) -> None:
        self._registry = registry
        self._module = module

    def add(self, kind: OverlayKind) -> None:
        self._registry.add(kind, module=self._module)


def load_overlay_kinds(*packages: ModuleType) -> OverlayRegistry:
    registry = OverlayRegistry()
    run_contributors("overlay kind", packages, "register", lambda module, hook: hook(registry.scope(module.__name__)))
    return registry


_DEFAULT: Optional[OverlayRegistry] = None


def default_registry() -> OverlayRegistry:
    """This package's overlay kinds, loaded once."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = load_overlay_kinds(sys.modules[__name__])
    return _DEFAULT


__all__: Sequence[str] = [
    "LinkGesture",
    "LinkView",
    "OverlayKind",
    "OverlayRegistry",
    "ToggleSpec",
    "default_registry",
    "load_overlay_kinds",
    "owning_widget",
    "starts_link",
]
