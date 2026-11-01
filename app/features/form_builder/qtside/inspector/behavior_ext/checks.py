"""Checks section (UX-CHK-001). One undo step per edit, named for the field."""

from __future__ import annotations

from types import SimpleNamespace
from typing import List, Optional, Tuple

from app.qt.QtCore import QEvent, QPoint, Qt, QTimer
from app.qt.QtWidgets import (
    QAction,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import enum_value

from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.commands.catalog_ext.checks import AddErrorLabel, SetChecks
from app.features.form_builder.engine.logic.checks import Check, Required, kind_text, read_checks
from app.features.form_builder.engine.logic.formula_env import env_for
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.qtside.checks import CheckOffer, CheckPage
from app.features.form_builder.qtside.checks.offer import _EnterButton
from app.features.form_builder.qtside.checks.catalog import (
    offered_kinds,
    words_of,
    writes_native,
    generated_message,
)
from app.features.form_builder.qtside.inspector._services import Dropped, Rejected
from app.features.form_builder.qtside.inspector.behavior_ext import BehaviorSection, SectionHost, SectionInputs
from app.features.form_builder.qtside.inspector.model import OneBehavior
from app.features.form_builder.qtside.theme.chrome import edge_on, link_ink

_ENTER = frozenset({enum_value(Qt.Key.Key_Return), enum_value(Qt.Key.Key_Enter)})
_UP = enum_value(Qt.Key.Key_Up)
_DOWN = enum_value(Qt.Key.Key_Down)
_DELETE = enum_value(Qt.Key.Key_Delete)
_ALT = enum_value(Qt.KeyboardModifier.AltModifier)
_OVERRIDE = enum_value(getattr(getattr(QEvent, "Type", QEvent), "ShortcutOverride"))
_KEY_PRESS = enum_value(getattr(getattr(QEvent, "Type", QEvent), "KeyPress"))
# User content for the form, the same red the check manual names. The hex
# check allows this one sentence and nothing else.
_OUTLINE = '*[cbcsInvalid="true"] { border: 1px solid #c62828; }'
_SELECTOR = '*[cbcsInvalid="true"]'
_ROW_WORDS = (
    "Required",
    "Between",
    "Length",
    "Email address",
    "Phone number",
    "US ZIP code",
    "Pattern",
    "One of",
    "Formula",
)


def _wrap(label: QLabel) -> None:
    label.setWordWrap(True)
    label.setMinimumWidth(0)
    # setSizePolicy() clears the height-for-width bit setWordWrap turned on.
    # The column then keeps a one-line hint and the wrapped sentence draws
    # over the next rows. Ignored keeps that sentence from widening the section.
    names = getattr(QSizePolicy, "Policy", QSizePolicy)
    label.setSizePolicy(getattr(names, "Ignored"), getattr(names, "Minimum"))
    fitted = label.sizePolicy()
    fitted.setHeightForWidth(True)
    label.setSizePolicy(fitted)


def _shrink(widget: QWidget) -> None:
    names = getattr(QSizePolicy, "Policy", QSizePolicy)
    widget.setMinimumWidth(0)
    widget.setSizePolicy(getattr(names, "Ignored"), getattr(names, "Minimum"))


def _words_width(widget: QWidget) -> int:
    metrics = widget.fontMetrics()
    widest = 0
    for word in _ROW_WORDS:
        widest = max(widest, int(metrics.horizontalAdvance(word)))
    return widest + 12


def _tab_stop(widget: QWidget) -> None:
    # Tab reaches the control. Click and show do not, so opening the section
    # does not pull focus out of the outline.
    widget.setFocusPolicy(Qt.FocusPolicy.TabFocus)


def _quiet(widget: QWidget) -> None:
    widget.setFocusPolicy(Qt.NoFocus)
    for child in widget.findChildren(QWidget):
        child.setFocusPolicy(Qt.NoFocus)


class _AddButton(QPushButton):
    def __init__(self, text: str, parent: QWidget) -> None:
        super().__init__(text, parent)
        _tab_stop(self)

    def keyPressEvent(self, event: QEvent) -> None:  # noqa: N802
        key = enum_value(event.key())  # type: ignore[attr-defined]
        if key == _DOWN or key in _ENTER:
            self.click()
            event.accept()
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]


class _CheckRow(QWidget):
    def __init__(self, body: "ChecksBody", index: int) -> None:
        super().__init__(body)
        self._body = body
        self.index = index
        self._full = ""
        self.setObjectName("formBuilder.checks.row.%d" % index)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setMinimumWidth(0)
        self.words = QLabel(self)
        self.words.setObjectName("formBuilder.checks.words.%d" % index)
        self.words.setMinimumWidth(0)
        self.message = QLabel(self)
        self.message.setObjectName("formBuilder.checks.messageText.%d" % index)
        self.message.setWordWrap(True)
        self.message.setMinimumWidth(0)
        message_policy = self.message.sizePolicy()
        message_policy.setHeightForWidth(True)
        self.message.setSizePolicy(message_policy)
        self.qt = QLabel("Qt", self)
        self.qt.setObjectName("formBuilder.checks.qt.%d" % index)
        host = QWidget(self)
        host.setMinimumHeight(22)
        host.setMinimumWidth(0)
        line = QHBoxLayout(host)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(8)
        line.addWidget(self.words)
        line.addWidget(self.message, 1)
        line.addWidget(self.qt)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(host)

    def show_check(self, words: str, message: str, native: bool, number: int, total: int) -> None:
        self.words.setText(words)
        self._full = message
        self.qt.setVisible(native)
        self._elide()
        sentence = "Check %d of %d, %s, message %s" % (number, total, words, message)
        self.setAccessibleName(sentence)

    def resizeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._elide()

    def event(self, event: QEvent) -> bool:  # noqa: N802
        if enum_value(event.type()) == _OVERRIDE and self._claim(event):
            event.accept()
            return True
        return bool(super().event(event))

    def keyPressEvent(self, event: QEvent) -> None:  # noqa: N802
        key = enum_value(event.key())  # type: ignore[attr-defined]
        mods = enum_value(event.modifiers())  # type: ignore[attr-defined]
        alt = bool(mods & _ALT)
        if key == _UP and alt:
            self._body.move_check(self.index, -1)
            event.accept()
            return
        if key == _DOWN and alt:
            self._body.move_check(self.index, 1)
            event.accept()
            return
        if key == _DELETE:
            self._body.remove_check(self.index)
            event.accept()
            return
        if key in _ENTER:
            self._body.edit_check(self.index)
            event.accept()
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]

    def _claim(self, event: QEvent) -> bool:
        key = enum_value(event.key())  # type: ignore[attr-defined]
        mods = enum_value(event.modifiers())  # type: ignore[attr-defined]
        if key in (_UP, _DOWN):
            return bool(mods & _ALT)
        return key == _DELETE or key in _ENTER

    def _elide(self) -> None:
        full = self._full
        if self.message.text() != full:
            self.message.setText(full)
        if self.message.toolTip():
            self.message.setToolTip("")


_LEFT = getattr(getattr(Qt, "AlignmentFlag", Qt), "AlignLeft")
_TOP = getattr(getattr(Qt, "AlignmentFlag", Qt), "AlignTop")


class _SentenceLink(QWidget):
    """A sentence with a link at its end. They stack when the row is narrow."""

    def __init__(self, sentence: str, link: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setMinimumWidth(0)
        self.words = QLabel(sentence, self)
        self.words.setWordWrap(False)
        self.words.setMinimumWidth(0)
        self.link = _EnterButton(link, self)
        self.link.setFlat(True)
        self.link.setAutoDefault(False)
        self.link.setCursor(getattr(getattr(Qt, "CursorShape", Qt), "PointingHandCursor"))
        names = getattr(QSizePolicy, "Policy", QSizePolicy)
        self.link.setSizePolicy(getattr(names, "Maximum"), getattr(names, "Fixed"))
        self._wide: Optional[bool] = None
        self._queued = False
        self._box = QVBoxLayout(self)
        self._box.setContentsMargins(0, 0, 0, 0)
        self._box.setSpacing(0)
        self._place(True)

    def resizeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._queue()

    def showEvent(self, event: QEvent) -> None:  # noqa: N802
        super().showEvent(event)  # type: ignore[arg-type]
        self._queue()

    def _queue(self) -> None:
        if self._queued:
            return
        self._queued = True
        # The context object cancels this if the section is already gone.
        QTimer.singleShot(0, self, self._apply)

    def _apply(self) -> None:
        self._queued = False
        try:
            self.words.setWordWrap(False)
        except RuntimeError:
            return
        self.words.setMaximumWidth(16777215)
        needed = self.words.sizeHint().width() + self.link.sizeHint().width() + 8
        wide = self.width() <= 1 or needed <= self.width()
        if wide != self._wide:
            self._place(wide)
            return
        if not wide and self.width() > 1:
            self.words.setMaximumWidth(self.width())
            self.words.setWordWrap(True)

    def _place(self, wide: bool) -> None:
        self._wide = wide
        self.words.setWordWrap(not wide)
        # A word-wrapped label keeps its one-line width unless something
        # caps it, so a 236px column clips the last word.
        cap = 16777215 if wide or self.width() <= 1 else self.width()
        self.words.setMaximumWidth(cap)
        while self._box.count():
            item = self._box.takeAt(0)
            nested = item.layout() if item is not None else None
            if nested is not None:
                while nested.count():
                    nested.takeAt(0)
        if wide:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            row.addWidget(self.words, 0, _TOP)
            row.addWidget(self.link, 0, _TOP)
            row.addStretch(1)
            self._box.setSpacing(0)
            self._box.addLayout(row)
        else:
            self._box.setSpacing(2)
            self._box.addWidget(self.words)
            self._box.addWidget(self.link, 0, _LEFT)
        self.updateGeometry()


def _run_order(checks: Tuple[Check, ...]) -> List[int]:
    """Required first, then the rest. That is the order ``plan`` runs."""
    required = [index for index, check in enumerate(checks) if isinstance(check, Required)]
    rest = [index for index, check in enumerate(checks) if not isinstance(check, Required)]
    return required + rest


class ChecksBody(QWidget):
    def __init__(self, host: SectionHost) -> None:
        super().__init__(host.parent)
        self.setObjectName("formBuilder.checks")
        self.setMinimumWidth(0)
        names = getattr(QSizePolicy, "Policy", QSizePolicy)
        self.setSizePolicy(getattr(names, "Preferred"), getattr(names, "Minimum"))
        self._services = host.services
        self._realizer = host.realizer
        self._node: Optional[WidgetNode] = None
        self._env = None
        self._env_revision = -1
        self._checks: Tuple[Check, ...] = ()
        self._row_widgets: List[_CheckRow] = []
        self._editing: Optional[int] = None
        self._pending: Optional[Tuple[Check, ...]] = None
        self._focus_index: Optional[int] = None
        self._accent = ""
        overline = QWidget(self)
        overline.setObjectName("formBuilder.checks.overline")
        heading = QHBoxLayout(overline)
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(0)
        title = QLabel("CHECKS", overline)
        title.setObjectName("formBuilder.checks.title")
        heading.addWidget(title)
        heading.addStretch(1)
        self._rows_host = QWidget(self)
        self._rows_host.setObjectName("formBuilder.checks.rows")
        self._rows_host.setMinimumWidth(0)
        self._rows_layout = QVBoxLayout(self._rows_host)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(4)
        self._add = _AddButton("+ Add check \u25be", self)
        self._add.setObjectName("formBuilder.checks.add")
        self._add.setAutoDefault(False)
        names = getattr(QSizePolicy, "Policy", QSizePolicy)
        self._add.setSizePolicy(getattr(names, "Maximum"), getattr(names, "Fixed"))
        self._menu: Optional[QMenu] = None
        self._page: Optional[CheckPage] = None
        self._offer = CheckOffer(self)
        self._prompt = QWidget(self)
        self._prompt.setObjectName("formBuilder.checks.prompt")
        self._prompt.setMinimumWidth(0)
        self._prompt_text = QLabel(self._prompt)
        self._prompt_text.setObjectName("formBuilder.checks.promptText")
        _wrap(self._prompt_text)
        self._prompt_add = _EnterButton("Add label", self._prompt)
        self._prompt_add.setObjectName("formBuilder.checks.promptAdd")
        self._prompt_add.setAutoDefault(False)
        prompt_column = QVBoxLayout(self._prompt)
        prompt_column.setContentsMargins(0, 0, 0, 0)
        prompt_column.setSpacing(4)
        prompt_column.addWidget(self._prompt_text)
        prompt_column.addWidget(self._prompt_add, 0)
        self._when_line = _SentenceLink("Checked when: leaving the field", "How checks run", self)
        self._when_line.setObjectName("formBuilder.checks.whenLine")
        self._when = self._when_line.words
        self._when.setObjectName("formBuilder.checks.when")
        self._manual = self._when_line.link
        self._manual.setObjectName("formBuilder.checks.manual")
        self._manual.clicked.connect(self._open_manual)
        self._outline_line = _SentenceLink(
            "Fields that fail a check get no outline yet.",
            "Add the red outline style",
            self,
        )
        self._outline_line.setObjectName("formBuilder.checks.outlineLine")
        self._outline_line.words.setObjectName("formBuilder.checks.outlineWords")
        self._outline = self._outline_line.link
        self._outline.setObjectName("formBuilder.checks.outline")
        column = QVBoxLayout(self)
        self._column = column
        column.setContentsMargins(0, 4, 0, 4)
        column.setSpacing(4)
        column.addWidget(overline)
        column.addWidget(self._rows_host)
        column.addWidget(self._add, 0, _LEFT)
        column.addWidget(self._offer)
        column.addWidget(self._prompt)
        column.addWidget(self._when_line)
        column.addWidget(self._outline_line)
        self._rows_host.hide()
        self._offer.hide()
        self._prompt.hide()
        self._outline_line.hide()
        self._outline_revision = -1
        self._outline_show = False
        self._offer.set_handlers(self._accept_label, self._skip_label)
        self._add.clicked.connect(self._open_menu)
        self._prompt_add.clicked.connect(self._add_label_only)
        self._outline.clicked.connect(self._add_outline)
        # A focusable child, shown while Behavior is not the current tab, pulls
        # focus off the outline. A timer then lands on the canvas. Stay out of
        # the focus chain until this section is actually on screen.
        _quiet(self)

    def apply_colors(self, panel: str, text: str) -> None:
        chrome = self._services.chrome
        self._accent = chrome.accent or text
        edge = edge_on(chrome, panel)
        focus = chrome.focus_width if chrome.focus_width else 1
        ink = link_ink(chrome)
        self.setStyleSheet(
            "QWidget#formBuilder\\.checks { background: %s; color: %s; }"
            "QLabel { color: %s; background: transparent; }"
            % (panel, text, text)
        )
        # Same action chrome as the summary and "+ Then…" buttons: a left-aligned
        # control that hugs its words, not a bar across the section.
        self._add.setStyleSheet(
            "QPushButton { color: %s; background: %s; border: 1px solid %s;"
            " border-radius: 4px; padding: 2px 8px; text-align: left; }"
            "QPushButton:focus { border: %dpx solid %s; }"
            % (text, chrome.input, edge, focus, chrome.accent)
        )
        link = (
            "QPushButton { color: %s; background: transparent; border: none; padding: 0; text-align: left;"
            " text-decoration: underline; }"
            "QPushButton:focus { border: %dpx solid %s; }"
            % (ink, focus, chrome.accent)
        )
        self._manual.setStyleSheet(link)
        self._outline.setStyleSheet(link)
        self._outline_line.words.setStyleSheet("color: %s; background: transparent;" % chrome.muted)
        if self._page is not None:
            self._page.set_chrome(chrome)
        self._paint_tags()

    def paint(self, inputs: SectionInputs) -> None:
        self._node = _selected(inputs)
        if self._node is None:
            self.discard_draft()
            self._checks = ()
            self._fill_rows()
            self._prompt.hide()
            self._sync_outline()
            self._arm_keys()
            return
        document = inputs.session.document
        if self._env is None or self._env_revision != document.revision:
            self._env = env_for(document, _window_facts(self), QtClassTable.shared())
            self._env_revision = document.revision
        if self._drafting():
            self._sync_outline()
            self._arm_keys()
            return
        self._checks = _stored(self._node)
        self._fill_rows()
        self._sync_prompt()
        self._sync_outline()
        self._arm_keys()

    def has_draft(self) -> bool:
        page = self._page
        return (page is not None and page.isVisible()) or self._offer.isVisible() or self._pending is not None

    def discard_draft(self) -> bool:
        if not self.has_draft():
            return False
        self._pending = None
        self._editing = None
        if self._page is not None:
            self._page.hide()
        self._offer.hide()
        self._sync_prompt()
        return True

    def _open_manual(self) -> None:
        from pathlib import Path

        from app.qt.QtWidgets import QDialog, QPlainTextEdit, QVBoxLayout
        from app.qt.qt_compat import exec_qt

        text = "Checks run when the person leaves the field."
        here = Path(__file__).resolve()
        for parent in here.parents:
            found = parent / "docs" / "form_builder" / "manual" / "checks.md"
            if found.is_file():
                text = found.read_text(encoding="utf-8")
                break
        dialog = QDialog(self)
        dialog.setWindowTitle("How checks run")
        dialog.setObjectName("formBuilder.checks.manualDialog")
        view = QPlainTextEdit(dialog)
        view.setObjectName("formBuilder.checks.manualText")
        view.setReadOnly(True)
        view.setPlainText(text)
        layout = QVBoxLayout(dialog)
        layout.addWidget(view)
        dialog.resize(480, 360)
        exec_qt(dialog)

    def _arm_keys(self) -> None:
        if not self.isVisible():
            return
        for widget in (self._add, self._manual, self._outline, self._prompt_add):
            _tab_stop(widget)
        offer = self._offer
        for name in ("formBuilder.checks.addLabel", "formBuilder.checks.notNow"):
            button = offer.findChild(QWidget, name)
            if button is not None:
                _tab_stop(button)
        for row in self._row_widgets:
            _tab_stop(row)

    def focus_first(self) -> None:
        if self._row_widgets:
            self._row_widgets[0].setFocus()
            return
        self._add.setFocus()

    def focus_check(self, index: int) -> None:
        for row in self._row_widgets:
            if row.index == index:
                row.setFocus()
                return
        self.focus_first()

    def move_check(self, index: int, delta: int) -> None:
        # ``index`` is the stored position. The row the person sees is run order,
        # and Required stays first because that is where the engine runs it.
        order = _run_order(self._checks)
        if index not in order or self._drafting():
            return
        place = order.index(index)
        other_place = place + delta
        if other_place < 0 or other_place >= len(order):
            return
        other = order[other_place]
        if isinstance(self._checks[index], Required) != isinstance(self._checks[other], Required):
            return
        items = list(self._checks)
        items[index], items[other] = items[other], items[index]
        moved = _run_order(tuple(items))
        self._focus_index = moved.index(other)
        self._write(tuple(items), "Move check")

    def remove_check(self, index: int) -> None:
        if index < 0 or index >= len(self._checks) or self._drafting():
            return
        order = _run_order(self._checks)
        place = order.index(index) if index in order else 0
        items = list(self._checks)
        del items[index]
        self._focus_index = place if place < len(items) else None
        self._write(tuple(items), "Remove check from %s" % self._display())
        if not items:
            self._add.setFocus()

    def edit_check(self, index: int) -> None:
        if index < 0 or index >= len(self._checks) or self._node is None:
            return
        self._editing = index
        self._ensure_page().show_edit(self._checks[index], self._context())

    def _open_menu(self) -> None:
        if self._drafting():
            self.discard_draft()
        menu = self._menu
        if menu is None:
            menu = QMenu(self)
            menu.setObjectName("formBuilder.checks.menu")
            menu.triggered.connect(self._chosen)
            self._menu = menu
        menu.clear()
        for item in offered_kinds(self._class_name(), self._kind_text()):
            action = menu.addAction(item.menu)
            action.setData(item.key)
        if not menu.actions():
            return
        menu.setActiveAction(menu.actions()[0])
        menu.popup(self._add.mapToGlobal(QPoint(0, self._add.height())))

    def _chosen(self, action: QAction) -> None:
        key = action.data()
        if not isinstance(key, str) or not key or self._node is None:
            return
        self._editing = None
        self._ensure_page().show_new(key, self._context())

    def _commit_page(self) -> None:
        page = self._page
        check = None if page is None else page.build()
        node = self._node
        if check is None or node is None:
            return
        editing = self._editing
        if editing is None and not self._checks and not self._has_label():
            # The offer chooses the commands before the write, so the check and
            # the label share one undo step instead of "Set checks".
            self._pending = self._checks + (check,)
            if page is not None:
                page.hide()
            self._editing = None
            self._prompt.hide()
            self._offer.show()
            self._offer.focus_add()
            return
        if page is not None:
            page.hide()
        self._editing = None
        if editing is None:
            self._write(self._checks + (check,), "Add check to %s" % self._display())
            self._add.setFocus()
            return
        current = list(self._checks)
        if editing < 0 or editing >= len(current):
            return
        current[editing] = check
        updated = tuple(current)
        if updated == self._checks:
            return
        self._write(updated, "Edit check on %s" % self._display())

    def _cancel_page(self) -> None:
        self._editing = None
        if self._page is not None:
            self._page.hide()

    def _ensure_page(self) -> CheckPage:
        page = self._page
        if page is not None:
            return page
        page = CheckPage(self)
        page.hide()
        page.set_handlers(self._commit_page, self._cancel_page)
        _quiet(page)
        index = self._column.indexOf(self._offer)
        self._column.insertWidget(index if index >= 0 else 0, page)
        chrome = self._services.chrome
        if chrome is not None:
            page.set_chrome(chrome)
        self._page = page
        return page

    def _accept_label(self) -> None:
        pending = self._pending
        if pending is None:
            return
        self._pending = None
        self._offer.hide()
        self._write(pending, "Add check to %s" % self._display(), with_label=True)
        self._add.setFocus()

    def _skip_label(self) -> None:
        pending = self._pending
        if pending is None:
            return
        self._pending = None
        self._offer.hide()
        self._write(pending, "Add check to %s" % self._display())
        self._add.setFocus()

    def _add_label_only(self) -> None:
        node = self._live()
        if node is None or self._has_label():
            return
        self._services.execute_all(
            "Add error label for %s" % self._display(),
            [AddErrorLabel(node.id)],
        )
        self._keep(node.id)
        self._node = self._live() or node
        self._sync_prompt()

    def _add_outline(self) -> None:
        root = self._services.session.document.root
        if not isinstance(root, WidgetNode):
            return
        current = ""
        value = root.value("styleSheet")
        if isinstance(value, StringValue):
            current = value.text
        if _SELECTOR in current:
            return
        text = current.rstrip()
        text = (text + "\n" + _OUTLINE) if text else _OUTLINE
        self._services.execute_all(
            "Add the red outline style",
            [SetProperty(root.id, "styleSheet", StringValue(text), undo_label="Add the red outline style")],
        )

    def _write(self, checks: Tuple[Check, ...], label: str, with_label: bool = False) -> bool:
        node = self._live()
        if node is None:
            return False
        commands = [SetChecks(node.id, checks)]
        if with_label:
            commands.append(AddErrorLabel(node.id))
        result = self._services.execute_all(label, commands)
        if isinstance(result, (Rejected, Dropped)):
            return False
        # Inserting the label selects it. The section stays on the field.
        self._keep(node.id)
        self._node = self._live() or node
        self._checks = _stored(self._node)
        self._fill_rows()
        self._sync_prompt()
        self._sync_outline()
        self._arm_keys()
        return True

    def _fill_rows(self) -> None:
        # Rebuilding drops keyboard focus onto Events. Same count: rewrite the rows.
        if len(self._row_widgets) != len(self._checks):
            while self._rows_layout.count():
                item = self._rows_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.hide()
                    widget.setParent(None)
                    widget.deleteLater()
            self._row_widgets = []
            for index in range(len(self._checks)):
                row = _CheckRow(self, index)
                self._rows_layout.addWidget(row)
                self._row_widgets.append(row)
        order = _run_order(self._checks)
        total = len(order)
        width = _words_width(self) if total else 0
        chrome = self._services.chrome
        muted = "color: %s; background: transparent;" % chrome.muted
        for place, stored in enumerate(order):
            check = self._checks[stored]
            row = self._row_widgets[place]
            row.index = stored
            row.words.setFixedWidth(width)
            row.message.setStyleSheet(muted)
            message = generated_message(
                self._class_name(),
                check,
                self._kind_text(),
                label=self._display(),
                object_name=self._object_name(),
            )
            native = writes_native(self._class_name(), (check,), self._kind_text())
            row.show_check(words_of(check), message, native, place + 1, total)
        self._rows_host.setVisible(bool(self._row_widgets))
        self._paint_tags()
        self._place_focus()

    def _place_focus(self) -> None:
        index = self._focus_index
        if index is None:
            return
        self._focus_index = None
        if 0 <= index < len(self._row_widgets):
            self._row_widgets[index].setFocus()

    def _sync_outline(self) -> None:
        # The line depends on every field, so a big form must not be walked on
        # every selection. A check edit moves the document revision.
        document = self._services.session.document
        revision = document.revision
        if revision != self._outline_revision:
            self._outline_revision = revision
            self._outline_show = self._form_has_check() and not self._has_outline()
        if self._outline_line.isVisible() != self._outline_show:
            self._outline_line.setVisible(self._outline_show)

    def _form_has_check(self) -> bool:
        for node in self._services.session.document.iter_widgets():
            value = node.value("cbcsValidate")
            if isinstance(value, StringValue) and value.text.strip():
                return True
        return False

    def _has_outline(self) -> bool:
        root = self._services.session.document.root
        if not isinstance(root, WidgetNode):
            return False
        value = root.value("styleSheet")
        return isinstance(value, StringValue) and _SELECTOR in value.text

    def _sync_prompt(self) -> None:
        show = bool(self._checks) and not self._has_label() and self._pending is None and not self._offer.isVisible()
        self._prompt.setVisible(show)
        if show:
            self._prompt_text.setText(
                "%s's messages show only as a tooltip. Add a label under the field?" % self._display()
            )

    def _paint_tags(self) -> None:
        if not self._accent:
            return
        style = "color: %s; background: transparent;" % self._accent
        for row in self._row_widgets:
            row.qt.setStyleSheet(style)

    def _drafting(self) -> bool:
        page = self._page
        return (page is not None and page.isVisible()) or self._offer.isVisible() or self._pending is not None

    def _context(self) -> SimpleNamespace:
        return SimpleNamespace(
            class_name=self._class_name(),
            kind=self._kind_text(),
            label=self._display(),
            object_name=self._object_name(),
            env=self._env,
            reader=self._reader(),
            chrome=self._services.chrome,
        )

    def _keep(self, owner: object) -> None:
        selection = self._services.session.selection
        if selection.state.ids == (owner,):
            return
        selection.set((owner,), source=SelectionSource.INSPECTOR)  # type: ignore[arg-type]

    def _display(self) -> str:
        name = self._object_name()
        env = self._env
        if env is not None and name:
            facts = env.widgets.get(name)
            if facts is not None and facts.display:
                return str(facts.display)
        return name

    def _object_name(self) -> str:
        node = self._node
        return node.object_name if node is not None and node.object_name else ""

    def _class_name(self) -> str:
        node = self._node
        if node is None:
            return ""
        return (node.class_name or "").rsplit(".", 1)[-1]

    def _kind_text(self) -> str:
        node = self._node
        if node is None:
            return ""
        return kind_text(node)

    def _has_label(self) -> bool:
        node = self._live() or self._node
        if node is None:
            return False
        value = node.value("cbcsErrorLabel")
        return isinstance(value, StringValue) and bool(value.text.strip())

    def _live(self) -> Optional[WidgetNode]:
        node = self._node
        if node is None:
            return None
        found = self._services.session.document.get(node.id)
        if isinstance(found, WidgetNode):
            return found
        return None

    def _reader(self) -> SimpleNamespace:
        env = self._env
        values = {}
        if env is not None:
            named = getattr(self._realizer, "widget_named", None)
            for name in env.widgets:
                widget = named(name) if callable(named) else None
                if widget is not None:
                    values[name] = widget
        return SimpleNamespace(**values)


def _stored(node: WidgetNode) -> Tuple[Check, ...]:
    value = node.value("cbcsValidate")
    if not isinstance(value, StringValue) or not value.text.strip():
        return ()
    read = read_checks(value.text)
    if read.error is not None:
        return ()
    return read.checks


def _selected(inputs: SectionInputs) -> Optional[WidgetNode]:
    view = inputs.view
    if not isinstance(view, OneBehavior) or not view.sender_name:
        return None
    found = inputs.session.document.by_name(view.sender_name)
    if not found:
        return None
    node = inputs.session.document.node(found[0])
    if isinstance(node, WidgetNode):
        return node
    return None


def _window_facts(widget: QWidget) -> object:
    current: Optional[QWidget] = widget
    surface = None
    while current is not None:
        if callable(getattr(current, "toggle_source_view", None)):
            surface = current
            break
        current = current.parentWidget()
    if surface is None:
        return None
    try:
        from app.features.form_builder.qtside.pickers import method_actions

        read = getattr(method_actions(), "reading", None)
        found = read(surface) if callable(read) else None
    except Exception:
        return None
    if found is None or getattr(found, "status", "") != "ok":
        return None
    return getattr(found, "facts", None)


def _create(host: SectionHost) -> QWidget:
    return ChecksBody(host)


def _applies(inputs: SectionInputs) -> bool:
    return _selected(inputs) is not None


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if add is None:
        return
    add(BehaviorSection("checks", 20, _create, applies=_applies))
