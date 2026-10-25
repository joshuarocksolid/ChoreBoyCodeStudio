"""Canvas-only text size, screen scale, and the two-widths view.

Nothing in this module writes the document. The realizer still owns the
widgets. A second realizer, when the wide copy is open, does not register
resources.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from app.qt.QtCore import QEvent, QPoint, QRectF, QTimer, Qt
from app.qt.QtGui import QColor, QFont, QPainter, QPen
from app.qt.QtWidgets import (
    QGraphicsProxyWidget,
    QGraphicsView,
    QLabel,
    QLineEdit,
    QWidget,
)
from app.qt.qt_compat import event_pos, wrapper_is_valid

from app.features.form_builder.engine.events import PRIORITY_REALIZE, ChangeSet
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.sizing import (
    QWIDGET_SIZE_MAX,
    WIDE_SCREEN_PX,
    effective_preview_points,
    preview_pill,
)
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import FontValue, SizeValue
from app.features.form_builder.qtside.canvas.core.structure import effective_selection
from app.features.form_builder.qtside.canvas.stage import Stage
from app.features.form_builder.qtside.realize.api import Realizer
from app.features.form_builder.qtside.realize.props import apply_entry
from app.features.form_builder.qtside.sizing_live import policy_name
from app.features.form_builder.qtside.theme.chrome import PAGE_TITLE_HEIGHT
from app.features.form_builder.qtside.theme.overlay import overlay_palette
from app.features.form_builder.qtside.theme.runtime import startup_font

# After the realizer pins the runtime font, before the page is placed.
_PRIORITY_PREVIEW = PRIORITY_REALIZE + 5
_CANNOT_GROW = frozenset({"Fixed", "Maximum"})
# sizeHint is stable across these. A text or font edit drops the cache.
_HINT_STABLE = frozenset(
    {
        "sizePolicy",
        "minimumSize",
        "maximumSize",
        "minimumWidth",
        "minimumHeight",
        "maximumWidth",
        "maximumHeight",
        "geometry",
    }
)
_NODE = "_cbcsNodeId"


def _sheet_text(entry: object) -> str:
    if entry is None:
        return ""
    value = getattr(entry, "value", None)
    text = getattr(value, "text", None)
    if isinstance(text, str):
        return text
    return ""


def _pt(points: float) -> str:
    return ("%.4f" % points).rstrip("0").rstrip(".")


def _css_ident(name: str) -> str:
    return "".join(ch for ch in name if ch.isalnum() or ch == "_")


def _named(root: QWidget, name: str) -> Optional[QWidget]:
    if root.objectName() == name:
        return root
    found = root.findChild(QWidget, name)
    return found if isinstance(found, QWidget) else None


def _sheets_by_name(document: UiDocument) -> Dict[str, str]:
    sheets: Dict[str, str] = {}
    for node in document.iter_widgets():
        if not node.object_name:
            continue
        sheets[node.object_name] = _sheet_text(node.prop("styleSheet"))
    return sheets


def _preview_sheet(
    document_sheet: str,
    points: float,
    overrides: Sequence[Tuple[str, float]],
) -> str:
    """The star rule sets the preview size. A saved point size keeps its ratio."""
    lines = [document_sheet, "* { font-size: %spt; }" % _pt(points)]
    for name, sized in overrides:
        ident = _css_ident(name)
        if not ident:
            continue
        lines.append("#%s { font-size: %spt; }" % (ident, _pt(sized)))
    return "\n".join(line for line in lines if line)


class FormPreview:
    """Preview scale and the second live copy. The command log is never used."""

    def __init__(
        self,
        view: QGraphicsView,
        session: FormSession,
        realizer: Realizer,
        stage: Stage,
    ) -> None:
        self._view = view
        self._session = session
        self._realizer = realizer
        self._stage = stage
        self._text_factor = 1.0
        self._screen = 100
        self._absolute: Optional[float] = None
        self._widths = False
        self._wide = WIDE_SCREEN_PX
        self._mirror: Optional[Realizer] = None
        self._mirror_proxy: Optional[QGraphicsProxyWidget] = None
        self._forced = False
        self._pill = _pill(view)
        self._narrow = _chip(view, "formBuilder.narrowChip", "Narrowest")
        self._wide_edit = QLineEdit(view)
        self._wide_edit.setObjectName("formBuilder.wideChip")
        self._wide_edit.setAccessibleName("Wide width")
        self._wide_edit.editingFinished.connect(self._commit_wide)
        self._wide_edit.hide()
        self._pill.linkActivated.connect(self._pill_link)
        self._font_rules: Dict[str, float] = {}
        self._font_rules_ready = False
        self._cut_widgets: List[QWidget] = []
        self._hint_cache: Dict[int, Tuple[int, int]] = {}
        self._moved: Optional[Tuple[NodeId, ...]] = None
        self._cut_wait = False
        self._cut_timer = QTimer(view)
        self._cut_timer.setSingleShot(True)
        self._cut_timer.timeout.connect(self._recount_cutoff)
        self._sub = session.log.subscribe(self._on_change, priority=_PRIORITY_PREVIEW)

    def preview_choice(self) -> Tuple[float, int, Optional[float]]:
        """Text factor, screen percent, and an absolute point size when set."""
        return (self._text_factor, self._screen, self._absolute)

    @property
    def widths_open(self) -> bool:
        return self._widths

    def points(self) -> float:
        base = float(startup_font().pointSizeF() or startup_font().pointSize() or 10)
        return effective_preview_points(base, self._text_factor, self._screen, self._absolute)

    def set_text_factor(self, factor: float) -> None:
        self._text_factor = float(factor)
        self._absolute = None
        self._refresh()

    def set_screen(self, percent: int) -> None:
        self._screen = int(percent)
        self._refresh()

    def set_points(self, points: Optional[float]) -> None:
        """An absolute point size, or None to follow the text factor again."""
        self._absolute = None if points is None else float(points)
        self._refresh()

    def set_wide(self, pixels: int) -> None:
        self._wide = max(1, int(pixels))
        if self._widths:
            self._refresh()
        else:
            self._wide_edit.setText("Wide · %d px" % self._wide)

    def toggle_widths(self) -> None:
        self._widths = not self._widths
        if not self._widths:
            self._release_width()
            self._drop_mirror()
        self._refresh()

    def reset(self) -> None:
        self._text_factor = 1.0
        self._screen = 100
        self._absolute = None
        self._refresh()

    def claim(self, event: QEvent) -> bool:
        """Select from the wide copy. The design copy keeps the gesture loop."""
        if not self._widths or self._mirror_proxy is None:
            return False
        press = getattr(getattr(QEvent, "Type", QEvent), "MouseButtonPress")
        if event.type() != press:
            return False
        proxy = self._mirror_proxy
        if not proxy.isVisible():
            return False
        pos = event_pos(event)
        scene_pos = self._view.mapToScene(QPoint(int(pos.x()), int(pos.y())))
        if not proxy.sceneBoundingRect().contains(scene_pos):
            return False
        local = proxy.mapFromScene(scene_pos)
        root = proxy.widget()
        if root is None:
            return True
        child = _widget_at(root, int(local.x()), int(local.y()))
        node = _node_of(child)
        if node is not None:
            self._session.selection.set((node,), source=SelectionSource.CANVAS)
        return True

    def raise_chrome(self) -> None:
        """Keep the preview chips above the page title."""
        for widget in (self._pill, self._narrow, self._wide_edit):
            if widget.isVisible():
                widget.raise_()

    def arrange(self) -> None:
        """Place the wide copy after the stage has placed the design page."""
        self._sync_pill()
        if not self._widths:
            self._hide_mirror()
            self._narrow.hide()
            self._wide_edit.hide()
            return
        mirror = self._ensure_mirror()
        wide = mirror.root_widget
        narrow = self._realizer.root_widget
        if wide is None or narrow is None:
            return
        self._force_width(narrow, _narrow_width(narrow, _stored_minimum_width(self._session.document.root)))
        self._force_width(wide, self._wide)
        factor = self._stage.view_map().factor or 1.0
        origin = self._stage.proxy.pos()
        proxy = self._mirror_proxy
        assert proxy is not None
        proxy.setWidget(wide)
        proxy.setScale(factor)
        proxy.show()
        gap = 32.0
        narrow_w = float(narrow.width()) * factor
        narrow_h = float(narrow.height()) * factor
        wide_w = float(wide.width()) * factor
        wide_h = float(wide.height()) * factor
        side = narrow_w + gap + wide_w <= float(self._view.viewport().width())
        if side:
            proxy.setPos(origin.x() + narrow_w + gap, origin.y())
            scene_w = origin.x() + narrow_w + gap + wide_w + 48
            scene_h = origin.y() + max(narrow_h, wide_h) + 64
            wide_origin = proxy.pos()
        else:
            proxy.setPos(origin.x(), origin.y() + narrow_h + gap + 18)
            scene_w = origin.x() + max(narrow_w, wide_w) + 48
            scene_h = origin.y() + narrow_h + gap + wide_h + 80
            wide_origin = proxy.pos()
        scene = self._view.scene()
        if scene is not None:
            current = scene.sceneRect()
            scene.setSceneRect(0, 0, max(current.width(), scene_w), max(current.height(), scene_h))
        self._move_chip(self._narrow, origin.x(), origin.y(), "Narrowest · %d px" % int(narrow.width()))
        self._move_wide(wide_origin.x(), wide_origin.y())

    def paint_cutoff(self, painter: QPainter) -> None:
        if self._identity():
            return
        root = self._realizer.root_widget
        if root is None:
            return
        pen = QPen(_tab_color(self._view))
        pen.setStyle(getattr(getattr(Qt, "PenStyle", Qt), "DashLine"))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(getattr(getattr(Qt, "BrushStyle", Qt), "NoBrush"))
        for widget in self._cut_widgets:
            if not wrapper_is_valid(widget):
                continue
            origin = widget.mapTo(root, QPoint(0, 0))
            rect = QRectF(float(origin.x()), float(origin.y()), float(widget.width()), float(widget.height()))
            painter.drawRect(self._stage.proxy.mapRectToScene(rect))

    def paint_wide_selection(self, painter: QPainter) -> None:
        """The design overlay only knows the narrow page. The wide copy gets the same stroke."""
        proxy = self._mirror_proxy
        mirror = self._mirror
        if not self._widths or proxy is None or mirror is None or not proxy.isVisible():
            return
        root = proxy.widget()
        if root is None or not wrapper_is_valid(root):
            return
        current = effective_selection(self._session.document, self._session.selection.state).current
        if current is None:
            return
        widget = mirror.widget_for(current)
        if widget is None or not widget.isVisible():
            return
        if widget is not root and not root.isAncestorOf(widget):
            return
        origin = widget.mapTo(root, QPoint(0, 0))
        rect = QRectF(float(origin.x()), float(origin.y()), float(widget.width()), float(widget.height()))
        pen = QPen(_overlay_color(self._view, "select"))
        pen.setCosmetic(True)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(getattr(getattr(Qt, "BrushStyle", Qt), "NoBrush"))
        painter.drawRect(proxy.mapRectToScene(rect))

    def dispose(self) -> None:
        self._cut_timer.stop()
        self._sub.close()
        self._drop_mirror()

    def _refresh(self) -> None:
        self._on_change(None)
        self._stage.place()
        self.arrange()

    def _on_change(self, changeset: object) -> None:
        if not _keeps_hints(changeset):
            self._hint_cache.clear()
        root = self._realizer.root_widget
        if _sheet_changed(changeset, self._session.document.root.id, previewing=not self._identity()):
            if not self._identity():
                self._sync_font_rules(changeset)
            if root is not None:
                self._apply_font(root)
            mirror = self._mirror
            if mirror is not None and self._widths:
                wide = mirror.root_widget
                if wide is not None:
                    self._apply_font(wide)
        if self._widths and root is not None:
            self._force_width(root, _narrow_width(root, _stored_minimum_width(self._session.document.root)))
        elif self._forced:
            self._release_width()
        mirror = self._mirror
        if mirror is not None and self._widths:
            wide = mirror.root_widget
            if wide is not None:
                self._force_width(wide, self._wide)

    def _identity(self) -> bool:
        return (
            self._absolute is None
            and abs(self._text_factor - 1.0) < 0.001
            and self._screen == 100
        )

    def _apply_font(self, widget: QWidget) -> None:
        # A shell rule such as "QLabel { font-weight }" replaces setFont.
        # The point size has to be a stylesheet on the form, or the label
        # stays at the theme size. The document sheet is kept in front.
        sheet = _sheet_text(self._session.document.root.prop("styleSheet"))
        if self._identity():
            self._font_rules_ready = False
            self._clear_saved_fonts(widget)
            widget.setStyleSheet(sheet)
            widget.setFont(QFont(startup_font()))
            entry = self._session.document.root.prop("font")
            if entry is not None:
                apply_entry(widget, entry, is_root=True, resolve_path=lambda path: path, problems=[])
            return
        font = QFont(startup_font())
        font.setPointSizeF(max(1.0, self.points()))
        widget.setFont(font)
        # Per-widget rules, not one long sheet. A root sheet with an id rule
        # per saved font makes the next layout match every rule against every
        # child, and that was the 16 pt edit.
        widget.setStyleSheet(_preview_sheet(sheet, self.points(), ()))
        self._paint_saved_fonts(widget)
        layout = widget.layout()
        if layout is not None:
            layout.invalidate()
            layout.activate()

    def _force_width(self, widget: QWidget, width: int) -> None:
        widget.setMinimumWidth(int(width))
        widget.setMaximumWidth(int(width))
        height = max(widget.sizeHint().height(), widget.minimumSizeHint().height(), widget.height(), 1)
        widget.resize(int(width), int(height))
        widget.show()
        layout = widget.layout()
        if layout is not None:
            layout.activate()
        self._forced = True

    def _release_width(self) -> None:
        root = self._realizer.root_widget
        if root is not None:
            min_w, min_h = _stored_size(self._session.document.root, "minimumSize", 0)
            max_w, max_h = _stored_size(self._session.document.root, "maximumSize", QWIDGET_SIZE_MAX)
            root.setMinimumSize(min_w, min_h)
            root.setMaximumSize(max_w, max_h)
            self._realizer.reapply_geometry((self._session.document.root.id,))
        self._forced = False

    def _ensure_mirror(self) -> Realizer:
        if self._mirror is None:
            self._mirror = Realizer(self._session, own_resources=False)
            self._mirror.build()
            proxy = QGraphicsProxyWidget()
            scene = self._view.scene()
            if scene is None:
                raise RuntimeError("two widths needs a scene")
            scene.addItem(proxy)
            self._mirror_proxy = proxy
        return self._mirror

    def _hide_mirror(self) -> None:
        proxy = self._mirror_proxy
        if proxy is not None:
            proxy.hide()

    def _drop_mirror(self) -> None:
        proxy = self._mirror_proxy
        if proxy is not None:
            proxy.setWidget(None)
            scene = self._view.scene()
            if scene is not None:
                scene.removeItem(proxy)
        mirror = self._mirror
        self._mirror = None
        self._mirror_proxy = None
        if mirror is not None:
            mirror.dispose()

    def _sync_font_rules(self, changeset: object) -> None:
        if changeset is None or not self._font_rules_ready:
            self._rebuild_font_rules()
            self._font_rules_ready = True
            return
        dirty = getattr(changeset, "property_dirty", ())
        for owner, kind, name in dirty:
            if kind != "property" or name != "font":
                continue
            node = self._session.document.get(owner)
            if not isinstance(node, WidgetNode) or not node.object_name:
                continue
            scaled = self._scaled_points(_saved_points(node))
            if scaled is None:
                self._font_rules.pop(node.object_name, None)
            else:
                self._font_rules[node.object_name] = scaled

    def _rebuild_font_rules(self) -> None:
        rules: Dict[str, float] = {}
        for node in self._session.document.iter_widgets():
            if not node.object_name:
                continue
            scaled = self._scaled_points(_saved_points(node))
            if scaled is None:
                continue
            rules[node.object_name] = scaled
        self._font_rules = rules

    def _paint_saved_fonts(self, root: QWidget) -> None:
        sheets = _sheets_by_name(self._session.document)
        for name, points in self._font_rules.items():
            found = _named(root, name)
            if found is None or found is root:
                continue
            ident = _css_ident(name)
            if not ident:
                continue
            found.setStyleSheet(sheets.get(name, "") + "\n#%s { font-size: %spt; }" % (ident, _pt(points)))

    def _clear_saved_fonts(self, root: QWidget) -> None:
        sheets = _sheets_by_name(self._session.document)
        for name in self._font_rules:
            found = _named(root, name)
            if found is None or found is root:
                continue
            found.setStyleSheet(sheets.get(name, ""))

    def _scaled_points(self, points: Optional[int]) -> Optional[float]:
        """Point size for an ``#objectName`` rule.

        A saved size equal to the theme size is already what ``* { font-size }``
        scales. An extra rule per widget makes every later layout walk a long
        stylesheet, which is the 16 pt edit cost.
        """
        if points is None:
            return None
        if abs(float(points) - _base_points()) < 0.05:
            return None
        return float(points) * self._scale()

    def _scale(self) -> float:
        base = _base_points()
        if self._absolute is not None:
            return float(self._absolute) / base
        return float(self._text_factor) * (float(self._screen) / 100.0)

    def _request_cutoff(self) -> None:
        if self._cut_wait:
            return
        self._cut_wait = True
        self._cut_timer.start(0)

    def note_moved(self, node_ids: Optional[Tuple[NodeId, ...]]) -> None:
        """The canvas frame names widgets whose rect changed. None scans the form."""
        self._moved = node_ids

    def _recount_cutoff(self) -> None:
        self._cut_wait = False
        if self._identity():
            self._cut_widgets = []
        elif self._moved is None:
            self._cut_widgets = _cutoff_widgets(self._realizer.root_widget, self._hint_cache)
        else:
            self._recheck(self._moved)
        self._moved = None
        self._place_pill()

    def _recheck(self, node_ids: Tuple[NodeId, ...]) -> None:
        moved = set(node_ids)
        kept: List[QWidget] = []
        for widget in self._cut_widgets:
            if not wrapper_is_valid(widget):
                continue
            node = _node_of(widget)
            if node is not None and node in moved:
                continue
            kept.append(widget)
        for node_id in node_ids:
            widget = self._realizer.widget_for(node_id)
            if widget is None or not widget.isVisible():
                continue
            if _cut_off(widget, self._hint_cache):
                kept.append(widget)
        self._cut_widgets = kept

    def _sync_pill(self) -> None:
        if self._identity():
            self._cut_widgets = []
            self._cut_timer.stop()
            self._cut_wait = False
        else:
            self._request_cutoff()
        self._place_pill()

    def _place_pill(self) -> None:
        base = float(startup_font().pointSizeF() or startup_font().pointSize() or 10)
        count = 0 if self._identity() else len(self._cut_widgets)
        text = preview_pill(base, self._text_factor, self._screen, self._absolute, count)
        if text is None:
            self._pill.hide()
            return
        self._pill.setText(_pill_html(text))
        self._pill.setMinimumWidth(_text_width(self._pill, text) + 16)
        self._pill.adjustSize()
        self._pill.show()
        self._pill.raise_()
        proxy = self._stage.proxy
        rect = proxy.sceneBoundingRect()
        corner = self._view.mapFromScene(rect.topRight())
        x = max(4, corner.x() - self._pill.width())
        y = max(4, corner.y() - PAGE_TITLE_HEIGHT - self._pill.height() - 6)
        self._pill.move(x, y)

    def _pill_link(self, href: str) -> None:
        if href == "reset":
            self.reset()
            return
        if href != "cutoff":
            return
        ids = _cutoff_ids(self._cut_widgets)
        if ids:
            self._session.selection.set(tuple(ids), source=SelectionSource.CANVAS)

    def _commit_wide(self) -> None:
        digits = "".join(ch for ch in self._wide_edit.text() if ch.isdigit())
        if digits:
            self.set_wide(int(digits))

    def _move_chip(self, label: QLabel, scene_x: float, scene_y: float, text: str) -> None:
        label.setText(text)
        label.adjustSize()
        origin = self._view.mapFromScene(scene_x, scene_y)
        label.move(int(origin.x()), max(4, int(origin.y()) - PAGE_TITLE_HEIGHT - label.height() - 4))
        label.show()
        label.raise_()

    def _move_wide(self, scene_x: float, scene_y: float) -> None:
        self._wide_edit.setText("Wide · %d px" % self._wide)
        self._wide_edit.setFixedWidth(max(120, _text_width(self._wide_edit, self._wide_edit.text()) + 16))
        origin = self._view.mapFromScene(scene_x, scene_y)
        self._wide_edit.move(int(origin.x()), max(4, int(origin.y()) - PAGE_TITLE_HEIGHT - self._wide_edit.height() - 4))
        self._wide_edit.show()
        self._wide_edit.raise_()


def _narrow_width(widget: QWidget, stored_minimum: int) -> int:
    hint = int(widget.minimumSizeHint().width())
    return max(hint, int(stored_minimum), 1)


def _widget_at(root: QWidget, x: int, y: int) -> QWidget:
    """Deepest visible child under a point. Transparent-for-mouse widgets still count."""
    chosen = root
    for child in root.children():
        if not isinstance(child, QWidget) or not child.isVisible():
            continue
        rect = child.geometry()
        if not rect.contains(int(x), int(y)):
            continue
        chosen = _widget_at(child, int(x) - int(rect.x()), int(y) - int(rect.y()))
    return chosen


def _sheet_changed(changeset: object, root_id: NodeId, *, previewing: bool) -> bool:
    """A preview setting change, or a root style or a saved font while previewing."""
    if not isinstance(changeset, ChangeSet):
        return True
    for owner, kind, name in changeset.property_dirty:
        if kind != "property":
            continue
        if owner == root_id and name in ("styleSheet", "font"):
            return True
        if previewing and name == "font":
            return True
    return False


def _base_points() -> float:
    base = float(startup_font().pointSizeF() or startup_font().pointSize() or 10)
    if base <= 0:
        return 10.0
    return base


def _saved_points(node: WidgetNode) -> Optional[int]:
    entry = node.prop("font")
    if entry is None or not isinstance(entry.value, FontValue):
        return None
    if entry.value.pointsize is None or int(entry.value.pointsize) <= 0:
        return None
    return int(entry.value.pointsize)


def _stored_minimum_width(node: WidgetNode) -> int:
    width, _height = _stored_size(node, "minimumSize", 0)
    return width


def _stored_size(node: WidgetNode, name: str, empty: int) -> Tuple[int, int]:
    entry = node.prop(name)
    if entry is None or not isinstance(entry.value, SizeValue):
        return empty, empty
    return int(entry.value.width), int(entry.value.height)


def _tab_color(view: QGraphicsView) -> QColor:
    return _overlay_color(view, "tab")


def _overlay_color(view: QGraphicsView, name: str) -> QColor:
    """Palette strings are ``#RRGGBBAA``. ``QColor`` reads eight digits as ``#AARRGGBB``."""
    viewport = view.viewport()
    contrast = bool(viewport.property("formBuilderHighContrast")) if viewport is not None else False
    raw = getattr(overlay_palette(contrast), name)
    text = raw[1:] if raw.startswith("#") else raw
    red = int(text[0:2], 16)
    green = int(text[2:4], 16)
    blue = int(text[4:6], 16)
    alpha = int(text[6:8], 16) if len(text) >= 8 else 255
    return QColor(red, green, blue, alpha)


def _cutoff_widgets(
    root: Optional[QWidget],
    cache: Optional[Dict[int, Tuple[int, int]]] = None,
) -> List[QWidget]:
    if root is None or not wrapper_is_valid(root):
        return []
    found = []
    for widget in root.findChildren(QWidget):
        if not widget.isVisible():
            continue
        if _cut_off(widget, cache):
            found.append(widget)
    return found


def _keeps_hints(changeset: object) -> bool:
    if not isinstance(changeset, ChangeSet):
        return False
    if changeset.replaced or changeset.added or changeset.removed or changeset.structure_dirty or changeset.renamed:
        return False
    if not changeset.property_dirty:
        return False
    for _owner, kind, name in changeset.property_dirty:
        if kind != "property" or name not in _HINT_STABLE:
            return False
    return True


def _cutoff_ids(widgets: Sequence[QWidget]) -> Sequence[NodeId]:
    ids: List[NodeId] = []
    for widget in widgets:
        node = _node_of(widget)
        if node is not None and node not in ids:
            ids.append(node)
    return ids


def _cut_off(widget: QWidget, cache: Optional[Dict[int, Tuple[int, int]]] = None) -> bool:
    hint_w, hint_h = _hint_size(widget, cache)
    policy = widget.sizePolicy()
    if hint_w > int(widget.width()) + 1 and policy_name(policy.horizontalPolicy()) in _CANNOT_GROW:
        return True
    if hint_h > int(widget.height()) + 1 and policy_name(policy.verticalPolicy()) in _CANNOT_GROW:
        return True
    return False


def _hint_size(widget: QWidget, cache: Optional[Dict[int, Tuple[int, int]]]) -> Tuple[int, int]:
    # height-for-width hints change when the widget gets narrower, so they
    # cannot be reused across a sizing edit.
    if cache is None or widget.hasHeightForWidth():
        hint = widget.sizeHint()
        return int(hint.width()), int(hint.height())
    raw = widget.property(_NODE)
    key = int(raw) if isinstance(raw, int) else id(widget)
    found = cache.get(key)
    if found is None:
        hint = widget.sizeHint()
        found = (int(hint.width()), int(hint.height()))
        cache[key] = found
    return found


def _node_of(widget: Optional[QWidget]) -> Optional[NodeId]:
    current = widget
    while current is not None:
        raw = current.property(_NODE)
        if isinstance(raw, int):
            return NodeId(raw)
        current = current.parentWidget()
    return None


def _text_width(widget: QWidget, text: str) -> int:
    metrics = widget.fontMetrics()
    advance = getattr(metrics, "horizontalAdvance", None)
    if advance is None:
        return int(metrics.width(text))
    return int(advance(text))


def _pill(parent: QWidget) -> QLabel:
    label = QLabel(parent)
    label.setObjectName("formBuilder.previewPill")
    label.setAccessibleName("Preview")
    label.setTextFormat(getattr(Qt, "TextFormat", Qt).RichText)
    label.setFocusPolicy(getattr(getattr(Qt, "FocusPolicy", Qt), "StrongFocus"))
    label.hide()
    return label


def _chip(parent: QWidget, object_name: str, accessible: str) -> QLabel:
    label = QLabel(parent, )
    label.setObjectName(object_name)
    label.setAccessibleName(accessible)
    label.hide()
    return label


def _pill_html(text: str) -> str:
    parts = text.split(" · ")
    if not parts:
        return ""
    body: List[str] = []
    for part in parts[:-1]:
        if "cut off" in part:
            body.append('<a href="cutoff">%s</a>' % _escape(part))
        else:
            body.append(_escape(part))
    body.append('<a href="reset">Reset</a>')
    return " · ".join(body)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
