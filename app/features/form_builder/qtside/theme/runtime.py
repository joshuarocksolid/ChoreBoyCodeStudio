"""Runtime look isolation for the canvas (CONTRACTS.md section 5.4).

The canvas shows the form as the shipped app will look, never in the
builder's chrome theme.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

from app.qt.QtCore import QEvent, QObject, QTimer, Qt
from app.qt.QtGui import QFont, QPalette
from app.qt.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsProxyWidget,
    QGraphicsScene,
    QGraphicsView,
    QStyle,
    QStyleFactory,
    QWidget,
)
from app.qt.qt_compat import wrapper_is_valid

RUNTIME_STYLE_KEY = "Fusion"

_STYLE: Optional[QStyle] = None
_PALETTE: Optional[QPalette] = None
_FONT: Optional[QFont] = None
_SEALING = False
_HOLDS: set = set()
_PENDING: set = set()

_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_BLOCK = re.compile(r"([^{}]+)\{")


def runtime_style() -> QStyle:
    """One process-wide Fusion style, parented to the application.

    ``QGraphicsScene.setStyle`` takes ownership and deletes that object, so a
    scene gets its own Fusion style. Widgets share this one. Widget
    ``setStyle`` does not take ownership.
    """
    global _STYLE
    if _STYLE is not None and not wrapper_is_valid(_STYLE):
        _STYLE = None
    if _STYLE is None:
        created = QStyleFactory.create(RUNTIME_STYLE_KEY)
        if created is None:
            raise RuntimeError("Qt did not provide the Fusion style")
        created.setParent(_ensure_app())
        _STYLE = created
    return _STYLE


def runtime_palette() -> QPalette:
    """Fusion's standard palette. Never derived from the shell theme."""
    global _PALETTE
    if _PALETTE is None:
        _PALETTE = runtime_style().standardPalette()
    return _PALETTE


def startup_font() -> QFont:
    """The application font from the first call, before a theme can replace it."""
    global _FONT
    if _FONT is None:
        _ensure_app()
        _FONT = QFont(QApplication.font())
    return _FONT


def isolate_scene(scene: QGraphicsScene) -> None:
    """Apply the runtime look to the scene that hosts the realized form."""
    owned = QStyleFactory.create(RUNTIME_STYLE_KEY)
    if owned is None:
        raise RuntimeError("Qt did not provide the Fusion style")
    scene.setStyle(owned)
    scene.setPalette(QPalette(runtime_palette()))
    scene.setFont(startup_font())


def isolate_widget(widget: QWidget) -> None:
    """Pin one realized root to the runtime look.

    Child widgets inherit the root palette and font. A later shell theme
    change updates the application, not widgets that already have their own.

    A ``QToolTip`` application style sheet still wraps widgets in
    ``QStyleSheetStyle``. That wrapper makes a spin box 2px taller than
    Fusion and shifts antialiasing. ``setStyle(Fusion)`` does not stick
    while the sheet is installed. Clearing the sheet and putting it back
    leaves a widget that already owns its style on Fusion. A later dynamic
    property change wraps it again, so the root re-seals on the next turn
    and lays out at the Fusion size.
    """
    widget.setStyle(runtime_style())
    widget.setPalette(QPalette(runtime_palette()))
    widget.setFont(startup_font())
    if not _application_stylesheet():
        return
    _pin_owned_style(widget)
    _release_stylesheet_style()
    _apply_runtime_look(widget)
    _hold_across_reparent(widget)


def _application_stylesheet() -> str:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return ""
    return app.styleSheet()


def _widget_children(widget: QWidget) -> list:
    found = widget.findChildren(QWidget)
    return list(found) if found is not None else []


def _pin_owned_style(widget: QWidget) -> None:
    style = runtime_style()
    for target in [widget, *_widget_children(widget)]:
        palette = None
        font = None
        if target.testAttribute(Qt.WidgetAttribute.WA_SetPalette):
            palette = QPalette(target.palette())
        if target.testAttribute(Qt.WidgetAttribute.WA_SetFont):
            font = QFont(target.font())
        if target.style().metaObject().className() != "QFusionStyle":
            target.setStyle(style)
            target.ensurePolished()
        if palette is not None:
            target.setPalette(palette)
        if font is not None:
            target.setFont(font)


def _apply_runtime_look(widget: QWidget) -> None:
    for target in [widget, *_widget_children(widget)]:
        if not target.testAttribute(Qt.WidgetAttribute.WA_SetPalette):
            target.setPalette(QPalette(runtime_palette()))
        if not target.testAttribute(Qt.WidgetAttribute.WA_SetFont):
            target.setFont(startup_font())


def _release_stylesheet_style() -> None:
    """Drop the stylesheet wrapper from widgets that already own a style."""
    global _SEALING
    if _SEALING:
        return
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return
    sheet = app.styleSheet()
    if not sheet:
        return
    _SEALING = True
    try:
        app.setStyleSheet("")
        app.setStyleSheet(sheet)
    finally:
        _SEALING = False


class _FusionHold(QObject):
    """Re-seal Fusion after a property change wraps the style again."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if _SEALING or not isinstance(watched, QWidget):
            return False
        if getattr(watched, "_cbcs_seal_settled", False):
            return False
        kind = int(event.type())
        watched_kind = (
            int(QEvent.Type.ParentChange),
            int(QEvent.Type.DynamicPropertyChange),
            int(QEvent.Type.StyleChange),
        )
        if kind in watched_kind:
            _schedule_reseal(watched)
        return False


def _schedule_reseal(widget: QWidget) -> None:
    if widget in _PENDING or _SEALING:
        return
    _PENDING.add(widget)
    QTimer.singleShot(0, lambda watched=widget: _finish_reseal(watched))


def _finish_reseal(widget: QWidget) -> None:
    _PENDING.discard(widget)
    if _SEALING or not wrapper_is_valid(widget):
        return
    if widget.style().metaObject().className() != "QStyleSheetStyle":
        return
    _pin_owned_style(widget)
    _release_stylesheet_style()
    _apply_runtime_look(widget)
    _relayout(widget)
    if widget.style().metaObject().className() == "QStyleSheetStyle":
        widget._cbcs_seal_settled = True  # noqa: SLF001


def _relayout(widget: QWidget) -> None:
    widget.updateGeometry()
    layout = widget.layout()
    if layout is not None and wrapper_is_valid(layout):
        layout.invalidate()
        layout.activate()
    widget.update()


def _hold_across_reparent(widget: QWidget) -> None:
    if getattr(widget, "_cbcs_fusion_hold", None) is not None:
        return
    guard = _FusionHold(widget)
    _HOLDS.add(guard)
    widget._cbcs_fusion_hold = guard  # noqa: SLF001
    widget.installEventFilter(guard)


def host_form(root: QWidget) -> QGraphicsView:
    """Embed ``root`` in a proxy so a window style sheet does not cascade into it.

    The view parents the scene. A scene with no parent is collected with the
    Python wrapper, and that deletes the form.
    """
    isolate_widget(root)
    view = QGraphicsView()
    scene = QGraphicsScene(view)
    isolate_scene(scene)
    proxy = QGraphicsProxyWidget()
    proxy.setWidget(root)
    scene.addItem(proxy)
    view.setScene(scene)
    shape = getattr(getattr(QFrame, "Shape", QFrame), "NoFrame")
    view.setFrameShape(shape)
    return view


def tooltip_selectors(style_sheet: str) -> Tuple[str, ...]:
    """Selectors of every rule in ``style_sheet``, comments removed."""
    text = _COMMENT.sub("", style_sheet)
    found = []
    for block in _BLOCK.findall(text):
        for part in block.split(","):
            selector = part.strip()
            if selector:
                found.append(selector)
    return tuple(found)


def selectors_are_tooltip_only(style_sheet: str) -> bool:
    """True when every selector is a ``QToolTip`` rule and there is at least one."""
    found = tooltip_selectors(style_sheet)
    if not found:
        return False
    return all(_is_tooltip(selector) for selector in found)


def _is_tooltip(selector: str) -> bool:
    head = selector.split()[0]
    return head == "QToolTip" or head.startswith("QToolTip:") or head.startswith("QToolTip[")


def _ensure_app() -> QApplication:
    app = QApplication.instance()
    if isinstance(app, QApplication):
        return app
    return QApplication([])
