"""Read as text. Numbered sentences, copy, and print through the image path."""

from __future__ import annotations

import html
from typing import List

from app.qt.QtCore import Qt
from app.qt.QtGui import QFont, QImage
from app.qt.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import enum_value, exec_qt

from app.core.constants import UI_EDITOR_FONT_FAMILY_DEFAULT
from app.features.form_builder.engine.events import PRIORITY_VIEWS
from app.features.form_builder.engine.logic.read_as_text import behavior_text, page_text

_PLAIN = getattr(getattr(Qt, "TextFormat", Qt), "PlainText")
_RICH = getattr(getattr(Qt, "TextFormat", Qt), "RichText")


class _Line(QLabel):
    def __init__(self, text: str, parent: QWidget, *, rich: bool) -> None:
        super().__init__(parent)
        self.setWordWrap(True)
        self.setMinimumWidth(0)
        self.setTextFormat(_RICH if rich else _PLAIN)
        self.setText(text)
        policy = QSizePolicy(_size_policy("Ignored"), _size_policy("Preferred"))  # type: ignore[arg-type]
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True


class BehaviorTextPage(QWidget):
    def __init__(self, surface: object) -> None:
        super().__init__()
        self._surface = surface
        self._sentences: tuple = ()
        self._tokens: object = None
        self.setObjectName("formBuilder.readAsText")
        self.setMinimumWidth(0)
        column = QVBoxLayout(self)
        column.setContentsMargins(8, 8, 8, 8)
        column.setSpacing(6)
        tools = QHBoxLayout()
        tools.setSpacing(6)
        tools.addWidget(self._button("Design", "formBuilder.readAsText.design", self._design))
        tools.addStretch(1)
        tools.addWidget(self._button("Copy", "formBuilder.readAsText.copy", self._copy))
        tools.addWidget(self._button("Print", "formBuilder.readAsText.print", self._print))
        column.addLayout(tools)
        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("formBuilder.readAsText.scroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(_no_frame())
        self._body = QWidget()
        self._body.setObjectName("formBuilder.readAsText.body")
        self._body.setMinimumWidth(0)
        self._lines = QVBoxLayout(self._body)
        self._lines.setContentsMargins(0, 0, 0, 0)
        self._lines.setSpacing(6)
        self._scroll.setWidget(self._body)
        column.addWidget(self._scroll, 1)

    def refresh(self) -> None:
        document = getattr(getattr(self._surface, "session", None), "document", None)
        sentences = behavior_text(document) if document is not None else ()
        self._sentences = sentences
        while self._lines.count():
            item = self._lines.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        family = _code_family(self._surface)
        last = ""
        for sentence in sentences:
            if sentence.section != last:
                title = QLabel(sentence.section, self._body)
                title.setObjectName("formBuilder.readText.title.%s" % sentence.section)
                title.setProperty("cbcsReadTitle", True)
                title.setMinimumWidth(0)
                title.setTextFormat(_PLAIN)
                self._lines.addWidget(title)
                last = sentence.section
            shown = "%d. %s" % (sentence.number, sentence.text)
            rich = "`" in shown
            line = _Line(_html(shown, family) if rich else shown, self._body, rich=rich)
            line.setObjectName("formBuilder.readText.paragraph.%d" % sentence.number)
            if not rich:
                font = QFont(self.font())
                line.setFont(font)
            self._lines.addWidget(line)
        self._lines.addStretch(1)
        if self._tokens is not None:
            self.apply_theme(self._tokens)

    def apply_theme(self, tokens: object) -> None:
        self._tokens = tokens
        width = int(getattr(tokens, "focus_border_width", 1) or 1)
        panel = str(getattr(tokens, "panel_bg", "") or "")
        text = str(getattr(tokens, "text_primary", "") or "")
        muted = str(getattr(tokens, "text_muted", "") or text)
        accent = str(getattr(tokens, "accent", "") or text)
        border = str(getattr(tokens, "border", "") or text)
        self.setStyleSheet(
            "QWidget#formBuilder\\.readAsText { background: %s; color: %s; }"
            "QWidget#formBuilder\\.readAsText\\.body { background: %s; color: %s; }"
            "QLabel { color: %s; background: transparent; }"
            "QLabel[cbcsReadTitle=\"true\"] { color: %s; background: transparent; border: none;"
            " font-size: 10px; font-weight: 600; letter-spacing: 0.5px; }"
            "QToolButton { color: %s; background: transparent; border: 1px solid %s; padding: 2px 8px; }"
            "QToolButton:focus { border: %dpx solid %s; }"
            "QScrollArea { background: %s; border: none; }"
            % (panel, text, panel, text, text, muted, text, border, width, accent, panel)
        )

    def _button(self, label: str, name: str, handler: object) -> QToolButton:
        button = QToolButton(self)
        button.setText(label)
        button.setObjectName(name)
        button.setAutoRaise(True)
        button.clicked.connect(handler)  # type: ignore[arg-type]
        return button

    def _design(self) -> None:
        stack = getattr(self._surface, "_stack", None)
        workbench = getattr(self._surface, "_workbench", None)
        if stack is not None and workbench is not None:
            stack.setCurrentWidget(workbench)

    def _copy(self) -> None:
        from app.qt.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(page_text(self._sentences))

    def _print(self) -> None:
        from app.qt.QtGui import QColor, QPalette
        from app.qt.QtPrintSupport import QPrintDialog, QPrinter
        from app.qt.QtWidgets import QDialog

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        dialog = QPrintDialog(printer, self)
        accepted = getattr(getattr(QDialog, "DialogCode", QDialog), "Accepted")
        if exec_qt(dialog) != enum_value(accepted):
            return
        target = self._body
        image = QImage(
            max(1, target.width()),
            max(1, target.height()),
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        role = getattr(getattr(QPalette, "ColorRole", QPalette), "Window")
        fill = self.palette().color(role)
        panel = str(getattr(self._tokens, "panel_bg", "") or "") if self._tokens is not None else ""
        if panel:
            fill = QColor(panel)
        image.fill(fill)
        target.render(image)
        paint = getattr(self._surface, "paint_behavior_page", None)
        if callable(paint):
            paint(image, printer)


def show_behavior_text(surface: object) -> None:
    """The Logic link and the Form menu both open this page."""
    page = getattr(surface, "_behavior_text_page", None)
    if not isinstance(page, BehaviorTextPage):
        page = BehaviorTextPage(surface)
        surface._behavior_text_page = page  # type: ignore[attr-defined]
        stack = getattr(surface, "_stack", None)
        if stack is not None:
            stack.addWidget(page)
        log = getattr(getattr(surface, "session", None), "log", None)
        subscribe = getattr(log, "subscribe", None)
        if callable(subscribe):
            sub = subscribe(lambda _change: _refresh(surface), priority=PRIORITY_VIEWS)
            surface._behavior_text_sub = sub  # type: ignore[attr-defined]
            page.destroyed.connect(lambda *_args: sub.close())
    _refresh(surface)
    tokens = getattr(surface, "_tokens", None)
    if tokens is not None:
        page.apply_theme(tokens)
    stack = getattr(surface, "_stack", None)
    if stack is not None:
        stack.setCurrentWidget(page)
    page.setFocus()


def _refresh(surface: object) -> None:
    page = getattr(surface, "_behavior_text_page", None)
    if isinstance(page, BehaviorTextPage):
        page.refresh()


def _code_family(surface: object) -> str:
    window = surface.window() if hasattr(surface, "window") else None
    family = getattr(window, "_editor_font_family", "") if window is not None else ""
    if isinstance(family, str) and family.strip():
        return family.strip()
    return UI_EDITOR_FONT_FAMILY_DEFAULT


def _size_policy(name: str) -> object:
    names = getattr(QSizePolicy, "Policy", QSizePolicy)
    return getattr(names, name)


def _no_frame() -> object:
    from app.qt.QtWidgets import QFrame

    names = getattr(QFrame, "Shape", QFrame)
    return getattr(names, "NoFrame")


def _html(text: str, family: str) -> str:
    parts: List[str] = []
    rest = text
    while True:
        start = rest.find("`")
        if start < 0:
            parts.append(html.escape(rest))
            break
        end = rest.find("`", start + 1)
        if end < 0:
            parts.append(html.escape(rest))
            break
        parts.append(html.escape(rest[:start]))
        parts.append(
            "<span style=\"font-family: '%s';\">%s</span>"
            % (html.escape(family, quote=True), html.escape(rest[start + 1 : end]))
        )
        rest = rest[end + 1 :]
    return "".join(parts)


__all__ = ["BehaviorTextPage", "show_behavior_text"]
