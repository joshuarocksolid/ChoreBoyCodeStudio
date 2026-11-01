"""State rows (UX-STATE-001 .. 003). One table, one formula field."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Dict, Optional, Tuple

from app.qt.QtCore import QSize, Qt, Signal
from app.qt.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import enum_value

from app.features.form_builder.engine.commands.catalog import SetLogic
from app.features.form_builder.engine.logic.events_catalog import class_chain
from app.features.form_builder.engine.logic.formula.env import SlotKind
from app.features.form_builder.engine.logic.formula.types import TEXT, lookup_spec, written_type
from app.features.form_builder.engine.logic.formula_env import env_for
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.qtside.formula.editor import FormulaEditor
from app.features.form_builder.qtside.formula.live_plate import plate_for
from app.features.form_builder.qtside.inspector._services import Dropped, Rejected
from app.features.form_builder.qtside.inspector.behavior_ext import BehaviorSection, SectionHost, SectionInputs
from app.features.form_builder.qtside.inspector.model import OneBehavior

_ENTER = frozenset({enum_value(Qt.Key.Key_Return), enum_value(Qt.Key.Key_Enter)})
_KIND_CLASSES = frozenset({"QLineEdit", "QLabel", "QPlainTextEdit"})
_FORMAT_CLASSES = frozenset({"QLabel", "QLineEdit"})
_KINDS = (
    ("Text", "text"),
    ("Whole number", "whole"),
    ("Number (places)", "number"),
    ("Money", "money"),
    ("Percent", "percent"),
    ("Date", "date"),
    ("Time", "time"),
)
_FORMATS = (
    ("", ""),
    ("Money", "money"),
    ("Number", "number"),
    ("Percent", "percent"),
    ("Short date", "date:short"),
    ("Long date", "date:long"),
    ("ISO date", "date:iso"),
    ("Uppercase", "text:upper"),
    ("Proper case", "text:proper"),
)
_SPEAK = {"condition": "condition", "value": "value", "default": "value"}


@dataclass(frozen=True)
class StateRowSpec:
    key: str
    words: str
    empty: str
    slot: str


_ORDER = (
    StateRowSpec("cbcsKind", "Kind", "", "kind"),
    StateRowSpec("cbcsEnabledWhen", "Enabled when", "always", "condition"),
    StateRowSpec("cbcsVisibleWhen", "Visible when", "always", "condition"),
    StateRowSpec("cbcsReadOnlyWhen", "Read-only when", "never", "condition"),
    StateRowSpec("cbcsValue", "Value", "typed by the person", "value"),
    StateRowSpec("cbcsFormat", "Format", "", "format"),
    StateRowSpec("cbcsDefault", "Default", "as designed", "default"),
)
# The five rule words. Kind and Format share this width so every row lines up.
_RULE_WORDS = ("Enabled when", "Visible when", "Read-only when", "Value", "Default")
_RIGHT = getattr(getattr(Qt, "AlignmentFlag", Qt), "AlignRight")
_VCENTER = getattr(getattr(Qt, "AlignmentFlag", Qt), "AlignVCenter")


class _Row(QWidget):
    def __init__(self, body: "StateBody", spec: StateRowSpec) -> None:
        super().__init__(body)
        self.spec = spec
        self._full = ""
        self.setObjectName("formBuilder.state.row.%s" % spec.key)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumWidth(0)
        self.words = QLabel(spec.words, self)
        self.words.setMinimumWidth(0)
        self.value = QLabel(self)
        self.value.setObjectName("formBuilder.state.value.%s" % spec.key)
        self.value.setWordWrap(True)
        self.value.setMinimumWidth(0)
        value_policy = self.value.sizePolicy()
        value_policy.setHeightForWidth(True)
        self.value.setSizePolicy(value_policy)
        self.now = QLabel(self)
        self.now.setObjectName("formBuilder.state.now.%s" % spec.key)
        self.now.setMinimumWidth(0)
        self.now.setAlignment(_RIGHT | _VCENTER)
        self.combo: Optional[QComboBox] = None
        self.places: Optional[QSpinBox] = None
        self.column = QVBoxLayout(self)
        self.column.setContentsMargins(0, 0, 0, 0)
        self.column.setSpacing(0)
        self.line_host = QWidget(self)
        self.line_host.setMinimumHeight(22)
        self.line = QHBoxLayout(self.line_host)
        self.line.setContentsMargins(0, 0, 0, 0)
        self.line.setSpacing(8)
        self.line.addWidget(self.words)
        self.line.addWidget(self.value, 1)
        self.column.addWidget(self.line_host)
        self.column.addWidget(self.now)
        self._body = body

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self.column.heightForWidth(width)

    def sizeHint(self) -> QSize:  # noqa: N802
        hint = super().sizeHint()
        laid_out = self.height()
        if laid_out > hint.height():
            hint.setHeight(laid_out)
        return hint

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._elide()

    def show_value(self, text: str, tip: str = "") -> None:
        self._full = text
        self._tip = tip
        self._elide()

    def _elide(self) -> None:
        """Keep the whole sentence. ``now:`` sits on the next line, so the rule is not cut."""
        if self.spec.slot in ("kind", "format"):
            return
        full = self._full
        if self.value.text() != full:
            self.value.setText(full)
        self._set_tip(getattr(self, "_tip", "") or "")

    def _set_tip(self, elided: str) -> None:
        tip = getattr(self, "_tip", "") or elided
        if self.value.toolTip() != tip:
            self.value.setToolTip(tip)

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        key = enum_value(event.key())  # type: ignore[attr-defined]
        if key in _ENTER and self.spec.slot not in ("kind", "format"):
            self._body.open_row(self.spec.key)
            event.accept()  # type: ignore[attr-defined]
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]

    def mouseReleaseEvent(self, event: object) -> None:  # noqa: N802
        if self.spec.slot not in ("kind", "format"):
            self._body.open_row(self.spec.key)
        super().mouseReleaseEvent(event)  # type: ignore[arg-type]


class StateBody(QWidget):
    rule_committed = Signal(str, str, str)

    def __init__(self, host: SectionHost) -> None:
        super().__init__(host.parent)
        self.setObjectName("formBuilder.state")
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self._services = host.services
        self._realizer = host.realizer
        self._refresh = None
        self._inputs: Optional[SectionInputs] = None
        self._node: Optional[WidgetNode] = None
        self._env = None
        self._open_key: Optional[str] = None
        self._live_id: object = None
        self._closing = False
        self._filling = False
        self._rows: Dict[str, _Row] = {}
        self._by_key = {spec.key: spec for spec in _ORDER}
        self._label_width = 0
        overline = QWidget(self)
        overline.setObjectName("formBuilder.state.overline")
        heading = QHBoxLayout(overline)
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(0)
        title = QLabel("STATE", overline)
        title.setObjectName("formBuilder.state.title")
        heading.addWidget(title)
        heading.addStretch(1)
        self._column = QVBoxLayout(self)
        self._column.setContentsMargins(0, 4, 0, 4)
        self._column.setSpacing(4)
        self._column.addWidget(overline)
        realizer = self._realizer
        if realizer is not None:
            def _clear_plate(*_args: object, realizer: object = realizer) -> None:
                plate_for(realizer).clear()

            self.destroyed.connect(_clear_plate)
        # The formula field is built the first time a row opens. Painting the
        # closed section only creates the label rows.
        self._pad: Optional[QWidget] = None
        self._editor: Optional[FormulaEditor] = None
        self._status: Optional[QLabel] = None
        self._complete = None
        self._fixes = None

    def set_refresh(self, refresh: object) -> None:
        self._refresh = refresh

    def apply_colors(self, panel: str, text: str) -> None:
        chrome = self._services.chrome
        self.setStyleSheet(
            "QWidget#formBuilder\\.state { background: %s; color: %s; }"
            "QLabel { color: %s; background: transparent; }"
            "QComboBox, QSpinBox { color: %s; background: %s; }"
            % (panel, text, text, text, chrome.input)
        )
        if self._editor is not None:
            self._editor.set_chrome(chrome)
        self._sync_columns()

    def paint(self, inputs: SectionInputs) -> None:
        self._inputs = inputs
        selected = _selected(inputs)
        selected_id = None if selected is None else selected.id
        if self._live_id is not None and selected_id != self._live_id:
            self._drop_live()
            self._cancel()
        self._node = selected
        if self._node is None:
            self._cancel()
            for row in self._rows.values():
                row.hide()
            return
        self._env = env_for(inputs.session.document, _window_facts(self), QtClassTable.shared())
        shown = _visible(self._node, QtClassTable.shared())
        self._show(shown)
        self._fill(shown)
        if self._open_key and self._open_key not in {spec.key for spec in shown}:
            self._cancel()
        elif self._open_key and not self._closing:
            spec = self._by_key.get(self._open_key)
            editor = self._editor
            if spec is not None and editor is not None and self._node is not None and self._env is not None:
                editor.set_chrome(self._services.chrome)
                editor.set_context(self._env, _slot(spec, self._env, self._node), self._reader())

    def note_focus(self, focus: object) -> None:
        if self._open_key is None or self._closing:
            return
        if _holds(self, focus):
            return
        editor = self._editor
        if editor is not None and editor.has_error():
            return
        self._commit_open()

    def has_draft(self) -> bool:
        return self._open_key is not None

    def discard_draft(self) -> bool:
        if self._open_key is None:
            return False
        self._cancel()
        return True

    def open_row(self, key: str) -> None:
        spec = self._by_key.get(key)
        row = self._rows.get(key)
        if spec is None or row is None or row.isHidden():
            return
        if spec.slot in ("kind", "format"):
            if row.combo is not None:
                row.combo.setFocus()
            return
        if self._open_key and self._open_key != key:
            if self._editor is not None and self._editor.has_error():
                return
            self._commit_open()
        if self._node is None or self._env is None:
            return
        self._ensure_editor()
        editor = self._editor
        pad = self._pad
        status = self._status
        if editor is None or pad is None or status is None or self._env is None or self._node is None:
            return
        self._open_key = key
        self._attach(row)
        pad.show()
        editor.set_chrome(self._services.chrome)
        editor.set_context(self._env, _slot(spec, self._env, self._node), self._reader())
        editor.show_text(_stored(self._node, key))
        editor.present()
        status.show()
        self._arm_live(key)

    def _commit_open(self) -> None:
        if self._open_key is None or self._closing:
            return
        spec = self._by_key.get(self._open_key)
        editor = self._editor
        if spec is None or editor is None:
            return
        if editor.has_error():
            return
        self._closing = True
        try:
            if self._write(spec.key, spec.words, editor.toPlainText(), formula=True):
                self._close_editor()
        finally:
            self._closing = False

    def _cancel(self) -> None:
        self._close_editor()

    def _write(self, key: str, words: str, text: str, *, formula: bool) -> bool:
        node = self._node
        env = self._env
        if node is None or env is None:
            return False
        if formula:
            from app.features.form_builder.engine.logic.formula import normalize

            shown = normalize(text)
            payload: Optional[str] = shown if shown else None
            current = normalize(_stored(node, key))
        else:
            shown = text.strip()
            payload = shown if shown else None
            current = _stored(node, key)
        if (payload or "") == current:
            return True
        name = node.object_name or ""
        facts = env.widgets.get(name)
        display = facts.display if facts is not None and facts.display else name
        if payload is None:
            label = "Clear %s for %s" % (words, display)
        else:
            label = "Set %s for %s" % (words, display)
        result = self._services.execute_all(label, [SetLogic(node.id, key, payload)])
        if isinstance(result, (Rejected, Dropped)):
            return False
        self.rule_committed.emit(name, key, shown if payload else "")
        return True

    def _show(self, specs: Tuple[StateRowSpec, ...]) -> None:
        wanted = {spec.key for spec in specs}
        for key, row in self._rows.items():
            if key not in wanted:
                row.hide()
        for index, spec in enumerate(specs):
            row = self._rows.get(spec.key)
            if row is None:
                row = self._make(spec)
                self._rows[spec.key] = row
            if self._column.indexOf(row) != index + 1:
                self._column.removeWidget(row)
                self._column.insertWidget(index + 1, row)
            row.show()
        # Rows created after the inspector is on screen never join Qt's tab
        # chain. Enabled when is already in that chain. Hang the later rows
        # off it. The first argument stays where it is.
        previous = self._rows.get("cbcsEnabledWhen")
        if previous is None or previous.isHidden():
            previous = None
        for spec in specs:
            if spec.key == "cbcsEnabledWhen":
                continue
            row = self._rows.get(spec.key)
            if row is None or row.isHidden() or previous is None:
                continue
            target = row.combo if spec.slot in ("kind", "format") and row.combo is not None else row
            QWidget.setTabOrder(previous, target)
            previous = target

    def _make(self, spec: StateRowSpec) -> _Row:
        row = _Row(self, spec)
        if spec.slot not in ("kind", "format"):
            return row
        row.value.hide()
        row.now.hide()
        combo = QComboBox(row)
        combo.setObjectName("formBuilder.state.%s" % spec.slot)
        combo.setMinimumWidth(0)
        items = _KINDS if spec.slot == "kind" else _FORMATS
        for label, code in items:
            combo.addItem(label, code)
        spin = QSpinBox(row)
        spin.setRange(0, 6)
        spin.setObjectName(
            "formBuilder.state.kindPlaces" if spec.slot == "kind" else "formBuilder.state.formatPlaces"
        )
        if spec.slot == "kind":
            spin.setAccessibleName("Decimal places")
        spin.hide()
        row.combo = combo
        row.places = spin
        row.line.addWidget(combo, 1)
        row.line.addWidget(spin)
        row.line_host.setFixedHeight(max(24, combo.sizeHint().height()))
        combo.currentIndexChanged.connect(lambda _index, key=spec.key: self._plain_changed(key))
        spin.valueChanged.connect(lambda _value, key=spec.key: self._plain_changed(key))
        return row

    def _plain_changed(self, key: str) -> None:
        if self._filling:
            return
        spec = self._by_key.get(key)
        row = self._rows.get(key)
        if spec is None or row is None or row.combo is None:
            return
        code = row.combo.currentData()
        if not isinstance(code, str):
            code = ""
        places = row.places
        if code in ("number", "percent") and places is not None and spec.slot == "format":
            places.show()
            code = "%s:%d" % (code, places.value())
        elif code == "number" and places is not None and spec.slot == "kind":
            places.show()
            code = "number:%d" % places.value()
        elif places is not None:
            places.hide()
        self._write(spec.key, spec.words, code, formula=False)

    def _fill(self, specs: Tuple[StateRowSpec, ...]) -> None:
        node = self._node
        env = self._env
        if node is None or env is None:
            return
        chrome = self._services.chrome
        self._filling = True
        try:
            for spec in specs:
                row = self._rows.get(spec.key)
                if row is None:
                    continue
                if spec.slot in ("kind", "format"):
                    self._fill_combo(row, _stored(node, spec.key))
                    continue
                stored = _stored(node, spec.key)
                muted = "color: %s; background: transparent;" % chrome.muted
                row.now.setStyleSheet(muted)
                if stored:
                    spoken = _spoken_formula(stored, spec.slot, env)
                    row.show_value(spoken or stored, stored if spoken else "")
                    row.value.setStyleSheet("color: %s; background: transparent;" % chrome.text)
                    now = _now_of(stored, spec, env, node, self._reader())
                    row.now.setText("now: %s" % now)
                    row.now.show()
                    line = "%s  %s   now: %s" % (spec.words, spoken or stored, now)
                else:
                    row.show_value(spec.empty)
                    row.value.setStyleSheet(muted)
                    row.now.hide()
                    line = "%s  %s" % (spec.words, spec.empty) if spec.empty else spec.words
                row.setAccessibleName(line)
            self._sync_columns()
        finally:
            self._filling = False

    def _fill_combo(self, row: _Row, stored: str) -> None:
        combo = row.combo
        places = row.places
        if combo is None:
            return
        head, count = _split_places(stored)
        index = combo.findData(head)
        if index < 0:
            index = 0 if row.spec.slot == "kind" else combo.findData("")
        combo.blockSignals(True)
        combo.setCurrentIndex(max(0, index))
        combo.blockSignals(False)
        if places is None:
            return
        show = head in ("number", "percent") and (row.spec.slot == "format" or head == "number")
        if row.spec.slot == "kind":
            show = head == "number"
        places.blockSignals(True)
        if count is not None:
            places.setValue(max(0, min(6, count)))
        places.blockSignals(False)
        places.setVisible(show)

    def _sync_columns(self) -> None:
        if not self._rows:
            return
        sample = next(iter(self._rows.values()))
        width = _label_width(sample)
        self._label_width = width
        for row in self._rows.values():
            row.words.setFixedWidth(width)
            row._elide()

    def _ensure_editor(self) -> None:
        if self._editor is not None:
            return
        pad = QWidget(self)
        pad.setObjectName("formBuilder.state.edit")
        layout = QVBoxLayout(pad)
        layout.setContentsMargins(12, 2, 8, 0)
        layout.setSpacing(2)
        editor = FormulaEditor(pad)
        status = QLabel(pad)
        status.setObjectName("formBuilder.state.status")
        status.setWordWrap(True)
        status.setMinimumWidth(0)
        # setSizePolicy() clears the height-for-width bit setWordWrap turned on.
        # The column then keeps a one-line hint and the wrapped sentence draws
        # over the next rows. Ignored keeps that sentence from widening the section.
        names = getattr(QSizePolicy, "Policy", QSizePolicy)
        status.setSizePolicy(getattr(names, "Ignored"), getattr(names, "Minimum"))
        fitted = status.sizePolicy()
        fitted.setHeightForWidth(True)
        status.setSizePolicy(fitted)
        pad.setMinimumWidth(0)
        pad.setSizePolicy(getattr(names, "Preferred"), getattr(names, "Minimum"))
        status.hide()
        editor.hide()
        editor.install_builder(layout)
        layout.addWidget(status)
        editor.set_status_label(status)
        editor.set_handlers(self._commit_open, self._cancel)
        editor.textChanged.connect(self._revise_live)
        editor.set_chrome(self._services.chrome)
        complete, fixes = editor.lists()
        self._pad = pad
        self._editor = editor
        self._status = status
        self._complete = complete
        self._fixes = fixes
        pad.hide()

    def _attach(self, row: _Row) -> None:
        self._sync_columns()
        pad = self._pad
        if pad is None:
            return
        index = self._column.indexOf(row)
        if self._column.indexOf(pad) >= 0:
            self._column.removeWidget(pad)
        pad.setParent(self)
        self._column.insertWidget(index + 1, pad)

    def _close_editor(self) -> None:
        key = self._open_key
        self._open_key = None
        self._drop_live()
        editor = self._editor
        pad = self._pad
        row = self._rows.get(key) if key else None
        if editor is None or pad is None or self._status is None:
            return
        editor.hide_lists()
        editor.hide()
        self._status.hide()
        pad.hide()
        self._column.removeWidget(pad)
        pad.setParent(self)
        pad.setMinimumHeight(0)
        self.setMinimumHeight(0)
        editor._reflow_block()
        if row is not None and row.isVisible():
            row.setFocus()

    def _arm_live(self, key: str) -> None:
        node = self._node
        env = self._env
        editor = self._editor
        if node is None or env is None or editor is None or self._realizer is None:
            return
        plate_for(self._realizer).arm(node, key, editor.toPlainText(), env, self._reader())
        self._live_id = node.id

    def _revise_live(self) -> None:
        editor = self._editor
        if self._live_id is None or editor is None or self._realizer is None:
            return
        plate_for(self._realizer).revise(editor.toPlainText(), self._reader())

    def _drop_live(self) -> None:
        realizer = self._realizer
        self._live_id = None
        if realizer is None:
            return
        plate_for(realizer).clear()

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


def _label_width(widget: QWidget) -> int:
    metrics = widget.fontMetrics()
    widest = 0
    for word in _RULE_WORDS:
        widest = max(widest, int(metrics.horizontalAdvance(word)))
    return widest + 12


def open_state_row(inspector: object, key: str) -> None:
    # focus_tab moves focus to Events. Open the row after that.
    from app.features.form_builder.qtside.inspector import TabId

    focus = getattr(inspector, "focus_tab", None)
    if callable(focus):
        focus(TabId.BEHAVIOR)
    page = getattr(inspector, "behavior", None)
    widget = page.section_widget("state") if page is not None and hasattr(page, "section_widget") else None
    opener = getattr(widget, "open_row", None)
    if callable(opener):
        opener(key)


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


def _visible(node: WidgetNode, classes: QtClassTable) -> Tuple[StateRowSpec, ...]:
    class_name = (node.class_name or "").rsplit(".", 1)[-1]
    chain = class_chain(classes, class_name) or (class_name,)
    names = set(chain)
    matched, spec = lookup_spec(class_name, chain)
    has_value = spec is not None and spec.type_rule != "none"
    found = []
    for row in _ORDER:
        if row.slot == "kind" and not names.intersection(_KIND_CLASSES):
            continue
        if row.slot == "condition" and row.key == "cbcsReadOnlyWhen":
            if classes.property_info(class_name, "readOnly") is None:
                continue
        if row.slot in ("value", "default") and not has_value:
            continue
        if row.slot == "format" and not (has_value and names.intersection(_FORMAT_CLASSES)):
            continue
        found.append(row)
    del matched
    return tuple(found)


def _slot(spec: StateRowSpec, env: object, node: WidgetNode) -> SlotKind:
    if spec.slot == "condition":
        return SlotKind.condition()
    name = node.object_name or ""
    facts = env.widgets.get(name)  # type: ignore[attr-defined]
    if facts is None:
        return SlotKind.value(TEXT)
    chain = env.class_chain(facts.class_name)  # type: ignore[attr-defined]
    matched, value_spec = lookup_spec(facts.class_name, chain)
    target = TEXT
    if value_spec is not None and matched is not None:
        target = written_type(
            value_spec,
            matched,
            kind=facts.kind,
            prefix=facts.prefix,
            decimals=facts.decimals,
            has_items_data=facts.has_items_data,
            fmt=_stored(node, "cbcsFormat"),
        )
    if spec.slot == "default":
        return SlotKind.default(target)
    return SlotKind.value(target)


def _spoken_formula(text: str, slot: str, env: object) -> str:
    kind = _SPEAK.get(slot, "")
    if not kind or env is None:
        return ""
    from app.features.form_builder.engine.logic.formula.speak import speak_text

    try:
        return speak_text(text, env, kind)  # type: ignore[arg-type]
    except Exception:
        return ""


def _stored(node: WidgetNode, key: str) -> str:
    value = node.value(key)
    if isinstance(value, StringValue):
        return value.text
    return ""


def _split_places(stored: str) -> Tuple[str, Optional[int]]:
    for head in ("number", "percent"):
        prefix = head + ":"
        if stored.startswith(prefix) and stored[len(prefix) :].isdigit():
            return head, int(stored[len(prefix) :])
    return stored, None


def _now_of(text: str, spec: StateRowSpec, env: object, node: WidgetNode, reader: SimpleNamespace) -> str:
    from app.features.form_builder.engine.logic.formula import analyze
    from app.features.form_builder.qtside.formula.now import now_text

    try:
        found = analyze(text, env, _slot(spec, env, node))  # type: ignore[arg-type]
    except Exception:
        return "blank"
    return now_text(found, env, reader)  # type: ignore[arg-type]


def _holds(body: StateBody, focus: object) -> bool:
    if focus is None:
        return True
    editor = body._editor
    if editor is None:
        return False
    # The builder and the mode switch sit beside the text field, in the same pad.
    pad = body._pad
    if pad is not None and (focus is pad or pad.isAncestorOf(focus)):  # type: ignore[attr-defined]
        return True
    if focus is editor or editor.isAncestorOf(focus):  # type: ignore[arg-type]
        return True
    for widget in (body._complete, body._fixes, body._status):
        if widget is None:
            continue
        if focus is widget or widget.isAncestorOf(focus):  # type: ignore[arg-type]
            return True
    return False


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
    return StateBody(host)


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if add is not None:
        add(BehaviorSection("state", 10, _create, applies=lambda inputs: _selected(inputs) is not None))
