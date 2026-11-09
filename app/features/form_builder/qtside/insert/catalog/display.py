"""UX-CAT-002: Display. Line entries share the class ``Line``."""

from __future__ import annotations

from typing import Tuple

from app.features.form_builder.qtside.insert.catalog._build import leaf, leaf_entry, number, orientation, text
from app.features.form_builder.qtside.insert.catalog._model import LABEL, Entry, Registry

CATEGORY = "Display"
_LINE_SYNONYMS = ("line", "separator", "divider", "rule")


def entries() -> Tuple[Entry, ...]:
    return (
        Entry(
            "QLabel", "Label", "QLabel", CATEGORY, "label", "Text or a picture.",
            ("caption", "static text", "title", "image", "picture", "photo", "logo", "icon"),
            "label", LABEL, leaf("QLabel", "label", (text("text", "Label"),)),
        ),
        leaf_entry("QTextBrowser", "Text browser", "QTextBrowser", CATEGORY, "textBrowser",
                   "Formatted text with links, read only.", ("html", "browser", "link", "help text"),
                   "text_browser"),
        leaf_entry("line-h", "Horizontal line", "Line", CATEGORY, "line",
                   "A thin line that separates groups.", _LINE_SYNONYMS, "line_h",
                   (orientation(True),)),
        leaf_entry("line-v", "Vertical line", "Line", CATEGORY, "line",
                   "A thin upright line that separates groups.", _LINE_SYNONYMS, "line_v",
                   (orientation(False),)),
        leaf_entry("QProgressBar", "Progress bar", "QProgressBar", CATEGORY, "progressBar",
                   "Shows how far a task has got.", ("progress", "loading", "percent"), "progress_bar",
                   (number("value", 24),)),
        leaf_entry("QLCDNumber", "LCD number", "QLCDNumber", CATEGORY, "lcdNumber",
                   "Digits in a calculator-style display.", ("lcd", "digits", "display"), "lcd"),
        leaf_entry("QGraphicsView", "Graphics view", "QGraphicsView", CATEGORY, "graphicsView",
                   "A drawing surface your code fills.", ("graphics", "drawing", "scene"), "graphics_view"),
        leaf_entry("QOpenGLWidget", "OpenGL widget", "QOpenGLWidget", CATEGORY, "openGLWidget",
                   "3D drawing from your code. The canvas shows a placeholder.", ("opengl", "3d"), "opengl"),
        leaf_entry("QQuickWidget", "Qt Quick view", "QQuickWidget", CATEGORY, "quickWidget",
                   "A Qt Quick scene from your code. The canvas shows a placeholder.", ("quick", "qml"), "quick"),
    )


def register(registry: Registry) -> None:
    registry.family("Line", "Line")
    for entry in entries():
        registry.add(entry)
