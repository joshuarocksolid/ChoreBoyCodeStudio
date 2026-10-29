"""The F1 help card (UX-MODE-007): a level-2 popover, 320 px wide, anchored to the selection.

The glyph and friendly name, the catalog description, the Qt class, the groups the
widget has ("You can set: Text, Echo mode, Maximum length …") and the links "All
form designer keys" and, when the user manual has a page for it, "Read more".
"""

from __future__ import annotations

import logging
from typing import Any, List, Mapping, Optional

from app.features.form_builder.engine.ui4.nodes import LayoutNode, WidgetNode
from app.features.form_builder.qtside.icons.glyphs import paint_glyph
from app.features.form_builder.qtside.inspector._live import live_classes
from app.features.form_builder.qtside.inspector.api import GroupId
from app.features.form_builder.qtside.inspector.editors import default_catalog
from app.features.form_builder.qtside.inspector.model import NodeBody, project
from app.features.form_builder.qtside.insert.catalog import load_catalog
from app.features.form_builder.qtside.layout_gestures import beside
from app.features.form_builder.qtside.outline.friendly import friendly_of
from app.features.form_builder.qtside.theme.chrome import popover_style
from app.qt.QtCore import QRect, QSize, Qt
from app.qt.QtGui import QPixmap
from app.qt.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

logger = logging.getLogger(__name__)

CARD_WIDTH = 320
KEYS_LINK = "All form designer keys"
MANUAL_LINK = "Read more"
SET_PREFIX = "You can set: "
_MAX_NAMES = 3


def manual_page(qt_class: str) -> Optional[str]:
    """The user-manual page for a widget class, or None. The manual has none yet, so "Read more" is absent."""
    del qt_class
    return None


def widget_summary(session: Any, node_id: Any, realizer: Any = None) -> Optional[Mapping[str, object]]:
    """What the card shows for one node, or None for the form itself."""
    document = session.document
    node = document.get(node_id)
    if not isinstance(node, (WidgetNode, LayoutNode)) or node_id == document.root.id:
        return None
    qt_class = node.class_name
    friendly = friendly_of(qt_class)
    description = ""
    glyph = "widget"
    for entry in load_catalog().entries:
        if entry.qt_class == qt_class:
            description = entry.description
            glyph = entry.glyph
            break
    if not description:
        description = "A %s." % friendly.lower()
    names: List[str] = []
    try:
        live = live_classes(realizer, document, (node_id,)) if realizer is not None else {}
        pages = project(session, default_catalog(), live=live, include_all=False)
    except Exception:
        logger.exception("the help card could not read the inspector rows")
        pages = None
    body = pages.body if pages is not None else None
    if isinstance(body, NodeBody):
        # What the widget is for: its first Content row, then its Input rows, then the rest of Content
        # and Appearance. Size, placement and accessibility rows are on every widget, so they say nothing.
        content = [getattr(row, "label", "") for row in body.group(GroupId.CONTENT).rows()]
        taken = [getattr(row, "label", "") for row in body.group(GroupId.INPUT).rows()]
        later = [getattr(row, "label", "") for row in body.group(GroupId.APPEARANCE).rows()]
        for label in content[:1] + taken + content[1:] + later:
            if label and label not in names:
                names.append(label)
    shown = names[:_MAX_NAMES]
    can_set = ""
    if shown:
        can_set = SET_PREFIX + ", ".join(shown) + (" …" if len(names) > len(shown) else "")
    return {
        "name": friendly,
        "glyph": glyph,
        "description": description,
        "qt_class": qt_class,
        "can_set": can_set,
        "manual": manual_page(qt_class),
    }


class WidgetHelpCard(QFrame):
    """A popover that closes on Esc and sends focus back to where it was."""

    def __init__(self, parent: QWidget, summary: Mapping[str, object], chrome: Any, glyph_color: str, on_keys: Any) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("formBuilder.widgetHelp")
        self.setAccessibleName("Help for %s" % summary["name"])
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setStyleSheet(popover_style(self.objectName(), chrome))
        self.setFixedWidth(CARD_WIDTH)
        column = QVBoxLayout(self)
        column.setContentsMargins(12, 10, 12, 12)
        column.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(8)
        icon = QLabel(self)
        icon.setFixedSize(QSize(16, 16))
        pixmap: QPixmap = paint_glyph(str(summary["glyph"]), glyph_color, 16, float(self.devicePixelRatioF()))
        icon.setPixmap(pixmap)
        title = QLabel(str(summary["name"]), self)
        title.setObjectName("formBuilder.widgetHelpName")
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        head.addWidget(icon)
        head.addWidget(title, 1)
        column.addLayout(head)
        for text, name in (
            (summary["description"], "description"),
            ("Qt class: %s" % summary["qt_class"], "class"),
            (summary["can_set"], "canSet"),
        ):
            if not text:
                continue
            label = QLabel(str(text), self)
            label.setObjectName("formBuilder.widgetHelp.%s" % name)
            label.setWordWrap(True)
            if name == "class":
                label.setProperty("note", True)
            column.addWidget(label)
        links = QHBoxLayout()
        links.setSpacing(6)
        self.keys_link = QPushButton(KEYS_LINK, self)
        self.keys_link.setObjectName("formBuilder.widgetHelp.keys")
        self.keys_link.setAccessibleName(KEYS_LINK)
        self.keys_link.clicked.connect(lambda _checked=False: (self.close(), on_keys()))
        links.addWidget(self.keys_link)
        self.manual_link: Optional[QPushButton] = None
        if summary.get("manual"):
            manual = QPushButton(MANUAL_LINK, self)
            manual.setObjectName("formBuilder.widgetHelp.manual")
            links.addWidget(manual)
            self.manual_link = manual
        links.addStretch(1)
        column.addLayout(links)

    def open_beside(self, subject: QRect, bounds: QRect) -> None:
        self.adjustSize()
        self.move(beside(subject, self.sizeHint(), bounds))
        self.show()
        self.keys_link.setFocus()

    def text(self) -> str:
        return " | ".join(label.text() for label in self.findChildren(QLabel) if label.text())
