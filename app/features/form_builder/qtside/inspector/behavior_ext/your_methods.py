"""Your methods, when the form itself is selected (UX-BEH-017)."""

from __future__ import annotations

from typing import List, Optional, Tuple

from app.qt.QtCore import Qt
from app.qt.QtGui import QKeyEvent
from app.qt.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from app.qt.qt_compat import enum_value

from app.features.form_builder.engine.commands.catalog_ext.methods import RemoveMethodDeclaration
from app.features.form_builder.engine.logic.compat import node_class, split_signature
from app.features.form_builder.engine.logic.events import declared_methods, read_events, sender_node
from app.features.form_builder.engine.logic.events_catalog import class_chain, event_words
from app.features.form_builder.engine.query.tab_stops import display_name
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.schema import SlotsDecl
from app.features.form_builder.qtside.inspector._services import Rejected
from app.features.form_builder.qtside.inspector.behavior_ext import BehaviorSection, SectionHost, SectionInputs
from app.features.form_builder.qtside.inspector.editors._editor_kit import warning_color
from app.features.form_builder.qtside.pickers import method_actions

_ENTER = frozenset({enum_value(Qt.Key.Key_Return), enum_value(Qt.Key.Key_Enter)})
_DELETE = enum_value(Qt.Key.Key_Delete)


class YourMethods(QWidget):
    def __init__(self, host: SectionHost) -> None:
        super().__init__(host.parent)
        self._services = host.services
        self.setObjectName("formBuilder.yourMethods")
        self._column = QVBoxLayout(self)
        self._column.setContentsMargins(0, 4, 0, 4)
        self._column.setSpacing(2)
        self._overline = QLabel(self)
        self._overline.setWordWrap(True)
        self._overline.setObjectName("formBuilder.yourMethods.overline")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._caption = QLabel(self)
        self._caption.setWordWrap(True)
        self._caption.setObjectName("formBuilder.yourMethods.caption")
        self._column.addWidget(self._overline)
        self._column.addWidget(self._caption)
        self._rows: List[QWidget] = []

    def paint(self, inputs: SectionInputs) -> None:
        del inputs
        self._refill()

    def apply_colors(self, panel: str, text: str) -> None:
        chrome = self._services.chrome
        self.setStyleSheet("QWidget#formBuilder.yourMethods { background: %s; }" % panel)
        self._overline.setStyleSheet("color: %s; background: %s;" % (text, panel))
        self._caption.setStyleSheet("color: %s; background: %s;" % (chrome.muted, panel))
        for row in self._rows:
            paint = getattr(row, "apply_colors", None)
            if callable(paint):
                paint(panel, text)

    def _refill(self) -> None:
        for row in self._rows:
            row.setParent(None)
            row.deleteLater()
        self._rows = []
        session = self._services.session
        doc = session.document
        file_name = _file(session) or "the window file"
        self._overline.setText("YOUR METHODS \u00b7 %s" % file_name)
        self._caption.setText("Code Studio adds methods to %s and never changes the rest of it." % file_name)
        lines = _lines(self)
        named = _named(doc)
        base_slots = _base_slots(doc)
        for name in sorted(named):
            phrases, _count = named[name]
            line = lines.get(name)
            if line is None and name in base_slots:
                continue
            self._add_method(name, file_name, phrases, line, name in declared_methods(doc))
        declared = doc.ui.field("form_slots")
        signals = declared.signals if isinstance(declared, SlotsDecl) else ()
        if signals:
            header = QLabel("SIGNALS YOUR FORM DECLARES", self)
            header.setObjectName("formBuilder.yourMethods.signals")
            self._column.addWidget(header)
            self._rows.append(header)
            for signature in signals:
                label = QLabel(signature, self)
                label.setAccessibleName("Signal %s, declared by this form." % signature)
                self._column.addWidget(label)
                self._rows.append(label)
        self.apply_colors(self._services.chrome.panel, self._services.chrome.text)

    def _add_method(self, name: str, file_name: str, phrases: Tuple[str, ...], line: Optional[int], declared: bool) -> None:
        if line is None:
            text = "%s() \u00b7 not in %s" % (name, file_name)
            accessible = "%s() is not in %s." % (name, file_name)
            warn = True
        elif phrases:
            where = ", ".join(phrases)
            text = "%s() \u00b7 %s \u00b7 line %d" % (name, where, line)
            accessible = "%s(), %s, line %d." % (name, where, line)
            warn = False
        else:
            text = "%s() \u00b7 not used \u00b7 line %d" % (name, line)
            accessible = "%s() is not used, line %d." % (name, line)
            warn = False
        row = _MethodRow(self, name, text, accessible, warn, declared and not phrases)
        self._column.addWidget(row)
        self._rows.append(row)

    def go(self, method: str) -> None:
        surface = _surface(self)
        go = getattr(method_actions(), "go_to", None)
        if surface is not None and callable(go):
            go(surface, method)

    def delete(self, method: str) -> None:
        doc = self._services.session.document
        used = _use_count(doc, method)
        if used:
            _narrate(self, "%s is used by %d steps. Delete those steps first." % (method, used))
            return
        result = self._services.execute(RemoveMethodDeclaration(method, "Remove method declaration %s" % method))
        if isinstance(result, Rejected):
            _narrate(self, result.message)


class _MethodRow(QWidget):
    def __init__(self, body: YourMethods, method: str, text: str, accessible: str, warn: bool, can_delete: bool) -> None:
        super().__init__(body)
        self._body = body
        self.method_name = method
        self._can_delete = can_delete
        self._warn = warn
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAccessibleName(accessible)
        line = QHBoxLayout(self)
        line.setContentsMargins(2, 0, 2, 0)
        self._label = QLabel(text, self)
        self._label.setMinimumWidth(0)
        line.addWidget(self._label, 1)

    def apply_colors(self, panel: str, text: str) -> None:
        chrome = self._body._services.chrome
        color = warning_color(chrome) if self._warn else text
        self._label.setStyleSheet("color: %s; background: %s;" % (color, panel))
        self.setStyleSheet(
            "QWidget { background: %s; } QWidget:focus { border: %dpx solid %s; background: %s; }"
            % (panel, chrome.focus_width, chrome.accent, panel)
        )

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = enum_value(event.key())
        if key in _ENTER:
            self._body.go(self.method_name)
            event.accept()
            return
        if key == _DELETE:
            if self._can_delete:
                self._body.delete(self.method_name)
            else:
                used = _use_count(self._body._services.session.document, self.method_name)
                if used:
                    _narrate(self._body, "%s is used by %d steps. Delete those steps first." % (self.method_name, used))
            event.accept()
            return
        super().keyPressEvent(event)


def _applies(inputs: SectionInputs) -> bool:
    return inputs.is_form


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if callable(add):
        add(BehaviorSection("your-methods", 50, lambda host: YourMethods(host), _applies))


def _base_slots(doc: object) -> set:
    """Public names of the form's Qt class. A slot of that class is not 'missing'."""
    root = getattr(doc, "root", None)
    class_name = str(getattr(root, "class_name", "") or "")
    if not class_name:
        return set()
    from app.qt import QtCore, QtGui, QtWidgets

    for module in (QtWidgets, QtGui, QtCore):
        found = getattr(module, class_name, None)
        if isinstance(found, type):
            return {name for name in dir(found) if not name.startswith("_")}
    return set()


def _file(session: object) -> str:
    scope = getattr(session, "scope", None)
    path = str(getattr(scope, "window_path", "") or "")
    return path.rsplit("/", 1)[-1]


def _lines(widget: QWidget) -> dict:
    surface = _surface(widget)
    listed = getattr(method_actions(), "methods", None)
    if surface is None or not callable(listed):
        return {}
    found = listed(surface)
    if not isinstance(found, tuple):
        return {}
    return {str(item.name): int(item.line) for item in found}


def _named(doc: object) -> dict:
    classes = QtClassTable.shared()
    found = {}
    for state in read_events(doc):  # type: ignore[arg-type]
        phrase = _phrase(doc, state, classes)
        for step in state.steps:
            name = ""
            if step.verb == "call" and step.method:
                name = step.method
            elif step.verb == "slot" and step.target == doc.root.object_name:  # type: ignore[attr-defined]
                name = split_signature(step.slot)[0]
            if not name:
                continue
            phrases, count = found.setdefault(name, ([], 0))
            if phrase not in phrases:
                phrases.append(phrase)
            found[name] = (phrases, count + 1)
    for name in declared_methods(doc):  # type: ignore[arg-type]
        found.setdefault(name, ([], 0))
    return {name: (tuple(phrases), count) for name, (phrases, count) in found.items()}


def _phrase(doc: object, state: object, classes: QtClassTable) -> str:
    node = sender_node(doc, state.sender)  # type: ignore[arg-type]
    class_name = node_class(doc, classes, node)[0] if node is not None else ""  # type: ignore[arg-type]
    words = event_words(state.signal_name, class_chain(classes, class_name)).header  # type: ignore[attr-defined]
    return "%s %s" % (display_name(doc, state.sender), words)  # type: ignore[arg-type]


def _use_count(doc: object, method: str) -> int:
    return int(_named(doc).get(method, ([], 0))[1])


def _surface(widget: QWidget) -> object:
    current: Optional[QWidget] = widget
    while current is not None:
        if hasattr(current, "code_bridge") and hasattr(current, "session"):
            return current
        current = current.parentWidget()
    return None


def _narrate(widget: QWidget, sentence: str) -> None:
    surface = _surface(widget)
    narrate = getattr(surface, "narrate", None)
    if callable(narrate):
        narrate(sentence)
