"""Shows logic badges and connection arrows on each design canvas (UX-ARR-001 .. 005).

``OverlayModes`` owns the F4 rubber-band layer and hides it on close. This
host owns the two layers close must not touch. Show all is a flag on the host.
Closing the form tab drops the host. Closing F4 does not clear the flag.
"""

from __future__ import annotations

from typing import Any, Optional, Tuple

from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
from app.features.form_builder.engine.events import PRIORITY_VIEWS
from app.features.form_builder.engine.logic.compat import split_signature
from app.features.form_builder.engine.logic.events import read_event, read_events
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.integration.overlay_ext.connections import arrow_status, code_status, step_sentence, window_file
from app.features.form_builder.qtside.canvas.layers.connections import (
    ARROWS,
    ArrowState,
    drawable_steps,
    mark_at,
)
from app.features.form_builder.qtside.canvas.layers.feeds import NAME as FEEDS
from app.features.form_builder.qtside.canvas.layers.feeds import form_has_rules
from app.features.form_builder.qtside.canvas.layers.logic_badges import NAME as BADGES
from app.features.form_builder.qtside.canvas.layers.logic_badges import mark_at as badge_at
from app.features.form_builder.qtside.canvas.layers.logic_badges import tip_at
from app.features.form_builder.qtside.inspector import TabId
from app.qt.QtCore import QEvent, QObject, Qt, QTimer
from app.qt.QtGui import QKeyEvent, QMouseEvent
from app.qt.qt_compat import enum_value, event_pos

SHOW_ALL = "Showing all %d connections. Ctrl+Shift+L hides them."


def _pointer(viewport: Optional[QObject], event: QMouseEvent) -> object:
    pos = event_pos(event)
    if viewport is None or pos is None or not hasattr(viewport, "mapToGlobal"):
        return None
    return viewport.mapToGlobal(pos)


def layer_plan(
    design: bool,
    overlay: str,
    behavior: bool,
    show_all: bool,
    has_events: bool,
    has_rules: bool = False,
) -> Tuple[bool, Optional[str]]:
    """``(badges on, arrow scope or None)``.

    Badges show in Design when no overlay is open. Scope ``all`` wins over the
    Behavior tab. Tab order and Buddies hide arrows even when Show all is on,
    so those clicks are not stolen. Any other overlay hides arrows unless
    Show all is on. A form with rules and no events uses the same scope.
    """
    if not design or not (has_events or has_rules):
        return False, None
    if overlay in ("tab_order", "buddies"):
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
        self._swallow_delete = False
        self._said = False

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
        document = workbench._session.document
        has_rules = form_has_rules(document)
        badges, scope = layer_plan(
            bool(surface.can_use_overlays()),
            str(getattr(surface._modes, "active", "") or ""),
            _behavior(workbench),
            self._show_all,
            bool(read_events(document)),
            has_rules,
        )
        if badges:
            canvas.show_layer(BADGES, True)
        else:
            canvas.hide_layer(BADGES)
        if scope is None:
            canvas.hide_layer(ARROWS)
        else:
            canvas.show_layer(ARROWS, ArrowState(scope, self._hover, self._aimed))
        if scope is not None and has_rules:
            canvas.show_layer(FEEDS, scope)
        else:
            canvas.hide_layer(FEEDS)
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
            kind = enum_value(event.type())
            if kind == enum_value(types.ShortcutOverride):
                return self._override(event)
            if kind == enum_value(types.KeyPress):
                return self._key(event)
        return False

    def _wire(self, surface: Any) -> None:
        if self._wired:
            return
        self._wired = True
        canvas = self._workbench.canvas
        self._canvas = canvas
        viewport = canvas.viewport()
        self._viewport = viewport
        canvas.installEventFilter(self)
        if viewport is not None:
            viewport.installEventFilter(self)
        self._workbench.inspector.tabs.currentChanged.connect(self.sync)
        session = self._workbench._session
        subscription = session.log.subscribe(self._on_log, priority=PRIORITY_VIEWS + 1)
        self._log_sub = subscription
        selection = session.selection.subscribe(self._on_selection)
        self._workbench.destroyed.connect(lambda *_: subscription.close())
        self._workbench.destroyed.connect(lambda *_: selection())
        toolbar = getattr(surface, "_toolbar", None)
        if toolbar is None:
            return
        for button in (getattr(toolbar, "tab_order", None), getattr(toolbar, "buddies", None)):
            if button is not None:
                button.toggled.connect(self.sync)
        for button in getattr(toolbar, "overlay_toggles", {}).values():
            button.toggled.connect(self.sync)

    def _on_log(self, *_ignored: object) -> None:
        self._aimed = None
        self.sync()

    def _on_selection(self, _change: object) -> None:
        self._aimed = None

    def _overlay(self) -> str:
        surface = _surface(self._workbench)
        return str(getattr(getattr(surface, "_modes", None), "active", "") or "")

    def _press(self, event: QMouseEvent, double: bool) -> bool:
        self._swallow_delete = False
        if self._overlay() in ("tab_order", "buddies"):
            self._aimed = None
            return False
        point = self._scene(event)
        if point is None:
            return False
        # A press on a widget body starts the F4 link. Arrows are hit only in the gaps.
        if self._overlay() == "connections" and self._on_widget(event):
            self._aimed = None
            return False
        items = self._workbench.canvas.overlay().items
        badge = badge_at(items, point[0], point[1])
        if badge:
            self._aimed = None
            self._select(badge)
            self._workbench.focus_inspector_tab(TabId.BEHAVIOR)
            return True
        found = mark_at(items, point[0], point[1])
        if found is None or not found.sender:
            if self._aimed is not None:
                self._aimed = None
                self.sync()
            return False
        self._select(found.sender)
        self._aimed = (found.sender, found.signal, found.index)
        self.sync()
        if not double and found.kind == "code":
            self._go_chip(found)
            return True
        if double and found.kind == "arrow":
            self._open_step(found, event)
        return True

    def _open_step(self, found: Any, event: QMouseEvent) -> None:
        """Double-click an arrow: the step picker on that step, anchored at the pointer."""
        surface = _surface(self._workbench)
        if surface is None:
            return
        located = self._workbench._session.document.by_name(found.sender)
        if not located:
            return
        from app.features.form_builder.qtside.pickers import open_for_step

        open_for_step(surface, located[0], found.signal, found.index, at=_pointer(self._viewport, event))

    def _go_chip(self, found: Any) -> None:
        """A click on the { } chip opens the method the step calls."""
        from app.features.form_builder.integration.handlers import service

        surface = _surface(self._workbench)
        if surface is None:
            return
        document = self._workbench._session.document
        bare = split_signature(found.signal)[0]
        state = read_event(document, found.sender, bare)
        if found.index < 0 or found.index >= len(state.steps):
            return
        method = state.steps[found.index].method
        if method:
            service().go_to(surface, method)

    def _on_widget(self, event: QMouseEvent) -> bool:
        canvas = self._canvas
        if canvas is None or not hasattr(canvas, "node_at"):
            return False
        pos = event_pos(event)
        if pos is None:
            return False
        node = canvas.node_at(pos)
        document = self._workbench._session.document
        if node is None or node == document.root.id:
            return False
        return isinstance(document.get(node), WidgetNode)

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
        viewport = self._viewport
        if viewport is not None and viewport.toolTip() != tip:
            viewport.setToolTip(tip)
        if found is None or found.kind not in ("arrow", "code", "label"):
            if self._said:
                self._said = False
                self._unsay()
            return
        sentence = self._hover_sentence(found)
        if not sentence:
            return
        self._said = True
        self._say(sentence)

    def _hover_sentence(self, found: Any) -> str:
        surface = _surface(self._workbench)
        document = self._workbench._session.document
        if found.kind == "code":
            bare = split_signature(found.signal)[0]
            state = read_event(document, found.sender, bare)
            if found.index < 0 or found.index >= len(state.steps):
                return ""
            return code_status(state.steps[found.index].method, window_file(surface))
        return arrow_status(document, found.sender, found.signal, found.index)

    def _say(self, sentence: str) -> None:
        surface = _surface(self._workbench)
        if surface is None:
            return
        if self._overlay():
            surface.set_overlay_status(sentence)
        else:
            surface.narrate(sentence)

    def _unsay(self) -> None:
        surface = _surface(self._workbench)
        if surface is None:
            return
        modes = getattr(surface, "_modes", None)
        if self._overlay() and modes is not None:
            modes._announce()
        else:
            surface.narrate("")

    def _override(self, event: QKeyEvent) -> bool:
        if self._aimed is None or not _delete_key(event):
            return False
        event.accept()
        self._swallow_delete = True
        self._remove_aimed()
        return True

    def _key(self, event: QKeyEvent) -> bool:
        if self._swallow_delete and _delete_key(event):
            self._swallow_delete = False
            return True
        self._swallow_delete = False
        if self._aimed is not None and _delete_key(event):
            self._remove_aimed()
            return True
        self._aimed = None
        return False

    def _remove_aimed(self) -> None:
        aimed = self._aimed
        self._aimed = None
        if aimed is None:
            return
        sender, signal, index = aimed
        surface = _surface(self._workbench)
        if surface is None:
            return
        document = surface.session.document
        bare = split_signature(signal)[0]
        state = read_event(document, sender, bare)
        if index < 0 or index >= len(state.steps):
            return
        words = step_sentence(document, state.steps[index])
        kept = tuple(step for at, step in enumerate(state.steps) if at != index)
        surface.session.log.execute(SetEventSteps(sender, bare, kept, caption="Delete %s" % words))

    def _select(self, name: str) -> None:
        document = self._workbench._session.document
        found = document.by_name(name)
        if not found:
            return
        self._workbench._session.selection.set((found[0],), current=found[0], source=SelectionSource.CANVAS)

    def _scene(self, event: QMouseEvent) -> Optional[Tuple[float, float]]:
        point = event_pos(event)
        if point is None:
            return None
        scene = self._workbench.canvas.mapToScene(point)
        return (scene.x(), scene.y())


def _delete_key(event: QKeyEvent) -> bool:
    key = enum_value(event.key())
    return key in (enum_value(Qt.Key.Key_Delete), enum_value(Qt.Key.Key_Backspace))


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
