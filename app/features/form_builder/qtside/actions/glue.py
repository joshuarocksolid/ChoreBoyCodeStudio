"""Menu editing on the canvas: keys in, the menu-edit layer out (UX-MAIN-003, 004, 015).

An event filter on the canvas turns Enter on a selected menu bar, menu or
toolbar into editing and sends keys to ``MenuEditor`` while it is on. After each
key, and after each change to the form, the bars and open menus are measured
from the realized widgets and shown through the ``menu_edit`` canvas layer.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query import actions as q
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.qtside.actions.editing import EditView, Key, LevelView, MenuEditor
from app.features.form_builder.qtside.actions.env import SessionEnv
from app.features.form_builder.qtside.actions.paint_model import (
    HINT_MIN_HEIGHT,
    HINT_MIN_WIDTH,
    MIN_MENU_WIDTH,
    ROW_HEIGHT,
    PaintItem,
    PaintState,
)
from app.features.form_builder.qtside.canvas.layers.menu_edit import NAME as LAYER
from app.qt.QtCore import QEvent, QObject, QPoint, Qt, QTimer
from app.qt.QtGui import QColor, QFont, QFontMetrics, QKeyEvent, QPalette
from app.qt.QtWidgets import QApplication, QLineEdit, QMenuBar, QToolBar, QWidget

CENTRAL_REFUSAL = "The central area belongs to the window. Delete what's inside it instead."

_NAMES = {
    Qt.Key.Key_Left: "Left",
    Qt.Key.Key_Right: "Right",
    Qt.Key.Key_Up: "Up",
    Qt.Key.Key_Down: "Down",
    Qt.Key.Key_Return: "Enter",
    Qt.Key.Key_Enter: "Enter",
    Qt.Key.Key_Escape: "Escape",
    Qt.Key.Key_Delete: "Delete",
    Qt.Key.Key_Backspace: "Backspace",
    Qt.Key.Key_Tab: "Tab",
}


def key_of(event: QKeyEvent) -> Key:
    name = _NAMES.get(event.key(), "")
    mods = event.modifiers()
    alt = bool(mods & Qt.KeyboardModifier.AltModifier)
    ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
    text = "" if name else event.text()
    return Key(name, text, alt=alt, ctrl=ctrl)


#: Keys the line edit hands to the ``MenuEditor``. Everything else (caret, selection, paste,
#: input methods) is the line edit's own.
_EDITOR_KEYS = ("Enter", "Tab", "Escape", "Up", "Down")


class _EditLine(QLineEdit):
    """The in-place editor: a frameless line edit that sits where the layer paints its box."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFrame(False)
        self.setObjectName("formBuilder.menuEditLine")
        self.setAccessibleName("Menu text")
        self.setTextMargins(5, 0, 3, 0)
        self.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)


class MenuEditGlue(QObject):
    def __init__(
        self,
        session: FormSession,
        realizer: object,
        canvas: QWidget,
        say: Callable[[str], None],
        toast: Callable[[str], None],
        confirm: Callable[[str, str], bool],
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._say = say
        self._realizer = realizer
        self._canvas = canvas
        self._editor = MenuEditor(SessionEnv(session, say, toast, confirm))
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self.refresh)
        viewport = getattr(canvas, "viewport")()
        viewport.installEventFilter(self)
        canvas.installEventFilter(self)
        self._watched = (viewport, canvas)
        from app.features.form_builder.engine.events import PRIORITY_DIAGNOSTICS

        self._sub = session.log.subscribe(self._on_change, priority=PRIORITY_DIAGNOSTICS + 1)
        self._diagnostics: Tuple[object, ...] = ()
        self._line: Optional[_EditLine] = None
        self._line_token: object = None
        self._syncing = False
        self._timer.start()

    @property
    def editor(self) -> MenuEditor:
        return self._editor

    def dispose(self) -> None:
        self._timer.stop()
        self._sub.close()
        self._drop_line()
        for widget in self._watched:
            try:
                widget.removeEventFilter(self)
            except RuntimeError:
                pass

    # ------------------------------------------------------------- events
    def _on_change(self, _change: object) -> None:
        self._timer.start()

    def start(self, node: NodeId) -> bool:
        started = self._editor.start(node)
        self.refresh()
        return started

    def eventFilter(self, watched: object, event: object) -> bool:  # noqa: N802
        if watched is self._line and self._line is not None:
            return self._line_event(event)
        kind = getattr(event, "type")()
        if kind not in (QEvent.Type.KeyPress, QEvent.Type.ShortcutOverride):
            return False
        if not isinstance(event, QKeyEvent):
            return False
        key = key_of(event)
        if self._editor.active:
            if not (key.name or key.text):
                return False
            if kind == QEvent.Type.ShortcutOverride:
                event.accept()
                return True
            self._editor.handle(key)
            self.refresh()
            return True
        if key.name == "Delete" and not key.alt and not key.ctrl and self._is_central_area():
            if kind == QEvent.Type.ShortcutOverride:
                event.accept()
                return True
            self._say(CENTRAL_REFUSAL)
            return True
        if key.name == "Enter" and not key.alt and not key.ctrl and self._startable() is not None:
            if kind == QEvent.Type.ShortcutOverride:
                event.accept()
                return True
            node = self._startable()
            if node is not None:
                self.start(node)
            return True
        return False

    # ----------------------------------------------------------- line edit
    def _line_event(self, event: object) -> bool:
        kind = getattr(event, "type")()
        if kind in (QEvent.Type.KeyPress, QEvent.Type.ShortcutOverride) and isinstance(event, QKeyEvent):
            key = key_of(event)
            if key.name in _EDITOR_KEYS and not key.ctrl and not key.alt:
                if kind == QEvent.Type.ShortcutOverride:
                    event.accept()
                    return True
                self._editor.handle(key)
                self.refresh()
                return True
            return False
        if kind == QEvent.Type.FocusOut and not self._syncing:
            reason = getattr(event, "reason")()
            if reason in (Qt.FocusReason.MouseFocusReason, Qt.FocusReason.OtherFocusReason, Qt.FocusReason.BacktabFocusReason):
                token = self._line_token
                QTimer.singleShot(0, lambda: self._keep_on_focus_loss(token))
        return False

    def _keep_on_focus_loss(self, token: object) -> None:
        """Clicking away keeps the text, as Enter does (UX-MAIN-006)."""
        if token is not self._line_token or self._editor.editor is None or self._line is None:
            return
        if self._line.hasFocus():
            return
        self._editor.handle(Key("Enter"))
        self.refresh()

    def _drop_line(self) -> None:
        line, self._line, self._line_token = self._line, None, None
        if line is None:
            return
        self._syncing = True
        try:
            line.removeEventFilter(self)
            line.hide()
            line.setParent(None)
            line.deleteLater()
        finally:
            self._syncing = False

    def _page_to_viewport(self) -> Optional[Tuple[int, int, float]]:
        """Origin of the page in viewport pixels and the zoom factor."""
        root = getattr(self._realizer, "root_widget", None)
        node = getattr(self._session.document, "root", None)
        rect_of = getattr(self._canvas, "viewport_rect", None)
        if root is None or node is None or rect_of is None or root.width() <= 0:
            return None
        rect = rect_of((node.id,))
        if rect is None:
            return None
        return rect.x(), rect.y(), rect.width() / float(root.width())

    def _ink(self) -> QColor:
        palette = getattr(self._canvas, "_palette", None)
        text = getattr(getattr(palette, "overlay", None), "stand_in_text", None)
        if isinstance(text, str) and text.startswith("#") and len(text) >= 7:
            return QColor("#" + text[1:7])
        return QApplication.palette().color(QPalette.ColorRole.Text)

    def _sync_line(self, state: PaintState) -> None:
        """Keep one frameless ``QLineEdit`` on the layer's "edit" box while a title or entry is typed."""
        spec = next((item for item in state.items if item.kind == "edit"), None)
        editor = self._editor.editor
        mapped = self._page_to_viewport() if spec is not None and editor is not None else None
        if spec is None or editor is None or mapped is None:
            if self._line is not None:
                had_focus = self._line.hasFocus()
                self._drop_line()
                if had_focus:
                    getattr(self._canvas, "viewport")().setFocus()
            return
        ox, oy, factor = mapped
        viewport = getattr(self._canvas, "viewport")()
        fresh = self._line is None
        if fresh:
            self._line = _EditLine(viewport)
            self._line.installEventFilter(self)
            self._line.textEdited.connect(self._on_line_edited)
        line = self._line
        assert line is not None
        self._syncing = True
        try:
            font = QFont(QApplication.font())
            font.setPixelSize(max(8, int(round(12 * factor))))
            line.setFont(font)
            pal = line.palette()
            pal.setColor(QPalette.ColorRole.Text, self._ink())
            pal.setColor(QPalette.ColorRole.Base, QColor(0, 0, 0, 0))
            line.setPalette(pal)
            line.setStyleSheet("QLineEdit { background: transparent; border: 0; }")
            line.setGeometry(
                int(round(ox + spec.x * factor)),
                int(round(oy + spec.y * factor)),
                max(8, int(round(spec.width * factor))),
                max(8, int(round(spec.height * factor))),
            )
            if fresh or self._line_token is not editor:
                self._line_token = editor
                line.setText(editor.text)
                line.show()
                line.raise_()
                line.setFocus(Qt.FocusReason.OtherFocusReason)
                if editor.selected:
                    line.selectAll()
            elif line.text() != editor.text:
                line.setText(editor.text)
            line.setAccessibleDescription(self._editor.reuse_phrase())
        finally:
            self._syncing = False

    def _on_line_edited(self, text: str) -> None:
        self._editor.set_text(text)
        self.refresh()

    def _describe_focus(self) -> None:
        phrase = self._editor.focus_phrase()
        for widget in (self._canvas, getattr(self._canvas, "viewport")()):
            setter = getattr(widget, "setAccessibleDescription", None)
            if setter is not None:
                setter(phrase)

    def _is_central_area(self) -> bool:
        """UX-MAIN-014: the central widget of a main window is selected on its own."""
        state = self._session.selection.state
        doc = self._session.document
        if len(state.ids) != 1 or state.current is None or not q.is_main_window(doc):
            return False
        found = doc.get(state.current)
        return found is not None and any(found.id == part.id for part in q.parts(doc)["central"])

    def _startable(self) -> Optional[NodeId]:
        state = self._session.selection.state
        if len(state.ids) != 1 or state.current is None:
            return None
        node = self._session.document.get(state.current)
        cls = getattr(node, "class_name", "")
        return state.current if cls in ("QMenuBar", "QMenu", "QToolBar") else None

    # ---------------------------------------------------------------- paint
    def refresh(self) -> None:
        doc = self._session.document
        found = q.main_window_diagnostics(doc)
        if found != self._diagnostics:
            self._diagnostics = found
            self._session.diagnostics.publish("main_window", found)
        if self._editor.active:
            hosts = [level.host for level in self._editor.levels if level.host is not None]
            if any(not doc.contains(host) for host in hosts):
                self._editor.leave()
        state = self._build_state()
        self._sync_line(state)
        self._describe_focus()
        show = getattr(self._canvas, "show_layer", None)
        hide = getattr(self._canvas, "hide_layer", None)
        if show is None or hide is None:
            return
        if state.items:
            show(LAYER, state)
        else:
            hide(LAYER)

    def _build_state(self) -> PaintState:
        doc = self._session.document
        if not q.is_main_window(doc):
            return PaintState()
        root = getattr(self._realizer, "root_widget", None)
        if root is None:
            return PaintState()
        if not self._editor.active:
            return PaintState(tuple(self._idle_hints(root)))
        return PaintState(tuple(self._open_items(root, self._editor.view())))

    def _bar_widgets(self, node_id: NodeId) -> Optional[QWidget]:
        return getattr(self._realizer, "widget_for")(node_id)

    def _action_rects(self, host: NodeId, root: QWidget) -> Tuple[List[Tuple[int, int, int, int]], Tuple[int, int, int, int]]:
        """Form-pixel rects of each action of a bar or toolbar, and the bar's own rect."""
        widget = self._bar_widgets(host)
        if widget is None:
            return [], (0, 0, 0, 0)
        origin = widget.mapTo(root, QPoint(0, 0))
        own = (origin.x(), origin.y(), widget.width(), widget.height())
        rects: List[Tuple[int, int, int, int]] = []
        if isinstance(widget, (QMenuBar, QToolBar)):
            for action in widget.actions():
                geo = widget.actionGeometry(action)
                rects.append((origin.x() + geo.x(), origin.y() + geo.y(), geo.width(), geo.height()))
        return rects, own

    def _hint_rect(self, rects: List[Tuple[int, int, int, int]], own: Tuple[int, int, int, int], metrics: QFontMetrics) -> Tuple[int, int, int, int]:
        width = max(HINT_MIN_WIDTH, metrics.horizontalAdvance("Type here") + 20)
        if rects:
            last = rects[-1]
            return (last[0] + last[2] + 6, last[1], width, max(HINT_MIN_HEIGHT, last[3]))
        return (own[0] + 6, own[1], width, max(HINT_MIN_HEIGHT, min(own[3], 30) if own[3] else HINT_MIN_HEIGHT))

    def _idle_hints(self, root: QWidget) -> List[PaintItem]:
        doc = self._session.document
        metrics = QFontMetrics(QApplication.font())
        out: List[PaintItem] = []
        parts = q.parts(doc)
        for node in tuple(parts["menubar"]) + tuple(parts["toolbar"]):
            rects, own = self._action_rects(node.id, root)
            if own == (0, 0, 0, 0) and not rects:
                continue
            x, y, w, h = self._hint_rect(rects, own, metrics)
            out.append(PaintItem("hint", x, y, w, h, "Type here"))
        return out

    def _open_items(self, root: QWidget, view: EditView) -> List[PaintItem]:
        metrics = QFontMetrics(QApplication.font())
        items: List[PaintItem] = []
        anchor: Optional[Tuple[int, int, int, int]] = None
        page_width = root.width()
        previous = ""
        for level in view.levels:
            if level.kind in ("bar", "toolbar") and level.host is not None:
                anchor = self._bar_items(root, level, metrics, items)
            else:
                anchor = self._menu_items(level, anchor, metrics, items, page_width, previous == "menu")
            previous = level.kind
        return items

    def _bar_items(
        self, root: QWidget, level: LevelView, metrics: QFontMetrics, items: List[PaintItem]
    ) -> Tuple[int, int, int, int]:
        assert level.host is not None
        rects, own = self._action_rects(level.host, root)
        hint = self._hint_rect(rects, own, metrics)
        anchor = hint
        for index, row in enumerate(level.rows):
            if row.kind == "type_here":
                if level.editing == index:
                    width = max(hint[2], metrics.horizontalAdvance(level.editor_text) + 24)
                    items.append(PaintItem("edit", hint[0], hint[1], width, hint[3], level.editor_text, selected=level.editor_selected))
                    if level.reuse:
                        self._reuse_items(items, hint[0], hint[1] + hint[3], level, metrics)
                else:
                    items.append(PaintItem("hint", hint[0], hint[1], hint[2], hint[3], "Type here", focused=row.focused))
                continue
            if index < len(rects):
                x, y, w, h = rects[index]
                if level.editing == index:
                    width = max(w, metrics.horizontalAdvance(level.editor_text) + 24)
                    items.append(PaintItem("edit", x, y, width, h, level.editor_text, selected=level.editor_selected))
                elif row.focused:
                    items.append(PaintItem("row", x, y, w, h, "", focused=True))
                if row.focused:
                    anchor = (x, y, w, h)
        return anchor

    def _reuse_items(self, items: List[PaintItem], x: int, y: int, level: LevelView, metrics: QFontMetrics) -> None:
        width = MIN_MENU_WIDTH
        for row in level.reuse:
            width = max(width, metrics.horizontalAdvance(row.label) + metrics.horizontalAdvance(row.shortcut) + 56)
        items.append(PaintItem("box", x, y, width, ROW_HEIGHT * len(level.reuse)))
        for index, row in enumerate(level.reuse):
            items.append(
                PaintItem("reuse", x, y + index * ROW_HEIGHT, width, ROW_HEIGHT, row.label, row.shortcut, current=index == level.reuse_current)
            )

    def _menu_items(
        self,
        level: LevelView,
        anchor: Optional[Tuple[int, int, int, int]],
        metrics: QFontMetrics,
        items: List[PaintItem],
        page_width: int,
        beside: bool,
    ) -> Tuple[int, int, int, int]:
        width = MIN_MENU_WIDTH
        for row in level.rows:
            width = max(width, metrics.horizontalAdvance(row.text) + metrics.horizontalAdvance(row.shortcut) + 56)
        if level.editing is not None:
            width = max(width, metrics.horizontalAdvance(level.editor_text) + 40)
        if anchor is None:
            anchor = (0, 0, 0, 0)
        if beside:
            x, y = anchor[0] + anchor[2], anchor[1]
            if x + width > page_width:
                x = max(0, anchor[0] - width)
        else:
            x, y = anchor[0], anchor[1] + anchor[3]
        height = ROW_HEIGHT * len(level.rows)
        items.append(PaintItem("box", x, y, width, height))
        focus_rect = (x, y, width, ROW_HEIGHT)
        late: List[PaintItem] = []
        for index, row in enumerate(level.rows):
            top = y + index * ROW_HEIGHT
            if row.focused:
                focus_rect = (x, top, width, ROW_HEIGHT)
            if row.kind == "separator":
                items.append(PaintItem("separator", x, top, width, ROW_HEIGHT))
                if row.focused:
                    items.append(PaintItem("row", x, top, width, ROW_HEIGHT, "", focused=True))
                continue
            if level.editing == index:
                items.append(PaintItem("edit", x, top, width, ROW_HEIGHT, level.editor_text, selected=level.editor_selected))
                if level.reuse:
                    self._reuse_items(late, x, top + ROW_HEIGHT, level, metrics)
                elif level.caption:
                    late.append(PaintItem("caption", x, top + ROW_HEIGHT, max(width, 360), 16, level.caption))
                continue
            items.append(
                PaintItem("row", x, top, width, ROW_HEIGHT, row.text, row.shortcut, focused=row.focused, opens=row.opens)
            )
        items.extend(late)
        return focus_rect
