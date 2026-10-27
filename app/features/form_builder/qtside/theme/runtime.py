"""Runtime look isolation for the canvas (CONTRACTS.md section 5.4).

The canvas shows the form as the shipped app will look, never in the
builder's chrome theme.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

from app.qt.QtCore import QEvent, QObject, Qt
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
_ROOT_MARK = "_cbcsRuntimeRoot"
_RELEASING = False
_PIN_FILTER: Optional[QObject] = None

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


def _fusion_for(widget: QWidget) -> QStyle:
    """A Fusion style owned by ``widget``.

    One shared style is deleted when a later stylesheet polish destroys the
    widget that was last given it, and the next build then crashes in setStyle.
    """
    created = QStyleFactory.create(RUNTIME_STYLE_KEY)
    if created is None:
        raise RuntimeError("Qt did not provide the Fusion style")
    created.setParent(widget)
    return created


def isolate_widget(widget: QWidget) -> None:
    """Pin one realized root to Fusion.

    The shell styles tooltips without an application style sheet. An ancestor
    sheet can still wrap this tree. The pin filter puts Fusion back and
    refreshes that ancestor widget only. It never clears the application sheet.
    """
    widget.setProperty(_ROOT_MARK, True)
    widget.setStyle(_fusion_for(widget))
    widget.setPalette(QPalette(runtime_palette()))
    widget.setFont(startup_font())
    _install_pin_filter()


def _pin_tree(widget: QWidget) -> None:
    targets = [widget]
    children = widget.findChildren(QWidget)
    if children:
        targets.extend(list(children))
    attribute = Qt.WidgetAttribute
    for target in targets:
        own_palette = QPalette(target.palette()) if target.testAttribute(attribute.WA_SetPalette) else None
        own_font = QFont(target.font()) if target.testAttribute(attribute.WA_SetFont) else None
        if target.style().metaObject().className() != "QFusionStyle":
            target.setStyle(_fusion_for(target))
        if own_palette is not None:
            target.setPalette(own_palette)
        else:
            target.setPalette(QPalette(runtime_palette()))
        if own_font is not None:
            target.setFont(own_font)
        else:
            target.setFont(startup_font())


def _release_ancestor_sheet(widget: QWidget) -> None:
    global _RELEASING
    parent = widget.parentWidget()
    seen = set()
    while parent is not None and id(parent) not in seen:
        seen.add(id(parent))
        sheet = parent.styleSheet()
        if sheet:
            _RELEASING = True
            try:
                parent.setStyleSheet("")
                parent.setStyleSheet(sheet)
            finally:
                _RELEASING = False
            return
        parent = parent.parentWidget()


class _FusionPin(QObject):
    """Put Fusion back when an ancestor style sheet wraps the realized tree."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        # StyleChange re-enters setStyle and crashes a corpus build. Parenting
        # is the moment an ancestor sheet can wrap the tree, and it does not.
        if _RELEASING or event.type() != QEvent.ParentChange or not isinstance(watched, QWidget):
            return False
        if not watched.property(_ROOT_MARK) or watched.property("_cbcsSheetReleased"):
            return False
        watched.setProperty("_cbcsSheetReleased", True)
        _pin_tree(watched)
        _release_ancestor_sheet(watched)
        return False


def _install_pin_filter() -> None:
    global _PIN_FILTER
    app = QApplication.instance()
    if not isinstance(app, QApplication) or _PIN_FILTER is not None:
        return
    _PIN_FILTER = _FusionPin(app)
    app.installEventFilter(_PIN_FILTER)


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
