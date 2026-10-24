"""Size group. Paints ``project`` and commits ``plan`` in one ``host.run``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.sizing import (
    QT_MAX,
    Axis,
    AxisMode,
    AxisView,
    Fill,
    Fixed,
    Hug,
    LimitKind,
    LimitView,
    MixedLimit,
    MixedMark,
    Outlined,
    Pixels,
    ResetLimits,
    ResetPolicy,
    SetLimit,
    SetShare,
    SetWord,
    ShareView,
    SizeEdit,
    SizeFacts,
    SizePanel,
    Word,
    edit_label,
    plan,
    project,
    qt_policy_text,
    why_lines,
)
from app.features.form_builder.qtside.inspector.api import (
    MIXED_TEXT,
    NOT_SET_TEXT,
    GroupHost,
    GroupId,
    OpenRow,
    Registrar,
    Row,
    set_style_flag,
)
from app.features.form_builder.qtside.sizing_live import find_realizer, measure, selection_facts
from app.features.form_builder.qtside.realize.api import Realizer
from app.qt.QtCore import QEvent, QObject, Qt
from app.qt.QtGui import QKeyEvent
from app.qt.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import enum_value

_TIPS = {
    "Hug": "As big as its content needs, and no bigger.",
    "Fill": "Takes the spare room the layout gives it.",
    "Fixed": "Exactly this many pixels.",
}
_WORDS: Tuple[Word, ...] = ("Hug", "Fill", "Fixed")
_LABEL_WIDTH = 104
_SHARE_HIGH = 1000000


class _Mark:
    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return self.name


_UNSET = _Mark("unset")
_MIXED = _Mark("mixed")


class _PixelBox(QSpinBox):
    """Empty is -1 so ``specialValueText`` can show the em dash and 0 stays a value."""

    def __init__(
        self,
        parent: QWidget,
        *,
        blankable: bool,
        high: int,
        access: str,
        on_commit: object,
    ) -> None:
        super().__init__(parent)
        self._blankable = blankable
        self._high = high
        self._access = access
        self._on_commit = on_commit
        self._edit: Optional[QLineEdit] = None
        self._guard = False
        self._shown_px: Optional[int] = None
        self._shown_mixed = False
        self._shown_text = ""
        self._last: object = _UNSET
        self.blockSignals(True)
        self.setKeyboardTracking(False)
        self.setFocusPolicy(Qt.StrongFocus)
        if blankable:
            self.setRange(-1, high)
            self.setSpecialValueText(NOT_SET_TEXT)
            self.setValue(-1)
            self._last = _UNSET
        else:
            self.setRange(0, high)
            self.setValue(0)
            self._last = 0
        self.blockSignals(False)
        self.valueChanged.connect(self._on_value)
        self.setAccessibleName(access)
        self._bind_line()

    def show_number(self, px: Optional[int], mixed: bool) -> None:
        self._guard = True
        self.blockSignals(True)
        if mixed:
            self.setRange(-1, self._high)
            self.setSpecialValueText(MIXED_TEXT)
            self.setValue(-1)
            token: object = _MIXED
            shown: Optional[int] = None
        elif px is None and self._blankable:
            self.setRange(-1, self._high)
            self.setSpecialValueText(NOT_SET_TEXT)
            self.setValue(-1)
            token = _UNSET
            shown = None
        else:
            shown = 0 if px is None else int(px)
            if shown < 0:
                shown = 0
            if shown > self._high:
                shown = self._high
            if self._blankable:
                self.setRange(-1, self._high)
                self.setSpecialValueText(NOT_SET_TEXT)
            else:
                self.setRange(0, self._high)
                self.setSpecialValueText("")
            self.setValue(shown)
            token = shown
        self._bind_line()
        edit = self._edit
        if edit is not None and self._blankable:
            edit.setPlaceholderText(NOT_SET_TEXT)
        self._shown_px = shown
        self._shown_mixed = mixed
        self._shown_text = "" if edit is None else edit.text()
        self._last = token
        self.blockSignals(False)
        self._guard = False

    def is_dirty(self) -> bool:
        edit = self._edit if self._edit is not None else self.lineEdit()
        if edit is None:
            return False
        return edit.text() != self._shown_text

    def revert(self) -> None:
        self.show_number(self._shown_px, self._shown_mixed)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self._edit and self._blankable and not self._guard:
            if event.type() == QEvent.KeyPress and isinstance(event, QKeyEvent) and _is_enter(event):
                if self._edit is not None and self._edit.text().strip() == "":
                    self._clear()
                    return True
            if event.type() == QEvent.FocusOut and self._edit is not None and self._edit.text().strip() == "":
                self._clear()
        return super().eventFilter(watched, event)

    def _bind_line(self) -> None:
        edit = self.lineEdit()
        if edit is None:
            return
        if edit is not self._edit:
            if self._edit is not None:
                self._edit.removeEventFilter(self)
            self._edit = edit
            edit.installEventFilter(self)
        if self._access:
            edit.setAccessibleName(self._access)

    def _on_value(self, number: int) -> None:
        if self._guard:
            return
        if number < 0:
            token: object = _MIXED if self.specialValueText() == MIXED_TEXT else _UNSET
        else:
            token = int(number)
        self._emit(token)

    def _clear(self) -> None:
        if self._guard or self._last is _UNSET:
            return
        self._guard = True
        self.blockSignals(True)
        self.setRange(-1, self._high)
        self.setSpecialValueText(NOT_SET_TEXT)
        self.setValue(-1)
        if self._edit is not None:
            self._edit.setText(NOT_SET_TEXT)
        self.blockSignals(False)
        self._guard = False
        self._emit(_UNSET)

    def _emit(self, token: object) -> None:
        if token == self._last:
            return
        self._last = token
        if token is _MIXED:
            return
        commit = self._on_commit
        if not callable(commit):
            return
        if token is _UNSET:
            commit(None)
            return
        commit(int(token))


class _RowBox(QWidget):
    def __init__(self, parent: QWidget, title: str, reset_name: str) -> None:
        super().__init__(parent)
        self.hovered = False
        self.changed = False
        self.bar = QFrame(self)
        self.bar.setObjectName("formBuilder.rowChanged")
        self.bar.setFixedWidth(2)
        self.bar.setMinimumHeight(18)
        set_style_flag(self.bar, "fbChanged", "false")
        self.label = QLabel(title, self)
        self.label.setWordWrap(True)
        self.label.setFixedWidth(_LABEL_WIDTH)
        self.controls = QWidget(self)
        self.controls_layout = QHBoxLayout(self.controls)
        self.controls_layout.setContentsMargins(0, 0, 0, 0)
        self.controls_layout.setSpacing(4)
        self.reset = _reset_button(self, reset_name)
        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        line.addWidget(self.bar)
        line.addWidget(self.label)
        line.addWidget(self.controls, 1)
        line.addWidget(self.reset)
        self.caption = QLabel(self)
        self.caption.setWordWrap(True)
        self.caption.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(2)
        layout.addLayout(line)
        layout.addWidget(self.caption)

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802
        self.hovered = True
        self.sync(QApplication.focusWidget())
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        self.hovered = False
        self.sync(QApplication.focusWidget())
        super().leaveEvent(event)

    def set_changed(self, changed: bool) -> None:
        self.changed = changed
        flag = "true" if changed else "false"
        set_style_flag(self.bar, "fbChanged", flag)
        set_style_flag(self.label, "fbChanged", flag)
        self.sync(QApplication.focusWidget())

    def set_caption(self, text: str, mixed: bool) -> None:
        self.caption.setText(text)
        _rename(self.caption, "formBuilder.rowMixed" if mixed else "formBuilder.rowDefault")
        self.caption.setVisible(bool(text))

    def sync(self, focus: Optional[QWidget]) -> None:
        inside = self.hovered or (focus is not None and (focus is self or self.isAncestorOf(focus)))
        self.reset.setVisible(self.changed and inside)


@dataclass
class _Words:
    row: _RowBox
    buttons: Dict[Word, QToolButton]
    group: QButtonGroup
    spin: _PixelBox
    unit: QLabel


@dataclass
class _ShareRow:
    row: _RowBox
    spin: _PixelBox


@dataclass
class _Limits:
    row: _RowBox
    width: _PixelBox
    height: _PixelBox
    times: QLabel


class SizeGroup:
    def __init__(self, host: GroupHost, parent: QWidget) -> None:
        self._host = host
        self._facts: Tuple[SizeFacts, ...] = ()
        self._panel: Optional[SizePanel] = None
        self._widget: Optional[QWidget] = None
        self._realizer: Optional[Realizer] = None
        self._painting = False
        self._dead = False
        self._app: Optional[QApplication] = None
        self._spins: List[_PixelBox] = []
        self._root = QWidget(parent)
        self._root.setObjectName("formBuilder.sizeGroup")
        layout = QVBoxLayout(self._root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self._width = self._word_row("width", "Width")
        self._share_width = self._share_row("width")
        self._height = self._word_row("height", "Height")
        self._share_height = self._share_row("height")
        self._at_least = self._limit_row("minimum", "At least")
        self._at_most = self._limit_row("maximum", "At most")
        self._why = QLabel(self._root)
        self._why.setObjectName("formBuilder.sizeWhy")
        self._why.setAccessibleName("Why is it this size?")
        self._why.setWordWrap(True)
        self._qt = QLabel(self._root)
        self._qt.setObjectName("formBuilder.rowQtName")
        self._qt.hide()
        for block in (
            self._width.row,
            self._share_width.row,
            self._height.row,
            self._share_height.row,
            self._at_least.row,
            self._at_most.row,
        ):
            layout.addWidget(block)
        layout.addWidget(self._why)
        layout.addWidget(self._qt)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            self._app = app
            app.focusChanged.connect(self._on_focus)
        self._root.destroyed.connect(self._unhook)

    @property
    def widget(self) -> QWidget:
        return self._root

    def show(self, rows: Tuple[Row, ...]) -> None:
        self._painting = True
        try:
            self._show_rows(rows)
        finally:
            self._painting = False
            self._sync_resets()

    def retint(self, show_qt: bool) -> None:
        self._qt.setVisible(bool(show_qt))

    def is_dirty(self) -> bool:
        return any(spin.is_dirty() for spin in self._spins)

    def revert(self) -> None:
        for spin in self._spins:
            spin.revert()

    def _show_rows(self, rows: Tuple[Row, ...]) -> None:
        keys = {row.key for row in rows}
        owners = _owners(rows)
        realizer = self._cached_realizer()
        self._facts = ()
        self._panel = None
        self._widget = None
        if realizer is None or not owners:
            self._why.setText("")
            self._qt.clear()
            return
        facts = selection_facts(self._host.document, owners, realizer)
        if not facts:
            self._why.setText("")
            self._qt.clear()
            return
        panel = project(facts)
        self._facts = facts
        self._panel = panel
        widget = realizer.widget_for(panel.why_owner)
        self._widget = widget
        fact = _fact_for(facts, panel.why_owner)
        if widget is None or fact is None:
            self._why.setText("")
            self._qt.clear()
        else:
            live = measure(widget, fact)
            self._why.setText("\n".join(line.text for line in why_lines(panel, live)))
            self._qt.setText(qt_policy_text(live))
        policy = "sizePolicy" in keys
        self._paint_axis(self._width, panel.horizontal, policy)
        self._paint_share(self._share_width, panel.share_width, policy)
        self._paint_axis(self._height, panel.vertical, policy)
        self._paint_share(self._share_height, panel.share_height, policy)
        self._paint_limits(
            self._at_least,
            panel.at_least,
            panel.horizontal.hide_limits,
            panel.vertical.hide_limits,
            "minimumSize" in keys,
        )
        self._paint_limits(
            self._at_most,
            panel.at_most,
            panel.horizontal.hide_limits,
            panel.vertical.hide_limits,
            "maximumSize" in keys,
        )

    def _paint_axis(self, block: _Words, view: AxisView, shown: bool) -> None:
        block.row.setVisible(shown)
        if not shown:
            return
        mode = view.mode
        outlined = mode.word if isinstance(mode, Outlined) else None
        stored = _stored_word(mode)
        block.group.setExclusive(False)
        for word, button in block.buttons.items():
            button.blockSignals(True)
            button.setChecked(stored == word)
            button.blockSignals(False)
            set_style_flag(button, "fbOutlined", "true" if outlined == word else "false")
        block.group.setExclusive(stored is not None)
        fixed = isinstance(mode, Fixed)
        block.spin.setVisible(fixed)
        block.unit.setVisible(fixed)
        block.spin.show_number(mode.px if fixed else 0, False)
        block.row.set_changed(view.changed)
        block.row.set_caption(view.caption, isinstance(mode, MixedMark))

    def _paint_share(self, block: _ShareRow, view: ShareView, policy: bool) -> None:
        visible = policy and view.shown
        block.row.setVisible(visible)
        block.spin.show_number(0 if view.factor is None else view.factor, view.mixed)
        block.row.set_changed(view.changed)
        block.row.set_caption(view.caption, False)

    def _paint_limits(
        self,
        block: _Limits,
        view: LimitView,
        hide_width: bool,
        hide_height: bool,
        shown: bool,
    ) -> None:
        block.row.setVisible(shown and not (hide_width and hide_height))
        block.width.setVisible(not hide_width)
        block.height.setVisible(not hide_height)
        block.times.setVisible(not hide_width and not hide_height)
        _paint_cell(block.width, view.width)
        _paint_cell(block.height, view.height)
        block.row.set_changed(view.changed)

    def _pick(self, axis: Axis, word: Word) -> None:
        panel = self._panel
        if self._painting or panel is None:
            return
        mode = panel.horizontal.mode if axis == "width" else panel.vertical.mode
        if _stored_word(mode) == word:
            return
        px = self._live_px(axis) if word == "Fixed" else None
        self._run(SetWord(axis, word, px))

    def _commit_fixed(self, axis: Axis, px: Optional[int]) -> None:
        if px is None:
            return
        self._run(SetWord(axis, "Fixed", px))

    def _commit_share(self, axis: Axis, factor: Optional[int]) -> None:
        if factor is None:
            return
        self._run(SetShare(axis, factor))

    def _commit_limit(self, kind: LimitKind, axis: Axis, px: Optional[int]) -> None:
        self._run(SetLimit(kind, axis, px))

    def _reset_policy(self, axis: Axis) -> None:
        self._run(ResetPolicy(axis))

    def _reset_share(self, axis: Axis) -> None:
        self._run(SetShare(axis, None))

    def _reset_limits(self, kind: LimitKind) -> None:
        self._run(ResetLimits(kind))

    def _run(self, edit: SizeEdit) -> None:
        if self._painting or not self._facts:
            return
        commands = plan(self._facts, edit)
        if not commands:
            return
        self._host.run(edit_label(edit), commands)

    def _live_px(self, axis: Axis) -> int:
        widget = self._widget
        if widget is None:
            return 0
        if axis == "width":
            size, hint = widget.width(), widget.sizeHint().width()
        else:
            size, hint = widget.height(), widget.sizeHint().height()
        if size > 0:
            return int(size)
        if hint > 0:
            return int(hint)
        return 0

    def _cached_realizer(self) -> Optional[Realizer]:
        found = self._realizer
        if found is not None:
            return found
        found = find_realizer(self._root)
        if found is not None:
            self._realizer = found
        return found

    def _word_row(self, axis: Axis, title: str) -> _Words:
        row = _RowBox(self._root, title, "formBuilder.sizeReset.%s" % axis)
        row.reset.clicked.connect(lambda _checked=False, axis=axis: self._reset_policy(axis))
        group = QButtonGroup(row)
        group.setExclusive(True)
        buttons: Dict[Word, QToolButton] = {}
        for word in _WORDS:
            button = QToolButton(row.controls)
            button.setText(word)
            button.setToolTip(_TIPS[word])
            button.setCheckable(True)
            button.setAutoExclusive(False)
            button.setFocusPolicy(Qt.TabFocus)
            button.setAccessibleName("%s %s" % (word, axis))
            set_style_flag(button, "fbSegment", "true")
            set_style_flag(button, "fbOutlined", "false")
            button.clicked.connect(lambda _checked=False, axis=axis, word=word: self._pick(axis, word))
            group.addButton(button)
            row.controls_layout.addWidget(button)
            buttons[word] = button
        spin = self._spin(
            row.controls,
            blankable=False,
            high=QT_MAX,
            access="Fixed %s" % axis,
            on_commit=lambda px, axis=axis: self._commit_fixed(axis, px),
        )
        unit = QLabel("px", row.controls)
        spin.hide()
        unit.hide()
        row.controls_layout.addWidget(spin)
        row.controls_layout.addWidget(unit)
        return _Words(row, buttons, group, spin, unit)

    def _share_row(self, axis: Axis) -> _ShareRow:
        row = _RowBox(self._root, "Share", "formBuilder.sizeReset.share.%s" % axis)
        row.reset.clicked.connect(lambda _checked=False, axis=axis: self._reset_share(axis))
        spin = self._spin(
            row.controls,
            blankable=False,
            high=_SHARE_HIGH,
            access="Share of spare room",
            on_commit=lambda px, axis=axis: self._commit_share(axis, px),
        )
        row.controls_layout.addWidget(spin)
        row.hide()
        return _ShareRow(row, spin)

    def _limit_row(self, kind: LimitKind, title: str) -> _Limits:
        row = _RowBox(self._root, title, "formBuilder.sizeReset.%s" % kind)
        row.reset.clicked.connect(lambda _checked=False, kind=kind: self._reset_limits(kind))
        width = self._spin(
            row.controls,
            blankable=True,
            high=QT_MAX,
            access="%s width" % title,
            on_commit=lambda px, kind=kind: self._commit_limit(kind, "width", px),
        )
        height = self._spin(
            row.controls,
            blankable=True,
            high=QT_MAX,
            access="%s height" % title,
            on_commit=lambda px, kind=kind: self._commit_limit(kind, "height", px),
        )
        times = QLabel("\u00d7", row.controls)
        unit = QLabel("px", row.controls)
        row.controls_layout.addWidget(width)
        row.controls_layout.addWidget(times)
        row.controls_layout.addWidget(height)
        row.controls_layout.addWidget(unit)
        return _Limits(row, width, height, times)

    def _spin(
        self,
        parent: QWidget,
        *,
        blankable: bool,
        high: int,
        access: str,
        on_commit: object,
    ) -> _PixelBox:
        box = _PixelBox(parent, blankable=blankable, high=high, access=access, on_commit=on_commit)
        box.setSizePolicy(_horizontal_policy("Minimum"), _horizontal_policy("Fixed"))
        self._spins.append(box)
        return box

    def _on_focus(self, _old: object, _new: object) -> None:
        self._sync_resets()

    def _sync_resets(self) -> None:
        if self._dead:
            return
        focus = QApplication.focusWidget()
        for row in (
            self._width.row,
            self._share_width.row,
            self._height.row,
            self._share_height.row,
            self._at_least.row,
            self._at_most.row,
        ):
            row.sync(focus)

    def _unhook(self, *_args: object) -> None:
        self._dead = True
        app = self._app
        self._app = None
        if app is None:
            return
        try:
            app.focusChanged.disconnect(self._on_focus)
        except (RuntimeError, TypeError):
            return


def register(registrar: Registrar) -> None:
    registrar.group_body(GroupId.SIZE, SizeGroup)


def _owners(rows: Tuple[Row, ...]) -> Tuple[NodeId, ...]:
    for row in rows:
        if not isinstance(row, OpenRow):
            continue
        owners = getattr(row.write, "owners", None)
        if isinstance(owners, tuple) and owners:
            return owners
    return ()


def _fact_for(facts: Tuple[SizeFacts, ...], owner: NodeId) -> Optional[SizeFacts]:
    for fact in facts:
        if fact.owner == owner:
            return fact
    return None


def _stored_word(mode: AxisMode) -> Optional[Word]:
    if isinstance(mode, Hug):
        return "Hug"
    if isinstance(mode, Fill):
        return "Fill"
    if isinstance(mode, Fixed):
        return "Fixed"
    return None


def _paint_cell(spin: _PixelBox, cell: object) -> None:
    if isinstance(cell, Pixels):
        spin.show_number(cell.px, False)
        return
    spin.show_number(None, isinstance(cell, MixedLimit))


def _reset_button(parent: QWidget, name: str) -> QToolButton:
    button = QToolButton(parent)
    button.setObjectName(name)
    button.setProperty("fbFlat", "true")
    button.setText("\u21ba")
    button.setFixedSize(16, 16)
    button.setAccessibleName("Reset")
    button.setToolTip("Reset: remove this property from the file")
    button.hide()
    return button


def _rename(label: QLabel, name: str) -> None:
    if label.objectName() == name:
        return
    label.setObjectName(name)
    style = label.style()
    style.unpolish(label)
    style.polish(label)


def _is_enter(event: QKeyEvent) -> bool:
    key = enum_value(event.key())
    return key == enum_value(Qt.Key_Return) or key == enum_value(Qt.Key_Enter)


def _horizontal_policy(name: str) -> QSizePolicy.Policy:
    policy = getattr(QSizePolicy, "Policy", QSizePolicy)
    found = getattr(policy, name, None)
    if found is None:
        return QSizePolicy.Preferred
    return found
