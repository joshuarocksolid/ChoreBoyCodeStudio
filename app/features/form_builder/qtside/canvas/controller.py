"""The canvas's imperative shell.

Public surface: ``handle``, ``post``, ``frame``, ``dispose``. What the canvas
decides lives in ``core.gesture.step`` and ``core.overlay.build_frame``.
"""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Dict, FrozenSet, Optional, Protocol, Tuple

from app.qt.QtCore import QEvent, QPoint, QRect, Qt, QTimer
from app.qt.QtGui import QFont, QFontMetrics, QPixmap
from app.qt.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QGraphicsView,
    QStackedWidget,
    QTabWidget,
    QToolBox,
    QWidget,
)
from app.qt import QtWidgets
from app.qt.qt_compat import enum_value

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog_ext.drop import InsertPage
from app.features.form_builder.engine.commands.drop_plan import auto_target, indicate_preview
from app.features.form_builder.engine.diagnostics import Severity
from app.features.form_builder.engine.events import PRIORITY_VIEWS, ChangeSet
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.drop_target import AcceptedDrop, DropPayload, NoDrop, RefusedDrop
from app.features.form_builder.engine.query.hit_index import HitIndex, Rect
from app.features.form_builder.engine.query.selection import SelectionChange, SelectionSource, SelectionState
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.qtside.canvas import _input
from app.features.form_builder.qtside.canvas.core.frame import (
    AddPage,
    Chip,
    OpenLayoutPopover,
    OpenProblem,
    OverlayFrame,
    ShowStacked,
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
    Key,
    Move,
    PlaceAsked,
    Placing,
    Narrate,
    OpenEditor,
    Press,
    Preview,
    PreviewPage,
    Reveal,
    RunChipAction,
    ScrollBy,
    Select,
    Tip,
    Toggle,
    World,
    Zoom,
    needs_fresh_geometry,
    previewing,
    step,
)
from app.features.form_builder.qtside.canvas.core.palette import tile_for
from app.features.form_builder.qtside.canvas.core.place import resolve_at
from app.features.form_builder.qtside.canvas.core.space import CanvasPoint, FormPoint
from app.features.form_builder.qtside.canvas.core.overlay import (
    FrameInputs,
    StaticLayer,
    build_frame,
    build_static,
    frame_basis,
)
from app.features.form_builder.qtside.canvas.core.structure import effective_selection
from app.features.form_builder.qtside.canvas.core.text import TextTarget, text_target
from app.features.form_builder.qtside.canvas.core.words import (
    SizingWord,
    describe_selection,
    sizing_word,
    zoom_label,
)
from app.features.form_builder.qtside.canvas.editor import InPlaceEditor
from app.features.form_builder.qtside.canvas.stage import Stage, visible_scene_rect
from app.features.form_builder.qtside.realize.api import Realizer

# The canvas scrolls to reveal only for these sources. Its own CANVAS changes
# never re-scroll it. Keyboard navigation reveals through a Reveal effect.
REVEAL_SOURCES: FrozenSet[SelectionSource] = frozenset(
    {SelectionSource.OUTLINE, SelectionSource.PROGRAM, SelectionSource.UNDO}
)

# Detach must run before the realizer deletes a replaced root (priority 10).
PRIORITY_DETACH = 9

_QT_MAX = 16777215


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
        self._spring_id: Optional[NodeId] = None
        self._refused: Optional[str] = None
        self._refused_at = 0.0
        self._shown_page: Dict[NodeId, int] = {}
        self._preview_key: Optional[str] = None
        self._pending_edit: Optional[Commit] = None
        self._pending_page: Optional[NodeId] = None
        self._queued_target: Optional[TextTarget] = None
        self._spring_flip: Optional[Tuple[NodeId, int]] = None
        self._tip = ""
        self._spring = QTimer()
        self._spring.setSingleShot(True)
        self._spring.timeout.connect(self._spring_fire)
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

    def dispose(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._spring.stop()
        if isinstance(self._gesture, Placing):
            self._fade(self._gesture.payload.source_ids, 1.0)
        self._ghost = None
        if previewing(self._gesture):
            self._stage.run(EndPreview())
        self._editor.close(False)
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
        return World(
            self._session.document,
            self._session.selection.state,
            self._index,
            self._stage.view_map(),
            self._frame,
            self._stage.page_minimum(),
            str(self._serial),
        )

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
        if isinstance(effect, CloseEditor):
            self._editor.close(True)
            return
        if isinstance(effect, CanvasPressed):
            self._host.canvas_pressed()
            return
        if isinstance(effect, Narrate):
            self._host.narrate(effect.sentence)
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
        raise AssertionError(type(effect))

    def placing(self) -> bool:
        return isinstance(self._gesture, Placing)

    def place_payload(self) -> Optional[DropPayload]:
        gesture = self._gesture
        if isinstance(gesture, Placing):
            return gesture.payload
        return None

    def paint_ghost(self, painter: object) -> None:
        gesture = self._gesture
        pixmap = self._ghost
        if pixmap is None or not isinstance(gesture, Placing) or gesture.outside:
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
            if effect.label == "Nudge":
                merge_token = _nudge_token(effect.commands)
                merge_within_s = 1.0
            elif effect.label in ("Drop", "Move", "Edit text"):
                merge_token = effect.token
                merge_within_s = 30.0
            with self._session.log.transaction(
                effect.label, merge_token=merge_token, merge_within_s=merge_within_s
            ) as txn:
                for command in effect.commands:
                    fields = getattr(command, "__dataclass_fields__", {})
                    stamped = replace(command, merge_token=effect.token) if "merge_token" in fields else command
                    txn.execute(stamped)
        except CommandRejected as exc:
            self._host.narrate(str(exc))
            return
        if effect.label in ("Drop", "Move"):
            self._view.setFocus()
        if effect.edit:
            self._pending_edit = effect
            self._pending_page = None
            QTimer.singleShot(0, self._open_edit_now)

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
            target = text_target(self._session.document, page, "page_tab")
            token = str(self._serial)
        elif effect is not None and effect.edit == "widget":
            current = self._session.selection.state.current
            target = None if current is None else text_target(self._session.document, current, "widget")
            token = effect.token
        else:
            return
        if target is None:
            return
        self._gesture = Editing(target, token)
        self._editor.open(target, self._stage.view_map())
        self._request_frame()

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
        finder = getattr(self._host, "outline_target", None)
        if finder is None:
            return None
        global_pos = self._view.viewport().mapToGlobal(QPoint(event.port.x, event.port.y))
        target = finder(global_pos)
        if target is None:
            return None
        self._gesture = replace(self._gesture, target=target, outside=False, draw=False)
        if isinstance(target, NoDrop):
            return ""
        return str(getattr(target, "sentence", ""))

    def _sync_drag(self, previous: Gesture, current: Gesture) -> None:
        if isinstance(current, Placing) and not isinstance(previous, Placing):
            self._grab(current)
            self._fade(current.payload.source_ids, 0.35)
            self._remember_refusal(previous, current)
        elif isinstance(previous, Placing) and not isinstance(current, Placing):
            self._fade(previous.payload.source_ids, 1.0)
            self._ghost = None
            self._spring.stop()
            self._spring_id = None
            self._remember_refusal(previous, current)
        elif isinstance(current, Placing):
            self._arm_spring(current)

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
        if isinstance(current, Placing) and isinstance(current.target, RefusedDrop):
            sentence = current.target.sentence
            previous_sentence = (
                previous.target.sentence
                if isinstance(previous, Placing) and isinstance(previous.target, RefusedDrop)
                else None
            )
            now = time.monotonic()
            if sentence != previous_sentence:
                if self._refused == sentence and now - self._refused_at <= 5.0:
                    toast = getattr(self._host, "show_plain", None)
                    if toast is not None:
                        toast(sentence)
                self._refused = sentence
                self._refused_at = now
            return
        if isinstance(previous, Placing) and isinstance(previous.target, RefusedDrop):
            self._refused = previous.target.sentence
            self._refused_at = time.monotonic()

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

    def _show_stacked(self, container: NodeId, delta: int) -> None:
        if delta == 0:
            return
        widget = self._realizer.widget_for(container)
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
            if isinstance(item, Chip) and item.tip and item.rect.contains(event.at):
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
        pending = self._pending_reveal
        self._pending_reveal = None
        if pending is not None:
            rect = self._index.rect_of(pending)
            if rect is not None:
                self._stage.run(Reveal(rect))
                self._editor.follow(self._stage.view_map())
        self._rebuild(static=self._static_stale())
        self._view.viewport().update()

    def _static_stale(self) -> bool:
        view = self._stage.view_map()
        return self._static is None or self._static.epoch != self._index.epoch or self._static.view != view

    def _rebuild(self, static: bool) -> None:
        view = self._stage.view_map()
        if static or self._static is None:
            self._static = build_static(self._session.document, self._index, view)
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
                dict(self._shown_page),
            ),
        )

    def refresh_overlay(self) -> None:
        if self._closed:
            return
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

    def _on_selection(self, change: SelectionChange) -> None:
        self._announce_selection(change.after)
        if change.source in REVEAL_SOURCES and change.after.current is not None:
            self._pending_reveal = change.after.current
        self._request_frame()

    def _announce_selection(self, state: SelectionState) -> None:
        shown = effective_selection(self._session.document, state)
        self._stage.set_form_selected(shown.current == self._session.document.root.id)
        self._view.setAccessibleDescription(describe_selection(self._session.document, state))

    def _on_diagnostics(self, _items: object) -> None:
        self._problems_revision += 1
        self._request_frame()

    def _on_editor_done(self, done: EditorDone) -> None:
        self._feed(done)

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
    ) -> Optional[Tuple[Optional[SizingWord], Optional[SizingWord]]]:
        current = effective_selection(self._session.document, selection).current
        if current is None:
            return None
        widget = self._realizer.widget_for(current)
        if widget is None:
            return None
        policy = widget.sizePolicy()
        return (
            sizing_word(_policy_name(policy.horizontalPolicy()), _axis_fixed(widget, True)),
            sizing_word(_policy_name(policy.verticalPolicy()), _axis_fixed(widget, False)),
        )

    def _measure(self, text: str) -> int:
        font = QFont(self._view.font())
        font.setPixelSize(11)
        font.setBold(True)
        metrics = QFontMetrics(font)
        advance = getattr(metrics, "horizontalAdvance", None)
        if advance is None:
            return int(metrics.width(text))
        return int(advance(text))


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


def _policy_name(value: object) -> str:
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name
    return str(value).rsplit(".", 1)[-1]


def _axis_fixed(widget: QWidget, horizontal: bool) -> bool:
    minimum = widget.minimumSize()
    maximum = widget.maximumSize()
    if horizontal:
        return minimum.width() == maximum.width() and maximum.width() < _QT_MAX
    return minimum.height() == maximum.height() and maximum.height() < _QT_MAX
