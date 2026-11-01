"""Read as text. A centred page of numbered sentences, copy, and print."""

from __future__ import annotations

import html
import os
from typing import List

from app.qt.QtCore import Qt
from app.qt.QtGui import QFont, QFontMetrics, QImage
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
from app.features.form_builder.engine.ui4.values import CStringValue, StringValue

_PLAIN = getattr(getattr(Qt, "TextFormat", Qt), "PlainText")
_RICH = getattr(getattr(Qt, "TextFormat", Qt), "RichText")
_COLUMN_MAX = 640
_PAGE_MARGIN = 24
_TITLE = "%s \u2014 what this form does"


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
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        tools = QHBoxLayout()
        tools.setContentsMargins(_PAGE_MARGIN, _PAGE_MARGIN, _PAGE_MARGIN, 0)
        tools.setSpacing(6)
        self._open = self._button("Open form", "formBuilder.readAsText.open", self._open_form)
        self._copy_button = self._button("Copy", "formBuilder.readAsText.copy", self._copy)
        self._print_button = self._button("Print", "formBuilder.readAsText.print", self._print)
        tools.addWidget(self._open)
        tools.addStretch(1)
        tools.addWidget(self._copy_button)
        tools.addWidget(self._print_button)
        root.addLayout(tools)
        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("formBuilder.readAsText.scroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(_no_frame())
        self._holder = QWidget()
        self._holder.setObjectName("formBuilder.readAsText.holder")
        self._holder.setMinimumWidth(0)
        hold = QHBoxLayout(self._holder)
        hold.setContentsMargins(_PAGE_MARGIN, _PAGE_MARGIN, _PAGE_MARGIN, _PAGE_MARGIN)
        hold.setSpacing(0)
        hold.addStretch(1)
        self._column = QWidget(self._holder)
        self._column.setObjectName("formBuilder.readText.column")
        self._column.setMinimumWidth(0)
        self._column.setMaximumWidth(_COLUMN_MAX)
        column = QVBoxLayout(self._column)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self._title = QLabel(self._column)
        self._title.setObjectName("formBuilder.readText.heading")
        self._title.setWordWrap(True)
        self._title.setTextFormat(_PLAIN)
        self._title.setFont(_heading_font())
        self._file = QLabel(self._column)
        self._file.setObjectName("formBuilder.readText.file")
        self._file.setProperty("fb.faint", True)
        self._file.setTextFormat(_PLAIN)
        self._file.setWordWrap(True)
        column.addWidget(self._title)
        column.addSpacing(4)
        column.addWidget(self._file)
        self._lines = QVBoxLayout()
        self._lines.setContentsMargins(0, 0, 0, 0)
        self._lines.setSpacing(0)
        column.addLayout(self._lines)
        hold.addWidget(self._column, 0, _align("AlignTop"))
        hold.addStretch(1)
        self._scroll.setWidget(self._holder)
        root.addWidget(self._scroll, 1)

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._fit_column()

    def refresh(self) -> None:
        document = getattr(getattr(self._surface, "session", None), "document", None)
        sentences = behavior_text(document) if document is not None else ()
        self._sentences = sentences
        title = _window_title(document)
        self._title.setText(_TITLE % title)
        self._file.setText(_file_name(self._surface))
        while self._lines.count():
            item = self._lines.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        family = _code_family(self._surface)
        body = QFont(self.font())
        metrics = QFontMetrics(body)
        gutter = int(metrics.horizontalAdvance("%d." % max(1, len(sentences)))) + 4  # type: ignore[attr-defined]
        last = ""
        for sentence in sentences:
            if sentence.section != last:
                self._lines.addSpacing(16)
                header = QLabel(sentence.section, self._column)
                header.setObjectName("formBuilder.readText.title.%s" % sentence.section)
                header.setProperty("cbcsReadTitle", True)
                header.setMinimumWidth(0)
                header.setTextFormat(_PLAIN)
                self._lines.addWidget(header)
                last = sentence.section
            self._lines.addSpacing(6)
            shown = sentence.text
            rich = "`" in shown
            row = QWidget(self._column)
            row.setObjectName("formBuilder.readText.row.%d" % sentence.number)
            row.setMinimumWidth(0)
            pair = QHBoxLayout(row)
            pair.setContentsMargins(0, 0, 0, 0)
            pair.setSpacing(8)
            number = QLabel("%d." % sentence.number, row)
            number.setObjectName("formBuilder.readText.number.%d" % sentence.number)
            number.setFont(body)
            number.setFixedWidth(gutter)
            number.setAlignment(_align("AlignRight") | _align("AlignTop"))  # type: ignore[operator]
            number.setTextFormat(_PLAIN)
            line = _Line(_html(shown, family) if rich else shown, row, rich=rich)
            line.setObjectName("formBuilder.readText.paragraph.%d" % sentence.number)
            if not rich:
                line.setFont(body)
            pair.addWidget(number, 0, _align("AlignTop"))
            pair.addWidget(line, 1)
            self._lines.addWidget(row)
        self._lines.addStretch(1)
        self._fit_column()
        if self._tokens is not None:
            self.apply_theme(self._tokens)

    def apply_theme(self, tokens: object) -> None:
        self._tokens = tokens
        width = int(getattr(tokens, "focus_border_width", 1) or 1)
        panel = str(getattr(tokens, "panel_bg", "") or "")
        text = str(getattr(tokens, "text_primary", "") or "")
        muted = str(getattr(tokens, "text_muted", "") or text)
        faint = str(getattr(tokens, "gutter_text", "") or muted)
        accent = str(getattr(tokens, "accent", "") or text)
        border = str(getattr(tokens, "border", "") or text)
        hover = str(getattr(tokens, "tree_hover_bg", "") or panel)
        selected = str(getattr(tokens, "tree_selected_bg", "") or hover)
        names = (
            "formBuilder\\.readAsText\\.open",
            "formBuilder\\.readAsText\\.copy",
            "formBuilder\\.readAsText\\.print",
        )

        def _buttons(suffix: str) -> str:
            return ", ".join("QToolButton#%s%s" % (name, suffix) for name in names)

        self.setStyleSheet(
            "QWidget#formBuilder\\.readAsText { background: %s; color: %s; }"
            "QWidget#formBuilder\\.readAsText\\.holder { background: %s; }"
            "QWidget#formBuilder\\.readText\\.column { background: %s; color: %s; }"
            "QLabel { color: %s; background: transparent; }"
            "QLabel[cbcsReadTitle=\"true\"] { color: %s; background: transparent; border: none;"
            " font-size: 10px; font-weight: 600; letter-spacing: 0.5px; }"
            "QLabel#formBuilder\\.readText\\.file { color: %s; }"
            "%s { color: %s; background: transparent; border: 1px solid transparent; padding: 2px 8px; }"
            "%s { background: %s; }"
            "%s { background: %s; border-color: %s; }"
            "%s { border: %dpx solid %s; }"
            "QScrollArea { background: %s; border: none; }"
            % (
                panel, text, panel, panel, text, text, muted, faint,
                _buttons(""), text, _buttons(":hover"), hover,
                _buttons(":checked"), selected, border,
                _buttons(":focus"), width, accent, panel,
            )
        )

    def _fit_column(self) -> None:
        inner = max(0, int(self.width()) - (_PAGE_MARGIN * 2))
        self._column.setFixedWidth(min(_COLUMN_MAX, inner))

    def _button(self, label: str, name: str, handler: object) -> QToolButton:
        button = QToolButton(self)
        button.setText(label)
        button.setObjectName(name)
        button.setAutoRaise(True)
        button.setProperty("fbFlat", True)
        button.setToolButtonStyle(getattr(getattr(Qt, "ToolButtonStyle", Qt), "ToolButtonTextOnly"))
        button.clicked.connect(handler)  # type: ignore[arg-type]
        return button

    def _open_form(self) -> None:
        stack = getattr(self._surface, "_stack", None)
        workbench = getattr(self._surface, "_workbench", None)
        if stack is not None and workbench is not None:
            stack.setCurrentWidget(workbench)

    def _copy(self) -> None:
        from app.qt.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        if clipboard is None:
            return
        clipboard.setText("\n".join((self._title.text(), self._file.text(), "", page_text(self._sentences))))

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
        target = self._column
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


def _window_title(document: object) -> str:
    root = getattr(document, "root", None)
    value = root.value("windowTitle") if root is not None and hasattr(root, "value") else None
    if isinstance(value, (StringValue, CStringValue)) and value.text.strip():
        return value.text.strip()
    name = str(getattr(root, "object_name", "") or "")
    return name or "Form"


def _file_name(surface: object) -> str:
    form_path = getattr(surface, "form_path", None)
    path = str(form_path() or "") if callable(form_path) else ""
    return os.path.basename(path)


def _heading_font() -> QFont:
    font = QFont()
    font.setPixelSize(18)
    font.setWeight(getattr(getattr(QFont, "Weight", QFont), "DemiBold"))
    return font


def _code_family(surface: object) -> str:
    window = surface.window() if hasattr(surface, "window") else None
    family = getattr(window, "_editor_font_family", "") if window is not None else ""
    if isinstance(family, str) and family.strip():
        return family.strip()
    return UI_EDITOR_FONT_FAMILY_DEFAULT


def _size_policy(name: str) -> object:
    names = getattr(QSizePolicy, "Policy", QSizePolicy)
    return getattr(names, name)


def _align(name: str) -> object:
    return getattr(getattr(Qt, "AlignmentFlag", Qt), name)


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
