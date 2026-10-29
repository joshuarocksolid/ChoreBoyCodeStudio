"""F1 and Help > Form designer keys: the glue between a form tab and ``qtside/keys_page`` (UX-MODE-005, UX-MODE-007)."""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from app.features.form_builder.engine.shell_commands import FORM_COMMANDS
from app.features.form_builder.integration import keys_ext
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.qtside.keys_page.help_card import WidgetHelpCard, widget_summary
from app.features.form_builder.qtside.keys_page.model import TITLE, build_groups
from app.features.form_builder.qtside.keys_page.page import KeysPage
from app.qt.QtCore import Qt
from app.qt.QtWidgets import QApplication, QDialog, QVBoxLayout, QWidget

logger = logging.getLogger(__name__)


def open_widget_help(surface: Any) -> Optional[QWidget]:
    """F1. The card for the selected widget, else Form designer keys."""
    if surface.session.document is None:
        return None
    state = surface.session.selection.state
    current = state.current
    summary = widget_summary(surface.session, current, surface.realizer) if current is not None else None
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
            "QTreeWidget#formBuilder\\.keysTable::item { background: transparent; color: %s; }"
            "QTreeWidget#formBuilder\\.keysTable QHeaderView::section { background: %s; color: %s; border: none; padding: 3px 6px; }"
            % (chrome.panel, chrome.panel, chrome.text, chrome.input, chrome.text, chrome.border, chrome.text, chrome.panel, chrome.text)
        )
    setattr(holder, "_form_keys_dialog", dialog)
    dialog.show()
    page.focus_filter()
    return dialog
