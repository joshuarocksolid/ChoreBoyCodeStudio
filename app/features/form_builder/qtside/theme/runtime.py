"""Runtime look isolation for the canvas (CONTRACTS.md section 5.4).

The canvas shows the form as the shipped app will look, never in the
builder's chrome theme.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional, Tuple, cast

from app.qt.QtCore import Qt
from app.qt.QtGui import QFont, QKeySequence, QPalette
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
    """Pin one realized root to the runtime look.

    Child widgets inherit the root's style, palette and font. The shell keeps
    the application style sheet empty, so no QStyleSheetStyle wraps the form.
    A later shell theme change updates the application, not this root.
    """
    widget.setStyle(_fusion_for(widget))
    widget.setPalette(QPalette(runtime_palette()))
    widget.setFont(startup_font())


def pin_runtime_look(root: QWidget) -> None:
    """The user's form, as the app will show it: Fusion and the light palette.

    Editor chrome stays off this subtree. A stylesheet on the form is what
    paints line edits dark while spin boxes and table viewports stay light.
    The form keeps the font it already has, including a screen profile.
    """

    root.setStyleSheet("")
    root.setStyle(_fusion_for(root))
    light = QPalette(runtime_palette())
    root.setPalette(light)
    root.setAutoFillBackground(True)
    finder = getattr(root, "findChildren", None)
    if not callable(finder):
        return
    found = finder(QWidget)
    if not isinstance(found, (list, tuple)):
        return
    for child in found:
        if not isinstance(child, QWidget):
            continue
        child.setStyleSheet("")
        child.setPalette(light)


def silence_design_shortcuts(root: QWidget) -> None:
    """Drop key sequences on a design-time copy of the form.

    A record bar stores Ctrl+S on Save. Inside a graphics proxy that sequence
    is live and eats the shell's Save, in the form tab and in code tabs. The
    saved ``.ui`` and the generated window keep the sequences. The running
    app is a different widget tree.
    """

    empty = QKeySequence()
    context = getattr(getattr(Qt, "ShortcutContext", Qt), "WidgetShortcut", None)
    widgets = [root]
    finder = getattr(root, "findChildren", None)
    if callable(finder):
        widgets.extend(finder(QWidget))
    for widget in widgets:
        setter = getattr(widget, "setShortcut", None)
        if callable(setter):
            setter(empty)
        if context is not None:
            set_context = getattr(widget, "setShortcutContext", None)
            if callable(set_context):
                set_context(context)
        listed = getattr(widget, "actions", None)
        found = listed() if callable(listed) else ()
        for action in cast(Iterable[object], found):
            action.setShortcut(empty)
            if context is not None:
                action.setShortcutContext(context)


def host_form(root: QWidget) -> QGraphicsView:
    """Embed ``root`` in a proxy so a window style sheet does not cascade into it.

    The view parents the scene. A scene with no parent is collected with the
    Python wrapper, and that deletes the form.
    """
    isolate_widget(root)
    silence_design_shortcuts(root)
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
