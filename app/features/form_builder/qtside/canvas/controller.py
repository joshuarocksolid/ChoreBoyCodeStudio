"""The canvas's imperative shell.

Public surface: ``handle``, ``post``, ``frame``, ``dispose``. What the canvas
decides lives in ``core.gesture.step`` and ``core.overlay.build_frame``.
"""

from __future__ import annotations

import math
import time
from dataclasses import replace
from typing import Callable, Dict, FrozenSet, Hashable, List, Optional, Protocol, Tuple, cast

from app.qt.QtCore import QEvent, QPoint, QPointF, QRect, Qt, QTimer
from app.qt.QtGui import QFont, QFontMetrics, QPixmap
from app.qt.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QGraphicsView,
    QMdiArea,
    QMdiSubWindow,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QToolBox,
    QWidget,
    QWizard,
)
from app.qt import QtWidgets
from app.qt.qt_compat import enum_value

from app.features.form_builder.engine.clipboard import dangling_sentence
from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import InsertFragment, InsertResult
from app.features.form_builder.engine.commands.catalog_ext.pages import InsertPage
from app.features.form_builder.engine.query.pages import (
    innermost_container,
    page_kind,
    page_title,
    pages,
    scroll_area_in_path,
    start_index,
)
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.commands.drop_plan import auto_target, indicate_preview
from app.features.form_builder.engine.sizing import chip_axis, project_axis
from app.features.form_builder.engine.diagnostics import Severity
from app.features.form_builder.engine.events import PRIORITY_VIEWS, ChangeSet
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.direct import KnobSet, Readout, Survey, knob_set, survey_scope
from app.features.form_builder.engine.query.drop_target import AcceptedDrop, DropPayload, NoDrop, RefusedDrop
from app.features.form_builder.engine.query.hit_index import GeoEntry, HitIndex, Rect
from app.features.form_builder.engine.query.selection import SelectionChange, SelectionSource, SelectionState
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import SizePolicyValue, SizeValue
from app.features.form_builder.qtside.canvas import _input
from app.features.form_builder.qtside.canvas.core.frame import (
    AddPage,
    Badge,
    Chip,
    FocusShare,
    OpenLayoutPopover,
    OpenProblem,
    OverlayFrame,
    ShowStacked,
    Stroke,
)
from app.features.form_builder.qtside.canvas.core.gesture import (
    CanvasPressed,
    CloseEditor,
    Commit,
    Cursor,
    DocumentChanged,
    Editing,
    EditorDone,
    Effect,
    EndPreview,
    Event,
    Focus,
    Gesture,
    HoverChanged,
    HostEvent,
    Idle,
    KEY_MERGE_S,
    Moving,
    Pressed,
    Key,
    Move,
    PlaceAsked,
    Placing,
    Narrate,
    Activate,
    OpenEditor,
    OpenItems,
    Press,
    Preview,
    PreviewPage,
    Reveal,
    RunChipAction,
    RevealInScroll,
    ScrollBy,
    ScrollContent,
    Select,
    ShowPageStep,
    Tip,
    Toggle,
    World,
    Zoom,
    no_claim,
    needs_fresh_geometry,
    previewing,
    step,
)
from app.features.form_builder.qtside.canvas.core.palette import tile_for
from app.features.form_builder.qtside.canvas.core.place import resolve_at
from app.features.form_builder.qtside.canvas.core.space import CanvasPoint, CanvasRect, FormPoint
from app.features.form_builder.qtside.canvas import layers as canvas_layers
from app.features.form_builder.qtside.canvas.core.overlay import (
    ActiveLayer,
    FrameInputs,
    StaticLayer,
    build_frame,
    build_static,
    frame_basis,
    shift_static,
)
from app.features.form_builder.qtside.canvas.core.space import ViewMap
from app.features.form_builder.qtside.canvas.core.structure import effective_selection
from app.features.form_builder.qtside.canvas.core.text import TextTarget, page_title_target, text_target
from app.features.form_builder.qtside.canvas.core.words import describe_selection, zoom_label
from app.features.form_builder.qtside.inspector.editors import default_catalog
from app.features.form_builder.qtside.sizing_live import class_default_policies, class_phrase
from app.features.form_builder.qtside.canvas.editor import InPlaceEditor
from app.features.form_builder.qtside.canvas.geometry import survey_live
from app.features.form_builder.qtside.canvas.stage import Stage, visible_scene_rect
from app.features.form_builder.qtside.realize.api import Realizer

# The canvas scrolls to reveal only for these sources. Its own CANVAS changes
# never re-scroll it. Keyboard navigation reveals through a Reveal effect.
REVEAL_SOURCES: FrozenSet[SelectionSource] = frozenset(
    {SelectionSource.OUTLINE, SelectionSource.PROGRAM, SelectionSource.UNDO}
)

# Detach must run before the realizer deletes a replaced root (priority 10).
PRIORITY_DETACH = 9

#: A knob's chip keeps its number this long after the commit lands.
READOUT_LINGER_MS = 600


class CanvasHost(Protocol):
    """What the canvas asks of the surface around it.

    ``qtside`` cannot import ``integration``, so the surface implements this.
    """

    def canvas_pressed(self) -> None:
        ...

    def narrate(self, sentence: str) -> None:
        ...

    def hover_changed(self, node: Optional[NodeId]) -> None:
        ...

    def zoom_changed(self, label: str) -> None:
        ...

    def open_problem(self, node: NodeId) -> None:
        ...

    def open_layout_popover(self, node: NodeId) -> None:
        ...

    def open_context_menu(self, node: Optional[NodeId], at: Optional[QPoint]) -> None:
        """``at`` is global. None places the menu beside the selection."""
        ...


def _enclosing_scroll_area(widget: QWidget) -> Optional[QScrollArea]:
    """The nearest scroll area above ``widget``, or None."""
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QScrollArea):
            return parent
        parent = parent.parentWidget()
    return None


class CanvasController:
    def __init__(
        self,
        view: QGraphicsView,
        session: FormSession,
        realizer: Realizer,
        index: HitIndex,
        stage: Stage,
        host: CanvasHost,
    ) -> None:
        self._view = view
        self._session = session
        self._realizer = realizer
        self._index = index
        self._stage = stage
        self._host = host
        self._gesture = Idle()
        self._static: Optional[StaticLayer] = None
        self._static_entries: Tuple[GeoEntry, ...] = ()
        self._frame = OverlayFrame(
            frame_basis(index, stage.view_map(), session.selection.state, 0),
            (),
            (),
            (),
        )
        self._frame_requested = False
        self._pending_reveal: Optional[NodeId] = None
        self._greeted = False
        self._reported_factor: Optional[float] = None
        self._serial = 0
        self._problems_revision = 0
        self._closed = False
        self._editor = InPlaceEditor(view.viewport(), realizer, self._on_editor_done)
        self._ghost: Optional[QPixmap] = None
        self._held_ghost: Optional[QPixmap] = None
        self._ghost_damage: Optional[CanvasRect] = None
        self._wide_prev: Tuple[CanvasRect, ...] = ()
        self._spring_id: Optional[NodeId] = None
        self._refused: Optional[str] = None
        self._refused_at = 0.0
        self._refused_open = False
        self._shown_page: Dict[NodeId, int] = {}
        self._mdi_cache: Optional[Tuple[object, int, Tuple[NodeId, ...]]] = None
        self._property_labels: Optional[Dict[str, str]] = None
        self._refusal_holders: List[QtWidgets.QLabel] = []
        self._preview_key: Optional[str] = None
        self._pending_edit: Optional[Commit] = None
        self._field_after_label: Optional[NodeId] = None
        self._pending_page: Optional[NodeId] = None
        self._queued_target: Optional[TextTarget] = None
        self._spring_flip: Optional[Tuple[NodeId, int]] = None
        self._tip = ""
        self._survey: Optional[Survey] = None
        self._knobs: Optional[Tuple[Survey, float, Rect, KnobSet]] = None
        self._site_key: Optional[tuple] = None
        self._sites: Optional[tuple] = None
        self._chip_metrics: Optional[QFontMetrics] = None
        self._chip_font_key: Optional[Tuple[str, int, int]] = None
        self._chip_widths: Dict[str, int] = {}
        self._readout: Optional[Readout] = None
        self._layer_states: Dict[str, Hashable] = {}
        self._layers: Tuple[ActiveLayer, ...] = ()
        self._linger = QTimer()
        self._linger.setSingleShot(True)
        self._linger.timeout.connect(self._end_readout)
        self._spring = QTimer()
        self._spring.setSingleShot(True)
        self._spring.timeout.connect(self._spring_fire)
        self._edge: Optional[Tuple[NodeId, int]] = None
        self._edge_repeat = False
        self._edge_timer = QTimer()
        self._edge_timer.setSingleShot(True)
        self._edge_timer.timeout.connect(self._edge_fire)
        self._detach_sub = session.log.subscribe(self._before_realize, priority=PRIORITY_DETACH)
        self._view_sub = session.log.subscribe(self._after_realize, priority=PRIORITY_VIEWS)
        self._selection_unsub = session.selection.subscribe(self._on_selection)
        self._diagnostics_unsub = session.diagnostics.subscribe(self._on_diagnostics)
        self._announce_selection(session.selection.state)
        self._request_frame()

    @property
    def frame(self) -> OverlayFrame:
        """The frame ``drawForeground`` paints. Immutable."""
        return self._frame

    def handle(self, event: QEvent) -> bool:
        """Every view and viewport event passes through here first."""
        if self._closed:
            return False
        if _input.is_frame_request(event):
            self._frame_requested = False
            self._pre_paint()
            return True
        if _input.is_resize(event):
            self._place_and_report()
            self._request_frame()
            return False
        first = not self._greeted
        translated = _input.translate(event, self._view, first)
        if translated is None:
            return False
        if isinstance(translated, Focus) and translated.gained:
            self._greeted = True
        return self._feed(translated)

    def post(self, event: HostEvent) -> None:
        """Zoom requests from the toolbar and hover from the outline."""
        if self._closed:
            return
        self._feed(event)

    def drag_node_ids(self) -> Tuple[NodeId, ...]:
        """Nodes a press or drag would move. Empty when the gesture is not a move."""
        gesture = self._gesture
        if isinstance(gesture, Pressed):
            gesture = gesture.on_drag
        if isinstance(gesture, Moving):
            return tuple(item.node for item in gesture.items)
        if isinstance(gesture, Placing):
            return tuple(gesture.payload.source_ids)
        return ()

    def abandon_drag(self) -> None:
        """Drop the in-progress move so another surface can take the pointer."""
        gesture = self._gesture
        active = gesture.on_drag if isinstance(gesture, Pressed) else gesture
        placing = gesture if isinstance(gesture, Placing) else active
        if isinstance(placing, Placing):
            self._fade(placing.payload.source_ids, 1.0)
        if previewing(gesture) or previewing(active):
            self._stage.run(EndPreview())
        self._ghost = None
        self._gesture = Idle()

    def dispose(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._spring.stop()
        self._linger.stop()
        self._edge_timer.stop()
        if isinstance(self._gesture, Placing):
            self._fade(self._gesture.payload.source_ids, 1.0)
        self._ghost = None
        if previewing(self._gesture):
            self._stage.run(EndPreview())
        self._editor.close(False)
        for holder in self._refusal_holders:
            holder.hide()
            holder.deleteLater()
        self._refusal_holders = []
        self._gesture = Idle()
        self._detach_sub.close()
        self._view_sub.close()
        self._selection_unsub()
        self._diagnostics_unsub()

    def _feed(self, event: Event) -> bool:
        if isinstance(event, Press) and isinstance(self._gesture, Editing):
            self._editor.commit_on_press()
        if needs_fresh_geometry(self._gesture, event):
            self._index.ensure_fresh()
            self._rebuild(static=self._static_stale())
        if _mints_token(self._gesture, event):
            self._serial += 1
        previous = self._gesture
        result = step(self._gesture, event, self._world())
        self._gesture = result.gesture
        steered = self._steer_outline(event)
        effects = result.effects
        if steered is not None:
            effects = tuple(effect for effect in effects if not isinstance(effect, Narrate)) + (Narrate(steered),)
        self._sync_drag(previous, self._gesture)
        self._tip_at(event)
        for effect in effects:
            self._run(effect)
        self._request_frame()
        return result.consumed

    def _world(self) -> World:
        current = effective_selection(self._session.document, self._session.selection.state).current
        widget = None if current is None else self._realizer.widget_for(current)
        defaults = class_default_policies(widget) if isinstance(widget, QWidget) else ("Preferred", "Preferred")
        return World(
            self._session.document,
            self._session.selection.state,
            self._index,
            self._stage.view_map(),
            self._frame,
            self._stage.page_minimum(),
            str(self._serial),
            defaults,
            self._claims(),
        )

    def _claims(self) -> Callable[[UiDocument, NodeId], Optional[str]]:
        """The host's double-click contributors (M6.0s). A host without them claims nothing."""
        found = getattr(self._host, "activation_claim", None)
        return found if callable(found) else no_claim

    def _run(self, effect: Effect) -> None:
        if isinstance(effect, Select):
            self._session.selection.set(effect.ids, current=effect.current, source=SelectionSource.CANVAS)
            return
        if isinstance(effect, Toggle):
            self._session.selection.toggle(effect.node, source=SelectionSource.CANVAS)
            return
        if isinstance(effect, Commit):
            self._commit(effect)
            return
        if isinstance(effect, (Preview, PreviewPage, EndPreview, Zoom, ScrollBy, Reveal, Cursor, Tip)):
            self._stage.run(effect)
            if isinstance(effect, (Preview, PreviewPage, EndPreview, Zoom, ScrollBy, Reveal)):
                self._editor.follow(self._stage.view_map())
            if isinstance(effect, Zoom):
                factor = self._stage.view_map().factor
                self._reported_factor = factor
                self._host.zoom_changed(zoom_label(factor))
            return
        if isinstance(effect, OpenEditor):
            self._queued_target = effect.target
            QTimer.singleShot(0, self._open_queued)
            return
        if isinstance(effect, OpenItems):
            self._open_items(effect.node)
            return
        if isinstance(effect, Activate):
            activate = getattr(self._host, "activate_node", None)
            if callable(activate):
                activate(effect.node)
            return
        if isinstance(effect, CloseEditor):
            self._editor.close(True)
            return
        if isinstance(effect, CanvasPressed):
            self._host.canvas_pressed()
            return
        if isinstance(effect, Narrate):
            self._host.narrate(effect.sentence)
            return
        if isinstance(effect, ShowPageStep):
            self._show_page_step(effect.delta, effect.node)
            return
        if isinstance(effect, ScrollContent):
            self._scroll_content(effect.node, effect.dx, effect.dy)
            return
        if isinstance(effect, RevealInScroll):
            self._reveal_in_scroll(effect.node)
            return
        if isinstance(effect, HoverChanged):
            self._host.hover_changed(effect.node)
            return
        if isinstance(effect, RunChipAction):
            action = effect.action
            if isinstance(action, OpenProblem):
                self._host.open_problem(action.node)
                return
            if isinstance(action, OpenLayoutPopover):
                self._host.open_layout_popover(action.node)
                return
            if isinstance(action, AddPage):
                self._add_page(action.container)
                return
            if isinstance(action, ShowStacked):
                self._show_stacked(action.container, action.delta)
                return
            if isinstance(action, FocusShare):
                focus = getattr(self._host, "focus_share", None)
                if focus is not None:
                    focus(action.node, action.axis)
                return
        raise AssertionError(type(effect))

    def placing(self) -> bool:
        return isinstance(self._gesture, Placing)

    def ghost_shown(self) -> bool:
        """O(1). True when this frame paints a drag ghost."""
        gesture = self._gesture
        return (
            self._ghost is not None
            and isinstance(gesture, Placing)
            and not gesture.outside
            and gesture.draw
        )

    def place_payload(self) -> Optional[DropPayload]:
        gesture = self._gesture
        if isinstance(gesture, Placing):
            return gesture.payload
        return None

    def paint_ghost(self, painter: object) -> None:
        gesture = self._gesture
        pixmap = self._ghost
        if pixmap is None or not isinstance(gesture, Placing) or gesture.outside or not gesture.draw:
            return
        view = self._stage.view_map()
        origin = view.to_canvas(
            Rect(
                int(gesture.pointer.x - gesture.grab.x),
                int(gesture.pointer.y - gesture.grab.y),
                1,
                1,
            )
        )
        width = max(1, int(pixmap.width() * view.factor))
        height = max(1, int(pixmap.height() * view.factor))
        painter.save()  # type: ignore[attr-defined]
        painter.setOpacity(0.6)  # type: ignore[attr-defined]
        painter.drawPixmap(QRect(origin.x, origin.y, width, height), pixmap)  # type: ignore[attr-defined]
        painter.restore()  # type: ignore[attr-defined]

    def _commit(self, effect: Commit) -> None:
        try:
            merge_token = None
            merge_within_s = 0.0
            if effect.merge is not None:
                merge_token = effect.merge
                merge_within_s = KEY_MERGE_S
            elif effect.label == "Nudge":
                merge_token = _nudge_token(effect.commands)
                merge_within_s = 1.0
            elif effect.commands and callable(getattr(effect.commands[0], "merge_window_s", None)):
                merge_token = "press:%s" % (effect.commands[0].merge_key(),)
                merge_within_s = float(effect.commands[0].merge_window_s())
            elif effect.label in ("Drop", "Move", "Change text"):
                merge_token = effect.token
                merge_within_s = 30.0
            applied: List[Tuple[object, object]] = []
            with self._session.log.transaction(
                effect.label, merge_token=merge_token, merge_within_s=merge_within_s
            ) as txn:
                for command in effect.commands:
                    fields = getattr(command, "__dataclass_fields__", {})
                    stamped = replace(command, merge_token=effect.token) if "merge_token" in fields else command
                    applied.append((stamped, txn.execute(stamped)))
        except CommandRejected as exc:
            self._host.narrate(str(exc))
            return
        self._note_dangling(applied)
        if effect.readout is not None:
            self._readout = effect.readout
            self._linger.start(READOUT_LINGER_MS)
        if effect.label in ("Drop", "Move"):
            self._view.setFocus()
        if effect.edit:
            self._pending_edit = effect
            self._pending_page = None
            QTimer.singleShot(0, self._open_edit_now)

    def _note_dangling(self, applied: List[Tuple[object, object]]) -> None:
        show = getattr(self._host, "show_paste_problem", None)
        if not callable(show):
            return
        alive = self._session.document.names()
        for command, result in applied:
            if not isinstance(command, InsertFragment) or not isinstance(result, InsertResult):
                continue
            sentence = dangling_sentence(command.fragment, result.dangling, result.renames, alive)
            if sentence is None:
                continue
            show(sentence)
            return

    def set_insert_preview(self, key: Optional[str]) -> None:
        self._preview_key = key
        self._request_frame()

    def preview_sentence(self) -> str:
        target = self._preview_target()
        if target is None:
            return ""
        return target.sentence

    def _open_edit_now(self) -> None:
        effect = self._pending_edit
        page = self._pending_page
        self._pending_edit = None
        self._pending_page = None
        if self._closed:
            return
        self._settle_geometry()
        if page is not None:
            target = page_title_target(self._session.document, page)
            if target is None:
                target = text_target(self._session.document, page, "page_tab")
            token = str(self._serial)
        elif effect is not None and effect.edit == "widget":
            state = self._session.selection.state
            current = state.current
            target = None if current is None else text_target(self._session.document, current, "widget")
            token = effect.token
            # A form-row drop selects the label and its field. Closing the label editor leaves the field.
            others = [node for node in state.ids if node != current]
            self._field_after_label = others[0] if len(others) == 1 and current is not None else None
        else:
            return
        if target is None:
            return
        self._gesture = Editing(target, token)
        self._editor.open(target, self._stage.view_map())
        self._request_frame()

    def _open_items(self, node: NodeId) -> None:
        from app.features.form_builder.qtside.items.editor import open_editor

        previous = getattr(self, "_items_editor", None)
        if previous is not None:
            previous.close_keep()
        widget = self._realizer.widget_for(node)
        beside = None
        if widget is not None:
            rect = widget.rect()
            beside = QRect(widget.mapToGlobal(rect.topLeft()), rect.size())
        self._items_editor = open_editor(self._session, node, self._view.viewport(), beside=beside)

    def _open_queued(self) -> None:
        target = self._queued_target
        self._queued_target = None
        if target is None or self._closed:
            return
        self._settle_geometry()
        self._gesture = Editing(target, str(self._serial))
        self._editor.open(target, self._stage.view_map())
        self._request_frame()

    def _settle_geometry(self) -> None:
        QApplication.sendPostedEvents(None, enum_value(QEvent.Type.LayoutRequest))
        self._index.invalidate("changeset")
        self._index.ensure_fresh()

    def _steer_outline(self, event: Event) -> Optional[str]:
        """While the canvas holds the mouse, a drag over the outline uses its rows.

        Returns the sentence to narrate when the outline took the target.
        """
        if not isinstance(event, Move) or not isinstance(self._gesture, Placing):
            return None
        viewport = self._view.viewport()
        inside = viewport.rect().contains(event.port.x, event.port.y)
        if not inside:
            self._gesture = replace(self._gesture, outside=False, draw=False)
        finder = getattr(self._host, "outline_target", None)
        if finder is None:
            return "" if not inside else None
        global_pos = viewport.mapToGlobal(QPoint(event.port.x, event.port.y))
        target = finder(global_pos)
        if target is None:
            return "" if not inside else None
        self._gesture = replace(self._gesture, target=target, outside=False, draw=False)
        if isinstance(target, NoDrop):
            return ""
        return str(getattr(target, "sentence", ""))

    def _sync_drag(self, previous: Gesture, current: Gesture) -> None:
        if isinstance(current, Placing) and not isinstance(previous, Placing):
            self._grab(current)
            self._fade(current.payload.source_ids, 0.35)
            self._remember_refusal(previous, current)
            self._watch_edge(current)
        elif isinstance(previous, Placing) and not isinstance(current, Placing):
            self._fade(previous.payload.source_ids, 1.0)
            self._ghost = None
            self._held_ghost = None
            self._spring.stop()
            self._spring_id = None
            self._edge = None
            self._edge_repeat = False
            self._edge_timer.stop()
            self._remember_refusal(previous, current)
        elif isinstance(current, Placing):
            self._park_ghost(current)
            self._arm_spring(current)
            self._watch_edge(current)
        else:
            self._edge = None
            self._edge_repeat = False
            self._edge_timer.stop()

    def _park_ghost(self, state: Placing) -> None:
        """Hide the ghost while the pointer is off the canvas. O(1). It comes back on re-entry."""
        if state.outside or not state.draw:
            if self._ghost is not None:
                self._held_ghost = self._ghost
                self._ghost = None
            return
        if self._ghost is None and self._held_ghost is not None:
            self._ghost = self._held_ghost

    def _grab(self, state: Placing) -> None:
        self._ghost = None
        if state.payload.source_ids:
            widget = self._realizer.widget_for(state.payload.source_ids[0])
            if widget is not None:
                self._ghost = widget.grab()
            return
        if state.insert_key:
            self._ghost = self._insert_pixmap(state.insert_key)

    def _insert_pixmap(self, key: str) -> Optional[QPixmap]:
        tile = tile_for(key)
        if tile is None:
            return None
        kind = getattr(QtWidgets, tile[0], None)
        if kind is None:
            return None
        widget = kind()
        widget.resize(96, 28)
        if hasattr(widget, "setText"):
            widget.setText(tile[2])
        pixmap = QPixmap(widget.size())
        transparent = getattr(getattr(Qt, "GlobalColor", Qt), "transparent")
        pixmap.fill(transparent)
        widget.render(pixmap)
        widget.deleteLater()
        return pixmap

    def _fade(self, ids: Tuple[NodeId, ...], amount: float) -> None:
        for node_id in ids:
            widget = self._realizer.widget_for(node_id)
            if widget is None:
                continue
            if amount >= 1.0:
                widget.setGraphicsEffect(None)
                continue
            effect = QGraphicsOpacityEffect(widget)
            effect.setOpacity(amount)
            widget.setGraphicsEffect(effect)

    def _arm_spring(self, state: Placing) -> None:
        key = self._spring_key(state)
        current = None if self._spring_id is None and self._spring_flip is None else (self._spring_id, self._spring_flip)
        if key == current:
            return
        self._spring_id = None if key is None else key[0]
        self._spring_flip = None if key is None else key[1]
        self._spring.stop()
        if key is not None:
            self._spring.start(600)

    def _spring_key(self, state: Placing) -> Optional[Tuple[Optional[NodeId], Optional[Tuple[NodeId, int]]]]:
        if state.outside:
            return None
        spring = getattr(state.target, "spring_id", None)
        if spring is not None:
            return spring, None
        if self._index.is_fresh():
            title = self._title_at(state.pointer)
            if title is not None:
                return title, None
        arrow = self._arrow_at(state.pointer)
        if arrow is not None:
            return None, arrow
        return None

    def _title_at(self, point: FormPoint) -> Optional[NodeId]:
        for entry in self._index.title_entries():
            if entry.kind == "page_tab" and entry.rect.contains(int(point.x), int(point.y)):
                return entry.node
        return None

    def _arrow_at(self, point: FormPoint) -> Optional[Tuple[NodeId, int]]:
        canvas = self._stage.view_map().to_canvas(Rect(int(point.x), int(point.y), 1, 1))
        probe = CanvasPoint(canvas.x, canvas.y)
        for rect, target in self._frame.targets:
            action = getattr(target, "action", None)
            if not isinstance(action, ShowStacked) or action.delta == 0:
                continue
            if rect.contains(probe):
                return action.container, action.delta
        return None

    def _spring_fire(self) -> None:
        if not isinstance(self._gesture, Placing):
            return
        flip = self._spring_flip
        if flip is not None:
            self._show_stacked(flip[0], flip[1])
            self._retarget_place()
            return
        page_id = self._spring_id
        if page_id is None:
            return
        page = self._realizer.widget_for(page_id)
        if page is None or not _show_page(page):
            return
        self._index.invalidate("page_switch")
        self._index.ensure_fresh()
        self._retarget_place()

    def _retarget_place(self) -> None:
        gesture = self._gesture
        if not isinstance(gesture, Placing):
            return
        target = resolve_at(self._session.document, self._index, gesture.pointer, gesture.payload)
        self._gesture = replace(gesture, target=target)
        self._request_frame()

    def _remember_refusal(self, previous: Gesture, current: Gesture) -> None:
        """O(1). A release on a refused target counts. The next attempt within 5 s toasts.

        A drag that starts on a refused target counts at the start. A drag that
        only becomes refused on the way counts at the release.
        """
        if isinstance(current, Placing) and isinstance(current.target, RefusedDrop):
            sentence = current.target.sentence
            previous_sentence = (
                previous.target.sentence
                if isinstance(previous, Placing) and isinstance(previous.target, RefusedDrop)
                else None
            )
            if sentence != previous_sentence:
                self._count_refusal(sentence)
                self._refused_open = True
            return
        if isinstance(previous, Placing) and isinstance(previous.target, RefusedDrop):
            if self._refused_open:
                self._refused_open = False
                return
            self._count_refusal(previous.target.sentence)

    def _count_refusal(self, sentence: str) -> None:
        """O(1). Remember ``sentence``. Toast when it repeats inside 5 s."""
        now = time.monotonic()
        if sentence and self._refused == sentence and now - self._refused_at <= 5.0:
            toast = getattr(self._host, "show_plain", None)
            if toast is not None:
                toast(sentence)
        self._refused = sentence
        self._refused_at = now

    def _add_page(self, container: NodeId) -> None:
        try:
            with self._session.log.transaction("Insert page") as txn:
                txn.execute(InsertPage(container))
        except CommandRejected as exc:
            self._host.narrate(str(exc))
            return
        self._view.setFocus()
        host = self._session.document.get(container)
        page = host.child_widgets[-1].id if isinstance(host, WidgetNode) and host.child_widgets else None
        self._pending_page = page
        self._pending_edit = None
        QTimer.singleShot(0, self._open_edit_now)

    def show_page_step(self, container: NodeId, delta: int) -> None:
        """Show the next or previous page of ``container``. Canvas only."""
        self._show_page_step(delta, container)

    def arrange_windows(self, container: NodeId, how: str) -> None:
        """Tile or cascade an MDI area on the canvas. Not saved."""
        if how == "tile":
            self.tile_windows(container)
        elif how == "cascade":
            self.cascade_windows(container)

    def _show_stacked(self, container: NodeId, delta: int) -> None:
        if delta == 0:
            return
        widget = self._realizer.widget_for(container)
        document = self._session.document
        if isinstance(widget, QWizard):
            self._show_step(widget, delta, document, container)
            return
        if isinstance(widget, QMdiArea):
            self._show_window_step(widget, delta, document, container)
            return
        if widget is None or not hasattr(widget, "count"):
            return
        count = int(widget.count())
        if count <= 0:
            return
        shown = self._shown_page.get(container, int(widget.currentIndex()))
        nxt = max(0, min(count - 1, shown + delta))
        if nxt == shown and container in self._shown_page:
            return
        self._shown_page[container] = nxt
        widget.setCurrentIndex(nxt)
        self._index.invalidate("page_switch")
        self._request_frame()

    def _scroll_area_widget(self, node: NodeId) -> Optional[QScrollArea]:
        widget = self._realizer.widget_for(node)
        return widget if isinstance(widget, QScrollArea) else None

    def _mdi_widget(self, node: NodeId) -> Optional[QMdiArea]:
        widget = self._realizer.widget_for(node)
        return widget if isinstance(widget, QMdiArea) else None

    _EDGE_PX = 16
    _EDGE_DWELL_MS = 400
    _EDGE_STEP_MS = 100

    def _watch_edge(self, state: Placing) -> None:
        """A drag held on a scroll area's top or bottom 16 px scrolls it (UX-CONT-010)."""
        found = self._edge_zone(state.pointer)
        if found == self._edge and (self._edge_timer.isActive() or self._edge_repeat):
            return
        self._edge = found
        self._edge_repeat = False
        self._edge_timer.stop()
        if found is not None:
            self._edge_timer.start(self._EDGE_DWELL_MS)

    def _edge_zone(self, point: object) -> Optional[Tuple[NodeId, int]]:
        self._index.ensure_fresh()
        x = int(getattr(point, "x"))
        y = int(getattr(point, "y"))
        hit = self._index.query(x, y)
        if hit is None:
            return None
        area_id = scroll_area_in_path(self._session.document, hit.path)
        if area_id is None:
            return None
        rect = self._index.rect_of(area_id)
        if rect is None:
            return None
        factor = float(self._stage.view_map().factor or 1.0)
        edge = max(1, int(round(self._EDGE_PX / factor)))
        if y <= rect.y + edge:
            return area_id, -1
        if y >= rect.y + rect.height - edge:
            return area_id, 1
        return None

    def _edge_fire(self) -> None:
        if not isinstance(self._gesture, Placing) or self._edge is None:
            return
        area_id, direction = self._edge
        if self._edge_zone(self._gesture.pointer) != self._edge:
            self._edge = None
            self._edge_repeat = False
            return
        self._step_scroll(area_id, direction)
        self._index.ensure_fresh()
        self._retarget_place()
        self._edge_repeat = True
        self._edge_timer.start(self._EDGE_STEP_MS)

    def _step_scroll(self, node: NodeId, direction: int) -> None:
        area = self._scroll_area_widget(node)
        if area is None:
            return
        bar = area.verticalScrollBar()
        bar.setValue(bar.value() + direction * max(bar.singleStep(), 1))
        QApplication.sendPostedEvents(None, enum_value(QEvent.Type.LayoutRequest))
        self._index.invalidate("scroll")

    def _scroll_content(self, node: NodeId, dx: int, dy: int) -> None:
        """Wheel over a scroll area. One notch (120) is three single steps, as Qt does it (UX-CONT-010)."""
        area = self._scroll_area_widget(node)
        if area is None:
            return
        horizontal = area.horizontalScrollBar()
        vertical = area.verticalScrollBar()
        for bar, delta in ((horizontal, dx), (vertical, dy)):
            if delta:
                bar.setValue(bar.value() + int(round(delta * bar.singleStep() / 40)))
        self._index.invalidate("scroll")
        self._request_frame()

    def _reveal_in_scroll(self, node: NodeId) -> None:
        """Selection inside a scroll area scrolls it so the widget is visible; the canvas then reveals it."""
        widget = self._realizer.widget_for(node)
        if widget is None:
            return
        area = _enclosing_scroll_area(widget)
        if area is not None:
            area.ensureWidgetVisible(widget)
        self._index.invalidate("scroll")
        self._pending_reveal = node
        self._request_frame()

    def _show_window_step(self, area: QMdiArea, delta: int, document: UiDocument, container: NodeId) -> None:
        """Show previous or next window (UX-CONT-011). Canvas only: the file does not change."""
        windows = area.subWindowList()
        if not windows:
            return
        current = area.activeSubWindow()
        index = windows.index(current) if current in windows else 0
        nxt = (index + delta) % len(windows)
        area.setActiveSubWindow(windows[nxt])
        self._shown_page[container] = nxt
        self._index.invalidate("page_switch")
        self._request_frame()
        self._host.narrate("Showing window %d of %d" % (nxt + 1, len(windows)))

    def _show_step(self, wizard: QWizard, delta: int, document: UiDocument, container: NodeId) -> None:
        """Show the next or previous wizard step, wrapping (UX-CONT-013). Canvas only."""
        ids = list(wizard.pageIds())
        if not ids:
            return
        current = wizard.currentId()
        # A wizard that is not shown has no current page (-1), so the first step is the base.
        index = ids.index(current) if current in ids else 0  # the canvas shows the first step until moved
        nxt = (index + delta) % len(ids)
        if current not in ids:
            wizard.restart()  # a wizard that was never shown has no page to move from
        wizard.setCurrentId(ids[nxt])
        self._shown_page[container] = nxt
        self._index.invalidate("page_switch")
        self._request_frame()
        page = pages(document, container)[nxt]
        title = page_title(document, page.id) or page.object_name
        self._host.narrate("Showing step %d of %d: %s" % (nxt + 1, len(ids), title))

    def tile_windows(self, container: NodeId) -> None:
        """Tile the windows of an MDI area on the canvas. Not saved (UX-CONT-011)."""
        area = self._mdi_widget(container)
        if area is not None:
            area.tileSubWindows()
            self._index.invalidate("page_switch")
            self._request_frame()

    def cascade_windows(self, container: NodeId) -> None:
        """Cascade the windows of an MDI area on the canvas. Not saved (UX-CONT-011)."""
        area = self._mdi_widget(container)
        if area is not None:
            area.cascadeSubWindows()
            self._index.invalidate("page_switch")
            self._request_frame()

    def _show_page_step(self, delta: int, node: NodeId) -> None:
        """Ctrl+PgDown and Ctrl+PgUp: show the next or previous page, wrapping (UX-CONT-007).

        Only the shown page changes. The file's start page is untouched.
        """
        document = self._session.document
        container = innermost_container(document, node)
        if container is None or page_kind(document, container) is None:
            return
        widget = self._realizer.widget_for(container)
        if isinstance(widget, QMdiArea):
            self._show_window_step(widget, delta, document, container)
            return
        if isinstance(widget, QWizard):
            self._show_step(widget, delta, document, container)
            return
        if widget is None or not hasattr(widget, "count") or not hasattr(widget, "setCurrentIndex"):
            return
        count = int(widget.count())
        if count <= 0:
            return
        shown = self._shown_page.get(container, int(widget.currentIndex()))
        nxt = (shown + delta) % count
        self._shown_page[container] = nxt
        widget.setCurrentIndex(nxt)
        self._index.invalidate("page_switch")
        self._request_frame()
        page = pages(document, container)[nxt]
        title = page_title(document, page.id) or page.object_name
        sentence = "Showing page %d of %d: %s" % (nxt + 1, count, title)
        start = start_index(document, container)
        if start is not None and start != nxt:
            sentence += " \u00b7 the file still starts on page %d" % (start + 1)
        self._host.narrate(sentence)

    def _reapply_pages(self, changeset: ChangeSet) -> None:
        for node_id, _kind, name in changeset.property_dirty:
            if name == "currentIndex" and node_id in self._shown_page:
                del self._shown_page[node_id]
        for node_id, index in list(self._shown_page.items()):
            widget = self._realizer.widget_for(node_id)
            if widget is not None and hasattr(widget, "setCurrentIndex") and widget.currentIndex() != index:
                widget.setCurrentIndex(index)

    def _preview_target(self) -> Optional[AcceptedDrop]:
        key = self._preview_key
        if not key or isinstance(self._gesture, (Placing, Editing)):
            return None
        tile = tile_for(key)
        kind = tile[1] if tile is not None else "widget"
        if kind not in ("widget", "spacer", "label"):
            kind = "widget"
        self._index.ensure_fresh()
        target = auto_target(self._session.document, self._session.selection.state.current, DropPayload(kind))
        if not isinstance(target, AcceptedDrop):
            return None
        return indicate_preview(self._session.document, self._index, target)

    def _tip_at(self, event: Event) -> None:
        if not isinstance(event, Move):
            return
        tip = ""
        for item in self._frame.items:
            if isinstance(item, (Chip, Badge)) and item.tip and item.rect.contains(event.at):
                tip = item.tip
                break
        if tip != self._tip:
            self._tip = tip
            self._view.setToolTip(tip)

    def _place_and_report(self) -> None:
        self._stage.place()
        factor = self._stage.view_map().factor
        if self._reported_factor is None or abs(factor - self._reported_factor) > 1e-4:
            self._reported_factor = factor
            self._host.zoom_changed(zoom_label(factor))

    def _request_frame(self) -> None:
        if self._closed or self._frame_requested:
            return
        self._frame_requested = True
        QApplication.postEvent(self._view, _input.frame_request())

    def _pre_paint(self) -> None:
        self._index.ensure_fresh()
        self._note_moved()
        pending = self._pending_reveal
        self._pending_reveal = None
        if pending is not None:
            rect = self._index.rect_of(pending)
            if rect is not None:
                self._stage.run(Reveal(rect))
                self._editor.follow(self._stage.view_map())
        previous = self._frame
        self._rebuild(static=self._static_stale())
        self._sync_dock()
        # O(changed overlay rects). The page pixmap is left alone.
        self._damage_overlay(previous)

    def _note_moved(self) -> None:
        preview = getattr(self._view, "preview", None)
        note = getattr(preview, "note_moved", None)
        if note is None:
            return
        changed = self._index.last_changed
        if changed is not None:
            # O(changed). A full walk leaves last_changed as None.
            note(changed)
            return
        note(_moved_ids(self._static_entries, self._index.indexed_entries()))

    def _static_stale(self) -> bool:
        view = self._stage.view_map()
        static = self._static
        if static is None or static.view != view:
            return True
        if static.epoch == self._index.epoch:
            return False
        changed = self._index.last_changed
        if changed is not None:
            return self._shift_changed(static, view, changed)
        # Rebuilding every stroke when one widget moved is the O(form) part
        # of an edit. Shift the obstacles that moved. The frame still rebuilds,
        # so the selection chip follows.
        current = self._index.indexed_entries()
        shifted = _reuse_static(static, view, self._static_entries, current)
        if shifted is None:
            return True
        self._static = replace(shifted, epoch=self._index.epoch)
        self._static_entries = current
        return False

    def _shift_changed(self, static: StaticLayer, view: ViewMap, changed: Tuple[NodeId, ...]) -> bool:
        """O(changed). True when the static layer has to be rebuilt."""
        if not changed:
            self._static = replace(static, epoch=self._index.epoch)
            self._static_entries = self._index.indexed_entries()
            return False
        updates = {}
        for node_id in changed:
            rect = self._index.rect_of(node_id)
            if rect is None:
                return True
            updates[node_id] = rect
        shifted = shift_static(static, view, updates)
        if shifted is None:
            return True
        self._static = replace(shifted, epoch=self._index.epoch)
        self._static_entries = self._index.indexed_entries()
        return False

    def _sync_dock(self) -> None:
        """Push docked chips when the frame is built. Paint must not move widgets."""
        sync = getattr(self._view, "sync_docked_chips", None)
        if sync is not None:
            sync(self._frame)

    def _ghost_rect(self) -> Optional[CanvasRect]:
        gesture = self._gesture
        pixmap = self._ghost
        if pixmap is None or not isinstance(gesture, Placing) or gesture.outside or not gesture.draw:
            return None
        view = self._stage.view_map()
        origin = view.to_canvas(
            Rect(
                int(gesture.pointer.x - gesture.grab.x),
                int(gesture.pointer.y - gesture.grab.y),
                1,
                1,
            )
        )
        width = max(1, int(pixmap.width() * view.factor))
        height = max(1, int(pixmap.height() * view.factor))
        return CanvasRect(origin.x, origin.y, width, height)

    def _damage_overlay(self, previous: OverlayFrame) -> None:
        """Repaint each overlay rect that appeared or disappeared. O(changed rects).

        The bounding box of a selection and its chip is mostly empty page. Updating
        that box repaints the widgets in the gap, so each rect is posted on its own.
        """
        rects = _changed_bounds(previous, self._frame)
        if self._ghost_damage is not None:
            rects.append(self._ghost_damage)
        ghost = self._ghost_rect()
        self._ghost_damage = ghost
        if ghost is not None:
            rects.append(ghost)
        wide = _wide_stroke_rects(self._view)
        rects.extend(self._wide_prev)
        rects.extend(wide)
        self._wide_prev = wide
        if not rects:
            return
        viewport = self._view.viewport()
        bounds = viewport.rect()
        origin = self._view.mapFromScene(QPointF(0.0, 0.0))
        unit = self._view.mapFromScene(QPointF(1.0, 0.0))
        down = self._view.mapFromScene(QPointF(0.0, 1.0))
        scale_x = unit.x() - origin.x()
        scale_y = down.y() - origin.y()
        ports: List[QRect] = []
        area = 0
        for rect in rects:
            port = _port_from(origin.x(), origin.y(), scale_x, scale_y, rect).adjusted(-4, -4, 4, 4).intersected(bounds)
            if port.isEmpty():
                continue
            ports.append(port)
            area += port.width() * port.height()
        if not ports:
            return
        if bounds.width() > 0 and area > bounds.width() * bounds.height() * 0.6:
            viewport.update()
            return
        for port in ports:
            viewport.update(port)

    def _shown_for_frame(self) -> Dict[NodeId, int]:
        """The page chip follows the live MDI window, which Qt activates last."""
        shown = dict(self._shown_page)
        for area_id in self._mdi_areas():
            widget = self._realizer.widget_for(area_id)
            if widget is None or not isinstance(widget, QMdiArea):
                continue
            windows = list(widget.subWindowList())
            active = widget.activeSubWindow()
            if active is None:
                continue
            try:
                shown[area_id] = windows.index(active)
            except ValueError:
                continue
        return shown

    def _mdi_areas(self) -> Tuple[NodeId, ...]:
        """MDI areas in the form. O(form) once per document revision, O(1) per frame."""
        document = self._session.document
        revision = document.revision
        cached = self._mdi_cache
        if cached is not None and cached[0] is document and cached[1] == revision:
            return cached[2]
        found = tuple(node.id for node in document.iter_widgets() if node.class_name == "QMdiArea")
        self._mdi_cache = (document, revision, found)
        return found

    def _rebuild(self, static: bool) -> None:
        view = self._stage.view_map()
        if static or self._static is None:
            self._static = build_static(self._session.document, self._index, view)
            self._static_entries = self._index.indexed_entries()
        selection = self._session.selection.state
        self._frame = build_frame(
            self._static,
            FrameInputs(
                self._session.document,
                selection,
                self._gesture,
                view,
                self._view.hasFocus(),
                self._problems(),
                self._problems_revision,
                self._sizing(selection),
                self._stage.chrome_rects(),
                self._measure,
                visible_scene_rect(self._view),
                self._stage.dock_rect(),
                self._preview_target(),
                self._shown_for_frame(),
                knobs=self._knob_set(self._static, selection),
                readout=self._readout,
                refusals=self._refusal_tips(),
                layers=self._layers,
            ),
        )
        self._sync_refusal_access()

    def _refusal_tips(self) -> Tuple[Tuple[NodeId, str], ...]:
        """Tooltip lines for refused properties. O(1) when Qt accepted everything."""
        marks = self._realizer.refusal_marks()
        if not marks:
            return ()
        return tuple((node_id, self._refusal_text(names)) for node_id, names in marks)

    def _refusal_text(self, names: Tuple[str, ...]) -> str:
        return "\n".join(
            "%s: saved in the file. The canvas can't show this value." % self._property_label(name)
            for name in names
        )

    def _property_label(self, name: str) -> str:
        labels = self._property_labels
        if labels is None:
            found: Dict[str, str] = {}
            for spec in default_catalog().rows():
                prop = getattr(spec.source, "name", None)
                if isinstance(prop, str) and prop not in found:
                    found[prop] = spec.label
            labels = found
            self._property_labels = labels
        return labels.get(name, name)

    def _sync_refusal_access(self) -> None:
        """A transparent widget carries the badge sentence for assistive tech."""
        badges = [item for item in self._frame.items if isinstance(item, Badge) and item.tip]
        viewport = self._view.viewport()
        while len(self._refusal_holders) < len(badges):
            label = QtWidgets.QLabel(viewport)
            label.setObjectName("formBuilder.refusalBadge")
            label.setAccessibleName("Problem")
            policy = getattr(Qt, "FocusPolicy", Qt)
            label.setFocusPolicy(getattr(policy, "NoFocus"))
            attribute = getattr(Qt, "WidgetAttribute", Qt)
            label.setAttribute(getattr(attribute, "WA_TransparentForMouseEvents"), True)
            self._refusal_holders.append(label)
        for index, label in enumerate(self._refusal_holders):
            if index >= len(badges):
                label.hide()
                continue
            badge = badges[index]
            origin = self._view.mapFromScene(QPoint(badge.rect.x, badge.rect.y))
            label.setGeometry(int(origin.x()), int(origin.y()), badge.rect.width, badge.rect.height)
            label.setAccessibleDescription(badge.tip)
            label.setToolTip(badge.tip)
            label.show()

    def _knob_set(self, static: StaticLayer, selection: SelectionState) -> KnobSet:
        """Survey on a new scope or a new index epoch. A preview keeps the epoch, so it reuses the survey."""
        document = self._session.document
        primary = effective_selection(document, selection).current
        scope = survey_scope(document, primary, static.splitters)
        survey = self._survey
        if survey is None or survey.scope != scope or survey.epoch != self._index.epoch:
            survey = survey_live(self._realizer, self._index, document, scope, survey)
            self._survey = survey
        view = self._stage.view_map()
        window = _knob_window(view, visible_scene_rect(self._view))
        cached = self._knobs
        if cached is not None and cached[0] is survey and cached[1] == view.factor and cached[2] == window:
            return cached[3]
        site_key = (self._index.epoch, scope.layouts, scope.splitters, view.factor, window)
        sites = self._sites if self._site_key == site_key else None
        knobs = knob_set(survey, document, view.factor, window, sites)
        if sites is None:
            self._site_key = site_key
            self._sites = knobs.sites
        self._knobs = (survey, view.factor, window, knobs)
        return knobs

    def _end_readout(self) -> None:
        self._readout = None
        self._request_frame()

    def refresh_overlay(self) -> None:
        if self._closed:
            return
        self._request_frame()

    def show_layer(self, name: str, state: Hashable = True) -> None:
        """Switch canvas layer ``name`` on for this canvas, or give it a new ``state`` (M5.0s).

        The layer's ``build`` gets ``state`` on every frame. Showing a name
        nobody registered does nothing.
        """
        if name in self._layer_states and self._layer_states[name] == state:
            return
        self._layer_states[name] = state
        self._resolve_layers()

    def hide_layer(self, name: str) -> None:
        if name not in self._layer_states:
            return
        del self._layer_states[name]
        self._resolve_layers()

    def layer_state(self, name: str) -> Optional[Hashable]:
        """The state ``name`` was shown with, or None when it is off."""
        return self._layer_states.get(name)

    def _resolve_layers(self) -> None:
        resolved = canvas_layers.default_registry().resolve(self._layer_states) if self._layer_states else ()
        if resolved == self._layers:
            return
        self._layers = resolved
        self._request_frame()

    def _before_realize(self, changeset: ChangeSet) -> None:
        if not changeset.replaced:
            return
        self._stage.detach()
        self._editor.close(False)
        self._gesture = Idle()

    def _after_realize(self, changeset: ChangeSet) -> None:
        self._place_and_report()
        self._reapply_pages(changeset)
        self._feed(DocumentChanged(changeset.removed, changeset.replaced))
        self._open_inserted_page(changeset)

    def _open_inserted_page(self, changeset: ChangeSet) -> None:
        """Insert page shows the new page and opens the title editor the container reads."""
        if changeset.label != "Insert page":
            return
        current = self._session.selection.state.current
        if current is None:
            return
        self._show_inserted(current)
        if page_title_target(self._session.document, current) is None:
            return
        self._pending_page = current
        self._pending_edit = None
        QTimer.singleShot(0, self._open_edit_now)

    def _show_inserted(self, page_id: NodeId) -> None:
        """Keep the new page on screen. A later realize must not snap back to the old one."""
        document = self._session.document
        container = innermost_container(document, page_id)
        if container is None:
            return
        index = next((item for item, page in enumerate(pages(document, container)) if page.id == page_id), None)
        if index is None:
            return
        self._shown_page[container] = index
        widget = self._realizer.widget_for(container)
        if isinstance(widget, QWizard):
            wizard = cast(QWizard, widget)
            ids = list(wizard.pageIds())
            if index < len(ids):
                wizard.setCurrentId(ids[index])
        elif isinstance(widget, QMdiArea):
            area = cast(QMdiArea, widget)
            windows = area.subWindowList()
            if index < len(windows):
                area.setActiveSubWindow(windows[index])
        elif widget is not None and hasattr(widget, "setCurrentIndex"):
            widget.setCurrentIndex(index)
        self._index.invalidate("page_switch")

    def _on_selection(self, change: SelectionChange) -> None:
        editor = getattr(self, "_items_editor", None)
        if editor is not None and (change.after.current is None or change.after.current != editor.draft.widget):
            # A command's selection change arrives inside its change listeners,
            # where the editor's closing commit cannot run; close once it returns.
            self._items_editor = None
            QTimer.singleShot(0, editor.close_keep)
        self._announce_selection(change.after)
        if change.after.current is not None:
            self._raise_mdi_window(change.after.current)
        if change.source in REVEAL_SOURCES and change.after.current is not None:
            self._show_pages_holding(change.after.current)
            self._pending_reveal = change.after.current
        self._request_frame()

    def _show_pages_holding(self, node_id: NodeId) -> None:
        """A widget selected outside the canvas on a hidden page brings its page into view.

        Canvas only, like a click on the tab (UX-CONT-006): the start page in the file stays.
        """
        document = self._session.document
        if not document.contains(node_id):
            return
        for ancestor in (node_id,) + tuple(document.ancestors(node_id)):
            parent = document.parent(ancestor)
            if parent is None or page_kind(document, parent.id) is None:
                continue
            found = pages(document, parent.id)
            index = next((item for item, page in enumerate(found) if page.id == ancestor), None)
            if index is None or index == self._shown_index(parent.id):
                continue
            self._show_inserted(ancestor)

    def _shown_index(self, container: NodeId) -> Optional[int]:
        shown = self._shown_page.get(container)
        if shown is not None:
            return shown
        widget = self._realizer.widget_for(container)
        current = getattr(widget, "currentIndex", None)
        if callable(current) and not isinstance(widget, QWizard):
            return int(current())
        return None

    def _raise_mdi_window(self, node_id: NodeId) -> None:
        """Bring the subwindow that holds the selection to the front.

        Canvas only. The file and the undo stack stay as they were (UX-CONT-006).
        """
        widget = self._realizer.widget_for(node_id)
        if not isinstance(widget, QWidget):
            return
        sub = widget if isinstance(widget, QMdiSubWindow) else None
        current: Optional[QWidget] = widget
        while sub is None and current is not None:
            parent = current.parentWidget()
            if isinstance(parent, QMdiSubWindow):
                sub = parent
                break
            current = parent
        if sub is None:
            return
        area = sub.mdiArea()
        if area is None or area.activeSubWindow() is sub:
            return
        area.setActiveSubWindow(sub)
        windows = area.subWindowList()
        try:
            index = windows.index(sub)
        except ValueError:
            return
        area_id = self._realizer.node_for(area)
        if area_id is not None:
            self._shown_page[area_id] = index
        self._index.invalidate("page_switch")

    def _announce_selection(self, state: SelectionState) -> None:
        shown = effective_selection(self._session.document, state)
        self._stage.set_form_selected(shown.current == self._session.document.root.id)
        self._view.setAccessibleDescription(describe_selection(self._session.document, state))

    def _on_diagnostics(self, _items: object) -> None:
        self._problems_revision += 1
        self._request_frame()

    def _on_editor_done(self, done: EditorDone) -> None:
        field = self._field_after_label
        self._field_after_label = None
        self._feed(done)
        if field is not None and done.how not in ("tab", "backtab") and self._session.document.contains(field):
            # The new row's label editor closed: the field is the selection, not the label and field pair,
            # so the inspector shows the field's own rows.
            self._session.selection.set((field,), current=field, source=SelectionSource.CANVAS)

    def _problems(self) -> Dict[NodeId, str]:
        found: Dict[NodeId, str] = {}
        for item in self._session.diagnostics.all():
            if item.severity is not Severity.ERROR:
                continue
            node = item.location.node_id
            if node is None or node in found:
                continue
            found[node] = item.message
        return found

    def _sizing(
        self, selection: SelectionState
    ) -> Optional[Tuple[Optional[str], Optional[str]]]:
        current = effective_selection(self._session.document, selection).current
        if current is None:
            return None
        widget = self._realizer.widget_for(current)
        if widget is None or not isinstance(widget, QWidget):
            return None
        node = self._session.document.get(current)
        if not isinstance(node, WidgetNode):
            return None
        stored = _stored_policy(node)
        minimum = _stored_size(node, "minimumSize")
        maximum = _stored_size(node, "maximumSize")
        defaults = class_default_policies(widget)
        phrase = class_phrase(node.class_name)
        horizontal = project_axis(
            stored_policy=None if stored is None else stored.hsizetype,
            minimum=None if minimum is None else minimum.width,
            maximum=None if maximum is None else maximum.width,
            class_default_policy=defaults[0],
            class_phrase=phrase,
        )
        vertical = project_axis(
            stored_policy=None if stored is None else stored.vsizetype,
            minimum=None if minimum is None else minimum.height,
            maximum=None if maximum is None else maximum.height,
            class_default_policy=defaults[1],
            class_phrase=phrase,
        )
        return (chip_axis(horizontal), chip_axis(vertical))

    def _measure(self, text: str) -> int:
        found = self._chip_widths.get(text)
        if found is not None:
            return found
        view_font = self._view.font()
        key = (view_font.family(), int(view_font.pointSize()), int(view_font.pixelSize()))
        metrics = self._chip_metrics
        if metrics is None or self._chip_font_key != key:
            font = QFont(view_font)
            font.setPixelSize(11)
            font.setBold(True)
            metrics = QFontMetrics(font)
            self._chip_metrics = metrics
            self._chip_font_key = key
            self._chip_widths = {}
        advance = getattr(metrics, "horizontalAdvance", None)
        width = int(metrics.width(text) if advance is None else advance(text))
        self._chip_widths[text] = width
        return width


def _changed_bounds(previous: OverlayFrame, current: OverlayFrame) -> List[CanvasRect]:
    """Rects whose painted item changed. The key is the item, so a style change at the same rect repaints."""
    before = _item_counts(previous)
    after = _item_counts(current)
    changed: List[CanvasRect] = []
    for item in set(before) | set(after):
        if before.get(item, 0) != after.get(item, 0):
            changed.extend(_damage_rects(item))
    return changed


def _item_counts(frame: OverlayFrame) -> Dict[object, int]:
    counts: Dict[object, int] = {}
    for item in frame.items:
        counts[item] = counts.get(item, 0) + 1
    return counts


def _damage_rects(item: object) -> List[CanvasRect]:
    """A page-wide stroke damages its four edges. The interior stays unexposed."""
    rect = _item_bounds(item)
    if (
        isinstance(item, Stroke)
        and not item.caps
        and rect.width > 12
        and rect.height > 12
    ):
        band = max(int(item.width) + 3, 4)
        return [
            CanvasRect(rect.x, rect.y, rect.width, band),
            CanvasRect(rect.x, rect.y + rect.height - band, rect.width, band),
            CanvasRect(rect.x, rect.y, band, rect.height),
            CanvasRect(rect.x + rect.width - band, rect.y, band, rect.height),
        ]
    return [rect]


def _item_bounds(item: object) -> CanvasRect:
    rect = item.rect  # type: ignore[attr-defined]
    leader = getattr(item, "leader", None)
    if leader is None:
        return rect
    xs = (rect.x, rect.x + rect.width, leader.start.x, leader.end.x)
    ys = (rect.y, rect.y + rect.height, leader.start.y, leader.end.y)
    left = min(xs)
    top = min(ys)
    return CanvasRect(left, top, max(xs) - left, max(ys) - top)


def _port_from(origin_x: float, origin_y: float, scale_x: float, scale_y: float, rect: CanvasRect) -> QRect:
    """Canvas pixels to viewport pixels from one measured origin. O(1)."""
    left = origin_x + rect.x * scale_x
    top = origin_y + rect.y * scale_y
    width = rect.width * scale_x
    height = rect.height * scale_y
    if width < 0:
        left += width
        width = -width
    if height < 0:
        top += height
        height = -height
    return QRect(int(left), int(top), max(1, int(width)), max(1, int(height)))


def _wide_stroke_rects(view: QGraphicsView) -> Tuple[CanvasRect, ...]:
    preview = getattr(view, "preview", None)
    reader = getattr(preview, "wide_stroke_rects", None)
    if reader is None:
        return ()
    found = reader()
    return tuple(found) if found else ()


def _moved_ids(
    previous: Tuple[GeoEntry, ...],
    current: Tuple[GeoEntry, ...],
) -> Optional[Tuple[NodeId, ...]]:
    """Node ids whose rect changed. None when the entry list is not the same widgets."""
    if len(previous) != len(current):
        return None
    moved: List[NodeId] = []
    for left, right in zip(previous, current):
        if left.kind != right.kind or left.node != right.node or left.visible != right.visible:
            return None
        if left.rect != right.rect:
            moved.append(right.node)
    return tuple(moved)


def _knob_window(view: ViewMap, shown: CanvasRect) -> Rect:
    """The visible scene and one viewport past each side, in form pixels.

    A scrollbar drag rebuilds the frame only on release, so the slack keeps nearby gaps drawn meanwhile.
    """
    factor = view.factor if view.factor else 1.0
    corner = view.to_form(CanvasPoint(shown.x - shown.width, shown.y - shown.height))
    return Rect(
        int(math.floor(corner.x)),
        int(math.floor(corner.y)),
        int(math.ceil(3 * shown.width / factor)),
        int(math.ceil(3 * shown.height / factor)),
    )


def _reuse_static(
    static: StaticLayer,
    view: ViewMap,
    previous: Tuple[GeoEntry, ...],
    current: Tuple[GeoEntry, ...],
) -> Optional[StaticLayer]:
    if len(previous) != len(current):
        return None
    updates = {}
    for left, right in zip(previous, current):
        if (
            left.kind != right.kind
            or left.node != right.node
            or left.visible != right.visible
            or left.container != right.container
            or left.z != right.z
        ):
            return None
        if left.rect != right.rect:
            if right.kind not in ("widget", "spacer"):
                return None
            updates[right.node] = right.rect
    return shift_static(static, view, updates)


def _show_page(page: QWidget) -> bool:
    """Switch the page through the container that owns it, not its inner stack."""
    current = page.parentWidget()
    while current is not None:
        if isinstance(current, QTabWidget):
            current.setCurrentWidget(page)
            return True
        if isinstance(current, QToolBox):
            index = current.indexOf(page)
            if index < 0:
                return False
            current.setCurrentIndex(index)
            return True
        if isinstance(current, QStackedWidget):
            parent = current.parentWidget()
            if isinstance(parent, (QTabWidget, QToolBox)):
                current = parent
                continue
            current.setCurrentWidget(page)
            return True
        current = current.parentWidget()
    return False


def _nudge_token(commands: Tuple[object, ...]) -> str:
    parts = []
    for command in commands:
        node = getattr(command, "id", None)
        if node is not None:
            parts.append(str(node))
            continue
        ids = getattr(command, "ids", None)
        if ids:
            parts.extend(str(item) for item in ids)
            continue
        layout = getattr(command, "layout", None)
        if layout is not None:
            parts.append("%s:%s" % (type(command).__name__, layout))
    return "nudge:" + ",".join(parts)


def _mints_token(gesture: Gesture, event: Event) -> bool:
    if isinstance(event, (Press, PlaceAsked)):
        return True
    if isinstance(event, Key) and isinstance(gesture, Idle):
        return True
    return isinstance(event, EditorDone) and event.how in ("tab", "backtab")


def _stored_policy(node: object) -> Optional[SizePolicyValue]:
    if not isinstance(node, WidgetNode):
        return None
    entry = node.prop("sizePolicy")
    if entry is None or not isinstance(entry.value, SizePolicyValue):
        return None
    return entry.value


def _stored_size(node: object, name: str) -> Optional[SizeValue]:
    if not isinstance(node, WidgetNode):
        return None
    entry = node.prop(name)
    if entry is None or not isinstance(entry.value, SizeValue):
        return None
    return entry.value
