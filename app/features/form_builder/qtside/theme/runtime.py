"""Runtime look isolation for the canvas (CONTRACTS.md section 5.4).

The canvas shows the form as the shipped app will look, never in the
builder's chrome theme.
"""

from __future__ import annotations

from typing import Optional

from app.qt.QtGui import QFont, QPalette
from app.qt.QtWidgets import QApplication, QGraphicsScene, QStyle, QStyleFactory

RUNTIME_STYLE_KEY = "Fusion"

_style: Optional[QStyle] = None
_startup_font: Optional[QFont] = None


def runtime_style() -> QStyle:
    """One process-wide ``QStyleFactory.create("Fusion")`` instance, owned by
    this module (never the application style object)."""
    global _style
    if _style is None:
        created = QStyleFactory.create(RUNTIME_STYLE_KEY)
        if created is None:
            raise RuntimeError("Fusion style is not available")
        _style = created
        _remember_startup_font()
    return _style


def runtime_palette() -> QPalette:
    """``runtime_style().standardPalette()``. Never derived from the shell theme."""
    return runtime_style().standardPalette()


def isolate_scene(scene: QGraphicsScene) -> None:
    """Apply the runtime look to the scene that hosts the realized form:
    ``scene.setStyle(runtime_style())``, ``scene.setPalette(runtime_palette())``,
    ``scene.setFont(<application default font at startup>)``.

    Rules (tested):
    1. The realized form root is embedded in a ``QGraphicsProxyWidget``; it is
       never a QWidget descendant of the main window, so the main window's
       style sheet does not cascade into it.
    2. No realized widget gets a chrome palette, chrome font or chrome style
       sheet. The form's own ``styleSheet`` property is applied as authored.
    3. The application style sheet may contain only ``QToolTip`` rules while the
       form builder is enabled (a test parses ``QApplication.styleSheet()``).
    4. A shell theme switch never touches the scene.
    """
    scene.setStyle(runtime_style())
    scene.setPalette(runtime_palette())
    scene.setFont(_font_for_scene())


def _remember_startup_font() -> None:
    global _startup_font
    if _startup_font is not None:
        return
    app = QApplication.instance()
    if app is None:
        return
    _startup_font = QFont(app.font())


def _font_for_scene() -> QFont:
    _remember_startup_font()
    if _startup_font is not None:
        return _startup_font
    return QFont()
