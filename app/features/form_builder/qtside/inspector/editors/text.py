"""String and C string editors (UX-PED-040, UX-PED-042, UX-PED-045).

One-line strings edit in the row. Multi-line names, word-wrapped label text,
and any value that already contains a line break open a text popover. Rich
label text and ``html`` use Formatted | Source in that popover. The written
HTML comes from ``rich_html.stable_html``, not from ``QTextDocument.toHtml``.

``register`` overrides the ``string`` and ``cstring`` baselines. The style
sheet row keeps its own key, so this module does not change it.
"""

from __future__ import annotations

from typing import Optional, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import (
    BoolValue,
    CStringValue,
    EnumValue,
    StringValue,
)
from app.features.form_builder.qtside.inspector.api import (
    MIXED_TEXT,
    NOT_SET_TEXT,
    EditorHost,
    EditorKey,
    Mixed,
    Registrar,
    RowValue,
    Unset,
    Written,
    mark,
)
from app.features.form_builder.qtside.inspector.editors._popover import RowPopover, SummaryButton
from app.features.form_builder.qtside.inspector.editors._translation import TranslationDisclosure
from app.features.form_builder.qtside.inspector.rich_html import (
    looks_like_html,
    paragraphs_from_document,
    stable_html,
    unsupported_formatting,
)
from app.features.form_builder.qtside.inspector.translatable import shows_translation
from app.qt.QtCore import QEvent, QObject, QRect, QSize, Qt
from app.qt.qt_compat import exec_qt
from app.qt.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextListFormat
from app.qt.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

_MULTILINE = frozenset({
    "plainText",
    "toolTip",
    "whatsThis",
    "statusTip",
    "html",
    "accessibleDescription",
})
_OBJECT_REFERENCE = frozenset({"buddy"})
_EXPANDED: dict = {}

_NO_WIDGET = "No widget called \u201c%s\u201d on this form."
_MAKE_RICH = "Make this text formatted? It is stored as HTML."
_LIMIT = "This text has formatting the editor can't keep."


def _key(name: str) -> object:
    return getattr(getattr(Qt, "Key", Qt), name)


def _mod(name: str) -> object:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)


def _change_label(label: str) -> str:
    if not label:
        return "Change value"
    return "Change " + label[0].lower() + label[1:]


def _translation_label(label: str) -> str:
    if not label:
        return "Change translation of value"
    return "Change translation of " + label[0].lower() + label[1:]


def _document(host: EditorHost) -> Optional[UiDocument]:
    return host.document()


def _owners(host: EditorHost) -> Tuple[NodeId, ...]:
    return host.owner_ids()


def _node(host: EditorHost) -> Optional[WidgetNode]:
    document = _document(host)
    owners = _owners(host)
    if document is None or not owners:
        return None
    node = document.node(owners[0])
    return node if isinstance(node, WidgetNode) else None


def _prop_text(node: Optional[WidgetNode], name: str) -> str:
    if node is None:
        return ""
    entry = node.prop(name)
    if entry is None:
        return ""
    value = entry.value
    if isinstance(value, EnumValue):
        return value.key()[1]
    if isinstance(value, StringValue):
        return value.text
    if isinstance(value, BoolValue):
        return "true" if value.value else ""
    return ""


class StringEditor:
    """Inline string, or a summary that opens the text popover."""

    def __init__(self, spec: object, host: EditorHost, parent: QWidget) -> None:
        self._spec = spec
        self._host = host
        self._shown = ""
        self._value: Optional[StringValue] = None
        self._popover: Optional[RowPopover] = None
        self._box = QWidget(parent)
        self._edit = QLineEdit(self._box)
        self._edit.editingFinished.connect(self._commit_line)
        _ignore_width(self._edit)
        self._summary = SummaryButton(host.label, self._box)
        self._summary.set_opener(self._open)
        self._summary.hide()
        self._translation = TranslationDisclosure()
        self._translation.set_on_change(self._change_attr)
        self._translation.set_on_toggle(self._remember_expanded)
        self._translation.hide()
        column = QVBoxLayout(self._box)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)
        column.addWidget(self._edit)
        column.addWidget(self._summary)

    @property
    def caption_widget(self) -> QWidget:
        return self._translation

    @property
    def widget(self) -> QWidget:
        return self._box

    def show(self, value: RowValue) -> None:
        self._value = _string_of(value)
        self._shown = self._value.text if self._value is not None else _plain(value)
        multiline = self._multiline(self._shown)
        self._edit.setVisible(not multiline)
        self._summary.setVisible(multiline)
        mark(self._edit, value)
        self._edit.blockSignals(True)
        self._edit.setText(self._shown if not multiline else "")
        if not self._edit.hasFocus():
            self._edit.setCursorPosition(0)
        self._edit.setPlaceholderText(_placeholder(value))
        self._edit.blockSignals(False)
        self._summary.set_row_label(self._host.label)
        self._summary.set_summary(_first_line(self._shown) if self._shown else _placeholder(value))
        self._show_translation(value)

    def is_dirty(self) -> bool:
        if self._summary.isVisible():
            return False
        return self._edit.text() != self._shown

    def _multiline(self, text: str) -> bool:
        name = self._host.qt_name
        if self._rich(text):
            return True
        if name in _MULTILINE or "\n" in text or name == "html":
            return True
        if name != "text":
            return False
        node = _node(self._host)
        return _prop_text(node, "wordWrap") in ("true", "True", "1")

    def _rich(self, text: str) -> bool:
        name = self._host.qt_name
        if name == "html":
            return True
        if name != "text":
            return False
        mode = _prop_text(_node(self._host), "textFormat")
        if mode == "RichText":
            return True
        if mode in ("", "AutoText") and looks_like_html(text):
            return True
        return False

    def _show_translation(self, value: RowValue) -> None:
        element = getattr(self._spec, "element", StringValue.ELEMENT)
        if not shows_translation(self._host.qt_name, element) or isinstance(value, Mixed):
            # Mixed: the owners' texts differ, and an attribute commit would
            # write one text to all of them. Edit translations one widget at a time.
            self._translation.hide()
            return
        current = self._value
        self._translation.show()
        self._translation.set_values(
            notr=None if current is None else current.notr,
            comment=None if current is None else current.comment,
            extracomment=None if current is None else current.extracomment,
            ident=None if current is None else current.id,
            show_id=self._host.qt_names(),
        )
        key = (self._host.qt_name, self._host.label)
        if key in _EXPANDED:
            self._translation.set_expanded(_EXPANDED[key])

    def _remember_expanded(self, expanded: bool) -> None:
        _EXPANDED[(self._host.qt_name, self._host.label)] = expanded

    def _commit_line(self) -> None:
        text = self._edit.text()
        if text == self._shown:
            return
        self._host.commit(self._with_text(text))

    def _with_text(self, text: str) -> StringValue:
        current = self._value
        if current is None:
            return StringValue(text)
        return StringValue(text, current.notr, current.comment, current.extracomment, current.id)

    def _change_attr(self, field: str, raw: object) -> None:
        _EXPANDED[(self._host.qt_name, self._host.label)] = self._translation.expanded()
        current = self._value or StringValue(self._shown)
        updated = StringValue(
            current.text,
            raw if field == "notr" else current.notr,  # type: ignore[arg-type]
            raw if field == "comment" else current.comment,  # type: ignore[arg-type]
            raw if field == "extracomment" else current.extracomment,  # type: ignore[arg-type]
            raw if field == "id" else current.id,  # type: ignore[arg-type]
        )
        self._value = updated
        session = self._host.begin_session(_translation_label(self._host.label))
        self._host.commit(updated, session=session)
        session.close()

    def _open(self) -> None:
        if self._popover is not None and not self._popover.closed:
            return
        text = self._current_text()
        popover = RowPopover(
            self._host.row_widget,
            self._host,
            row_label=self._host.label,
            session_label=_change_label(self._host.label),
            qt_name=self._host.qt_name,
            anchor=self._summary,
            large=self._rich(text),
        )
        self._popover = popover
        _TextBody(popover, self._host, self._with_text(text), self._rich(text))
        popover.open_popover()

    def _current_text(self) -> str:
        """The document's text, so a popover opened after undo does not edit a stale copy."""
        owners = _owners(self._host)
        document = _document(self._host)
        if document is None or len(owners) != 1:
            return self._shown
        node = document.node(owners[0])
        if not isinstance(node, WidgetNode):
            return self._shown
        entry = node.prop(self._host.qt_name)
        if entry is None or not isinstance(entry.value, StringValue):
            return self._shown
        self._value = entry.value
        self._shown = entry.value.text
        return self._shown


class _TextBody:
    def __init__(
        self,
        popover: RowPopover,
        host: EditorHost,
        value: StringValue,
        rich: bool,
    ) -> None:
        self._popover = popover
        self._host = host
        self._value = value
        self._rich = rich
        self._dirty = False
        self._ready = False
        self._mode = "plain"
        self._link_row: Optional[QWidget] = None
        layout = popover.body()
        self._plain = QPlainTextEdit()
        self._plain.setPlainText(value.text)
        self._plain.setAccessibleName("%s: text" % host.label)
        self._app_size = _app_point_size()
        display = QFont(_app_family(), self._app_size)
        self._formatted = QTextEdit()
        self._formatted.setFont(display)
        self._formatted.document().setDefaultFont(display)
        self._formatted.setAccessibleName("%s: formatted text" % host.label)
        self._source = QPlainTextEdit()
        self._source.setAccessibleName("%s: HTML source" % host.label)
        self._source.setFont(display)
        _XmlHighlighter(self._source, host.chrome.accent, host.chrome.text)
        self._bar = QWidget()
        bar = QHBoxLayout(self._bar)
        bar.setContentsMargins(0, 0, 0, 0)
        self._formatted_button = QPushButton("Formatted")
        self._source_button = QPushButton("Source")
        self._formatted_button.setCheckable(True)
        self._source_button.setCheckable(True)
        self._formatted_button.setAccessibleName("Formatted")
        self._source_button.setAccessibleName("Source")
        bar.addWidget(self._formatted_button)
        bar.addWidget(self._source_button)
        bar.addStretch(1)
        self._tools = QWidget()
        tools = _Flow(self._tools)
        self._bold = self._tool("B", "Bold")
        self._italic = self._tool("I", "Italic")
        self._underline = self._tool("U", "Underline")
        self._link = self._tool("\u2197", "Link")
        self._bullets = self._tool("\u2022", "Bulleted list")
        self._numbers = self._tool("1.", "Numbered list")
        self._smaller = self._tool("A\u2212", "Smaller")
        self._normal = self._tool("A", "Normal")
        self._larger = self._tool("A+", "Larger")
        for button in (
            self._bold, self._italic, self._underline, self._link,
            self._bullets, self._numbers, self._smaller, self._normal, self._larger,
        ):
            tools.addWidget(button)
        layout.addWidget(self._bar)
        layout.addWidget(self._tools)
        self._limit = QLabel(_LIMIT)
        self._limit.setObjectName("formBuilder.richLimit")
        self._limit.setWordWrap(True)
        self._limit.hide()
        layout.addWidget(self._limit)
        layout.addWidget(self._formatted)
        layout.addWidget(self._plain)
        layout.addWidget(self._source)
        self._plain.textChanged.connect(self._mark)
        self._formatted.textChanged.connect(self._mark)
        self._source.textChanged.connect(self._mark)
        self._formatted_button.clicked.connect(lambda: self._show_mode("formatted"))
        self._source_button.clicked.connect(lambda: self._show_mode("source"))
        self._bold.clicked.connect(lambda: self._style("bold"))
        self._italic.clicked.connect(lambda: self._style("italic"))
        self._underline.clicked.connect(lambda: self._style("underline"))
        self._link.clicked.connect(self._ask_link)
        self._bullets.clicked.connect(lambda: self._list_style(False))
        self._numbers.clicked.connect(lambda: self._list_style(True))
        self._smaller.clicked.connect(lambda: self._size("small"))
        self._normal.clicked.connect(lambda: self._size("normal"))
        self._larger.clicked.connect(lambda: self._size("large"))
        self._formatted.cursorPositionChanged.connect(self._sync_checks)
        for edit in (self._plain, self._formatted, self._source):
            edit.installEventFilter(_CtrlEnter(popover, self))
        self._limited = unsupported_formatting(value.text)
        if self._limited:
            self._source.setPlainText(value.text)
            self._show_mode("source")
        elif rich or looks_like_html(value.text):
            self._show_mode("formatted" if rich else "source")
            if looks_like_html(value.text):
                self._formatted.setHtml(value.text)
                self._source.setPlainText(value.text)
            else:
                self._formatted.setPlainText(value.text)
        else:
            self._show_mode("plain")
        self._ready = True

    def _tool(self, glyph: str, name: str) -> QPushButton:
        button = QPushButton(glyph)
        button.setAccessibleName(name)
        button.setToolTip(name)
        button.setCheckable(True)
        button.setProperty("fbGlyph", "true")
        fixed = getattr(getattr(QSizePolicy, "Policy", QSizePolicy), "Fixed")
        button.setSizePolicy(fixed, fixed)
        return button

    def _mark(self) -> None:
        if self._ready:
            self._dirty = True
            self._write()

    def _show_mode(self, mode: str) -> None:
        if mode == "formatted" and not self._rich and not looks_like_html(self._value.text):
            if not self._confirm():
                self._formatted_button.setChecked(self._mode == "formatted")
                return
            self._rich = True
            self._set_rich_format()
            self._formatted.setPlainText(self._plain.toPlainText() or self._value.text)
        elif self._ready and mode != self._mode:
            # Carry the latest written text into the segment being shown, so an
            # edit made in Formatted is not lost by typing in a stale Source.
            self._ready = False
            current = self._value.text
            if mode == "source":
                self._source.setPlainText(current)
            elif mode == "formatted":
                if looks_like_html(current):
                    self._formatted.setHtml(current)
                else:
                    self._formatted.setPlainText(current)
            self._ready = True
        self._mode = mode
        rich = mode in ("formatted", "source")
        self._bar.setVisible(rich or self._rich)
        self._tools.setVisible(mode == "formatted")
        self._limit.setVisible(self._limited)
        self._formatted.setVisible(mode == "formatted")
        self._source.setVisible(mode == "source")
        self._plain.setVisible(mode == "plain")
        self._formatted_button.setChecked(mode == "formatted")
        self._source_button.setChecked(mode == "source")
        if mode == "source" and not self._source.toPlainText():
            self._source.setPlainText(self._value.text)

    def _confirm(self) -> bool:
        box = QMessageBox(self._popover)
        box.setText(_MAKE_RICH)
        make = box.addButton("Make formatted", QMessageBox.AcceptRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        exec_qt(box)
        return box.clickedButton() is make

    def _set_rich_format(self) -> None:
        owners = _owners(self._host)
        if not owners:
            return
        from app.features.form_builder.engine.commands.catalog import SetProperty

        self._popover.session.run(
            (SetProperty(owners[0], "textFormat", EnumValue("Qt::RichText")),)
        )

    def _style(self, which: str) -> None:
        self._toggle(which)

    def _toggle(self, which: str) -> None:
        cursor = self._formatted.textCursor()
        font = cursor.charFormat().font()
        fmt = QTextCharFormat()
        if which == "bold":
            on = bool(font.bold()) or int(font.weight()) >= 600
            weight = getattr(QFont, "Normal", 400) if on else getattr(QFont, "Bold", 700)
            fmt.setFontWeight(weight)
        elif which == "italic":
            fmt.setFontItalic(not bool(font.italic()))
        else:
            fmt.setFontUnderline(not bool(font.underline()))
        cursor.mergeCharFormat(fmt)
        self._formatted.mergeCurrentCharFormat(fmt)
        self._sync_checks()
        self._formatted.setFocus()

    def _sync_checks(self) -> None:
        font = self._formatted.textCursor().charFormat().font()
        self._bold.setChecked(bool(font.bold()) or int(font.weight()) >= 600)
        self._italic.setChecked(bool(font.italic()))
        self._underline.setChecked(bool(font.underline()))

    def _display_point(self, name: str) -> int:
        if name == "small":
            return max(1, self._app_size - 4)
        if name == "large":
            return self._app_size + 5
        return self._app_size

    def _size(self, name: str) -> None:
        fmt = QTextCharFormat()
        fmt.setFontPointSize(self._display_point(name))
        self._formatted.textCursor().mergeCharFormat(fmt)

    def _list_style(self, numbered: bool) -> None:
        cursor = self._formatted.textCursor()
        styles = getattr(QTextListFormat, "Style", QTextListFormat)
        cursor.createList(getattr(styles, "ListDecimal" if numbered else "ListDisc"))
        self._formatted.setFocus()

    def _ask_link(self) -> None:
        if self._link_row is None:
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(QLabel("Link address"))
            edit = QLineEdit()
            edit.setAccessibleName("Link address")
            edit.setObjectName("formBuilder.linkAddress")
            layout.addWidget(edit, 1)
            apply = QPushButton("Apply")
            apply.clicked.connect(lambda: self._apply_link(edit.text()))
            layout.addWidget(apply)
            self._popover.body().insertWidget(2, row)
            self._link_row = row
            edit.setFocus()
            return
        self._link_row.show()

    def _apply_link(self, href: str) -> None:
        fmt = QTextCharFormat()
        fmt.setAnchor(True)
        fmt.setAnchorHref(href)
        fmt.setFontUnderline(True)
        self._formatted.textCursor().mergeCharFormat(fmt)

    def _write(self) -> None:
        if not self._dirty:
            return
        if self._mode == "source":
            text = self._source.toPlainText()
        elif self._mode == "formatted":
            text = stable_html(paragraphs_from_document(self._formatted.document()))
        else:
            text = self._plain.toPlainText()
        self._value = StringValue(
            text,
            self._value.notr,
            self._value.comment,
            self._value.extracomment,
            self._value.id,
        )
        self._host.commit(self._value, session=self._popover.session)


class CStringEditor:
    """A plain field. Buddy names that are not on the form are refused."""

    def __init__(self, spec: object, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._shown = ""
        self._edit = QLineEdit(parent)
        self._edit.editingFinished.connect(self._commit)
        _ignore_width(self._edit)

    @property
    def widget(self) -> QWidget:
        return self._edit

    def show(self, value: RowValue) -> None:
        mark(self._edit, value)
        self._shown = _cstring_of(value)
        self._edit.blockSignals(True)
        self._edit.setText(self._shown)
        if not self._edit.hasFocus():
            self._edit.setCursorPosition(0)
        self._edit.setPlaceholderText(_placeholder(value))
        self._edit.blockSignals(False)

    def is_dirty(self) -> bool:
        return self._edit.text() != self._shown

    def _commit(self) -> None:
        text = self._edit.text()
        if text == self._shown:
            return
        if self._host.qt_name in _OBJECT_REFERENCE and text and not self._known(text):
            self._host.invalid(_NO_WIDGET % text)
            return
        self._host.commit(CStringValue(text))

    def _known(self, name: str) -> bool:
        document = _document(self._host)
        if document is None:
            return True
        return any(widget.object_name == name for widget in document.iter_widgets())


class _CtrlEnter(QObject):
    def __init__(self, popover: RowPopover, body: _TextBody) -> None:
        super().__init__(popover)
        self._popover = popover
        self._body = body

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() != getattr(getattr(QEvent, "Type", QEvent), "KeyPress"):
            return False
        key = event.key()  # type: ignore[attr-defined]
        mods = event.modifiers()  # type: ignore[attr-defined]
        ctrl = bool(mods & _mod("ControlModifier"))
        if key in (_key("Key_Return"), _key("Key_Enter")) and ctrl:
            self._popover.done()
            return True
        if not ctrl or not isinstance(watched, QTextEdit):
            return False
        if key == _key("Key_B"):
            self._body._toggle("bold")
            return True
        if key == _key("Key_I"):
            self._body._toggle("italic")
            return True
        if key == _key("Key_U"):
            self._body._toggle("underline")
            return True
        return False


def _app_point_size() -> int:
    app = QApplication.instance()
    if app is None:
        return 9
    size = app.font().pointSize()
    return size if size > 0 else 9


def _app_family() -> str:
    app = QApplication.instance()
    if app is None:
        return "Sans Serif"
    family = app.font().family()
    return family or "Sans Serif"


class _Flow(QLayout):
    """Wraps the rich-text glyphs onto as many lines as the popover is wide."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._items: list = []
        self._gap = 4

    def addItem(self, item: object) -> None:  # noqa: N802
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> object:  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> object:  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> object:  # noqa: N802
        orient = getattr(Qt, "Orientation", None)
        if orient is not None:
            return orient(0)
        return 0

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._arrange(QRect(0, 0, width, 0), False)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._arrange(rect, True)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        return QSize(48, self._arrange(QRect(0, 0, 220, 0), False))

    def _arrange(self, rect: QRect, apply: bool) -> int:
        x = rect.x()
        y = rect.y()
        line = 0
        right = rect.x() + max(0, rect.width())
        for item in self._items:
            hint = item.sizeHint()
            width = hint.width()
            height = hint.height()
            if x > rect.x() and x + width > right:
                x = rect.x()
                y += line + self._gap
                line = 0
            if apply:
                item.setGeometry(QRect(x, y, width, height))
            x += width + self._gap
            line = max(line, height)
        return (y + line) - rect.y()


class _XmlHighlighter(QSyntaxHighlighter):
    def __init__(self, parent: QPlainTextEdit, accent: str, text: str) -> None:
        super().__init__(parent.document())
        self._tag = QTextCharFormat()
        self._tag.setForeground(_color(accent))
        self._text = QTextCharFormat()
        self._text.setForeground(_color(text))

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        self.setFormat(0, len(text), self._text)
        start = 0
        while True:
            opened = text.find("<", start)
            if opened < 0:
                return
            closed = text.find(">", opened)
            if closed < 0:
                self.setFormat(opened, len(text) - opened, self._tag)
                return
            self.setFormat(opened, closed - opened + 1, self._tag)
            start = closed + 1


def _color(value: str) -> QColor:
    if not value:
        return QColor(0, 0, 0)
    return QColor(value)


def _string_of(value: RowValue) -> Optional[StringValue]:
    if isinstance(value, Written) and isinstance(value.value, StringValue):
        return value.value
    if isinstance(value, Unset) and isinstance(value.default, StringValue):
        return None
    return None


def _plain(value: RowValue) -> str:
    if isinstance(value, Written) and isinstance(value.value, StringValue):
        return value.value.text
    if isinstance(value, Unset) and isinstance(value.default, StringValue):
        return ""
    return ""


def _cstring_of(value: RowValue) -> str:
    if isinstance(value, Written) and isinstance(value.value, CStringValue):
        return value.value.text
    return ""


def _placeholder(value: RowValue) -> str:
    if isinstance(value, Mixed):
        return MIXED_TEXT
    if isinstance(value, Unset):
        default = value.default
        if isinstance(default, (StringValue, CStringValue)) and default.text:
            return default.text
        return NOT_SET_TEXT
    return ""


def _first_line(text: str) -> str:
    if "\n" not in text:
        return text
    return text.split("\n", 1)[0] + " \u21b5"


def _ignore_width(widget: QWidget) -> None:
    policy = getattr(QSizePolicy, "Policy", QSizePolicy)
    widget.setMinimumWidth(0)
    widget.setSizePolicy(getattr(policy, "Ignored"), getattr(policy, "Preferred"))


def register(registrar: Registrar) -> None:
    registrar.editor(EditorKey(StringValue.ELEMENT), StringEditor)
    registrar.editor(EditorKey(CStringValue.ELEMENT), CStringEditor)
