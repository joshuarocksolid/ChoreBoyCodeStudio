"""One tab look for the builder's own tab bars.

Flat, 28 px, a 1 px line under the bar. The selected tab is weight 600
with a 2 px accent underline. No fill and no scroll arrows.
"""

from __future__ import annotations

from app.features.form_builder.qtside.theme.chrome import FormChrome
from app.features.form_builder.qtside.theme.metrics import TAB, TAB_PAD, TYPE_BODY
from app.qt.QtCore import Qt
from app.qt.QtWidgets import QTabWidget

_BARS = (
    "QTabWidget#formBuilder\\.inspectorTabs",
    "QTabWidget#formBuilder\\.leftTabs",
)


def configure_tab_widget(tabs: QTabWidget) -> None:
    """Stop the bar from growing a scroll arrow or stretching its tabs."""
    tabs.setDocumentMode(True)
    bar = tabs.tabBar()
    bar.setUsesScrollButtons(False)
    bar.setExpanding(False)
    elide = getattr(Qt, "TextElideMode", Qt)
    bar.setElideMode(getattr(elide, "ElideNone"))
    bar.setDrawBase(False)


def tab_bar_qss(chrome: FormChrome) -> str:
    """Underline tabs for the inspector and the left pane."""
    parts = []
    for name in _BARS:
        parts.append(
            "%(name)s::pane { background: %(panel)s; border: none; top: 0px; }"
            "%(name)s QTabBar { background: transparent; border: none;"
            " border-bottom: 1px solid %(border)s; }"
            "%(name)s QTabBar::tab {"
            " background: transparent; color: %(muted)s; border: none;"
            " border-bottom: 2px solid transparent; padding: 0px %(pad)dpx; margin: 0px;"
            " min-height: %(height)dpx; max-height: %(height)dpx;"
            " font-size: %(body)dpx; font-weight: 400; }"
            "%(name)s QTabBar::tab:hover { color: %(text)s; background: transparent; }"
            "%(name)s QTabBar::tab:selected {"
            " color: %(text)s; background: transparent; font-weight: 600;"
            " border: none; border-bottom: 2px solid %(accent)s; }"
            "%(name)s QTabBar::tab:focus { outline: none; }"
            % {
                "name": name,
                "panel": chrome.panel,
                "border": chrome.border,
                "muted": chrome.muted,
                "text": chrome.text,
                "accent": chrome.accent,
                "pad": TAB_PAD,
                "height": TAB,
                "body": TYPE_BODY,
            }
        )
    return "".join(parts)
