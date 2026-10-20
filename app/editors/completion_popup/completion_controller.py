"""Completion popup behavior shared by the code editor and the Python Console.

The host widget owns the text. The controller owns everything else: when the
list opens, the member list cached for the current expression, matching and
ranking as the user types, when the list closes, and when Backspace reopens it.

Rules (owner approved for v0.4.13):

* Off: nothing opens; Ctrl+Space shows a status hint.
* Manual: only Ctrl+Space opens the list, never ``.`` by itself.
* While typing: ``.`` after a name, or the second letter of a name, opens it.
* Never inside strings or comments, or after a digit-dot, in any mode.
* The list closes when nothing matches and when the whole name is typed;
  Backspace in the same expression reopens it from the cached list.
  Esc closes it for good: a following Backspace does not reopen it.
* Tab and Enter accept and replace only the typed prefix.
"""

from __future__ import annotations

from contextlib import contextmanager
import time
from typing import Any, Dict, Iterator, List, Optional, Protocol, Tuple

from PySide2.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer, Signal
from PySide2.QtGui import QFontMetrics, QKeyEvent
from PySide2.QtWidgets import QApplication, QWidget

from app.core.completion_tier import is_tier_header_item
from app.editors.completion_popup.completion_item_delegate import CHIP_GAP, CHIP_LEFT, CHIP_SIZE
from app.editors.completion_popup.completion_item_model import CompletionItemModel, row_short_type
from app.editors.completion_popup.completion_popup_container import OUTER_MARGINS, CompletionPopupContainer
from app.intelligence.completion_matcher import (
    ACCEPTANCE_RECENCY,
    filter_and_rank,
    typed_full_name,
)
from app.intelligence.completion_mode import (
    COMPLETION_MODE_DEFAULT,
    COMPLETION_MODE_OFF,
    COMPLETION_OFF_HINT,
    normalize_completion_mode,
)
from app.intelligence.completion_models import CompletionItem
from app.intelligence.completion_site import (
    BLOCKED_COMMENT,
    BLOCKED_NUMBER,
    BLOCKED_NUMERIC_DOT,
    BLOCKED_STRING,
    SITE_MEMBER,
    CompletionSite,
    completion_site,
    should_open_while_typing,
)
from app.shell.theme_tokens import ShellThemeTokens

MIN_LIST_WIDTH = 240
MAX_LIST_WIDTH = 560
NARROW_MIN_QUERY = 3
FOOTER_HINT = "Tab insert · Esc close"
_METRICS_LIMIT = 200

_BLOCKED_HINTS = {
    BLOCKED_STRING: "No completions inside a string.",
    BLOCKED_COMMENT: "No completions inside a comment.",
    BLOCKED_NUMERIC_DOT: "No completions after a number.",
    BLOCKED_NUMBER: "No completions after a number.",
}

CLOSE_ESCAPE = "escape"
CLOSE_ACCEPTED = "accepted"
CLOSE_NO_MATCH = "no_match"
CLOSE_TYPED_FULL_NAME = "typed_full_name"
CLOSE_LEFT_EXPRESSION = "left_expression"
CLOSE_MODE = "mode_changed"
CLOSE_CLICK_AWAY = "click_away"


class CompletionHost(Protocol):
    """What the controller needs from the widget that owns the text."""

    def completion_text_and_cursor(self) -> Tuple[str, int]:
        """Return the completable text and the cursor offset in it."""

    def completion_anchor_rect(self, position: int) -> QRect:
        """Return the cursor rect for ``position`` in host widget coordinates."""

    def completion_dispatch(self, text: str, cursor: int, trigger_kind: str, trigger_character: str) -> int:
        """Start an async list request at ``cursor`` and return its generation."""

    def completion_status(self, message: str) -> None:
        """Show a short status-bar hint."""


class _Pending:
    def __init__(self, generation: int, key: Tuple[str, int, str], root: str, started_at: float) -> None:
        self.generation = generation
        self.key = key
        self.root = root
        self.started_at = started_at


class CompletionController(QObject):
    """Owns the popup, its rows and the open / filter / close rules."""

    activated: Any = Signal(object)
    selection_changed: Any = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._widget: QWidget | None = None
        self._host: CompletionHost | None = None
        self._mode = COMPLETION_MODE_DEFAULT
        self._model = CompletionItemModel(self)
        popup_parent = parent if isinstance(parent, QWidget) else None
        self._popup = CompletionPopupContainer(popup_parent)
        list_view = self._popup.list_view()
        list_view.setModel(self._model)
        list_view.doubleClicked.connect(lambda _index: self.accept_current())
        list_view.current_item_changed.connect(self._on_current_item_changed)
        self._popup.installEventFilter(self)
        self._popup.closed.connect(self._on_popup_closed)

        self._site: Optional[CompletionSite] = None
        self._pending: Optional[_Pending] = None
        self._base_items: List[CompletionItem] = []
        self._base_names: List[str] = []
        self._base_key: Optional[Tuple[str, int, str]] = None
        self._base_root = ""
        self._list_width = MIN_LIST_WIDTH
        self._narrow_query: Optional[str] = None
        self._narrow_matches: List[int] = []
        self._user_moved_selection = False
        self._reopen_key: Optional[Tuple[str, int, str]] = None
        self._closing_internally = False
        self._editing_depth = 0
        self._selection_started_at = 0.0
        self._last_selection_label = ""
        self.metrics: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def set_widget(self, widget: QWidget | None) -> None:
        """Attach the widget used for placement and as the popup focus proxy."""

        self._widget = widget
        self._popup.setFocusProxy(widget)

    def set_host(self, host: CompletionHost | None) -> None:
        self._host = host

    def widget(self) -> QWidget | None:
        return self._widget

    def model(self) -> CompletionItemModel:
        return self._model

    def popup(self) -> CompletionPopupContainer:
        return self._popup

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self._model.set_theme_tokens(tokens)
        self._popup.apply_theme(tokens)

    def set_mode(self, mode: str) -> None:
        normalized = normalize_completion_mode(mode) or COMPLETION_MODE_DEFAULT
        if normalized == self._mode:
            return
        self._mode = normalized
        self._close(CLOSE_MODE)
        self._forget_expression()

    def mode(self) -> str:
        return self._mode

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    def is_visible(self) -> bool:
        return self._popup.isVisible()

    def is_pending(self) -> bool:
        return self._pending is not None

    def current_item(self) -> CompletionItem | None:
        return self._popup.list_view().current_item()

    def visible_labels(self, limit: int = 12) -> List[str]:
        return self._model.labels()[:limit]

    def total_count(self) -> int:
        return len(self._base_items)

    def site(self) -> Optional[CompletionSite]:
        return self._site

    # ------------------------------------------------------------------
    # Host entry points
    # ------------------------------------------------------------------

    @contextmanager
    def editing(self) -> Iterator[None]:
        """Wrap the host's own key handling so cursor moves are not mistaken for clicks."""

        self._editing_depth += 1
        try:
            yield
        finally:
            self._editing_depth -= 1

    def handle_key_press(self, event: QKeyEvent) -> bool:
        """Handle popup keys and Ctrl+Space before the host sees ``event``."""

        key = event.key()
        modifiers = event.modifiers()
        if key == Qt.Key_Space and modifiers & Qt.ControlModifier:
            if self.is_visible():
                self._popup.set_docs_visible(not self._popup.docs_visible())
                self._place()
            else:
                self.open_manual()
            event.accept()
            return True
        if not self.is_visible():
            return False
        if key == Qt.Key_Escape:
            self._close(CLOSE_ESCAPE)
            self._forget_expression()
            event.accept()
            return True
        if key in (Qt.Key_Tab, Qt.Key_Return, Qt.Key_Enter) and not modifiers & Qt.ShiftModifier:
            self.accept_current()
            event.accept()
            return True
        if key in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown):
            self._popup.list_view().move_selection(key)
            self._user_moved_selection = True
            event.accept()
            return True
        return False

    def open_manual(self) -> None:
        """Ctrl+Space: open the list here, or explain why it cannot open."""

        if self._mode == COMPLETION_MODE_OFF:
            self._status(COMPLETION_OFF_HINT)
            return
        self._open(trigger_kind="manual", trigger_character="", manual=True)

    def after_text_input(self, inserted_text: str) -> None:
        """Call after the host inserted ``inserted_text`` at the cursor."""

        if not inserted_text:
            return
        is_word = inserted_text.isalnum() or inserted_text == "_"
        if self.is_visible() or self._pending is not None:
            if is_word:
                site = self._live_site(check_strings=False)
                if site is not None and site.key == self._active_key():
                    self._site = site
                    if self.is_visible():
                        self._refilter(site.prefix, event="filter")
                    return
            self._close(CLOSE_LEFT_EXPRESSION)
            self._forget_expression()
        elif not is_word:
            self._forget_expression()
        elif self._reopen_key is not None:
            site = self._live_site(check_strings=False)
            if site is None or site.key != self._reopen_key:
                self._forget_expression()
        if self.is_visible() or self._mode == COMPLETION_MODE_OFF:
            return
        site = self._live_site(check_strings=True)
        if site is not None and should_open_while_typing(self._mode, site, inserted_text):
            trigger_kind = "trigger_character" if inserted_text == "." else "typing"
            self._open(trigger_kind=trigger_kind, trigger_character=inserted_text if inserted_text == "." else "")

    def after_backspace(self) -> None:
        """Call after the host deleted text before the cursor."""

        site = self._live_site(check_strings=False)
        if self.is_visible():
            if site is not None and site.key == self._active_key() and self._root_allows(site.prefix):
                self._site = site
                self._refilter(site.prefix, event="backspace_filter")
                return
            self._close(CLOSE_LEFT_EXPRESSION)
            self._forget_expression()
            return
        if (
            site is not None
            and self._reopen_key is not None
            and site.key == self._reopen_key
            and self._base_items
            and self._root_allows(site.prefix)
        ):
            self._site = site
            self._refilter(site.prefix, event="backspace_reopen", started_at=time.perf_counter())
            return
        if self._pending is not None:
            if site is not None and site.key == self._pending.key and self._root_allows(site.prefix):
                return
            self._forget_expression()
            return
        if site is None or site.key != self._reopen_key:
            self._forget_expression()

    def on_cursor_moved(self) -> None:
        """Close the list when the cursor leaves the expression (arrow keys, clicks)."""

        if self._editing_depth > 0:
            return
        if not self.is_visible() and self._pending is None and self._reopen_key is None:
            return
        site = self._live_site(check_strings=False)
        key = self._active_key() if (self.is_visible() or self._pending is not None) else self._reopen_key
        if site is None or site.key != key or not self._root_allows(site.prefix):
            self._close(CLOSE_LEFT_EXPRESSION)
            self._forget_expression()
            return
        if self.is_visible() and self._site is not None and site.prefix != self._site.prefix:
            self._site = site
            self._refilter(site.prefix, event="cursor_filter")

    def deliver_items(self, generation: int, items: List[CompletionItem]) -> None:
        """Apply an async list result if it still belongs to the open request."""

        pending = self._pending
        if pending is None or generation != pending.generation:
            return
        site = self._live_site(check_strings=False)
        if site is None or site.key != pending.key or not site.prefix.lower().startswith(pending.root.lower()):
            return
        self._set_base(items, key=pending.key, root=pending.root)
        if not self._base_items:
            return
        first_delivery = not self.is_visible() and self._site is None
        self._site = site
        self._refilter(
            site.prefix,
            event="open" if first_delivery else "update",
            started_at=pending.started_at if first_delivery else 0.0,
        )

    def replace_item(self, item: CompletionItem) -> bool:
        """Apply lazily resolved docs for one row."""

        replaced = self._model.replace_item(item)
        for index, existing in enumerate(self._base_items):
            if existing.label == item.label:
                self._base_items[index] = item
                break
        current = self.current_item()
        if replaced and current is not None and current.label == item.label:
            docs = self._popup.docs_panel()
            docs.set_item(item)
            if self._selection_started_at:
                self._record(
                    "docs",
                    label=item.label,
                    docs_ms=round((time.perf_counter() - self._selection_started_at) * 1000.0, 3),
                )
                self._selection_started_at = 0.0
        return replaced

    def set_docs_resolving(self, resolving: bool) -> None:
        self._popup.docs_panel().set_resolving(resolving)

    def accept_current(self) -> None:
        item = self.current_item()
        self._close(CLOSE_ACCEPTED)
        self._forget_expression()
        if item is None:
            return
        ACCEPTANCE_RECENCY.note_accepted(item.label)
        self.activated.emit(item)

    def hide(self) -> None:
        """Close the list and forget the expression (host-driven resets)."""

        self._close(CLOSE_ESCAPE)
        self._forget_expression()

    def clear(self) -> None:
        self.hide()
        self._model.clear()

    # ------------------------------------------------------------------
    # Opening and filtering
    # ------------------------------------------------------------------

    def _open(self, *, trigger_kind: str, trigger_character: str, manual: bool = False) -> None:
        host = self._host
        if host is None:
            return
        started_at = time.perf_counter()
        text, cursor = host.completion_text_and_cursor()
        site = completion_site(text, cursor, check_strings=True)
        if not site.is_open_able:
            if manual and site.blocked in _BLOCKED_HINTS:
                self._status(_BLOCKED_HINTS[site.blocked])
            return
        if self._base_items and self._base_key == site.key and self._root_allows(site.prefix):
            self._site = site
            self._refilter(site.prefix, event="open_cached", started_at=started_at, manual=manual)
            return
        self._forget_expression()
        root = "" if site.kind == SITE_MEMBER else site.prefix[:1]
        generation = host.completion_dispatch(text, site.anchor + len(root), trigger_kind, trigger_character)
        self._pending = _Pending(generation, site.key, root, started_at)
        self._record("request", trigger=trigger_kind, prefix=site.prefix, kind=site.kind)

    def _set_base(self, items: List[CompletionItem], *, key: Tuple[str, int, str], root: str) -> None:
        seen: set = set()
        base: List[CompletionItem] = []
        for item in items:
            if is_tier_header_item(item) or not item.label or item.label in seen:
                continue
            seen.add(item.label)
            base.append(item)
        if base and base_labels_equal(self._base_items, base) and self._base_key == key:
            self._base_items = base
            return
        self._base_items = base
        self._base_names = [item.label for item in base]
        self._base_key = key
        self._base_root = root
        self._narrow_query = None
        self._narrow_matches = []
        self._list_width = self._width_for(base)

    def _refilter(self, query: str, *, event: str, started_at: float = 0.0, manual: bool = False) -> bool:
        started = time.perf_counter()
        candidates: Optional[List[int]] = None
        if (
            self.is_visible()
            and self._narrow_query is not None
            and len(self._narrow_query) >= NARROW_MIN_QUERY
            and query.startswith(self._narrow_query)
        ):
            candidates = self._narrow_matches
        matched: List[int] = []
        ranked = filter_and_rank(
            self._base_names,
            query,
            recent=ACCEPTANCE_RECENCY.snapshot(),
            candidates=candidates,
            matched_out=matched,
        )
        self._narrow_query = query
        self._narrow_matches = matched
        filter_ms = (time.perf_counter() - started) * 1000.0
        key = self._base_key
        if not ranked:
            self._close(CLOSE_NO_MATCH)
            self._reopen_key = key
            self._record(event, prefix=query, rows=0, filter_ms=round(filter_ms, 3), closed=CLOSE_NO_MATCH)
            return False
        if not event.startswith("open") and typed_full_name(self._base_names, query):
            self._close(CLOSE_TYPED_FULL_NAME)
            self._reopen_key = key
            self._record(event, prefix=query, rows=len(ranked), closed=CLOSE_TYPED_FULL_NAME)
            return False
        keep = ""
        current = self.current_item()
        if self.is_visible() and self._user_moved_selection and current is not None:
            keep = current.label
        items = [self._base_items[row.index] for row in ranked]
        self._model.set_rows(items, [row.positions for row in ranked])
        row = 0
        if keep:
            row = self._model.row_of_label(keep)
            if row < 0:
                row = 0
                self._user_moved_selection = False
        else:
            self._user_moved_selection = False
        self._popup.set_footer_text(
            "{} of {} · {}".format(len(ranked), len(self._base_items), FOOTER_HINT)
        )
        self._popup.list_view().select_row(row)
        was_visible = self.is_visible()
        self._place(rows=len(ranked))
        self._reopen_key = None
        self._record(
            event,
            prefix=query,
            rows=len(ranked),
            total=len(self._base_items),
            filter_ms=round(filter_ms, 3),
            narrowed=candidates is not None,
            manual=manual,
            reopened=not was_visible,
        )
        self._schedule_paint_metric(started_at or started)
        return True

    # ------------------------------------------------------------------
    # Placement
    # ------------------------------------------------------------------

    def _width_for(self, items: List[CompletionItem]) -> int:
        list_view = self._popup.list_view()
        bold = list_view.font()
        bold.setBold(True)
        name_metrics = QFontMetrics(bold)
        small = list_view.font()
        small.setPointSizeF(max(7.5, small.pointSizeF() - 1.0))
        type_metrics = QFontMetrics(small)
        widest_name = max((name_metrics.horizontalAdvance(item.label) for item in items), default=120)
        widest_type = max((type_metrics.horizontalAdvance(row_short_type(item)) for item in items), default=0)
        width = list_view.delegate().width_for(widest_name, widest_type) + list_view.verticalScrollBar().sizeHint().width()
        return max(MIN_LIST_WIDTH, min(MAX_LIST_WIDTH, width))

    def _place(self, rows: Optional[int] = None) -> None:
        widget = self._widget
        host = self._host
        site = self._site
        if widget is None or host is None or site is None:
            return
        list_view = self._popup.list_view()
        row_count = self._model.rowCount() if rows is None else rows
        list_view.setFixedWidth(self._list_width)
        list_view.setFixedHeight(list_view.height_for_rows(row_count))
        self._popup.adjustSize()
        size = self._popup.sizeHint()
        anchor_rect = host.completion_anchor_rect(site.anchor)
        text_left = OUTER_MARGINS[0] + 1 + CHIP_LEFT + CHIP_SIZE + CHIP_GAP
        global_anchor = widget.mapToGlobal(QPoint(anchor_rect.x() - text_left, anchor_rect.bottom() + 2))
        screen = _screen_geometry(widget, global_anchor)
        x = max(screen.left(), min(global_anchor.x(), screen.right() - size.width()))
        y = global_anchor.y()
        if y + size.height() > screen.bottom():
            y = max(screen.top(), widget.mapToGlobal(QPoint(0, anchor_rect.top())).y() - size.height() - 2)
        self._popup.setGeometry(x, y, size.width(), size.height())
        if not self._popup.isVisible():
            self._popup.show()
        self._popup.raise_()

    # ------------------------------------------------------------------
    # Closing
    # ------------------------------------------------------------------

    def _close(self, reason: str) -> None:
        self._pending_cancel_if(reason)
        if not self._popup.isVisible():
            return
        self._closing_internally = True
        try:
            self._popup.hide()
        finally:
            self._closing_internally = False
        self._record("close", reason=reason)

    def _pending_cancel_if(self, reason: str) -> None:
        if reason in (CLOSE_NO_MATCH, CLOSE_TYPED_FULL_NAME):
            return
        self._pending = None

    def _forget_expression(self) -> None:
        self._reopen_key = None
        self._pending = None
        self._site = None
        self._user_moved_selection = False

    def _on_popup_closed(self) -> None:
        if self._closing_internally:
            return
        self._forget_expression()
        self._record("close", reason=CLOSE_CLICK_AWAY)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _active_key(self) -> Optional[Tuple[str, int, str]]:
        if self._pending is not None:
            return self._pending.key
        return self._base_key

    def _root_allows(self, prefix: str) -> bool:
        root = self._pending.root if self._pending is not None else self._base_root
        return prefix.lower().startswith(root.lower())

    def _live_site(self, *, check_strings: bool) -> Optional[CompletionSite]:
        if self._host is None:
            return None
        text, cursor = self._host.completion_text_and_cursor()
        return completion_site(text, cursor, check_strings=check_strings)

    def _status(self, message: str) -> None:
        if self._host is not None:
            self._host.completion_status(message)

    def _on_current_item_changed(self, item: object) -> None:
        if not isinstance(item, CompletionItem):
            return
        if item.label == self._last_selection_label and self.is_visible():
            return
        self._last_selection_label = item.label
        self._selection_started_at = time.perf_counter()
        self.selection_changed.emit(item)

    def _record(self, event: str, **data: Any) -> None:
        entry: Dict[str, Any] = {"event": event, "mode": self._mode}
        entry.update(data)
        self.metrics.append(entry)
        if len(self.metrics) > _METRICS_LIMIT:
            del self.metrics[: len(self.metrics) - _METRICS_LIMIT]

    def _schedule_paint_metric(self, started_at: float) -> None:
        if not self.metrics:
            return
        entry = self.metrics[-1]
        list_view = self._popup.list_view()

        def capture() -> None:
            if list_view.last_paint_at >= started_at:
                entry["to_paint_ms"] = round((list_view.last_paint_at - started_at) * 1000.0, 3)

        QTimer.singleShot(0, capture)

    # ------------------------------------------------------------------
    # Event filter: Qt.Popup grabs the keyboard; send typing back to the host.
    # ------------------------------------------------------------------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        popup = getattr(self, "_popup", None)
        if popup is None or watched is not popup or event.type() != QEvent.KeyPress:
            return super().eventFilter(watched, event)
        widget = self._widget
        if widget is None:
            return super().eventFilter(watched, event)
        QApplication.sendEvent(widget, event)
        return True


def base_labels_equal(left: List[CompletionItem], right: List[CompletionItem]) -> bool:
    if len(left) != len(right):
        return False
    return all(a.label == b.label for a, b in zip(left, right))


def _screen_geometry(widget: QWidget, point: QPoint) -> QRect:
    for screen in QApplication.screens():
        if screen.geometry().contains(point):
            return screen.availableGeometry()
    screen = widget.screen() if hasattr(widget, "screen") else None
    if screen is None:
        app = QApplication.instance()
        screen = app.primaryScreen() if app is not None else None
    if screen is None:
        return QRect(0, 0, 1920, 1080)
    return screen.availableGeometry()
