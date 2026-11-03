"""After eject, the Data tab points at the window file."""

from __future__ import annotations

from typing import Any

from app.qt.QtCore import Qt
from app.qt.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.features.form_builder.engine.codegen.eject import ejected_method, method_line
from app.features.form_builder.qtside.data_panel.host import narrate, session_of, surface_of
from app.features.form_builder.qtside.data_panel.sections_ext import PanelSection


def _create(host: Any) -> QWidget:
    body = QWidget(host)
    body.setObjectName("formBuilder.data.ejected")
    layout = QVBoxLayout(body)
    layout.setContentsMargins(0, 0, 0, 0)
    sentence = QLabel(body)
    sentence.setObjectName("formBuilder.data.ejectedText")
    sentence.setWordWrap(True)
    sentence.setTextFormat(Qt.TextFormat.RichText)
    sentence.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
    sentence.setOpenExternalLinks(False)
    sentence.setProperty("fbLink", True)
    layout.addWidget(sentence)

    def refresh() -> None:
        session = session_of(host)
        method = ejected_method(session.document) if session is not None else None
        if not method:
            sentence.setText("")
            return
        filename = _filename(session)
        sentence.setText(
            'This form\'s data code is in <a href="%s">%s</a>.' % (method, filename)
        )

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
        current = bridge.open_text(path)
        if current is None:
            try:
                with open(path, encoding="utf-8") as handle:
                    current = handle.read()
            except OSError:
                current = ""
        bridge.open_at(path, method_line(current or "", method))

    sentence.linkActivated.connect(open_link)
    body.refresh = refresh  # type: ignore[attr-defined]
    refresh()
    return body


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
