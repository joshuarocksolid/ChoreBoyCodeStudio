"""Shows logic badges and connection arrows on each design canvas (UX-ARR-001 .. 005).

``OverlayModes`` owns the F4 rubber-band layer and hides it on close. This
host owns the two layers close must not touch. Show all is a flag on the host.
Closing the form tab drops the host. Closing F4 does not clear the flag.
"""

from __future__ import annotations

from typing import Any, Optional, Tuple

from app.features.form_builder.engine.events import PRIORITY_VIEWS
from app.features.form_builder.engine.logic.events import read_events
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.integration.overlay_ext.connections import choose_step
from app.features.form_builder.qtside.canvas.layers.connections import (
    ARROWS,
    ArrowState,
    drawable_steps,
    mark_at,
)
from app.features.form_builder.qtside.canvas.layers.logic_badges import NAME as BADGES
from app.features.form_builder.qtside.canvas.layers.logic_badges import mark_at as badge_at
from app.features.form_builder.qtside.canvas.layers.logic_badges import tip_at
from app.features.form_builder.qtside.inspector.pane import TabId
from app.qt.QtCore import QEvent, QObject, Qt, QTimer
from app.qt.QtGui import QKeyEvent, QMouseEvent
from app.qt.qt_compat import enum_value, event_pos

SHOW_ALL = "Showing all %d connections. Ctrl+Shift+L hides them."
REMOVE = "Remove this step from the Behavior tab."


def layer_plan(
    design: bool,
    overlay: str,
    behavior: bool,
    show_all: bool,
    has_events: bool,
) -> Tuple[bool, Optional[str]]:
    """``(badges on, arrow scope or None)``.

    Badges show in Design when no overlay is open. Scope ``all`` wins over the
    Behavior tab. A different overlay hides badges and, unless Show all is on,
    hides arrows too.
    """
    if not design or not has_events:
        return False, None
    badges = overlay == ""
    if show_all or overlay == "connections":
        return badges, "all"
    if behavior and overlay == "":
        return badges, "selected"
    return badges, None


_SURFACE_WAITS = 20


def links_for(surface: Any) -> Optional["ConnectionHost"]:
    canvas = getattr(getattr(surface, "workbench", None), "canvas", None)
    host = getattr(canvas, "_cbcs_connection_links", None)
    if isinstance(host, ConnectionHost):
        return host
    return None


def register(slots: Any) -> None:
    slots.on_workbench(attach, module=__name__)


def attach(workbench: Any) -> None:
    host = ConnectionHost(workbench)
    workbench.canvas._cbcs_connection_links = host
    QTimer.singleShot(0, host, host.sync)


class ConnectionHost(QObject):
    """Per canvas. The Show all flag is not written to the document."""

    def __init__(self, workbench: Any) -> None:
        super().__init__(workbench)
        self._workbench = workbench
        self._show_all = False
        self._hover: Optional[Tuple[str, str, int]] = None
        self._aimed: Optional[Tuple[str, str, int]] = None
        self._wired = False
        self._log_sub: object = None
        self._waits = 0
        self._canvas: Optional[QObject] = None
        self._viewport: Optional[QObject] = None

    @property
    def show_all(self) -> bool:
        return self._show_all

    def toggle_show_all(self) -> None:
        self._show_all = not self._show_all
        self.sync()

    def _announce(self) -> None:
        """The Show all sentence survives a selection change, which clears narrate()."""
        surface = _surface(self._workbench)
        if surface is None or getattr(surface._modes, "active", ""):
            return
        if self._show_all:
            count = len(drawable_steps(self._workbench._session.document))
            surface.set_overlay_status(SHOW_ALL % count)
        else:
            surface.set_overlay_status("")

    def sync(self, *_ignored: object) -> None:
        workbench = self._workbench
        surface = _surface(workbench)
        if surface is None or not hasattr(surface, "_modes"):
            # A workbench without a surface (inspector-only hosts) never gets one; stop asking.
            self._waits += 1
            if self._waits <= _SURFACE_WAITS:
                QTimer.singleShot(0, self, self.sync)
            return
        self._wire(surface)
        canvas = workbench.canvas
        badges, scope = layer_plan(
            bool(surface.can_use_overlays()),
            str(getattr(surface._modes, "active", "") or ""),
            _behavior(workbench),
            self._show_all,
            bool(read_events(workbench._session.document)),
        )
        if badges:
            canvas.show_layer(BADGES, True)
        else:
            canvas.hide_layer(BADGES)
        if scope is None:
            canvas.hide_layer(ARROWS)
        else:
            canvas.show_layer(ARROWS, ArrowState(scope, self._hover))
        self._announce()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        # Qt also calls this while the canvas is being torn down: look only at
        # mouse and key events, and compare against the objects stored when the
        # filter was installed instead of asking the canvas for them.
        if isinstance(event, QMouseEvent):
            if watched is not self._viewport:
                return False
            kind = enum_value(event.type())
            types = getattr(QEvent, "Type", QEvent)
            if kind in (enum_value(types.MouseButtonPress), enum_value(types.MouseButtonDblClick)):
                return self._press(event, kind == enum_value(types.MouseButtonDblClick))
            if kind == enum_value(types.MouseMove):
                self._hover_at(event)
            return False
        if isinstance(event, QKeyEvent) and watched is self._canvas:
            types = getattr(QEvent, "Type", QEvent)
            if enum_value(event.type()) == enum_value(types.KeyPress):
                return self._key(event)
        return False

    def _wire(self, surface: Any) -> None:
        if self._wired:
            return
        self._wired = True
        canvas = self._workbench.canvas
        self._canvas = canvas
        self._viewport = canvas.viewport()
        canvas.installEventFilter(self)
        self._viewport.installEventFilter(self)
        self._workbench.inspector.tabs.currentChanged.connect(self.sync)
        subscription = self._workbench._session.log.subscribe(self.sync, priority=PRIORITY_VIEWS + 1)
        self._log_sub = subscription
        self._workbench.destroyed.connect(lambda *_: subscription.close())
        toolbar = getattr(surface, "_toolbar", None)
        if toolbar is None:
            return
        for button in (getattr(toolbar, "tab_order", None), getattr(toolbar, "buddies", None)):
            if button is not None:
                button.toggled.connect(self.sync)
        for button in getattr(toolbar, "overlay_toggles", {}).values():
            button.toggled.connect(self.sync)

    def _press(self, event: QMouseEvent, double: bool) -> bool:
        point = self._scene(event)
        if point is None:
            return False
        items = self._workbench.canvas.overlay().items
        badge = badge_at(items, point[0], point[1])
        if badge:
            self._select(badge)
            self._workbench.focus_inspector_tab(TabId.BEHAVIOR)
            return True
        found = mark_at(items, point[0], point[1])
        if found is None or not found.sender:
            return False
        self._select(found.sender)
        self._aimed = (found.sender, found.signal, found.index)
        if double and found.kind == "arrow":
            self._edit(found.sender, found.signal, found.index)
        return True

    def _hover_at(self, event: QMouseEvent) -> None:
        point = self._scene(event)
        if point is None:
            return
        items = self._workbench.canvas.overlay().items
        tip = tip_at(items, point[0], point[1])
        found = mark_at(items, point[0], point[1])
        hover = (found.sender, found.signal, found.index) if found is not None and found.kind == "arrow" else None
        if hover != self._hover:
            self._hover = hover
            self.sync()
        text = tip
        if found is not None and found.kind == "arrow":
            text = "When %s is connected. Click to select. Remove the step from the Behavior tab." % found.sender
        viewport = self._workbench.canvas.viewport()
        if viewport.toolTip() != text:
            viewport.setToolTip(text)

    def _key(self, event: QKeyEvent) -> bool:
        key = enum_value(event.key())
        delete = enum_value(Qt.Key.Key_Delete)
        backspace = enum_value(Qt.Key.Key_Backspace)
        if self._aimed is None or key not in (delete, backspace):
            return False
        surface = _surface(self._workbench)
        if surface is not None:
            surface.narrate(REMOVE)
        return True

    def _select(self, name: str) -> None:
        document = self._workbench._session.document
        found = document.by_name(name)
        if not found:
            return
        self._workbench._session.selection.set((found[0],), current=found[0], source=SelectionSource.CANVAS)

    def _edit(self, sender: str, signal: str, index: int) -> None:
        del signal, index
        surface = _surface(self._workbench)
        document = self._workbench._session.document
        found = document.by_name(sender)
        if surface is None or not found:
            return
        choose_step(surface, found[0], found[0])

    def _scene(self, event: QMouseEvent) -> Optional[Tuple[float, float]]:
        point = event_pos(event)
        if point is None:
            return None
        scene = self._workbench.canvas.mapToScene(point)
        return (scene.x(), scene.y())


def _surface(workbench: Any) -> Any:
    widget = workbench
    while widget is not None:
        if hasattr(widget, "toggle_overlay") and hasattr(widget, "can_use_overlays"):
            return widget
        widget = widget.parent()
    return None


def _behavior(workbench: Any) -> bool:
    tabs = workbench.inspector.tabs
    return tabs.tabText(tabs.currentIndex()).startswith("Behavior")
