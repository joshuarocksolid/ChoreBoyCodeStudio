"""A Value rule locks the property it writes. A when-rule adds a link beside the design value."""

from __future__ import annotations

from dataclasses import replace
from typing import Optional, Tuple

from app.features.form_builder.engine.logic.events_catalog import class_chain
from app.features.form_builder.engine.logic.formula.types import lookup_spec
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.values import BoolValue
from app.features.form_builder.qtside.inspector.api import (
    EditorHost,
    EditorKey,
    GroupId,
    Mixed,
    OpenRow,
    Prop,
    Registrar,
    RowSpec,
    Unset,
    Written,
    mark,
)
from app.qt.QtCore import Qt
from app.qt.QtWidgets import (
    QBoxLayout,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

_WRITE_PROP = {
    "setText(formatted)": "text",
    "setPlainText": "plainText",
    "setValue": "value",
    "setValue(float(x))": "value",
    "setChecked": "checked",
}
_WHEN = {
    "enabled": "cbcsEnabledWhen",
    "visible": "cbcsVisibleWhen",
    "readOnly": "cbcsReadOnlyWhen",
}
class _Silent:
    def __init__(self, owners: Tuple[NodeId, ...]) -> None:
        self.owners = owners

    def edit(self, value: object, token: Optional[str]) -> Tuple[object, ...]:
        del value, token
        return ()

    def reset(self) -> Tuple[object, ...]:
        return ()


class _Box(QWidget):
    def __init__(self, owner: object, parent: QWidget) -> None:
        super().__init__(parent)
        self._owner = owner
        self.setMinimumWidth(0)

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        reflow = getattr(self._owner, "reflow", None)
        if callable(reflow):
            reflow()


class CalculatedEditor:
    def __init__(self, spec: object, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._formula = ""
        self._root = _Box(self, parent)
        self._root.setObjectName("formBuilder.calculated")
        layout = QVBoxLayout(self._root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self._layout = layout
        self._label = QLabel(self._root)
        self._label.setObjectName("formBuilder.calculatedLabel")
        self._label.setMinimumWidth(0)
        self._label.setWordWrap(True)
        names = getattr(QSizePolicy, "Policy", QSizePolicy)
        self._label.setSizePolicy(getattr(names, "Preferred"), getattr(names, "Minimum"))
        self._button = QPushButton("Edit rule", self._root)
        self._button.setObjectName("formBuilder.calculatedEdit")
        self._button.setFlat(True)
        self._button.setAutoDefault(False)
        self._button.setDefault(False)
        self._button.setMinimumWidth(0)
        self._button.clicked.connect(self._edit)
        layout.addWidget(self._label)
        layout.addWidget(self._button)
        self._root.setSizePolicy(getattr(names, "Preferred"), getattr(names, "Minimum"))

    @property
    def widget(self) -> QWidget:
        return self._root

    def show(self, value: object) -> None:
        del value
        self._formula = _stored(self._node(), "cbcsValue")
        self._paint()
        self.reflow()

    def is_dirty(self) -> bool:
        return False

    def wants_stacked(self, width: int) -> bool:
        self.reflow()
        return self._label.sizeHint().width() > max(0, int(width) - 96)

    def reflow(self) -> None:
        full = "Calculated: %s" % self._formula
        if self._label.text() != full:
            self._label.setText(full)
        if self._label.toolTip() != full:
            self._label.setToolTip(full)
        width = self._label.width()
        if width < 8:
            width = max(self._root.width(), self._label.sizeHint().width(), 1)
        text_height = max(self._label.heightForWidth(width), self._label.fontMetrics().height())
        if self._label.minimumHeight() != text_height:
            self._label.setMinimumHeight(text_height)
        height = text_height + self._button.sizeHint().height() + self._layout.spacing()
        if self._root.minimumHeight() != height:
            self._root.setMinimumHeight(height)
        _activate(self._root)

    def _edit(self) -> None:
        from app.features.form_builder.qtside.inspector.behavior_ext.state import open_state_row

        inspector = _inspector(self._root)
        if inspector is not None:
            open_state_row(inspector, "cbcsValue")

    def _paint(self) -> None:
        chrome = self._host.chrome
        focus = chrome.focus_width if chrome.focus_width > 0 else 1
        ink = chrome.accent or chrome.text
        self._label.setStyleSheet("color: %s; background: transparent;" % chrome.text)
        self._button.setStyleSheet(
            "QPushButton { color: %s; background: transparent; border: none; padding: 0 4px; text-align: left; }"
            "QPushButton:focus { border: %dpx solid %s; }" % (ink, focus, ink)
        )

    def _node(self) -> object:
        owners = self._host.owner_ids()
        if len(owners) != 1:
            return None
        return self._host.document().node(owners[0])


class RuleLinkEditor:
    def __init__(self, spec: object, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._root = _Box(self, parent)
        self._root.setObjectName("formBuilder.ruleLink")
        self._layout = QHBoxLayout(self._root)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self._box = QCheckBox(self._root)
        self._box.setText("")
        self._box.setMinimumWidth(0)
        self._box.clicked.connect(self._commit)
        self._link = QPushButton("rule", self._root)
        self._link.setObjectName("formBuilder.ruleLink.%s" % host.qt_name)
        self._link.setFlat(True)
        self._link.setAutoDefault(False)
        self._link.setDefault(False)
        self._link.setMinimumWidth(0)
        self._link.clicked.connect(self._open)
        self._layout.addWidget(self._box)
        self._layout.addWidget(self._link)
        names = getattr(QSizePolicy, "Policy", QSizePolicy)
        self._root.setSizePolicy(getattr(names, "Preferred"), getattr(names, "Minimum"))
        self._stack(True)

    @property
    def widget(self) -> QWidget:
        return self._root

    def show(self, value: object) -> None:
        mark(self._box, value)  # type: ignore[arg-type]
        self._box.blockSignals(True)
        flag = _bool_of(value)
        if isinstance(value, Mixed):
            self._box.setTristate(True)
            self._box.setCheckState(Qt.PartiallyChecked)  # type: ignore[attr-defined]
        else:
            self._box.setTristate(False)
            self._box.setChecked(bool(flag))
        self._box.blockSignals(False)
        self._paint()
        self.reflow()

    def is_dirty(self) -> bool:
        return False

    def wants_stacked(self, width: int) -> bool:
        self.reflow(width)
        return False

    def reflow(self, row_width: int = 0) -> None:
        available = self._root.width()
        if available < 8:
            available = int(row_width)
        needed = self._box.sizeHint().width() + self._link.sizeHint().width() + self._layout.spacing()
        self._stack(available < 8 or needed > available)

    def _stack(self, stack: bool) -> None:
        direction = getattr(QBoxLayout, "Direction", QBoxLayout)
        self._layout.setDirection(getattr(direction, "TopToBottom") if stack else getattr(direction, "LeftToRight"))
        if stack:
            height = self._box.sizeHint().height() + self._link.sizeHint().height() + self._layout.spacing()
        else:
            height = max(self._box.sizeHint().height(), self._link.sizeHint().height())
        if self._root.minimumHeight() != height:
            self._root.setMinimumHeight(height)
        _activate(self._root)

    def _commit(self, checked: bool) -> None:
        self._box.setTristate(False)
        self._host.commit(BoolValue(bool(checked)))

    def _open(self) -> None:
        from app.features.form_builder.qtside.inspector.behavior_ext.state import open_state_row

        key = _WHEN.get(self._host.qt_name, "")
        inspector = _inspector(self._root)
        if key and inspector is not None:
            open_state_row(inspector, key)

    def _paint(self) -> None:
        chrome = self._host.chrome
        focus = chrome.focus_width if chrome.focus_width > 0 else 1
        ink = chrome.accent or chrome.text
        self._link.setStyleSheet(
            "QPushButton { color: %s; background: transparent; border: none; padding: 0 4px; text-align: left; }"
            "QPushButton:focus { border: %dpx solid %s; }" % (ink, focus, ink)
        )


def rule_row(doc: UiDocument, owners: Tuple[NodeId, ...], row: OpenRow) -> OpenRow:
    if len(owners) != 1:
        return row
    node = doc.node(owners[0])
    if _stored(node, "cbcsValue") and row.qt_name == _written_property(node):
        return replace(row, editor=EditorKey("calculated"), value=Unset(), write=_Silent(owners))
    when = _WHEN.get(row.qt_name, "")
    if when and _stored(node, when):
        return replace(row, editor=EditorKey("rule_link"))
    return row


def register(registrar: Registrar) -> None:
    registrar.editor(EditorKey("calculated"), CalculatedEditor)
    registrar.editor(EditorKey("rule_link"), RuleLinkEditor)
    registrar.row(
        RowSpec(
            "visible",
            GroupId.INPUT,
            "Visible",
            "Off hides it.",
            Prop("visible"),
            after="readOnly",
            visible=_has_visible_rule,
        )
    )


def _has_visible_rule(doc: UiDocument, owners: Tuple[NodeId, ...]) -> bool:
    if len(owners) != 1:
        return False
    return bool(_stored(doc.node(owners[0]), "cbcsVisibleWhen"))


def _written_property(node: object) -> str:
    class_name = (getattr(node, "class_name", "") or "").rsplit(".", 1)[-1]
    if not class_name:
        return ""
    chain = class_chain(QtClassTable.shared(), class_name) or (class_name,)
    _matched, spec = lookup_spec(class_name, chain)
    if spec is None:
        return ""
    return _WRITE_PROP.get(spec.write, "")


def _bool_of(value: object) -> Optional[bool]:
    found = None
    if isinstance(value, Written):
        found = value.value
    elif isinstance(value, Unset):
        found = value.default
    if isinstance(found, BoolValue):
        return found.value
    return None


def _stored(node: object, key: str) -> str:
    if node is None:
        return ""
    value = node.value(key) if hasattr(node, "value") else None
    text = getattr(value, "text", None)
    return text.strip() if isinstance(text, str) else ""


def _inspector(widget: QWidget) -> Optional[QWidget]:
    current: Optional[QWidget] = widget
    while current is not None:
        if current.objectName() == "formBuilder.inspector":
            return current
        current = current.parentWidget()
    return None


def _activate(widget: QWidget) -> None:
    widget.updateGeometry()
    current: Optional[QWidget] = widget
    steps = 0
    while current is not None and steps < 8:
        layout = current.layout()
        if layout is not None:
            layout.activate()
        if current.objectName() == "formBuilder.inspector":
            return
        current = current.parentWidget()
        steps += 1
