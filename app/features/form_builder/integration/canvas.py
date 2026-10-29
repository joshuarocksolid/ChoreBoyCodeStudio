"""Design canvas (UX-WB-004).

The realized form sits in a proxy on the runtime scene. The controller owns
selection, hover and gestures. ``drawForeground`` paints the overlay frame.
The page caption, shadow and toast stay view chrome.
"""

from __future__ import annotations

from typing import Hashable, List, Optional, Sequence, Tuple

from app.qt.QtCore import QEvent, QMimeData, QPoint, QPointF, QRect, QRectF, Qt, QTimer
from app.qt.QtGui import QColor, QContextMenuEvent, QCursor, QDrag, QFont, QImage, QPainter, QPen, QPixmap
from app.qt.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QWidget,
)
from app.qt.qt_compat import enum_value, event_pos, wrapper_is_valid

from app.features.form_builder.engine.commands.drop_plan import flagged
from app.features.form_builder.engine.events import PRIORITY_HIT_INDEX, PRIORITY_VIEWS
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.drop_target import DropPayload, PayloadKind
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.reader import UiReadError, read_fragment
from app.features.form_builder.engine.ui4.spec import Fragment
from app.features.form_builder.engine.query.hit_index import HitIndex
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.integration.chrome_text import page_title_text
from app.features.form_builder.qtside.canvas import file_drops
from app.features.form_builder.qtside.canvas.controller import CanvasController, CanvasHost
from app.features.form_builder.qtside.canvas.core.frame import (
    Caption,
    Chip,
    OnHandle,
    OnPageEdge,
    OnSpace,
    OnWidget,
    OverlayFrame,
)
from app.features.form_builder.qtside.canvas.core.space import CanvasPoint, CanvasRect
from app.features.form_builder.qtside.canvas.core.gesture import (
    HostEvent,
    PlaceAsked,
    PlaceDrop,
    PlaceHover,
    aim,
)
from app.features.form_builder.qtside.canvas.core.palette import (
    MIME_DESIGNER_FRAGMENT,
    MIME_FRAGMENT,
    MIME_INSERT,
    MIME_NODE,
    fragment_for,
    tile_for,
)
from app.features.form_builder.qtside.canvas.core.place import payload_for
from app.features.form_builder.qtside.canvas.geometry import HitIndexInvalidator, LiveGeometrySource
from app.features.form_builder.qtside.canvas.paint import paint_docked_chip, paint_frame
from app.features.form_builder.qtside.canvas.preview import FormPreview
from app.features.form_builder.qtside.canvas.stage import Stage, visible_scene_rect
from app.features.form_builder.qtside.realize.api import Realizer
from app.features.form_builder.qtside.theme.chrome import (
    PAGE_TITLE_FILL,
    PAGE_TITLE_GLYPH,
    PAGE_TITLE_HEIGHT,
    PAGE_TITLE_TEXT,
    backdrop_colors,
    fallback_backdrop_roles,
    on_accent_for,
    page_shadow_rgba,
)
from app.features.form_builder.qtside.theme.overlay import (
    BackdropPalette,
    CanvasPalette,
    overlay_palette,
)
from app.features.form_builder.qtside.theme.runtime import isolate_scene, startup_font
from app.shell.theme_tokens import ShellThemeTokens

_DOT = 16


def _keep_claimed_shortcut(event: QEvent) -> None:
    """A claimed ShortcutOverride stays accepted, so the shell key does not fire."""
    override = getattr(getattr(QEvent, "Type", QEvent), "ShortcutOverride")
    if event.type() != override:
        return
    event.accept()


def _over_saved_pieces(widget: object) -> bool:
    current = widget
    while current is not None:
        name = getattr(current, "objectName", lambda: "")()
        if name in ("formBuilder.savedPieces", "formBuilder.savedPiecesBox"):
            return True
        current = getattr(current, "parentWidget", lambda: None)()
    return False


def _focus_policy() -> Qt.FocusPolicy:
    policy = getattr(Qt, "FocusPolicy", Qt)
    return getattr(policy, "StrongFocus")


def _no_focus() -> Qt.FocusPolicy:
    policy = getattr(Qt, "FocusPolicy", Qt)
    return getattr(policy, "NoFocus")


def _drop_payload(event: object, doc: UiDocument) -> Optional[Tuple[DropPayload, str, Optional[Fragment]]]:
    mime = event.mimeData()  # type: ignore[attr-defined]
    if mime.hasFormat(MIME_INSERT):
        key = bytes(mime.data(MIME_INSERT)).decode("utf-8")
        tile = tile_for(key)
        kind = tile[1] if tile is not None else "widget"
        # A dock shows the side bands and a wizard page looks for a wizard (UX-CONT-012, UX-CAT-014).
        return flagged(DropPayload(kind), fragment_for(key)), key, None
    if mime.hasFormat(MIME_NODE):
        raw = bytes(mime.data(MIME_NODE)).decode("utf-8")
        ids = tuple(NodeId(int(part)) for part in raw.split(",") if part)
        return payload_for(doc, ids), "", None
    fragment = _fragment_mime(mime)
    if fragment is None:
        return None
    return flagged(DropPayload(_fragment_kind(fragment)), fragment), "", fragment


def _fragment_mime(mime: object) -> Optional[Fragment]:
    for name in (MIME_FRAGMENT, MIME_DESIGNER_FRAGMENT):
        if not mime.hasFormat(name):  # type: ignore[attr-defined]
            continue
        text = bytes(mime.data(name)).decode("utf-8")  # type: ignore[attr-defined]
        try:
            fragment = read_fragment(text)
        except UiReadError:
            return None
        if fragment.nodes:
            return fragment
        return None
    return None


def _fragment_kind(fragment: Fragment) -> PayloadKind:
    spec = fragment.nodes[0]
    if spec.kind == "spacer":
        return "spacer"
    if spec.kind == "widget" and spec.field("class_name") == "QLabel":
        return "label"
    return "widget"


def _drop_point(event: object, view: QGraphicsView) -> CanvasPoint:
    pos = event_pos(event)
    scene = view.mapToScene(pos)
    return CanvasPoint(int(scene.x()), int(scene.y()))


def _drop_snap(event: object) -> bool:
    value = enum_value(event.modifiers())  # type: ignore[attr-defined]
    shift = enum_value(getattr(getattr(Qt, "KeyboardModifier", Qt), "ShiftModifier"))
    return not bool(value & shift)


def _transparent() -> Qt.WidgetAttribute:
    attrs = getattr(Qt, "WidgetAttribute", Qt)
    return getattr(attrs, "WA_TransparentForMouseEvents")


class FormCanvas(QGraphicsView):
    """Dot grid, centred page, and the chrome around it."""

    def __init__(
        self,
        session: FormSession,
        realizer: Realizer,
        host: CanvasHost,
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._realizer = realizer
        self._host = host
        self._tokens: Optional[ShellThemeTokens] = None
        self._palette = _palette(None)
        self._canvas_bg = self._palette.backdrop.fill
        self._dot = self._palette.backdrop.dot
        self._dot_tile: Optional[Tuple[str, QPixmap]] = None
        self._shadow_rgba: Optional[Tuple[int, int, int, int]] = None
        self._shadow_plate: Optional[QPixmap] = None
        self.setObjectName("formBuilder.canvas")
        self.setAccessibleName("Form canvas")
        self.setFocusPolicy(_focus_policy())
        # Qt focuses the viewport, not the view.
        self.viewport().setAccessibleName("Form canvas")
        shape = getattr(getattr(QFrame, "Shape", QFrame), "NoFrame")
        self.setFrameShape(shape)
        drag = getattr(QGraphicsView, "DragMode", QGraphicsView)
        self.setDragMode(getattr(drag, "NoDrag"))
        self.setInteractive(False)
        self.setAcceptDrops(True)
        scene = QGraphicsScene(self)
        isolate_scene(scene)
        self.setScene(scene)
        self.viewport().setMouseTracking(True)
        self._index = HitIndex(LiveGeometrySource(realizer))
        self._hit_sub = session.log.subscribe(
            HitIndexInvalidator(self._index).on_changeset, priority=PRIORITY_HIT_INDEX
        )
        self._stage = Stage(
            self,
            session,
            realizer,
            self._index.invalidate,
            self._index.set_screen_factor,
            self._position_chrome,
        )
        self._stage.set_banner_push(PAGE_TITLE_HEIGHT)
        self._build_chrome()
        self._controller = CanvasController(self, session, realizer, self._index, self._stage, host)
        self._preview = FormPreview(self, session, realizer, self._stage)
        # The page can change size without a ChangeSet: two widths forces the
        # narrowest width, a layout grows the root. Rects in the hit index and
        # the overlay are then stale, so any page resize re-measures. O(1) here;
        # the walk runs on the next frame.
        self._stage.proxy.geometryChanged.connect(self._page_resized)
        # Same priority as the controller's view listener, subscribed after it,
        # so the caption follows the page the controller just placed.
        self._chrome_sub = session.log.subscribe(self._position_after, priority=PRIORITY_VIEWS)
        realizer.build()
        self._chip_viewport = visible_scene_rect(self)
        self.horizontalScrollBar().valueChanged.connect(self._position_chrome)
        self.verticalScrollBar().valueChanged.connect(self._position_chrome)
        self.horizontalScrollBar().sliderReleased.connect(self._refresh_chips_after_scroll)
        self.verticalScrollBar().sliderReleased.connect(self._refresh_chips_after_scroll)
        # Track clicks, arrow buttons and keys move the bars without a release.
        # One 0 ms timer folds both bars' changes into one re-solve.
        self._chip_timer = QTimer(self)
        self._chip_timer.setSingleShot(True)
        self._chip_timer.setInterval(0)
        self._chip_timer.timeout.connect(self._refresh_chips_after_scroll)
        self.horizontalScrollBar().valueChanged.connect(self._scroll_moved)
        self.verticalScrollBar().valueChanged.connect(self._scroll_moved)
        self._stage.place()
        self._sync_title()
        self._position_chrome()

    @property
    def preview(self) -> FormPreview:
        return self._preview

    def show_layer(self, name: str, state: Hashable = True) -> None:
        """Switch a ``qtside/canvas/layers`` layer on for this canvas (M5.0s); see that package."""
        self._controller.show_layer(name, state)

    def hide_layer(self, name: str) -> None:
        self._controller.hide_layer(name)

    def layer_state(self, name: str) -> Optional[Hashable]:
        return self._controller.layer_state(name)

    def _page_resized(self) -> None:
        proxy = self._stage.proxy
        size = (round(proxy.size().width()), round(proxy.size().height()))
        if size == getattr(self, "_page_size", None):
            return
        self._page_size = size
        self._index.invalidate("root_resize")
        controller = getattr(self, "_controller", None)
        if controller is not None:
            controller.refresh_overlay()

    def _file_drop(self, event: object) -> Tuple[str, ...]:
        """Desktop files, when a handler wants them (M5.2)."""
        if not file_drops.has_handlers():
            return ()
        return file_drops.local_paths(event.mimeData())  # type: ignore[attr-defined]

    def dragEnterEvent(self, event: object) -> None:  # noqa: N802
        if self._file_drop(event):
            event.acceptProposedAction()  # type: ignore[attr-defined]
            return
        payload = _drop_payload(event, self._session.document)
        if payload is None:
            event.ignore()  # type: ignore[attr-defined]
            return
        event.acceptProposedAction()  # type: ignore[attr-defined]
        body, key, fragment = payload
        at = _drop_point(event, self)
        if self._controller.placing():
            self._controller.post(PlaceHover(at, True))
            return
        self._controller.post(PlaceAsked(at, body, key, fragment))

    def dragMoveEvent(self, event: object) -> None:  # noqa: N802
        if self._file_drop(event):
            event.acceptProposedAction()  # type: ignore[attr-defined]
            return
        if _drop_payload(event, self._session.document) is None:
            event.ignore()  # type: ignore[attr-defined]
            return
        event.acceptProposedAction()  # type: ignore[attr-defined]
        self._controller.post(PlaceHover(_drop_point(event, self), _drop_snap(event)))

    def dropEvent(self, event: object) -> None:  # noqa: N802
        paths = self._file_drop(event)
        if paths:
            event.acceptProposedAction()  # type: ignore[attr-defined]
            target = self.node_at(event_pos(event)) or self._session.document.root.id
            sentence = file_drops.dispatch(target, paths)
            if sentence:
                self._host.narrate(sentence)
            return
        if _drop_payload(event, self._session.document) is None:
            event.ignore()  # type: ignore[attr-defined]
            return
        event.acceptProposedAction()  # type: ignore[attr-defined]
        self._controller.post(PlaceDrop(_drop_point(event, self), _drop_snap(event)))

    def dragLeaveEvent(self, event: object) -> None:  # noqa: N802
        del event
        if self._controller.placing():
            self._controller.post(PlaceHover(CanvasPoint(0, 0), True, None, True))

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        if event.reason() == QContextMenuEvent.Reason.Mouse:
            self._host.open_context_menu(self.node_at(event.pos()), event.globalPos())
        else:
            self._host.open_context_menu(None, None)
        event.accept()

    def node_at(self, pos: QPoint) -> Optional[NodeId]:
        """The node a left click at viewport ``pos`` would select. None over a chip."""
        self._index.ensure_fresh()
        scene = self.mapToScene(pos)
        target = aim(
            CanvasPoint(int(scene.x()), int(scene.y())),
            self._controller.frame,
            self._index,
            self._session.document,
            self._stage.view_map(),
        )
        if isinstance(target, (OnWidget, OnHandle)):
            return target.node
        if isinstance(target, OnSpace):
            return target.select
        if isinstance(target, OnPageEdge):
            return self._session.document.root.id
        return None

    def viewport_rect(self, ids: Sequence[NodeId]) -> Optional[QRect]:
        """Where ``ids`` are drawn, in viewport coordinates. None when none of them is."""
        self._index.ensure_fresh()
        view = self._stage.view_map()
        drawn = [view.to_canvas(rect) for rect in map(self._index.rect_of, ids) if rect is not None]
        if not drawn:
            return None
        top_left = self.mapFromScene(QPointF(min(rect.x for rect in drawn), min(rect.y for rect in drawn)))
        bottom_right = self.mapFromScene(
            QPointF(max(rect.x + rect.width for rect in drawn), max(rect.y + rect.height for rect in drawn))
        )
        return QRect(top_left.x(), top_left.y(), bottom_right.x() - top_left.x(), bottom_right.y() - top_left.y())

    def tab_viewport_rect(self, node: NodeId) -> Optional[QRect]:
        """The page's tab or toolbox header, in viewport coordinates."""
        self._index.ensure_fresh()
        view = self._stage.view_map()
        for entry in self._index.title_entries():
            if entry.kind == "page_tab" and entry.node == node:
                return self._viewport_of_canvas(view.to_canvas(entry.rect))
        return None

    def overlay_block_rects(self) -> Tuple[QRect, ...]:
        """Chips and captions in viewport coordinates. The toast stays off them."""
        rects: List[QRect] = []
        for item in self._controller.frame.items:
            if isinstance(item, Caption) or (isinstance(item, Chip) and not item.docked):
                rects.append(self._viewport_of_canvas(item.rect))
        viewport = self.viewport()
        for widget in self._stage.chrome_widgets():
            origin = viewport.mapFromGlobal(widget.mapToGlobal(QPoint(0, 0)))
            rects.append(QRect(origin, widget.size()))
        for local in self._title.docked_view_rects():
            origin = viewport.mapFromGlobal(self._title.mapToGlobal(local.topLeft()))
            rects.append(QRect(origin, local.size()))
        return tuple(rect for rect in rects if rect.width() > 0 and rect.height() > 0)

    def _viewport_of_canvas(self, rect: CanvasRect) -> QRect:
        top_left = self.mapFromScene(QPointF(rect.x, rect.y))
        bottom_right = self.mapFromScene(QPointF(rect.x + rect.width, rect.y + rect.height))
        return QRect(top_left, bottom_right).normalized()

    def page_widget(self) -> Optional[QWidget]:
        root = self._realizer.root_widget
        if root is None or not wrapper_is_valid(root):
            return None
        return root

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        """Chrome only. The page palette stays the runtime palette."""
        self._tokens = tokens
        self._palette = _palette(tokens)
        self._canvas_bg = self._palette.backdrop.fill
        self._dot = self._palette.backdrop.dot
        self.viewport().setProperty("formBuilderHighContrast", tokens.is_high_contrast)
        self._apply_page_chrome(tokens)
        width = tokens.focus_border_width
        self.setStyleSheet(
            "QGraphicsView#formBuilder\\.canvas {"
            f" background: {self._canvas_bg}; border: 1px solid {tokens.border}; }}"
            "QGraphicsView#formBuilder\\.canvas:focus {"
            f" border: {width}px solid {tokens.accent}; }}"
            "QLabel#formBuilder\\.name {"
            f" color: {tokens.text_primary}; background: {tokens.panel_bg};"
            f" border: 1px solid {tokens.border}; border-radius: 4px; padding: 1px 6px;"
            " font-size: 11px; font-weight: 600; }"
            "QLabel#formBuilder\\.sizeReadout {"
            f" color: {tokens.text_muted}; background: transparent; border: none; padding: 0; }}"
            "QLabel#formBuilder\\.toast {"
            f" color: {tokens.text_primary}; background: {tokens.panel_bg};"
            f" border: 1px solid {tokens.border}; padding: 4px 8px; }}"
            "QLabel#formBuilder\\.previewPill, QLabel#formBuilder\\.narrowChip,"
            " QLineEdit#formBuilder\\.wideChip {"
            f" color: {tokens.text_primary}; background: {tokens.panel_bg};"
            f" border: 1px solid {tokens.border}; border-radius: 4px; padding: 1px 6px;"
            " font-size: 11px; }"
        )
        self._stage.apply_palette(self._palette.backdrop)
        fill = tokens.tree_selected_bg
        text = on_accent_for(fill)
        self._stage.set_page_chip_selected_style(
            "QLabel { color: %s; background: %s; border: 1px solid %s;"
            " border-radius: 4px; padding: 1px 6px; font-size: 11px; font-weight: 600; }"
            % (text, fill, fill)
        )
        self.viewport().update()
        self._position_chrome()

    def send(self, event: HostEvent) -> None:
        self._controller.post(event)

    def place_payload(self) -> Optional[DropPayload]:
        return self._controller.place_payload()

    def set_insert_preview(self, key: Optional[str]) -> None:
        self._controller.set_insert_preview(key)

    def preview_sentence(self) -> str:
        return self._controller.preview_sentence()

    def show_container_page(self, container: NodeId, delta: int) -> None:
        """Show the next or previous page. Canvas only. The file does not change."""
        self._controller.show_page_step(container, delta)

    def arrange_windows(self, container: NodeId, how: str) -> None:
        """Tile or cascade the windows of an MDI area. Not saved."""
        self._controller.arrange_windows(container, how)

    def overlay(self) -> OverlayFrame:
        return self._controller.frame

    def visible_canvas_rect(self) -> CanvasRect:
        return visible_scene_rect(self)

    def ensure_widget_visible(self, object_name: str) -> None:
        """Scroll so the named widget on the page is inside the viewport."""
        root = self.page_widget()
        if root is None or not object_name:
            return
        target = root if root.objectName() == object_name else root.findChild(QWidget, object_name)
        if target is None or not wrapper_is_valid(target):
            return
        origin = target.mapTo(root, QPoint(0, 0))
        rect = QRectF(
            float(origin.x()),
            float(origin.y()),
            float(max(target.width(), 1)),
            float(max(target.height(), 1)),
        )
        scene = self._stage.proxy.mapRectToScene(rect)
        left = int(scene.left())
        top = int(scene.top())
        self._stage.reveal_canvas(
            CanvasRect(left, top, max(1, int(scene.right()) - left), max(1, int(scene.bottom()) - top))
        )

    def refresh_chip(self) -> None:
        self._sync_title()
        self._stage.refresh_chrome()
        self._position_chrome()

    def detach(self) -> None:
        self._stage.detach()

    def dispose(self) -> None:
        self._preview.dispose()
        self._controller.dispose()
        self._chrome_sub.close()
        self._hit_sub.close()
        self.detach()

    def viewportEvent(self, event: QEvent) -> bool:  # noqa: N802
        controller = getattr(self, "_controller", None)
        if controller is None:
            return bool(super().viewportEvent(event))
        preview = getattr(self, "_preview", None)
        if preview is not None and preview.claim(event):
            return True
        if self._offer_piece_drag(event):
            return True
        if controller.handle(event):
            _keep_claimed_shortcut(event)
            return True
        return bool(super().viewportEvent(event))

    def _offer_piece_drag(self, event: QEvent) -> bool:
        """A canvas drag that lands on Saved pieces saves the dragged widgets."""
        move = getattr(getattr(QEvent, "Type", QEvent), "MouseMove")
        if event.type() != move:
            return False
        buttons = getattr(event, "buttons", None)
        if not callable(buttons):
            return False
        left = getattr(getattr(Qt, "MouseButton", Qt), "LeftButton")
        if not (enum_value(buttons()) & enum_value(left)):
            return False
        if not _over_saved_pieces(QApplication.widgetAt(QCursor.pos())):
            return False
        controller = self._controller
        ids = controller.drag_node_ids()
        if not ids:
            return False
        controller.abandon_drag()
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(MIME_NODE, str(int(ids[0])).encode("utf-8"))
        drag.setMimeData(mime)
        action = getattr(getattr(Qt, "DropAction", Qt), "CopyAction")
        starter = getattr(drag, "exec", None) or getattr(drag, "exec_")
        starter(action)
        return True

    def event(self, event: QEvent) -> bool:  # noqa: N802
        # Qt sends events from inside the QWidget constructor, before the
        # controller exists.
        controller = getattr(self, "_controller", None)
        if controller is None:
            return bool(super().event(event))
        if controller.handle(event):
            _keep_claimed_shortcut(event)
            return True
        return bool(super().event(event))

    def focusNextPrevChild(self, next: bool) -> bool:  # noqa: N802
        del next
        return False

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        preview = getattr(self, "_preview", None)
        if preview is not None:
            preview.arrange()
        self._position_chrome()

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        controller = getattr(self, "_controller", None)
        if controller is None:
            return
        preview = getattr(self, "_preview", None)
        if preview is not None:
            preview.paint_cutoff(painter)
            preview.paint_wide_selection(painter)
        frame = controller.frame
        # The ghost sits under the chips, so a move drag does not wash out band labels.
        controller.paint_ghost(painter)
        paint_frame(painter, frame, self._palette, rect)

    def sync_docked_chips(self, frame: OverlayFrame) -> None:
        """Dock chips when the frame is built, never from inside paint."""
        self._title.set_docked(_docked(frame), self._palette)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        painter.fillRect(rect, QColor(self._canvas_bg))
        if self._dot:
            # A 16 px tile. An ellipse per dot was most of a selection frame.
            painter.drawTiledPixmap(
                rect,
                self._dot_pixmap(),
                QPoint(int(rect.left()) % _DOT, int(rect.top()) % _DOT),
            )
        self._paint_page_shadow(painter)

    def _paint_page_shadow(self, painter: QPainter) -> None:
        plate = self._shadow_plate
        proxy = self._stage.proxy
        if plate is None or proxy.widget() is None:
            return
        page = proxy.sceneBoundingRect()
        _paint_shadow_plate(painter, plate, page)

    def _dot_pixmap(self) -> QPixmap:
        cached = self._dot_tile
        if cached is not None and cached[0] == self._dot:
            return cached[1]
        tile = QPixmap(_DOT, _DOT)
        tile.fill(QColor(0, 0, 0, 0))
        painter = QPainter(tile)
        painter.setPen(getattr(getattr(Qt, "PenStyle", Qt), "NoPen"))
        painter.setBrush(QColor(self._dot))
        painter.drawEllipse(0, 0, 2, 2)
        painter.end()
        self._dot_tile = (self._dot, tile)
        return tile

    def _build_chrome(self) -> None:
        self._toast = QLabel(self)
        self._toast.setObjectName("formBuilder.toast")
        self._toast.setAccessibleName("Notice")
        self._toast.hide()
        self._title = _PageTitle(self)
        self._frame = QWidget(self)
        self._frame.setObjectName("formBuilder.pageFrame")
        self._frame.setFocusPolicy(_no_focus())
        self._frame.setAttribute(_transparent(), True)
        self._stage.track_chrome(self._title)
        self._stage.dock_on(self._title)

    def _sync_title(self) -> None:
        self._title.setText(page_title_text(self._session.document))

    def _position_after(self, _changeset: object) -> None:
        self._sync_title()
        self._preview.arrange()
        self._position_chrome()

    def _scroll_moved(self, _value: int) -> None:
        # A drag re-solves once on sliderReleased.
        if self.horizontalScrollBar().isSliderDown() or self.verticalScrollBar().isSliderDown():
            return
        self._chip_timer.start()

    def _refresh_chips_after_scroll(self) -> None:
        rect = visible_scene_rect(self)
        if rect == self._chip_viewport:
            return
        self._chip_viewport = rect
        controller = getattr(self, "_controller", None)
        if controller is not None:
            controller.refresh_overlay()

    def _position_chrome(self) -> None:
        proxy = self._stage.proxy
        if proxy.widget() is None:
            return
        self._stage.position_labels()
        rect = proxy.sceneBoundingRect()
        top_left = self.mapFromScene(rect.topLeft())
        bottom_right = self.mapFromScene(rect.bottomRight())
        page_width = max(1, bottom_right.x() - top_left.x())
        page_height = max(1, bottom_right.y() - top_left.y())
        title_y = max(0, top_left.y() - PAGE_TITLE_HEIGHT)
        self._title.setFixedWidth(page_width)
        self._title.move(top_left.x(), title_y)
        if top_left.y() <= PAGE_TITLE_HEIGHT:
            self._stage.seat_page_chip(self._title)
        self._title.raise_()
        preview = getattr(self, "_preview", None)
        if preview is not None:
            preview.raise_chrome()
        self._frame.setGeometry(top_left.x(), title_y, page_width, page_height + PAGE_TITLE_HEIGHT)
        self._frame.lower()
        self._place_toast()

    def _apply_page_chrome(self, tokens: ShellThemeTokens) -> None:
        shadow = page_shadow_rgba(is_dark=tokens.is_dark, is_high_contrast=tokens.is_high_contrast)
        self._stage.proxy.setGraphicsEffect(None)
        if shadow == self._shadow_rgba and self._shadow_plate is not None:
            _apply_page_chrome_style(self._title, self._frame, tokens)
            return
        self._shadow_rgba = shadow
        self._shadow_plate = None if shadow is None else _shadow_plate(shadow)
        _apply_page_chrome_style(self._title, self._frame, tokens)

    def _place_toast(self) -> None:
        if self._toast.isVisible():
            self._toast.adjustSize()
            toast_x = max(0, (self.width() - self._toast.width()) // 2)
            self._toast.move(toast_x, self.height() - self._toast.height() - 16)


def _palette(tokens: Optional[ShellThemeTokens]) -> CanvasPalette:
    if tokens is None:
        fill, dot = backdrop_colors(is_dark=False, is_high_contrast=False)
        faint, accent, muted, panel, border, text = fallback_backdrop_roles()
        return CanvasPalette(
            overlay=overlay_palette(False),
            backdrop=BackdropPalette(
                fill=fill,
                dot=dot,
                faint=faint,
                accent=accent,
                muted=muted,
                panel=panel,
                border=border,
                text=text,
            ),
        )
    fill, dot = backdrop_colors(is_dark=tokens.is_dark, is_high_contrast=tokens.is_high_contrast)
    return CanvasPalette(
        overlay=overlay_palette(tokens.is_high_contrast),
        backdrop=BackdropPalette(
            fill=fill,
            dot=dot,
            faint=tokens.gutter_text or tokens.text_muted,
            accent=tokens.accent,
            muted=tokens.text_muted,
            panel=tokens.panel_bg,
            border=tokens.border,
            text=tokens.text_primary,
        ),
    )


def _apply_page_chrome_style(title: QWidget, frame: QWidget, tokens: Optional[ShellThemeTokens]) -> None:
    border = ""
    if tokens is not None and tokens.is_high_contrast:
        border = tokens.text_primary
    setter = getattr(title, "set_border", None)
    if callable(setter):
        setter(border)
    frame_border = "1px solid %s" % border if border else "none"
    frame.setStyleSheet(
        "QWidget#formBuilder\\.pageFrame { background: transparent; border: %s; }" % frame_border
    )


def _docked(frame: OverlayFrame) -> Tuple[Tuple[Chip, int, int], ...]:
    """Docked chips with the dock origin they were solved against."""
    dock = frame.dock
    if dock is None:
        return ()
    return tuple(
        (item, dock.x, dock.y) for item in frame.items if isinstance(item, Chip) and item.docked
    )


def _title_font() -> QFont:
    font = QFont(startup_font())
    font.setPixelSize(11)
    weight = getattr(getattr(QFont, "Weight", QFont), "DemiBold")
    font.setWeight(weight)
    return font


class _PageTitle(QWidget):
    """22 px caption. Fill, glyphs, and title text stay the same in every theme."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.pageTitle")
        self.setAccessibleName("Page title")
        self.setFixedHeight(PAGE_TITLE_HEIGHT)
        self.setFont(_title_font())
        self._text = ""
        self._border = ""
        self._docked: Tuple[Tuple[Chip, int, int], ...] = ()
        self._palette: Optional[CanvasPalette] = None

    def text(self) -> str:
        return self._text

    def setText(self, text: str) -> None:  # noqa: N802 - Qt-style setter the canvas already calls
        self._text = text
        self.update()

    def set_border(self, color: str) -> None:
        self._border = color
        self.update()

    def set_docked(self, docked: Tuple[Tuple[Chip, int, int], ...], palette: CanvasPalette) -> None:
        """Selection chips that had no clear seat on the canvas sit on this strip."""
        if docked == self._docked and palette is self._palette:
            return
        self._docked = docked
        self._palette = palette
        self.update()

    def docked(self) -> Tuple[Chip, ...]:
        return tuple(item for item, _x, _y in self._docked)

    def docked_view_rects(self) -> Tuple[QRect, ...]:
        """Where docked chips are painted, in this caption's coordinates."""
        return tuple(
            QRect(item.rect.x - dock_x, item.rect.y - dock_y, item.rect.width, item.rect.height)
            for item, dock_x, dock_y in self._docked
        )

    def paintEvent(self, _event: object) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(PAGE_TITLE_FILL))
        if self._border:
            pen = QPen(QColor(self._border))
            painter.setPen(pen)
            painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        painter.setFont(self.font())
        painter.setPen(QColor(PAGE_TITLE_TEXT))
        metrics = painter.fontMetrics()
        available = max(0, self.width() - 8 - 56)
        elide = getattr(getattr(Qt, "TextElideMode", Qt), "ElideRight")
        shown = metrics.elidedText(self._text, elide, available)
        baseline = (self.height() + metrics.ascent() - metrics.descent()) // 2
        painter.drawText(8, baseline, shown)
        _paint_caption_glyphs(painter, self.width())
        if self._palette is not None:
            for item, dock_x, dock_y in self._docked:
                painter.save()
                painter.translate(-dock_x, -dock_y)
                paint_docked_chip(painter, item, self._palette)
                painter.restore()
        painter.end()


_SHADOW_BLUR = 18
_SHADOW_OFFSET_Y = 2
_SHADOW_CORE = 40


def _shadow_plate(color: Tuple[int, int, int, int]) -> QPixmap:
    """One blurred rectangle. Corners stay 1:1 and the middle stretches over the page."""
    span = _SHADOW_BLUR * 2 + _SHADOW_CORE
    image = QImage(span, span, getattr(getattr(QImage, "Format", QImage), "Format_ARGB32_Premultiplied"))
    image.fill(0)
    painter = QPainter(image)
    painter.setPen(getattr(getattr(Qt, "PenStyle", Qt), "NoPen"))
    painter.setBrush(QColor(*color))
    painter.drawRect(_SHADOW_BLUR, _SHADOW_BLUR, _SHADOW_CORE, _SHADOW_CORE)
    painter.end()
    return QPixmap.fromImage(_box_blur(image, _SHADOW_BLUR // 3))


def _box_blur(image: QImage, radius: int) -> QImage:
    current = image
    for _pass in range(3):
        current = _blur_once(current, radius)
    return current


def _blur_once(image: QImage, radius: int) -> QImage:
    width = image.width()
    height = image.height()
    src = [int(image.pixel(x, y)) for y in range(height) for x in range(width)]
    blurred = _blur_axis(_blur_axis(src, width, height, radius, True), width, height, radius, False)
    out = QImage(width, height, image.format())
    for y in range(height):
        for x in range(width):
            out.setPixel(x, y, blurred[y * width + x])
    return out


def _blur_axis(src: List[int], width: int, height: int, radius: int, horizontal: bool) -> List[int]:
    out = [0] * (width * height)
    if horizontal:
        for y in range(height):
            _blur_line(src, out, y * width, 1, width, radius)
    else:
        for x in range(width):
            _blur_line(src, out, x, width, height, radius)
    return out


def _blur_line(src: List[int], out: List[int], start: int, step: int, count: int, radius: int) -> None:
    prefix: List[Tuple[int, int, int, int]] = [(0, 0, 0, 0)]
    acc = (0, 0, 0, 0)
    for index in range(count):
        pixel = src[start + index * step]
        channel = ((pixel >> 24) & 255, (pixel >> 16) & 255, (pixel >> 8) & 255, pixel & 255)
        acc = (acc[0] + channel[0], acc[1] + channel[1], acc[2] + channel[2], acc[3] + channel[3])
        prefix.append(acc)
    for index in range(count):
        left = max(0, index - radius)
        right = min(count - 1, index + radius)
        sample = right - left + 1
        high = prefix[right + 1]
        low = prefix[left]
        out[start + index * step] = (
            ((high[0] - low[0]) // sample) << 24
            | ((high[1] - low[1]) // sample) << 16
            | ((high[2] - low[2]) // sample) << 8
            | ((high[3] - low[3]) // sample)
        )


def _paint_shadow_plate(painter: QPainter, plate: QPixmap, page: QRectF) -> None:
    blur = _SHADOW_BLUR
    dest_x = page.x() - blur
    dest_y = page.y() - blur + _SHADOW_OFFSET_Y
    dest_w = page.width() + blur * 2
    dest_h = page.height() + blur * 2
    if dest_w <= blur * 2 or dest_h <= blur * 2:
        painter.drawPixmap(QRectF(dest_x, dest_y, dest_w, dest_h), plate, QRectF(plate.rect()))
        return
    source = plate.rect()
    margin = blur
    core_w = source.width() - margin * 2
    core_h = source.height() - margin * 2
    pieces = (
        (0, 0, margin, margin, dest_x, dest_y, margin, margin),
        (margin, 0, core_w, margin, dest_x + margin, dest_y, dest_w - margin * 2, margin),
        (source.width() - margin, 0, margin, margin, dest_x + dest_w - margin, dest_y, margin, margin),
        (0, margin, margin, core_h, dest_x, dest_y + margin, margin, dest_h - margin * 2),
        (margin, margin, core_w, core_h, dest_x + margin, dest_y + margin, dest_w - margin * 2, dest_h - margin * 2),
        (source.width() - margin, margin, margin, core_h, dest_x + dest_w - margin, dest_y + margin, margin, dest_h - margin * 2),
        (0, source.height() - margin, margin, margin, dest_x, dest_y + dest_h - margin, margin, margin),
        (margin, source.height() - margin, core_w, margin, dest_x + margin, dest_y + dest_h - margin, dest_w - margin * 2, margin),
        (source.width() - margin, source.height() - margin, margin, margin, dest_x + dest_w - margin, dest_y + dest_h - margin, margin, margin),
    )
    for sx, sy, sw, sh, dx, dy, dw, dh in pieces:
        painter.drawPixmap(QRectF(dx, dy, dw, dh), plate, QRectF(sx, sy, sw, sh))


def _paint_caption_glyphs(painter: QPainter, width: int) -> None:
    pen = QPen(QColor(PAGE_TITLE_GLYPH))
    pen.setWidth(1)
    painter.setPen(pen)
    no_brush = getattr(getattr(Qt, "BrushStyle", Qt), "NoBrush")
    painter.setBrush(no_brush)
    size = 10
    top = 6
    right = width - 8
    close_x = right - size
    painter.drawLine(close_x, top, close_x + size, top + size)
    painter.drawLine(close_x, top + size, close_x + size, top)
    square_x = close_x - size - 6
    painter.drawRect(square_x, top, size, size)
    dash_x = square_x - size - 6
    mid = top + size // 2
    painter.drawLine(dash_x, mid, dash_x + size, mid)


__all__ = ["FormCanvas"]
