"""The Tab order and Buddies overlays of one form tab (UX-OVL-001 .. 008, UX-MODE-001 .. 004).

Overlays are never sticky: Esc, F3, Done, a structural change and a tab switch
close them. Only one is open at a time. The marks are canvas layers
(``qtside/canvas/layers/tab_order.py`` and ``buddies.py``); this module owns
the state, the clicks and keys the canvas hands over while an overlay is open,
and the commands they run.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional, Tuple

from app.features.form_builder.engine.commands.catalog_ext.tab_order import ChangeTabOrder, PairLabels, SetLabelBuddy
from app.features.form_builder.engine.events import PRIORITY_VIEWS, ChangeSet
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query import tab_stops as q
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.query.tree import effective_tab_order, takes_tab_focus
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.qtside.canvas.layers.buddies import BuddyState
from app.features.form_builder.qtside.canvas.layers.tab_order import TabOrderState
from app.qt.QtCore import QEvent, QPoint, Qt
from app.qt.QtGui import QKeyEvent, QMouseEvent
from app.qt.QtWidgets import QLabel
from app.qt.qt_compat import enum_value, event_pos

logger = logging.getLogger(__name__)

TAB_ORDER = "tab_order"
BUDDIES = "buddies"

TAB_SENTENCE = "Click the fields in the order Tab should visit them. Shift+click continues from one."
BUDDY_SENTENCE = "Drag from a label to its field, or pick a label and press Enter."
RESET_LABEL = "Reset to reading order"
PAIR_LABEL = "Pair labels automatically"
_DRAG_START = 6


def press_sentence(name: str, number: int) -> str:
    return "Press Enter to make %s number %d." % (name, number)


def choose_sentence(label_text: str) -> str:
    return "Choose the field for “%s”, then press Enter." % label_text


def paired_sentence(count: int) -> str:
    return "Paired %d label%s" % (count, "" if count == 1 else "s")


class LabelMetrics:
    """Where a label's words sit inside the label, for the link start of UX-OVL-007."""

    def __init__(self, realizer: Any, document: Callable[[], Any]) -> None:
        self._realizer = realizer
        self._document = document

    def text_box(self, label_name: str) -> Optional[Tuple[float, float]]:
        document = self._document()
        found = document.by_name(label_name)
        widget = self._realizer.widget_for(found[0]) if found else None
        if not isinstance(widget, QLabel):
            return None
        text = widget.text().replace("&&", "\0").replace("&", "").replace("\0", "&")
        if not text:
            return None
        metrics = widget.fontMetrics()
        longest = max((metrics.horizontalAdvance(line) for line in text.splitlines() or [text]), default=0)
        area = widget.contentsRect()
        width = min(longest, area.width())
        flags = widget.alignment()
        if flags & Qt.AlignmentFlag.AlignRight:
            left = area.right() - width + 1
        elif flags & Qt.AlignmentFlag.AlignHCenter:
            left = area.left() + (area.width() - width) // 2
        else:
            left = area.left()
        return (float(left), float(width))


class OverlayModes:
    """Tab order and Buddies for one form tab. ``surface`` is the ``FormSurface``."""

    def __init__(self, surface: Any) -> None:
        self._surface = surface
        self._session = surface.session
        self._kind = ""
        self._token = 0
        # Tab order session.
        self._picked: List[str] = []
        self._base: Tuple[str, ...] = ()
        self._orig: Optional[Tuple[str, ...]] = None
        self._hover = ""
        # Buddies session.
        self._active: Optional[NodeId] = None
        self._candidate = ""
        self._pointer: Optional[Tuple[int, int]] = None
        self._press_at: Optional[QPoint] = None
        self._press_node: Optional[NodeId] = None
        self._dragging = False
        self._unlink: Optional[NodeId] = None
        self._metrics = LabelMetrics(surface.realizer, lambda: self._session.document)
        self._changes = self._session.log.subscribe(self._on_change, priority=PRIORITY_VIEWS)
        self._selection = self._session.selection.subscribe(self._on_selection)

    # ------------------------------------------------------------------ state

    @property
    def active(self) -> str:
        """``""``, ``"tab_order"`` or ``"buddies"``."""
        return self._kind

    @property
    def picked(self) -> Tuple[str, ...]:
        return tuple(self._picked)

    @property
    def linking(self) -> str:
        """The label a link is being made from, as its object name, or ``""``."""
        node = self._session.document.get(self._active) if self._active is not None else None
        return node.object_name if isinstance(node, WidgetNode) else ""

    @property
    def _canvas(self) -> Any:
        return self._surface.workbench.canvas

    def dispose(self) -> None:
        self.close()
        self._changes.close()
        self._selection()

    # ---------------------------------------------------------------- open/close

    def toggle(self, kind: str) -> None:
        if self._kind == kind:
            self.close()
        else:
            self.open(kind)

    def open(self, kind: str) -> bool:
        if kind not in (TAB_ORDER, BUDDIES) or not self._surface.can_use_overlays():
            return False
        if self._kind == kind:
            return True
        if self._kind:
            self.close()
        self._kind = kind
        self._token += 1
        self._picked = []
        self._hover = ""
        self._active = None
        self._candidate = ""
        self._pointer = None
        self._unlink = None
        canvas = self._canvas
        canvas.set_claimer(self.claim)
        if kind == TAB_ORDER:
            document = self._session.document
            self._base = effective_tab_order(document)
            saved = document.tabstops()
            self._orig = None if saved is None else tuple(saved)
            canvas.show_banner("tab_order", "Tab order", TAB_SENTENCE, RESET_LABEL, self.reset_order, self.close)
        else:
            canvas.show_banner("buddy", "Buddies", BUDDY_SENTENCE, PAIR_LABEL, self.pair_labels, self.close)
        self._surface.style_banner()
        self._push()
        self._sync_toggles()
        canvas.setFocus()
        self._announce()
        return True

    def close(self) -> None:
        if not self._kind:
            return
        kind = self._kind
        self._kind = ""
        canvas = self._canvas
        canvas.hide_layer(kind)
        canvas.set_claimer(None)
        canvas.hide_banner()
        self._picked = []
        self._active = None
        self._candidate = ""
        self._pointer = None
        self._hover = ""
        self._dragging = False
        self._sync_toggles()
        self._surface.set_overlay_status("")

    def escape(self) -> bool:
        """Esc: cancel a link in progress, else close the overlay. False when none is open."""
        if not self._kind:
            return False
        if self._kind == BUDDIES and self._active is not None:
            self._active = None
            self._candidate = ""
            self._pointer = None
            self._dragging = False
            self._push()
            self._announce()
            return True
        self.close()
        self._canvas.setFocus()
        return True

    def _sync_toggles(self) -> None:
        self._surface.sync_overlay_toggles(self._kind)

    # ------------------------------------------------------------------ marks

    def _push(self) -> None:
        if self._kind == TAB_ORDER:
            order = effective_tab_order(self._session.document)
            self._canvas.show_layer(TAB_ORDER, TabOrderState(order, len(self._picked), self._hover))
        elif self._kind == BUDDIES:
            self._canvas.show_layer(
                BUDDIES, BuddyState(self._metrics, self.linking, self._candidate, self._pointer)
            )

    def _on_change(self, changeset: ChangeSet) -> None:
        if not self._kind:
            return
        if changeset.replaced or changeset.added or changeset.removed or changeset.structure_dirty:
            self.close()
            return
        self._push()
        self._announce()

    def _on_selection(self, _change: object) -> None:
        if self._kind:
            self._announce()

    def _announce(self) -> None:
        if not self._kind:
            return
        document = self._session.document
        current = self._session.selection.state.current
        node = document.get(current) if current is not None else None
        name = node.object_name if isinstance(node, WidgetNode) else ""
        sentence = ""
        if self._kind == TAB_ORDER:
            if name and isinstance(node, WidgetNode) and takes_tab_focus(node):
                if name in self._picked:
                    sentence = "%s is number %d." % (name, self._picked.index(name) + 1)
                else:
                    sentence = press_sentence(name, len(self._picked) + 1)
            elif name:
                sentence = "%s doesn't take Tab, so it has no number." % name
        else:
            if self._active is not None:
                sentence = choose_sentence(q.caption(document, self._active))
            elif current is not None and q.is_label(document, current):
                sentence = "Press Enter to choose the field for “%s”." % q.caption(document, current)
        self._surface.set_overlay_status(sentence)

    # --------------------------------------------------------------- tab order

    def _write_order(self, names: Optional[Tuple[str, ...]]) -> None:
        from app.features.form_builder.engine.commands.base import CommandRejected

        try:
            self._session.log.execute(ChangeTabOrder(names, merge_token="tab-order-%d" % self._token))
        except CommandRejected:
            logger.exception("tab order was refused")

    def _stop_name(self, node_id: Optional[NodeId]) -> str:
        node = self._session.document.get(node_id) if node_id is not None else None
        if isinstance(node, WidgetNode) and node.object_name and takes_tab_focus(node):
            return node.object_name
        return ""

    def assign(self, name: str) -> bool:
        """Give ``name`` the next number (UX-OVL-005)."""
        if not name:
            return False
        if name in self._picked:
            self._surface.set_overlay_status("%s is number %d." % (name, self._picked.index(name) + 1))
            return False
        self._picked.append(name)
        self._write_order(q.order_after_picks(self._base, tuple(self._picked)))
        self._push()
        self._announce()
        return True

    def continue_from(self, name: str) -> bool:
        """Numbering goes on after ``name`` (Shift+click, Shift+Enter)."""
        order = effective_tab_order(self._session.document)
        prefix = q.picks_through(order, name)
        if not prefix:
            return False
        self._picked = list(prefix)
        self._push()
        self._announce()
        return True

    def undo_last(self) -> bool:
        """Backspace: take back the last number of this session."""
        if not self._picked:
            return False
        self._picked.pop()
        if self._picked:
            self._write_order(q.order_after_picks(self._base, tuple(self._picked)))
        else:
            self._write_order(self._orig)
        self._push()
        self._announce()
        return True

    def reset_order(self) -> None:
        """"Reset to reading order": deletes ``<tabstops>`` (UX-OVL-005)."""
        if self._kind != TAB_ORDER:
            return
        self._picked = []
        self._write_order(None)
        self._base = effective_tab_order(self._session.document)
        self._push()
        self._announce()

    # ----------------------------------------------------------------- buddies

    def pair_labels(self) -> int:
        pairs = q.form_row_pairs(self._session.document)
        outcome = self._session.log.execute(PairLabels(pairs, merge_token=None))
        count = int(outcome.result or 0)
        self._surface.set_overlay_status(paired_sentence(count))
        self._surface.show_plain(paired_sentence(count))
        self._push()
        return count

    def start_link(self, label: NodeId) -> bool:
        document = self._session.document
        if not q.is_label(document, label):
            return False
        self._active = label
        existing = q.buddy_of(document, label)
        choices = [stop.name for stop in q.buddy_choices(document)]
        self._candidate = existing if existing in choices else (choices[0] if choices else "")
        self._push()
        self._announce()
        return True

    def step_candidate(self, delta: int) -> None:
        choices = [stop.name for stop in q.buddy_choices(self._session.document)]
        if not choices:
            return
        try:
            at = choices.index(self._candidate)
        except ValueError:
            at = -1 if delta > 0 else 0
        self._candidate = choices[(at + delta) % len(choices)]
        self._push()

    def set_buddy(self, label: NodeId, target: Optional[str]) -> None:
        document = self._session.document
        if q.buddy_of(document, label) == target:
            return
        self._session.log.execute(SetLabelBuddy(label, target, q.caption(document, label)))

    def finish_link(self) -> None:
        label = self._active
        if label is None or not self._candidate:
            return
        self.set_buddy(label, self._candidate)
        self._active = None
        self._candidate = ""
        self._pointer = None
        self._push()
        self._announce()

    # ------------------------------------------------------------------ events

    def claim(self, event: QEvent) -> bool:
        """The canvas offers every event first while an overlay is open. True consumes it."""
        if not self._kind:
            return False
        kind = enum_value(event.type())
        kinds = getattr(QEvent, "Type", QEvent)
        if kind in (enum_value(kinds.KeyPress), enum_value(kinds.ShortcutOverride)) and isinstance(event, QKeyEvent):
            return self._claim_key(event, kind == enum_value(kinds.ShortcutOverride))
        if isinstance(event, QMouseEvent):
            if kind in (enum_value(kinds.MouseButtonPress), enum_value(kinds.MouseButtonDblClick)):
                return self._claim_press(event)
            if kind == enum_value(kinds.MouseMove):
                return self._claim_move(event)
            if kind == enum_value(kinds.MouseButtonRelease):
                return self._claim_release(event)
        if kind == enum_value(kinds.Leave) and self._hover:
            self._hover = ""
            self._push()
        return False

    def _claim_key(self, event: QKeyEvent, override: bool) -> bool:
        keys = Qt.Key
        key = enum_value(event.key())
        shift = bool(enum_value(event.modifiers()) & enum_value(Qt.KeyboardModifier.ShiftModifier))
        other = bool(
            enum_value(event.modifiers())
            & (enum_value(Qt.KeyboardModifier.ControlModifier) | enum_value(Qt.KeyboardModifier.AltModifier))
        )
        if other:
            return False
        enter = key in (enum_value(keys.Key_Return), enum_value(keys.Key_Enter))
        escape = key == enum_value(keys.Key_Escape)
        backspace = key == enum_value(keys.Key_Backspace)
        walking = key in (
            enum_value(keys.Key_Tab),
            enum_value(keys.Key_Backtab),
            enum_value(keys.Key_Left),
            enum_value(keys.Key_Right),
            enum_value(keys.Key_Up),
            enum_value(keys.Key_Down),
        )
        if self._kind == TAB_ORDER:
            mine = enter or escape or backspace
        else:
            mine = enter or escape or (walking and self._active is not None)
        if not mine:
            return False
        if override:
            return True
        if escape:
            self.escape()
            return True
        current = self._session.selection.state.current
        if self._kind == TAB_ORDER:
            if backspace:
                self.undo_last()
                return True
            name = self._stop_name(current)
            if not name:
                self._announce()
                return True
            if shift:
                self.continue_from(name)
            else:
                self.assign(name)
            return True
        if walking:
            backwards = shift or key in (
                enum_value(keys.Key_Backtab),
                enum_value(keys.Key_Left),
                enum_value(keys.Key_Up),
            )
            self.step_candidate(-1 if backwards else 1)
            return True
        if self._active is not None:
            self.finish_link()
        elif current is not None:
            self.start_link(current)
        return True

    def _position(self, event: QMouseEvent) -> QPoint:
        return event_pos(event)

    def _left(self, event: QMouseEvent) -> bool:
        return enum_value(event.button()) == enum_value(Qt.MouseButton.LeftButton)

    def _claim_press(self, event: QMouseEvent) -> bool:
        if not self._left(event):
            return False
        pos = self._position(event)
        node = self._canvas.node_at(pos)
        if self._kind == TAB_ORDER:
            name = self._stop_name(node)
            if node is not None:
                self._session.selection.set((node,), current=node, source=SelectionSource.CANVAS)
            if not name:
                self._announce()
                return True
            shift = bool(enum_value(event.modifiers()) & enum_value(Qt.KeyboardModifier.ShiftModifier))
            if shift:
                self.continue_from(name)
            else:
                self.assign(name)
            return True
        # Buddies.
        document = self._session.document
        self._press_at = pos
        self._press_node = node
        self._dragging = False
        self._unlink = None
        if node is None:
            ring = self._ring_at(pos)
            if ring is not None:
                self.start_link(ring)
                self._press_node = ring
            return True
        if self._active is not None and self._stop_name(node) and not q.is_label(document, node):
            self._candidate = self._stop_name(node)
            self.finish_link()
            self._press_node = None
            return True
        if q.is_label(document, node):
            self._session.selection.set((node,), current=node, source=SelectionSource.CANVAS)
            self.start_link(node)
            self._candidate = ""
            self._pointer = (pos.x(), pos.y())
            return True
        name = self._stop_name(node)
        if name:
            for label in q.labels(document):
                if q.buddy_of(document, label) == name:
                    self._unlink = label
                    break
        return True

    def _claim_move(self, event: QMouseEvent) -> bool:
        pos = self._position(event)
        if self._kind == TAB_ORDER:
            name = self._stop_name(self._canvas.node_at(pos))
            if name != self._hover:
                self._hover = name
                self._push()
            return False
        if self._press_at is not None and (self._active is not None or self._unlink is not None):
            if (pos - self._press_at).manhattanLength() >= _DRAG_START:
                self._dragging = True
            if self._active is not None:
                scene = self._canvas.mapToScene(pos)
                self._pointer = (int(scene.x()), int(scene.y()))
                target = self._stop_name(self._canvas.node_at(pos))
                self._candidate = target
                self._push()
            return True
        return False

    def _claim_release(self, event: QMouseEvent) -> bool:
        if not self._left(event):
            return False
        if self._kind == TAB_ORDER:
            return True
        pos = self._position(event)
        node = self._canvas.node_at(pos)
        target = self._stop_name(node) if node is not None and not q.is_label(self._session.document, node) else ""
        pressed = self._press_at is not None
        self._press_at = None
        if not pressed:
            return True
        if self._unlink is not None:
            label = self._unlink
            self._unlink = None
            if self._dragging:
                if target:
                    self.set_buddy(label, target)
                elif node is None or not self._stop_name(node):
                    self.set_buddy(label, None)
            self._dragging = False
            return True
        if self._active is not None and self._dragging:
            if target:
                self._candidate = target
                self.finish_link()
            else:
                self._active = None
                self._candidate = ""
                self._pointer = None
                self._push()
                self._announce()
            self._dragging = False
            return True
        self._dragging = False
        self._pointer = None
        self._push()
        return True

    def _ring_at(self, pos: QPoint) -> Optional[NodeId]:
        """The unpaired label whose ring is under ``pos``."""
        document = self._session.document
        for label in q.labels(document):
            if q.buddy_of(document, label):
                continue
            box = self._canvas.viewport_rect((label,))
            if box is None:
                continue
            centre_y = box.top() + box.height() // 2
            left = box.left() - 16
            if left <= pos.x() <= left + 16 and abs(pos.y() - centre_y) <= 8:
                return label
        return None
