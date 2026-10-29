"""Size, point, rect and size policy. Below 300 px, or at larger text, each field is on its own line."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple, Union

from app.features.form_builder.engine.ui4.values import (
    PointFValue,
    PointValue,
    RectFValue,
    RectValue,
    SizeFValue,
    SizePolicyValue,
    SizeValue,
    Value,
)
from app.features.form_builder.qtside.inspector.api import (
    EditorHost,
    EditorKey,
    EditSession,
    Mixed,
    Registrar,
    RowValue,
    Unset,
    ValueSpec,
    Written,
    mark,
)
from app.features.form_builder.qtside.inspector.editors._editor_kit import (
    change_label,
    name_part,
    payload,
)
from app.features.form_builder.qtside.inspector.editors._enum_words import POLICY_HELP, POLICY_ORDER, friendly
from app.features.form_builder.qtside.inspector.editors._number_box import IntBox, RealBox, _SpinHooks
from app.features.form_builder.qtside.inspector.editors._popover import RowPopover, SummaryButton
from app.qt.QtCore import Qt
from app.qt.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

_PAIR = 300


def _pair_limit(widget: QWidget) -> int:
    """Side by side only while two fields fit. Larger text stacks X and Y.

    The 300 px rule is the normal-text budget (UX-PED-002). At 200% a
    ``Height`` field is about twice as wide, so the budget grows with the font.
    """
    metrics = widget.fontMetrics()
    if metrics.height() <= 18:
        return _PAIR
    one = metrics.horizontalAdvance("Height") + metrics.height() * 5 + 24
    return max(_PAIR, one * 2 + 96)
_INT_RANGE = (-2147483648, 2147483647)
_SHARE = (0, 255)


class _Field:
    def __init__(self, key: str, title: str, box: QWidget, unit: str, parent: QWidget) -> None:
        self.key = key
        self.title = QLabel(title, parent)
        self.box = box
        self.unit = QLabel(unit, parent) if unit else None
        if self.unit is not None:
            self.unit.setFocusPolicy(getattr(getattr(Qt, "FocusPolicy", Qt), "NoFocus"))  # type: ignore[arg-type]


class _BoxEditor:
    """One spin per component. Repeated steps on one spin are one undo step."""

    def __init__(self, host: EditorHost, parent: QWidget, fields: Sequence[Tuple[str, str]], *, real: bool) -> None:
        self._host = host
        self._real = real
        self._root = QWidget(parent)
        self._grid = QGridLayout(self._root)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(6)
        self._grid.setVerticalSpacing(4)
        self._fields: List[_Field] = []
        self._session: Optional[EditSession] = None
        self._session_field = ""
        self._stacked = True
        self._mixed = False
        unit = "" if real else "px"
        for key, title in fields:
            hooks = _SpinHooks(
                lambda number, key=key: self._changed(key, number),
                self._host.invalid,
                lambda: self._host.invalid("Type a number, like 12."),
                lambda key=key: self._closed(key),
            )
            if real:
                box: QWidget = RealBox(self._root, hooks, places=2, strip=False)
            else:
                box = IntBox(_INT_RANGE[0], _INT_RANGE[1], self._root, hooks)
            self._fields.append(_Field(key, title, box, unit, self._root))
        self._apply(True)

    @property
    def widget(self) -> QWidget:
        return self._root

    def wants_stacked(self, width: int) -> bool:
        stacked = int(width) < _pair_limit(self._root)
        self._apply(stacked)
        return stacked

    def show(self, value: RowValue) -> None:
        mark(self._root, value)
        numbers = _components(value, [field.key for field in self._fields])
        mixed = isinstance(value, Mixed)
        self._mixed = mixed
        for index, field in enumerate(self._fields):
            name_part(field.box, self._host, field.key)
            if mixed or numbers is None:
                field.box.show_blank("Mixed" if mixed else "", can_reset=False)
            else:
                field.box.show_number(numbers[index], can_reset=False)

    def is_dirty(self) -> bool:
        return any(field.box.is_dirty() for field in self._fields)

    def _apply(self, stacked: bool) -> None:
        if stacked == self._stacked and self._grid.count():
            return
        self._stacked = stacked
        for field in self._fields:
            field.title.setParent(self._root)
            field.box.setParent(self._root)
            if field.unit is not None:
                field.unit.setParent(self._root)
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        columns = 1 if stacked else 2
        for index, field in enumerate(self._fields):
            row = index // columns
            column = index % columns
            line = QWidget(self._root)
            layout = QHBoxLayout(line)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)
            layout.addWidget(field.title, 0)
            layout.addWidget(field.box, 1)
            if field.unit is not None:
                layout.addWidget(field.unit, 0)
            self._grid.addWidget(line, row, column)

    def _changed(self, key: str, number: Union[int, float]) -> None:
        del number
        if self._session is None or self._session.closed or self._session_field != key:
            self._finish()
            self._session = self._host.begin_session(change_label(self._host.label))
            self._session_field = key
        self._write(self._session)

    def _closed(self, key: str) -> None:
        if self._session_field == key:
            self._finish()

    def _finish(self) -> None:
        if self._session is not None and not self._session.closed:
            self._session.close()
        self._session = None
        self._session_field = ""

    def _write(self, session: EditSession) -> None:
        # A Mixed value has no number to keep in the fields left empty, so
        # nothing is written until every field holds one.
        if self._mixed and any(_blank(field.box) for field in self._fields):
            return
        values = [_read(field.box) for field in self._fields]
        if any(item is None for item in values):
            return
        self._host.commit(_pack(self._real, [field.key for field in self._fields], values), session=session)


def _blank(box: QWidget) -> bool:
    is_blank = getattr(box, "is_blank", None)
    return bool(is_blank()) if callable(is_blank) else False


def _read(box: QWidget) -> Optional[float]:
    if isinstance(box, IntBox):
        return float(int(box.value()))
    if isinstance(box, RealBox):
        return float(box.value())
    return None


def _components(value: RowValue, keys: Sequence[str]) -> Optional[List[float]]:
    found = payload(value)
    if found is None:
        return None
    numbers = []
    for key in keys:
        raw = getattr(found, key, None)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return None
        numbers.append(float(raw))
    return numbers


def _pack(real: bool, keys: Sequence[str], values: Sequence[Optional[float]]) -> Value:
    data = {key: (float(values[index]) if real else int(values[index] or 0)) for index, key in enumerate(keys)}
    if keys == ("x", "y") or list(keys) == ["x", "y"]:
        return PointFValue(data["x"], data["y"]) if real else PointValue(int(data["x"]), int(data["y"]))
    if "x" not in data:
        return SizeFValue(data["width"], data["height"]) if real else SizeValue(int(data["width"]), int(data["height"]))
    if real:
        return RectFValue(data["x"], data["y"], data["width"], data["height"])
    return RectValue(int(data["x"]), int(data["y"]), int(data["width"]), int(data["height"]))


class SizeEditor(_BoxEditor):
    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        super().__init__(
            host,
            parent,
            (("width", "Width"), ("height", "Height")),
            real=spec.element in (SizeFValue.ELEMENT, PointFValue.ELEMENT, RectFValue.ELEMENT),
        )


class PointEditor(_BoxEditor):
    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        super().__init__(
            host,
            parent,
            (("x", "X"), ("y", "Y")),
            real=spec.element in (PointFValue.ELEMENT, SizeFValue.ELEMENT, RectFValue.ELEMENT),
        )


class RectEditor(_BoxEditor):
    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        super().__init__(
            host,
            parent,
            (("x", "X"), ("y", "Y"), ("width", "Width"), ("height", "Height")),
            real=spec.element in (RectFValue.ELEMENT, PointFValue.ELEMENT, SizeFValue.ELEMENT),
        )


class SizePolicyEditor:
    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._button = SummaryButton(host.label or "Size policy", parent)
        self._button.set_opener(self._open)
        self._popover: Optional[RowPopover] = None
        self._horizontal: Optional[QComboBox] = None
        self._vertical: Optional[QComboBox] = None
        self._horizontal_share: Optional[IntBox] = None
        self._vertical_share: Optional[IntBox] = None
        self._resetting = False
        self._current = SizePolicyValue("Preferred", "Preferred", 0, 0)
        self._can_reset = False

    @property
    def widget(self) -> QWidget:
        return self._button

    def show(self, value: RowValue) -> None:
        self._button.set_row_label(self._host.label or "Size policy")
        policy = _policy(value)
        self._can_reset = isinstance(value, Written) or (
            isinstance(value, Unset) and value.default is not None
        )
        mark(self._button, value)
        if isinstance(value, Mixed):
            self._button.set_summary("Mixed")
            return
        if policy is None:
            # Never the previous selection's policy: a pooled editor outlives it.
            policy = SizePolicyValue("Preferred", "Preferred", 0, 0)
        self._current = policy
        self._button.set_summary(_policy_summary(policy))

    def _open(self) -> None:
        if self._popover is not None and not self._popover.closed:
            return
        popover = RowPopover(
            self._host.row_widget,
            self._host,
            row_label=self._host.label or "Size policy",
            session_label=change_label(self._host.label),
            qt_name=self._host.qt_name,
            anchor=self._button,
        )
        self._popover = popover
        body = popover.body()
        horizontal = _policy_combo(popover, self._host.qt_name)
        vertical = _policy_combo(popover, self._host.qt_name)
        help_h = _policy_caption(popover, self._host)
        help_v = _policy_caption(popover, self._host)
        horizontal.currentIndexChanged.connect(
            lambda _i: help_h.setText(POLICY_HELP.get(_combo_policy(horizontal), ""))
        )
        vertical.currentIndexChanged.connect(
            lambda _i: help_v.setText(POLICY_HELP.get(_combo_policy(vertical), ""))
        )
        self._horizontal = horizontal
        self._vertical = vertical
        hooks_h = _SpinHooks(lambda _n: self._commit(), self._host.invalid, lambda: None, lambda: None)
        hooks_v = _SpinHooks(lambda _n: self._commit(), self._host.invalid, lambda: None, lambda: None)
        horizontal_share = IntBox(_SHARE[0], _SHARE[1], popover, hooks_h)
        vertical_share = IntBox(_SHARE[0], _SHARE[1], popover, hooks_v)
        self._horizontal_share = horizontal_share
        self._vertical_share = vertical_share
        policy = self._current
        _select_policy(horizontal, policy.hsizetype)
        _select_policy(vertical, policy.vsizetype)
        help_h.setText(POLICY_HELP.get(_combo_policy(horizontal), ""))
        help_v.setText(POLICY_HELP.get(_combo_policy(vertical), ""))
        horizontal_share.show_number(policy.horstretch, can_reset=False)
        vertical_share.show_number(policy.verstretch, can_reset=False)
        horizontal.currentIndexChanged.connect(lambda _i: self._commit())
        vertical.currentIndexChanged.connect(lambda _i: self._commit())
        body.addWidget(_policy_block(popover, "Horizontal", horizontal, help_h))
        body.addWidget(_policy_block(popover, "Vertical", vertical, help_v))
        body.addWidget(_labeled(popover, "Horizontal share", horizontal_share))
        body.addWidget(_labeled(popover, "Vertical share", vertical_share))
        name_part(horizontal, self._host, "horizontal")
        name_part(vertical, self._host, "vertical")
        name_part(horizontal_share, self._host, "horizontal share")
        name_part(vertical_share, self._host, "vertical share")
        if self._can_reset:
            popover.set_reset(self._reset)
        popover.open_popover()

    def _commit(self) -> None:
        if self._resetting or self._popover is None or self._horizontal is None:
            return
        value = SizePolicyValue(
            _combo_policy(self._horizontal),
            _combo_policy(self._vertical) if self._vertical is not None else "Preferred",
            int(self._horizontal_share.value()) if self._horizontal_share is not None else 0,
            int(self._vertical_share.value()) if self._vertical_share is not None else 0,
        )
        self._host.commit(value, session=self._popover.session)
        self._button.set_summary(_policy_summary(value))

    def _reset(self) -> None:
        self._resetting = True
        popover = self._popover
        if popover is not None and popover.session.has_step():
            popover.session.revert()
        self._host.reset()
        self._resetting = False


def _policy_combo(parent: QWidget, prop_name: str) -> QComboBox:
    combo = QComboBox(parent)
    for name in POLICY_ORDER:
        combo.addItem(friendly("", prop_name, name))
        index = combo.count() - 1
        combo.setItemData(index, name)
        combo.setItemData(index, POLICY_HELP.get(name, ""), Qt.ToolTipRole)  # type: ignore[attr-defined]
    return combo


def _select_policy(combo: QComboBox, name: str) -> None:
    for index in range(combo.count()):
        if combo.itemData(index) == name:
            combo.setCurrentIndex(index)
            return
    combo.insertItem(0, "%s (kept as is)" % name)
    combo.setItemData(0, name)
    combo.setCurrentIndex(0)


def _combo_policy(combo: Optional[QComboBox]) -> str:
    if combo is None:
        return "Preferred"
    data = combo.currentData()
    if isinstance(data, str) and data:
        return data
    return "Preferred"


def _policy_caption(parent: QWidget, host: EditorHost) -> QLabel:
    caption = QLabel(parent)
    caption.setObjectName("formBuilder.policyHelp")
    caption.setWordWrap(True)
    caption.setStyleSheet("color: %s;" % host.chrome.faint)
    return caption


def _policy_block(parent: QWidget, title: str, combo: QWidget, caption: QLabel) -> QWidget:
    block = QWidget(parent)
    layout = QVBoxLayout(block)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    layout.addWidget(_labeled(block, title, combo))
    layout.addWidget(caption)
    return block


def _labeled(parent: QWidget, title: str, field: QWidget) -> QWidget:
    row = QWidget(parent)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    layout.addWidget(QLabel(title, row), 0)
    layout.addWidget(field, 1)
    return row


def _policy(value: RowValue) -> Optional[SizePolicyValue]:
    found = payload(value)
    if isinstance(found, SizePolicyValue):
        return found
    return None


def _policy_summary(policy: SizePolicyValue) -> str:
    text = "%s × %s" % (friendly("", "sizePolicy", policy.hsizetype), friendly("", "sizePolicy", policy.vsizetype))
    if policy.horstretch or policy.verstretch:
        text += " · share %d : %d" % (policy.horstretch, policy.verstretch)
    return text


def register(registrar: Registrar) -> None:
    registrar.editor(EditorKey(SizeValue.ELEMENT), SizeEditor, baseline=True)
    registrar.editor(EditorKey(SizeFValue.ELEMENT), SizeEditor, baseline=True)
    registrar.editor(EditorKey(PointValue.ELEMENT), PointEditor, baseline=True)
    registrar.editor(EditorKey(PointFValue.ELEMENT), PointEditor, baseline=True)
    registrar.editor(EditorKey(RectValue.ELEMENT), RectEditor, baseline=True)
    registrar.editor(EditorKey(RectFValue.ELEMENT), RectEditor, baseline=True)
    registrar.editor(EditorKey(SizePolicyValue.ELEMENT), SizePolicyEditor, baseline=True)
