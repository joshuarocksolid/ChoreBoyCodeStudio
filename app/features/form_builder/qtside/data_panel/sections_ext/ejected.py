"""After eject, the Data tab points at the window file."""

from __future__ import annotations

import html
from typing import Any

from app.qt.QtCore import Qt
from app.qt.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from app.features.form_builder.engine.codegen.eject import ejected_method, method_line
from app.features.form_builder.qtside.data_panel.host import narrate, session_of, surface_of
from app.features.form_builder.qtside.data_panel.sections_ext import PanelSection


def _create(host: Any) -> QWidget:
    body = QWidget(host)
    body.setObjectName("formBuilder.data.ejected")
    layout = QVBoxLayout(body)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setAlignment(Qt.AlignmentFlag.AlignTop)
    sentence = QLabel(body)
    sentence.setObjectName("formBuilder.data.ejectedText")
    sentence.setWordWrap(True)
    sentence.setTextFormat(Qt.TextFormat.RichText)
    sentence.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
    sentence.setOpenExternalLinks(False)
    sentence.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    sentence.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
    layout.addWidget(sentence, 0, Qt.AlignmentFlag.AlignTop)
    layout.addStretch(1)

    def refresh() -> None:
        session = session_of(host)
        method = ejected_method(session.document) if session is not None else None
        if not method:
            sentence.setText("")
            return
        filename = _filename(session)
        color = _link_color(host)
        link = html.escape(filename)
        if color:
            link = '<a href="%s" style="color:%s;">%s</a>' % (
                html.escape(method),
                html.escape(color),
                link,
            )
        else:
            link = '<a href="%s">%s</a>' % (html.escape(method), link)
        sentence.setText("This form's data code is in %s." % link)

    def open_link(method: str) -> None:
        session = session_of(host)
        surface = surface_of(host)
        if session is None or surface is None:
            narrate(host, "Open the window file to see %s." % method)
            return
        path = str(getattr(session.scope, "window_path", "") or "")
        bridge = getattr(surface, "code_bridge", None)
        if not path or bridge is None:
            narrate(host, "Open the window file to see %s." % method)
            return
        current = _text(bridge, path)
        if not current:
            if not bridge.open_at(path, 1):
                narrate(host, "Open the window file to see %s." % method)
                return
            current = _text(bridge, path)
        if not current:
            narrate(host, "Open the window file to see %s." % method)
            return
        bridge.open_at(path, method_line(current, method))

    sentence.linkActivated.connect(open_link)
    body.refresh = refresh  # type: ignore[attr-defined]
    refresh()
    return body


def _text(bridge: Any, path: str) -> str:
    reader = getattr(bridge, "text_of", None)
    if callable(reader):
        found = reader(path)
        return "" if found is None else str(found)
    return ""


def _link_color(host: Any) -> str:
    tokens = getattr(host, "_tokens", None)
    accent = getattr(tokens, "accent", None) if tokens is not None else None
    if isinstance(accent, str) and accent:
        return accent
    return ""


def _filename(session: Any) -> str:
    path = str(getattr(session.scope, "window_path", "") or "")
    if path:
        return path.rsplit("/", 1)[-1]
    ui = str(getattr(session, "path", "") or "form.ui")
    base = ui.rsplit("/", 1)[-1]
    stem = base[:-3] if base.endswith(".ui") else base
    return stem + "_window.py"


def _applies(doc: Any) -> bool:
    return ejected_method(doc) is not None


def register(registry: Any) -> None:
    registry.add(PanelSection("ejected", 15, _create, _applies))
