"""The canvas's imperative shell.

Public surface: ``handle``, ``post``, ``frame``, ``dispose``. What the canvas
decides lives in ``core.gesture.step`` and ``core.overlay.build_frame``.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, FrozenSet, Optional, Protocol, Tuple

from app.qt.QtCore import QEvent
from app.qt.QtGui import QFont, QFontMetrics, QMouseEvent
from app.qt.QtWidgets import QApplication, QGraphicsView, QWidget
from app.qt.qt_compat import event_global_pos

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.diagnostics import Severity
from app.features.form_builder.engine.events import PRIORITY_VIEWS, ChangeSet
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.hit_index import GeoEntry, HitIndex
from app.features.form_builder.engine.query.slots import DropPaint, Point
from app.features.form_builder.engine.query.selection import SelectionChange, SelectionSource, SelectionState
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.qtside.canvas import _input
from app.features.form_builder.qtside.canvas.core.frame import (
    OpenLayoutPopover,
    OpenProblem,
    OverlayFrame,
)
from app.features.form_builder.qtside.canvas.core.gesture import (
    ArmSlot,
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
    Narrate,
    NudgeSlots,
    OpenEditor,
    Press,
    Preview,
    PreviewPage,
    Reveal,
    RunChipAction,
    ScrollBy,
    Select,
    SlotCancel,
    SlotPointer,
    SlotRelease,
    Tip,
    Toggle,
    World,
    Yielded,
    Zoom,
    needs_fresh_geometry,
    previewing,
    step,
)
from app.features.form_builder.qtside.canvas.core.overlay import (
    FrameInputs,
    StaticLayer,
    build_frame,
    build_static,
    frame_basis,
)
from app.features.form_builder.qtside.canvas.core.structure import effective_selection
from app.features.form_builder.qtside.canvas.core.text import text_target
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

    def arm_slot(self, effect: ArmSlot) -> None:
        ...

    def slot_pointer(self, effect: SlotPointer) -> None:
        ...

    def slot_release(self) -> None:
        ...

    def slot_cancel(self) -> None:
        ...

    def nudge_slots(self, key: str) -> None:
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
        self._drop_paint: Optional[DropPaint] = None
        self._pointer_global = Point(0, 0)
        self._closed = False
        self._editor = InPlaceEditor(view.viewport(), realizer, self._on_editor_done)
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
        if isinstance(event, QMouseEvent):
            pos = event_global_pos(event)
            self._pointer_global = Point(int(pos.x()), int(pos.y()))
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
        result = step(self._gesture, event, self._world())
        self._gesture = result.gesture
        for effect in result.effects:
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
            self._editor.open(effect.target, self._stage.view_map())
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
        if isinstance(effect, ArmSlot):
            self._host.arm_slot(effect)
            return
        if isinstance(effect, SlotPointer):
            self._host.slot_pointer(replace(effect, global_at=self._pointer_global))
            return
        if isinstance(effect, SlotRelease):
            self._host.slot_release()
            return
        if isinstance(effect, SlotCancel):
            self._host.slot_cancel()
            return
        if isinstance(effect, NudgeSlots):
            self._host.nudge_slots(effect.key)
            return
        raise AssertionError(type(effect))

    def _commit(self, effect: Commit) -> None:
        try:
            merge_token = None
            merge_within_s = 0.0
            if effect.label == "Nudge":
                merge_token = "nudge:" + ",".join(str(command.id) for command in effect.commands)
                merge_within_s = 1.0
            elif effect.label == "Edit text":
                merge_token = effect.token
            with self._session.log.transaction(
                effect.label, merge_token=merge_token, merge_within_s=merge_within_s
            ) as txn:
                for command in effect.commands:
                    txn.execute(replace(command, merge_token=effect.token))
        except CommandRejected as exc:
            self._host.narrate(str(exc))

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
                self._drop_paint,
            ),
        )

    def edit_for_join(self, node: NodeId, token: str) -> None:
        """Open the in-place editor on ``node`` and enter ``Editing`` with ``token``. Do not mint another."""
        target = text_target(self._session.document, node, "widget")
        if target is None:
            return
        self._gesture = Editing(target, token)
        self._editor.open(target, self._stage.view_map())
        self._request_frame()

    def geometry_entries(self) -> Tuple[GeoEntry, ...]:
        self._index.ensure_fresh()
        return self._index.geometry()

    def set_drop_paint(self, paint: Optional[DropPaint]) -> None:
        self._drop_paint = paint
        self._request_frame()

    def slot_open(self) -> bool:
        return isinstance(self._gesture, Yielded)

    def end_slot(self) -> None:
        if isinstance(self._gesture, Yielded):
            self._gesture = Idle()

    def pointer_global(self) -> Point:
        return self._pointer_global

    def refresh_overlay(self) -> None:
        if self._closed:
            return
        self._request_frame()

    def _before_realize(self, changeset: ChangeSet) -> None:
        if not changeset.replaced:
            return
        if isinstance(self._gesture, Yielded):
            self._run(SlotCancel())
        self._stage.detach()
        self._editor.close(False)
        self._gesture = Idle()

    def _after_realize(self, changeset: ChangeSet) -> None:
        self._place_and_report()
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


def _mints_token(gesture: Gesture, event: Event) -> bool:
    if isinstance(event, Press):
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
