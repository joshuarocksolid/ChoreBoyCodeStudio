"""F1 help card (UX-MODE-007) and the Form designer keys page (UX-MODE-005).

The card is a level-2 popover, 320 px wide, anchored to the selection: the glyph
and friendly name, the catalog description, the Qt class, the groups the widget
has ("You can set: Text, Echo mode, Maximum length …") and the links "All form
designer keys" and, when the user manual has a page for it, "Read more". With
only the form selected, F1 opens Form designer keys instead.
"""

from __future__ import annotations

import logging
from typing import Any, List, Mapping, Optional

from app.features.form_builder.engine.shell_commands import FORM_COMMANDS
from app.features.form_builder.engine.ui4.nodes import LayoutNode, WidgetNode
from app.features.form_builder.integration import keys_ext
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.qtside.icons.glyphs import paint_glyph
from app.features.form_builder.qtside.inspector.api import GroupId
from app.features.form_builder.qtside.inspector.editors import default_catalog
from app.features.form_builder.qtside.inspector.model import NodeBody, project
from app.features.form_builder.qtside.inspector.words import class_words
from app.features.form_builder.qtside.insert.catalog import load_catalog
from app.features.form_builder.qtside.keys_page.model import TITLE, build_groups
from app.features.form_builder.qtside.keys_page.page import KeysPage
from app.features.form_builder.qtside.layout_gestures import beside
from app.features.form_builder.qtside.theme.chrome import popover_style
from app.qt.QtCore import QRect, QSize, Qt
from app.qt.QtGui import QPixmap
from app.qt.QtWidgets import QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

logger = logging.getLogger(__name__)

CARD_WIDTH = 320
KEYS_LINK = "All form designer keys"
MANUAL_LINK = "Read more"
SET_PREFIX = "You can set: "
_GROUP_SKIP = frozenset({GroupId.ALL})
_MAX_NAMES = 3


def manual_page(qt_class: str) -> Optional[str]:
    """The user-manual page for a widget class, or None. The manual has none yet, so "Read more" is absent."""
    del qt_class
    return None


def widget_summary(surface: Any, node_id: Any) -> Optional[Mapping[str, object]]:
    """What the card shows for one node, or None for the form itself. Qt-free except for the inspector's catalog."""
    session = surface.session
    document = session.document
    node = document.get(node_id)
    if not isinstance(node, (WidgetNode, LayoutNode)) or node_id == document.root.id:
        return None
    qt_class = node.class_name
    words = class_words(qt_class)
    description = ""
    for entry in load_catalog().entries:
        if entry.qt_class == qt_class:
            description = entry.description
            break
    if not description:
        description = "A %s." % words.noun
    names: List[str] = []
    try:
        pages = project(session, default_catalog(), include_all=False)
    except Exception:
        logger.exception("the help card could not read the inspector rows")
        pages = None
    body = pages.body if pages is not None else None
    if isinstance(body, NodeBody):
        for view in body.groups:
            if view.group in _GROUP_SKIP:
                continue
            for row in view.rows():
                label = getattr(row, "label", "")
                if label and label not in names:
                    names.append(label)
    shown = names[:_MAX_NAMES]
    can_set = ""
    if shown:
        can_set = SET_PREFIX + ", ".join(shown) + (" …" if len(names) > len(shown) else "")
    return {
        "name": words.friendly,
        "glyph": words.glyph,
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
            self.manual_link = QPushButton(MANUAL_LINK, self)
            self.manual_link.setObjectName("formBuilder.widgetHelp.manual")
            links.addWidget(self.manual_link)
        links.addStretch(1)
        column.addLayout(links)

    def open_beside(self, subject: QRect, bounds: QRect) -> None:
        self.adjustSize()
        self.move(beside(subject, self.sizeHint(), bounds))
        self.show()
        self.keys_link.setFocus()

    def text(self) -> str:
        return " | ".join(label.text() for label in self.findChildren(QLabel) if label.text())


def open_widget_help(surface: Any) -> Optional[QWidget]:
    """F1. The card for the selected widget, else Form designer keys."""
    if surface.session.document is None:
        return None
    state = surface.session.selection.state
    current = state.current
    summary = widget_summary(surface, current) if current is not None else None
    if summary is None:
        return show_keys_page(surface)
    tokens = surface._tokens  # pyright: ignore[reportPrivateUsage]
    chrome = chrome_for(tokens)
    card = WidgetHelpCard(surface, summary, chrome, tokens.icon_primary or tokens.text_primary, lambda: show_keys_page(surface))
    ids = state.ids or (surface.session.document.root.id,)
    card.open_beside(*surface.place_for(ids))
    return card


def _effective(window: Any) -> Mapping[str, str]:
    found = getattr(window, "_effective_shortcuts", None)
    return found if isinstance(found, Mapping) else {}


def keys_groups(window: Any = None) -> Any:
    """The page's groups for the shortcuts in force now."""
    return build_groups(FORM_COMMANDS + keys_ext.extra_commands(), _effective(window))


def show_keys_page(surface: Any = None) -> Optional[QWidget]:
    """Help > Form designer keys. One window; rebuilt each time it is shown, so Settings rebinds appear."""
    window = surface.window() if surface is not None else QApplication.activeWindow()
    holder = window if window is not None else QApplication.instance()
    dialog = getattr(holder, "_form_keys_dialog", None)
    if dialog is not None:
        try:
            dialog.close()
            dialog.deleteLater()
        except RuntimeError:
            pass
    dialog = QDialog(window)
    dialog.setObjectName("formBuilder.keysDialog")
    dialog.setWindowTitle(TITLE)
    dialog.setWindowFlag(Qt.WindowType.Window, True)
    dialog.setModal(False)
    dialog.resize(860, 560)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(0, 0, 0, 0)
    page = KeysPage(keys_groups(window), dialog, on_close=dialog.close)
    layout.addWidget(page)
    tokens = getattr(surface, "_tokens", None)
    if tokens is not None:
        chrome = chrome_for(tokens)
        dialog.setStyleSheet(
            "QDialog#formBuilder\\.keysDialog { background: %s; }"
            "QWidget#formBuilder\\.keysPage { background: %s; color: %s; }"
            "QTreeWidget#formBuilder\\.keysTable, QLineEdit#formBuilder\\.keysFilter {"
            " background: %s; color: %s; border: 1px solid %s; }"
            % (chrome.panel, chrome.panel, chrome.text, chrome.input, chrome.text, chrome.border)
        )
    setattr(holder, "_form_keys_dialog", dialog)
    dialog.show()
    page.focus_filter()
    return dialog
