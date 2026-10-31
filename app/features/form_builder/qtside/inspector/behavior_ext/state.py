"""State rows (UX-STATE-001 .. 003). One table, one formula field."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Dict, Optional, Tuple

from app.qt.QtCore import Qt, Signal
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
from app.features.form_builder.engine.logic.formula.types import TEXT, lookup_spec, main_type
from app.features.form_builder.engine.logic.formula_env import env_for
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.qtside.formula.editor import FormulaEditor
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
    ("money", "money"),
    ("number", "number"),
    ("percent", "percent"),
    ("date:short", "date:short"),
    ("date:long", "date:long"),
    ("date:iso", "date:iso"),
    ("text:upper", "text:upper"),
    ("text:proper", "text:proper"),
)


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


class _Row(QWidget):
    def __init__(self, body: "StateBody", spec: StateRowSpec) -> None:
        super().__init__(body)
        self.spec = spec
        self.setObjectName("formBuilder.state.row.%s" % spec.key)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumWidth(0)
        self.words = QLabel(spec.words, self)
        self.words.setMinimumWidth(0)
        self.value = QLabel(self)
        self.value.setObjectName("formBuilder.state.value.%s" % spec.key)
        self.value.setWordWrap(True)
        self.value.setMinimumWidth(0)
        self.now = QLabel(self)
        self.now.setObjectName("formBuilder.state.now.%s" % spec.key)
        self.now.setMinimumWidth(0)
        self.combo: Optional[QComboBox] = None
        self.places: Optional[QSpinBox] = None
        self.column = QVBoxLayout(self)
        self.column.setContentsMargins(0, 0, 0, 0)
        self.column.setSpacing(2)
        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)
        line.addWidget(self.words)
        line.addWidget(self.value, 1)
        line.addWidget(self.now)
        self.column.addLayout(line)
        self._body = body

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
        self._closing = False
        self._filling = False
        self._rows: Dict[str, _Row] = {}
        self._by_key = {spec.key: spec for spec in _ORDER}
        title = QLabel("STATE", self)
        title.setObjectName("formBuilder.state.title")
        self._column = QVBoxLayout(self)
        self._column.setContentsMargins(0, 4, 0, 4)
        self._column.setSpacing(2)
        self._column.addWidget(title)
        self._editor = FormulaEditor(self)
        self._editor.hide()
        self._status = QLabel(self)
        self._status.setObjectName("formBuilder.state.status")
        self._status.setWordWrap(True)
        self._status.setMinimumWidth(0)
        self._status.hide()
        self._editor.set_status_label(self._status)
        self._editor.set_handlers(self._commit_open, self._cancel)
        complete, fixes = self._editor.lists()
        self._complete = complete
        self._fixes = fixes

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
        self._editor.set_chrome(chrome)

    def paint(self, inputs: SectionInputs) -> None:
        self._inputs = inputs
        self._node = _selected(inputs)
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
            if spec is not None:
                self._editor.set_chrome(self._services.chrome)
                self._editor.set_context(self._env, _slot(spec, self._env, self._node), self._reader())

    def note_focus(self, focus: object) -> None:
        if self._open_key is None or self._closing:
            return
        if _holds(self, focus):
            return
        if self._editor.has_error():
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
            if self._editor.has_error():
                return
            self._commit_open()
        if self._node is None or self._env is None:
            return
        self._open_key = key
        self._attach(row)
        self._editor.set_chrome(self._services.chrome)
        self._editor.set_context(self._env, _slot(spec, self._env, self._node), self._reader())
        self._editor.show_text(_stored(self._node, key))
        self._editor.show()
        self._status.show()
        self._editor.setFocus()

    def _commit_open(self) -> None:
        if self._open_key is None or self._closing:
            return
        spec = self._by_key.get(self._open_key)
        if spec is None:
            return
        if self._editor.has_error():
            return
        self._closing = True
        try:
            if self._write(spec.key, spec.words, self._editor.toPlainText(), formula=True):
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
        previous = self._column.count()
        for index, spec in enumerate(specs):
            row = self._rows.get(spec.key)
            if row is None:
                row = self._make(spec)
                self._rows[spec.key] = row
            if self._column.indexOf(row) != index + 1:
                self._column.removeWidget(row)
                self._column.insertWidget(index + 1, row)
            row.show()
        del previous

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
        line = row.column.itemAt(0)
        if line is not None and line.layout() is not None:
            line.layout().addWidget(combo)
            line.layout().addWidget(spin)
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
                if stored:
                    row.value.setText(stored)
                    row.value.setStyleSheet("color: %s;" % chrome.text)
                    now = _now_of(stored, spec, env, node, self._reader())
                    row.now.setText("now: %s" % now)
                    row.now.show()
                    line = "%s  %s   now: %s" % (spec.words, stored, now)
                else:
                    row.value.setText(spec.empty)
                    row.value.setStyleSheet("color: %s;" % chrome.muted)
                    row.now.hide()
                    line = "%s  %s" % (spec.words, spec.empty) if spec.empty else spec.words
                row.setAccessibleName(line)
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

    def _attach(self, row: _Row) -> None:
        for widget in (self._editor, self._complete, self._fixes, self._status):
            widget.setParent(row)
            if row.column.indexOf(widget) < 0:
                row.column.addWidget(widget)

    def _close_editor(self) -> None:
        self._open_key = None
        for widget in (self._editor, self._complete, self._fixes, self._status):
            widget.hide()
            widget.setParent(self)

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
        found, _unknown = main_type(
            value_spec,
            matched,
            kind=facts.kind,
            prefix=facts.prefix,
            decimals=facts.decimals,
            has_items_data=facts.has_items_data,
        )
        if found is not None:
            target = found
    if spec.slot == "default":
        return SlotKind.default(target)
    return SlotKind.value(target)


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
    if focus is editor or editor.isAncestorOf(focus):  # type: ignore[arg-type]
        return True
    for widget in (body._complete, body._fixes, body._status):
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
