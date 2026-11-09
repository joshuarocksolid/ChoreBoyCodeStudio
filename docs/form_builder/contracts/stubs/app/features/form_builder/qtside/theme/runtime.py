"""Runtime look isolation for the canvas (CONTRACTS.md section 5.4).

The canvas shows the form as the shipped app will look, never in the
builder's chrome theme.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from app.qt.QtGui import QPalette
    from app.qt.QtWidgets import QGraphicsScene, QStyle

RUNTIME_STYLE_KEY = "Fusion"


def runtime_style() -> "QStyle":
    """One process-wide ``QStyleFactory.create("Fusion")`` instance, owned by
    this module (never the application style object)."""
    ...


def runtime_palette() -> "QPalette":
    """``runtime_style().standardPalette()``. Never derived from the shell theme."""
    ...


def isolate_scene(scene: "QGraphicsScene") -> None:
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
    ...
