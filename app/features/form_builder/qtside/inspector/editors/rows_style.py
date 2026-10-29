"""Style rows (M5.3): Style sheet, Text colour and Background, and the form's Look group.

Appearance order for text-bearing widgets is Font, Text colour, Background,
Style sheet, then the M4 rows (UX-STYLE-011). Text colour writes a ``color``
declaration in the widget's own style sheet, because FreeCAD's application
style sheet overrides palette text roles on ChoreBoy (UX-STYLE-010, section
16.3); Background writes one palette role. None of these rows has a property of
its own to write, so each editor reads the document and writes through its own
edit session.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.commands.base import Command
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.style import colour_rows
from app.features.form_builder.engine.style.colors import Rgb, parse_color
from app.features.form_builder.engine.style.edit import StyleEditRefused, read_color
from app.features.form_builder.engine.style.override import BACKGROUND_NAMES, TEXT_NAMES, sheet_sets
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import ColorValue, NumberValue, StringValue, Value
from app.features.form_builder.qtside.inspector.api import (
    STYLESHEET,
    EditorHost,
    EditorKey,
    GroupHost,
    GroupId,
    Mixed,
    OpenRow,
    Prop,
    Registrar,
    RowSpec,
    RowValue,
    Summary,
    Unset,
    ValueSpec,
    Written,
    mark,
)
from app.features.form_builder.qtside.inspector.editors._editor_kit import warning_color
from app.features.form_builder.qtside.style import gateway
from app.features.form_builder.qtside.style.verdict import summary_text
from app.features.form_builder.qtside.visual.color_picker import ColorPicker, Swatch, colour_summary
from app.features.form_builder.qtside.visual.common import RowSummary, begin_popover, owner_name, refit
from app.qt.QtCore import Qt
from app.qt.QtGui import QColor, QPalette
from app.qt.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

TEXT_COLOUR_KEY = EditorKey("textcolour")
BACKGROUND_KEY = EditorKey("background")
ACCENT_KEY = EditorKey("accentcolour")
TEXT_SIZE_KEY = EditorKey("textsize")

ACCENT_CAPTION = "Colour of selections, progress bars and links."
SIZE_CAPTION = "Every widget that doesn't set its own size follows this."
_NO_SHEET_EDIT = "The style sheet can't be read, so it can't be changed here."
_EDIT_LINK = "Edit style sheet"


def _visible(document: UiDocument, owners: Tuple[NodeId, ...]) -> bool:
    return colour_rows.shows_rows(document, owners)


def register(registrar: Registrar) -> None:
    registrar.editor(TEXT_COLOUR_KEY, TextColourEditor)
    registrar.editor(BACKGROUND_KEY, BackgroundEditor)
    registrar.editor(ACCENT_KEY, AccentColourEditor)
    registrar.editor(TEXT_SIZE_KEY, TextSizeEditor)
    registrar.editor(STYLESHEET, StyleSheetEditor)
    registrar.row(
        RowSpec(
            key="textColour",
            group=GroupId.APPEARANCE,
            label="Text colour",
            help="The colour of the words. Set in the widget's style sheet.",
            source=Summary(),
            editor=str(TEXT_COLOUR_KEY),
            after="font",
            visible=_visible,
        )
    )
    registrar.row(
        RowSpec(
            key="backgroundColour",
            group=GroupId.APPEARANCE,
            label="Background",
            help="The colour behind the widget.",
            source=Summary(),
            editor=str(BACKGROUND_KEY),
            after="textColour",
            visible=_visible,
        )
    )
    registrar.row(
        RowSpec(
            key="styleSheet",
            group=GroupId.APPEARANCE,
            label="Style sheet",
            help="Rules that restyle this widget and everything inside it.",
            source=Prop("styleSheet"),
            editor=str(STYLESHEET),
            after="backgroundColour",
        )
    )


def register_form_groups(registry: object) -> None:
    registry.add("look", "Look", LookBody, order=400)  # type: ignore[attr-defined]


# helpers ----------------------------------------------------------------


def _session_of(host: object) -> object:
    session = getattr(host, "session", None)
    if session is not None:
        return session
    services = getattr(host, "_services", None)
    return getattr(services, "session", None)


def _faint_label(parent: QWidget, color: str) -> QLabel:
    label = QLabel(parent)
    label.setWordWrap(True)
    label.setStyleSheet("color: %s; background: transparent;" % color)
    label.hide()
    return label


class _Proxy:
    """An ``EditorHost`` whose ``commit`` and ``reset`` are the row's own."""

    def __init__(self, host: EditorHost, write: Callable[[Value, object], None], clear: Callable[[], None]) -> None:
        self._host = host
        self._write = write
        self._clear = clear

    def commit(self, value: Value, session: object = None) -> None:
        self._write(value, session)

    def reset(self) -> None:
        self._clear()

    def __getattr__(self, name: str) -> object:
        return getattr(self._host, name)


# Style sheet row ---------------------------------------------------------


class _EnterButton(QPushButton):
    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        key = event.key()  # type: ignore[attr-defined]
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.click()
            event.accept()  # type: ignore[attr-defined]
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]


class StyleSheetEditor:
    """A summary of the sheet and an [Edit…] button that opens the drawer (UX-STYLE-001)."""

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._root = QWidget(parent)
        layout = QHBoxLayout(self._root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._summary = QLabel("None", self._root)
        self._summary.setObjectName("formBuilder.styleSummary")
        self._button = _EnterButton("Edit…", self._root)
        self._button.setObjectName("formBuilder.styleEdit")
        self._button.setAutoDefault(False)
        self._button.clicked.connect(self._open)
        layout.addWidget(self._summary, 1)
        layout.addWidget(self._button, 0)

    @property
    def widget(self) -> QWidget:
        return self._root

    def show(self, value: RowValue) -> None:
        mark(self._summary, value)
        if isinstance(value, Mixed):
            text = "Mixed"
        elif isinstance(value, Written) and isinstance(value.value, StringValue):
            text = summary_text(value.value.text)
        else:
            text = "None"
        self._summary.setText(text)
        warn = text == "Can't be read"
        self._summary.setStyleSheet(
            "color: %s; background: transparent;" % warning_color(self._host.chrome) if warn else "background: transparent;"
        )
        label = self._host.label or "Style sheet"
        self._button.setAccessibleName("%s: edit" % label)
        owners = self._host.owner_ids()
        self._button.setEnabled(len(owners) == 1)

    def _open(self) -> None:
        owners = self._host.owner_ids()
        session = _session_of(self._host)
        if len(owners) != 1 or session is None:
            return
        gateway.open_drawer(session, owners[0])


# Text colour and Background ---------------------------------------------


class _ColourRow:
    """Shared body of the Text colour and Background rows."""

    row_label = ""
    undo_words = ""
    object_name = ""

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._outer_host = host
        self._root = QWidget(parent)
        self._root.setObjectName(self.object_name)
        layout = QHBoxLayout(self._root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._swatch = Swatch(self._root, 16)
        self._swatch.set_tokens(host.chrome)
        self._proxy = _Proxy(host, self._write_from_picker, self._reset_all)
        self._summary = RowSummary(host.label or self.row_label, self._root)
        self._summary.set_opener(self._open)
        self._summary.set_summary("Default")
        self._reset_button = QToolButton(self._root)
        self._reset_button.setText("↺")
        self._reset_button.setAutoRaise(True)
        self._reset_button.setAccessibleName("Reset %s" % self.row_label.lower())
        self._reset_button.clicked.connect(self._reset_all)
        self._reset_button.hide()
        layout.addWidget(self._swatch)
        layout.addWidget(self._summary, 1)
        layout.addWidget(self._reset_button)
        self._caption = _faint_label(self._root, host.chrome.muted)
        self._caption.linkActivated.connect(lambda _link: self._open_sheet())
        self._color: Optional[ColorValue] = None
        self._written = False
        self._popover: Optional[object] = None
        self._picker: Optional[ColorPicker] = None
        self._error: Optional[QLabel] = None

    @property
    def widget(self) -> QWidget:
        return self._root

    @property
    def caption_widget(self) -> QWidget:
        return self._caption

    # reading -------------------------------------------------------------

    def _read(self, document: UiDocument, owner: NodeId) -> Tuple[Optional[Rgb], bool, str]:
        """``(colour, written by this row, raw text when it isn't a plain colour)``."""
        raise NotImplementedError

    def _caption_for(self, document: UiDocument, owners: Tuple[NodeId, ...], palette_only: bool) -> Tuple[str, bool]:
        """``(text, is a warning)``."""
        raise NotImplementedError

    def _write_commands(self, document: UiDocument, owner: NodeId, rgb: Rgb) -> Tuple[Command, ...]:
        raise NotImplementedError

    def _clear_commands(self, document: UiDocument, owner: NodeId) -> Tuple[Command, ...]:
        raise NotImplementedError

    def show(self, value: RowValue) -> None:
        del value
        document = self._host.document()
        owners = self._host.owner_ids()
        reads = [self._read(document, owner) for owner in owners if document.contains(owner)]
        mixed = len({(item[0], item[1]) for item in reads}) > 1
        first = reads[0] if reads else (None, False, "")
        color = None if mixed or first[0] is None else ColorValue(first[0][0], first[0][1], first[0][2])
        self._color = color
        self._written = bool(reads) and all(item[1] for item in reads)
        palette_only = not mixed and first[0] is not None and not first[1]
        if mixed:
            summary = "Mixed"
        elif color is not None:
            summary = colour_summary(color, mixed=False, unset=False)
        elif first[2]:
            summary = first[2]
        else:
            summary = "Default"
        self._summary.set_summary(summary)
        self._swatch.set_color(color, hollow=color is None and not mixed, mixed=mixed)
        shown = Written(color) if (color is not None and self._written) else Unset()
        self._summary.show_state(Mixed() if mixed else shown, self._host.chrome.faint)
        any_written = any(item[1] for item in reads)
        self._reset_button.setVisible(any_written)
        text, warn = self._caption_for(document, owners, palette_only) if reads else ("", False)
        self._set_caption(text, warn)
        if (
            self._picker is not None
            and color is not None
            and (self._picker.color().red, self._picker.color().green, self._picker.color().blue)
            != (color.red, color.green, color.blue)
        ):
            self._picker.set_color(color)

    def _set_caption(self, text: str, warn: bool) -> None:
        chrome = self._host.chrome
        if not text:
            self._caption.hide()
            self._caption.setText("")
            return
        tint = warning_color(chrome) if warn else chrome.muted
        self._caption.setStyleSheet("color: %s; background: transparent;" % tint)
        if warn:
            self._caption.setTextFormat(Qt.TextFormat.RichText)
            self._caption.setText('%s <a href="#edit">[%s]</a>' % (text, _EDIT_LINK))
            self._caption.setOpenExternalLinks(False)
            palette = self._caption.palette()
            palette.setColor(QPalette.ColorRole.Link, QColor(chrome.accent))
            self._caption.setPalette(palette)
        else:
            self._caption.setTextFormat(Qt.TextFormat.PlainText)
            self._caption.setText(text)
        self._caption.show()

    def _open_sheet(self) -> None:
        owners = self._host.owner_ids()
        session = _session_of(self._host)
        if len(owners) == 1 and session is not None:
            gateway.open_drawer(session, owners[0])

    # writing -------------------------------------------------------------

    def _label(self) -> str:
        return self.undo_words % owner_name(self._host) if "%s" in self.undo_words else self.undo_words

    def _run(self, commands: Sequence[Command], session: Optional[object]) -> bool:
        if not commands:
            return True
        own = session
        if own is None:
            own = self._host.begin_session(self._label())
        try:
            result = own.run(tuple(commands))  # type: ignore[attr-defined]
        finally:
            if session is None:
                own.close()  # type: ignore[attr-defined]
        message = getattr(result, "message", "")
        if message:
            code = getattr(result, "code", None)
            self._host.invalid("%s %s" % (code, message) if code else message)
            return False
        return True

    def _write_from_picker(self, value: Value, session: object = None) -> None:
        if not isinstance(value, ColorValue):
            return
        document = self._host.document()
        rgb = (value.red, value.green, value.blue)
        commands: List[Command] = []
        try:
            for owner in self._host.owner_ids():
                commands.extend(self._write_commands(document, owner, rgb))
        except StyleEditRefused:
            self._host.invalid(_NO_SHEET_EDIT)
            self._invalid_in_popover(_NO_SHEET_EDIT)
            return
        self._invalid_in_popover("")
        if self._run(commands, session):
            self._color = value
            self._written = True
            self._swatch.set_color(value)
            self._summary.set_summary(colour_summary(value, mixed=False, unset=False))

    def _reset_all(self) -> None:
        document = self._host.document()
        commands: List[Command] = []
        try:
            for owner in self._host.owner_ids():
                commands.extend(self._clear_commands(document, owner))
        except StyleEditRefused:
            self._host.invalid(_NO_SHEET_EDIT)
            return
        popover = self._popover
        session = None if popover is None or popover.closed else popover.session  # type: ignore[attr-defined]
        self._run(commands, session)

    def _invalid_in_popover(self, message: str) -> None:
        if self._error is None:
            return
        if message:
            self._error.setText(message)
            self._error.show()
        else:
            self._error.hide()

    # the popover -----------------------------------------------------------

    def _open(self) -> None:
        popover = self._popover
        if popover is not None and not popover.closed:  # type: ignore[attr-defined]
            return
        opened = begin_popover(self._proxy, self._summary, self._label())  # type: ignore[arg-type]
        picker = ColorPicker(
            opened,
            on_color=lambda color: self._write_from_picker(color, opened.session),
            on_invalid=self._picker_invalid,
            on_done=opened.done,
            row=self.row_label,
        )
        picker.set_tokens(self._host.chrome)
        picker.set_color(self._color if self._color is not None else ColorValue(0, 0, 0))
        opened.body().addWidget(picker)
        error = QLabel(opened)
        error.setObjectName("formBuilder.rowError")
        error.setStyleSheet("color: %s;" % self._host.chrome.error)
        error.hide()
        opened.body().addWidget(error)
        opened.set_reset(self._reset_all if self._written else None)
        self._popover = opened
        self._picker = picker
        self._error = error
        opened.open_popover()
        refit(opened)
        picker.fit_width(opened.width())

    def _picker_invalid(self, message: str) -> None:
        if message:
            self._host.invalid(message)
        self._invalid_in_popover(message)


class TextColourEditor(_ColourRow):
    row_label = "Text colour"
    undo_words = "Change text colour of %s"
    object_name = "formBuilder.textColour"

    def _read(self, document: UiDocument, owner: NodeId) -> Tuple[Optional[Rgb], bool, str]:
        node = document.node(owner)
        raw = read_color(_sheet(node), node.object_name) if isinstance(node, WidgetNode) else None  # type: ignore[attr-defined]
        if raw is not None:
            return parse_color(raw), True, raw
        return colour_rows.palette_text_color(document, owner), False, ""

    def _caption_for(self, document: UiDocument, owners: Tuple[NodeId, ...], palette_only: bool) -> Tuple[str, bool]:
        if len(owners) == 1 and not colour_rows.has_own_text_color(document, owners[0]):
            if sheet_sets(document, owners[0], TEXT_NAMES):
                return colour_rows.OVERRIDDEN_CAPTION, True
        if palette_only:
            return colour_rows.PALETTE_CAPTION, False
        return "", False

    def _write_commands(self, document: UiDocument, owner: NodeId, rgb: Rgb) -> Tuple[Command, ...]:
        return colour_rows.text_color_commands(document, owner, rgb, "Edit")

    def _clear_commands(self, document: UiDocument, owner: NodeId) -> Tuple[Command, ...]:
        return colour_rows.clear_text_color_commands(document, owner, "Edit")


class BackgroundEditor(_ColourRow):
    row_label = "Background"
    undo_words = "Change background of %s"
    object_name = "formBuilder.backgroundColour"

    def _read(self, document: UiDocument, owner: NodeId) -> Tuple[Optional[Rgb], bool, str]:
        color = colour_rows.background_color(document, owner)
        return color, color is not None, ""

    def _caption_for(self, document: UiDocument, owners: Tuple[NodeId, ...], palette_only: bool) -> Tuple[str, bool]:
        del palette_only
        if len(owners) == 1 and sheet_sets(document, owners[0], BACKGROUND_NAMES):
            return colour_rows.OVERRIDDEN_CAPTION, True
        return "", False

    def _write_commands(self, document: UiDocument, owner: NodeId, rgb: Rgb) -> Tuple[Command, ...]:
        return colour_rows.background_commands(document, owner, rgb, "Edit")

    def _clear_commands(self, document: UiDocument, owner: NodeId) -> Tuple[Command, ...]:
        return colour_rows.clear_background_commands(document, owner, "Edit")


class AccentColourEditor(_ColourRow):
    """The form's accent colour: the root palette's Highlight and Link roles (UX-STYLE-012)."""

    row_label = "Accent colour"
    undo_words = "Change accent colour"
    object_name = "formBuilder.accentColour"

    def _read(self, document: UiDocument, owner: NodeId) -> Tuple[Optional[Rgb], bool, str]:
        color = colour_rows.accent_color(document)
        return color, color is not None, ""

    def _caption_for(self, document: UiDocument, owners: Tuple[NodeId, ...], palette_only: bool) -> Tuple[str, bool]:
        del document, owners, palette_only
        return ACCENT_CAPTION, False

    def _write_commands(self, document: UiDocument, owner: NodeId, rgb: Rgb) -> Tuple[Command, ...]:
        return colour_rows.accent_commands(document, rgb, "Edit")

    def _clear_commands(self, document: UiDocument, owner: NodeId) -> Tuple[Command, ...]:
        return colour_rows.accent_commands(document, None, "Edit")


def _sheet(node: object) -> str:
    entry = node.prop("styleSheet")  # type: ignore[attr-defined]
    if entry is not None and isinstance(entry.value, StringValue):
        return entry.value.text
    return ""


# The form's Look group ----------------------------------------------------


class _FormOwner:
    """A row write for rows that write through their own editor: it only says which nodes the row shows."""

    def __init__(self) -> None:
        self.owners: Tuple[NodeId, ...] = ()

    def edit(self, value: Value, token: Optional[str]) -> Tuple[Command, ...]:
        del value, token
        return ()

    def reset(self) -> Tuple[Command, ...]:
        return ()


class LookBody:
    """Accent colour and Text size of the whole form (UX-STYLE-012)."""

    def __init__(self, host: GroupHost, parent: QWidget) -> None:
        self._host = host
        self._root = QWidget(parent)
        self._root.setObjectName("formBuilder.lookBody")
        layout = QVBoxLayout(self._root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self._write = _FormOwner()
        self._accent = host.editor_for(self._row("look.accent", "Accent colour", ACCENT_CAPTION, ACCENT_KEY), self._root)
        self._size = host.editor_for(self._row("look.size", "Text size", SIZE_CAPTION, TEXT_SIZE_KEY), self._root)
        layout.addWidget(self._accent.widget)
        layout.addWidget(self._size.widget)

    @property
    def widget(self) -> QWidget:
        return self._root

    def _row(self, key: str, label: str, help_text: str, editor: EditorKey) -> OpenRow:
        self._write.owners = self._host.owners
        return OpenRow(key, label, "", help_text, Unset(), ValueSpec("summary"), editor, self._write)

    def show(self, rows: Sequence[object]) -> None:
        del rows
        self._write.owners = self._host.owners
        self._accent.show(Unset())
        self._size.show(Unset())


class TextSizeEditor:
    """A point size from 8 to 24 on the form's font. "Default" means every widget keeps Qt's own size."""

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._root = QWidget(parent)
        row = QHBoxLayout(self._root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self._box = QSpinBox(self._root)
        self._box.setObjectName("formBuilder.textSize")
        self._box.setAccessibleName("Text size")
        self._box.setRange(colour_rows.TEXT_SIZE_MIN - 1, colour_rows.TEXT_SIZE_MAX)
        self._box.setSpecialValueText("Default")
        self._box.setSuffix(" pt")
        self._box.setKeyboardTracking(False)
        self._box.setMinimumWidth(0)
        self._reset = QToolButton(self._root)
        self._reset.setText("\u21ba")
        self._reset.setAutoRaise(True)
        self._reset.setAccessibleName("Reset text size")
        self._reset.clicked.connect(self._clear)
        self._reset.hide()
        row.addWidget(self._box, 1)
        row.addWidget(self._reset)
        self._caption = _faint_label(self._root, host.chrome.muted)
        self._caption.setText(SIZE_CAPTION)
        self._caption.show()
        self._showing = False
        self._box.valueChanged.connect(self._changed)

    @property
    def widget(self) -> QWidget:
        return self._root

    @property
    def caption_widget(self) -> QWidget:
        return self._caption

    def show(self, value: RowValue) -> None:
        del value
        # The theme can change after the editor is built; the caption follows it like the colour rows' captions.
        self._caption.setStyleSheet("color: %s; background: transparent;" % self._host.chrome.muted)
        size = colour_rows.text_size(self._host.document())
        mark(self._box, Written(NumberValue(size)) if size is not None else Unset())
        shown = size if size is not None else self._box.minimum()
        self._showing = True
        try:
            if self._box.value() != shown:
                self._box.setValue(shown)
        finally:
            self._showing = False
        self._reset.setVisible(size is not None)

    def _run(self, points: Optional[int]) -> None:
        commands = colour_rows.text_size_commands(self._host.document(), points, "Edit")
        if not commands:
            return
        session = self._host.begin_session("Change text size")
        try:
            result = session.run(commands)
        finally:
            session.close()
        message = getattr(result, "message", "")
        if message:
            self._host.invalid(message)

    def _clear(self) -> None:
        self._run(None)

    def _changed(self, number: int) -> None:
        if self._showing:
            return
        self._run(number if number >= colour_rows.TEXT_SIZE_MIN else None)


__all__: Sequence[str] = ["register", "register_form_groups"]
