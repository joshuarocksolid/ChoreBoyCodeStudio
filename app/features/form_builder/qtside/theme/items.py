"""Host selection colours for builder item views.

Hover is ``row_hover`` (the shell tree hover). The chosen row is ``selected``
(the shell tree selection) with primary text. Focus is the view border.
High contrast also draws a 2 px accent bar, so the state is not fill alone.
"""

from __future__ import annotations

from app.features.form_builder.qtside.theme.chrome import FormChrome
from app.features.form_builder.qtside.theme.metrics import ROW
from app.qt.QtWidgets import QFrame, QWidget


def item_view_qss(selector: str, chrome: FormChrome) -> str:
    """QSS for one ``QListView``, ``QTreeView`` or ``QTableView`` selector."""
    focus = chrome.focus_width if chrome.focus_width > 0 else 1
    left = ""
    if chrome.is_high_contrast:
        left = " border-left: %dpx solid %s;" % (max(focus, 2), chrome.accent)
    return (
        "%(sel)s { background: %(panel)s; color: %(text)s; border: none; outline: none; }"
        "%(sel)s:focus { border: %(focus)dpx solid %(accent)s; outline: none; }"
        "%(sel)s::item { color: %(text)s; background: transparent; border: none;"
        " min-height: %(row)dpx; padding: 0px 4px; }"
        "%(sel)s::item:hover { background: %(hover)s; color: %(text)s; }"
        "%(sel)s::item:selected, %(sel)s::item:selected:active, %(sel)s::item:selected:!active {"
        " background: %(chosen)s; color: %(text)s;%(left)s }"
        "%(sel)s::item:selected:hover { background: %(chosen)s; color: %(text)s; }"
        % {
            "sel": selector,
            "panel": chrome.panel,
            "text": chrome.text,
            "hover": chrome.row_hover,
            "chosen": chrome.selected or chrome.row_hover,
            "accent": chrome.accent,
            "focus": focus,
            "row": ROW,
            "left": left,
        }
    )


def polish_item_view(view: QWidget, chrome: FormChrome) -> None:
    """Frame off, and the host item colours on this view."""
    frame = getattr(view, "setFrameShape", None)
    if callable(frame):
        shapes = getattr(QFrame, "Shape", QFrame)
        frame(getattr(shapes, "NoFrame"))
    name = view.objectName()
    kind = view.metaObject().className()
    selector = kind if not name else "%s#%s" % (kind, name.replace(".", "\\."))
    view.setStyleSheet(item_view_qss(selector, chrome))
