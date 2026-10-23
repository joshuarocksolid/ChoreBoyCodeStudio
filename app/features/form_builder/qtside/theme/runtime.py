"""Runtime look isolation for the canvas (CONTRACTS.md section 5.4).

The canvas shows the form as the shipped app will look, never in the
builder's chrome theme.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

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
    # Shiboken deletes an unparented style when this name dies. setStyle keeps
    # only the C++ pointer, so the next style() call reads freed memory.
    owned.setParent(scene)
    scene.setStyle(owned)
    scene.setPalette(QPalette(runtime_palette()))
    scene.setFont(startup_font())


def isolate_widget(widget: QWidget) -> None:
    """Pin one realized root to the runtime look.

    Child widgets inherit this palette and font. A later shell theme change
    updates the application, not widgets that already have their own style.
    """
    style = runtime_style()
    widget.setStyle(style)
    widget.setPalette(QPalette(runtime_palette()))
    widget.setFont(startup_font())
    # A style that is only inherited is replaced by QStyleSheetStyle when the
    # application sheet is set. A style object set on the widget stays Fusion.
    # Widgets already drawing an authored style sheet must keep that style.
    for child in widget.findChildren(QWidget):
        current = child.style()
        if current is not None and _style_class_name(current) == "QStyleSheetStyle":
            continue
        child.setStyle(style)


def restore_authored_fonts(root: QWidget) -> None:
    """Put back fonts an application style sheet polish replaced.

    Qt saves the previous font on ``_q_styleSheetWidgetFont`` and then
    reports the application font. Passing that saved object to ``setFont``
    does not stick. A font built from its fields does.
    """
    widgets = [root]
    widgets.extend(root.findChildren(QWidget))
    for widget in widgets:
        saved = widget.property("_q_styleSheetWidgetFont")
        if not isinstance(saved, QFont):
            continue
        current = widget.font()
        if _same_font(current, saved):
            continue
        widget.setFont(_copy_font(saved))


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


def _style_class_name(style: QStyle) -> str:
    name = style.metaObject().className()
    if isinstance(name, bytes):
        return name.decode("ascii", "replace")
    return str(name)


def _same_font(left: QFont, right: QFont) -> bool:
    return (
        left.family() == right.family()
        and left.pointSize() == right.pointSize()
        and left.pixelSize() == right.pixelSize()
        and left.bold() == right.bold()
        and left.italic() == right.italic()
        and left.underline() == right.underline()
        and left.strikeOut() == right.strikeOut()
    )


def _copy_font(font: QFont) -> QFont:
    copied = QFont()
    copied.setFamily(font.family())
    if font.pointSize() > 0:
        copied.setPointSize(font.pointSize())
    elif font.pixelSize() > 0:
        copied.setPixelSize(font.pixelSize())
    copied.setBold(font.bold())
    copied.setItalic(font.italic())
    copied.setUnderline(font.underline())
    copied.setStrikeOut(font.strikeOut())
    copied.setKerning(font.kerning())
    return copied


def _ensure_app() -> QApplication:
    app = QApplication.instance()
    if isinstance(app, QApplication):
        return app
    return QApplication([])
