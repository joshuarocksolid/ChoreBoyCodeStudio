# pyright: reportAttributeAccessIssue=false
"""Checks: each kind, undo names, the label offer, and the outline."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterator, Tuple

import pytest

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.diagnostics import DiagnosticLocation, FormDiagnostic, Severity
from app.features.form_builder.engine.logic.checks import (
    Bound,
    FormulaCheck,
    Length,
    OneOf,
    Pattern,
    Preset,
    Range,
    Required,
    read_checks,
)
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import NumberValue, StringValue
from app.features.form_builder.integration.problem_fixes import FixContext, default_registry
from app.features.form_builder.qtside.checks.catalog import offered_kinds
from app.features.form_builder.qtside.inspector import TabId
from app.features.form_builder.qtside.inspector.pane import InspectorPane
from app.qt.QtCore import Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QLabel, QLineEdit, QMenu, QPushButton, QWidget
from tests.form_builder.qtside.support import form, opened

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("qapp")]

EMAIL_FORM = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>320</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QLabel" name="emailLabel">
     <property name="text"><string>Email</string></property>
     <property name="buddy"><cstring>emailEdit</cstring></property>
    </widget>
   </item>
   <item>
    <widget class="QLineEdit" name="emailEdit"/>
   </item>
   <item>
    <widget class="QLabel" name="qtyLabel">
     <property name="text"><string>Qty</string></property>
     <property name="buddy"><cstring>qtySpin</cstring></property>
    </widget>
   </item>
   <item>
    <widget class="QSpinBox" name="qtySpin"/>
   </item>
   <item>
    <widget class="QPushButton" name="okButton">
     <property name="text"><string>OK</string></property>
    </widget>
   </item>
  </layout>
""",
)

_OUTLINE = '*[cbcsInvalid="true"] { border: 1px solid #c62828; }'


def pump() -> None:
    app = QApplication.instance()
    assert app is not None
    for _ in range(4):
        app.processEvents()


def _key(name: str) -> object:
    return getattr(getattr(Qt, "Key", Qt), name)


def _mod(name: str) -> object:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)


def _id(session: FormSession, name: str) -> object:
    found = session.document.by_name(name)
    assert found, name
    return found[0]


def _widget(session: FormSession, name: str) -> WidgetNode:
    node = session.document.node(_id(session, name))  # type: ignore[arg-type]
    assert isinstance(node, WidgetNode)
    return node


def _validate(session: FormSession, name: str) -> str:
    value = _widget(session, name).value("cbcsValidate")
    if isinstance(value, StringValue):
        return value.text
    return ""


def _checks(session: FormSession, name: str) -> tuple:
    text = _validate(session, name)
    if not text:
        return ()
    read = read_checks(text)
    assert read.error is None
    return read.checks


def _number(session: FormSession, name: str, prop: str) -> object:
    entry = _widget(session, name).prop(prop)
    if entry is None:
        return None
    if isinstance(entry.value, NumberValue):
        return entry.value.value
    return entry.value


def _order(session: FormSession) -> Tuple[str, ...]:
    layout = session.document.node(_id(session, "verticalLayout"))  # type: ignore[arg-type]
    names = []
    for item in layout.items:  # type: ignore[attr-defined]
        for child in item.children("content"):
            object_name = getattr(child, "object_name", None)
            if object_name:
                names.append(object_name)
    return tuple(names)


@contextmanager
def desk() -> Iterator[Tuple[FormSession, InspectorPane]]:
    with opened(EMAIL_FORM) as (session, realizer):
        window = QWidget()
        pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
        window.resize(480, 720)
        window.show()
        app = QApplication.instance()
        assert isinstance(app, QApplication)
        app.setActiveWindow(window)
        pump()
        try:
            yield session, pane
        finally:
            pane.dispose()
            window.close()
            window.deleteLater()
            pump()


def _select(session: FormSession, pane: InspectorPane, name: str) -> None:
    session.selection.set((_id(session, name),), source=SelectionSource.PROGRAM)  # type: ignore[arg-type]
    pane.focus_tab(TabId.BEHAVIOR)
    pane.flush()
    pump()


def _child(pane: QWidget, kind: type, name: str) -> QWidget:
    found = pane.findChild(kind, name)
    assert found is not None, name
    return found


def _open_kind(pane: QWidget, key: str) -> None:
    add = _child(pane, QPushButton, "formBuilder.checks.add")
    add.click()
    pump()
    menu = _child(pane, QMenu, "formBuilder.checks.menu")
    picked = None
    for action in menu.actions():
        if action.data() == key:
            picked = action
            break
    assert picked is not None, key
    picked.trigger()
    pump()


def _finish(pane: QWidget, label: bool) -> None:
    commit = _child(pane, QPushButton, "formBuilder.checks.commit")
    assert commit.isEnabled()
    commit.click()
    pump()
    offer = pane.findChild(QWidget, "formBuilder.checks.offer")
    if offer is not None and offer.isVisible():
        name = "formBuilder.checks.addLabel" if label else "formBuilder.checks.notNow"
        _child(pane, QPushButton, name).click()
        pump()


def _add(pane: QWidget, key: str, fill: Callable[[QWidget], None], *, label: bool = False) -> None:
    _open_kind(pane, key)
    fill(pane)
    _finish(pane, label)


def _line(pane: QWidget, name: str) -> QLineEdit:
    found = _child(pane, QLineEdit, name)
    assert isinstance(found, QLineEdit)
    return found


def test_offered_kinds_follow_the_plan_probe() -> None:
    menus = tuple(item.menu for item in offered_kinds("QLineEdit"))
    assert menus == (
        "Required",
        "Between\u2026",
        "Length\u2026",
        "Email address",
        "Phone number",
        "US ZIP code",
        "Pattern\u2026",
        "One of\u2026",
        "Formula\u2026",
    )
    for class_name in ("QSpinBox", "QDateEdit", "QSlider", "QDial"):
        assert "Required" not in tuple(item.menu for item in offered_kinds(class_name))
        assert "Between\u2026" in tuple(item.menu for item in offered_kinds(class_name))


def test_each_kind_is_one_undo_step_named_for_the_buddy() -> None:
    cases = (
        ("required", lambda pane: None, Required(None), None),
        ("email", lambda pane: None, Preset("email", None), None),
        ("phone", lambda pane: None, Preset("phone", None), None),
        ("zip", lambda pane: None, Preset("zip", None), None),
        ("range", _between, Range(Bound(number=1), Bound(number=10), None), None),
        ("length", _length, Length(2, 8, None), ("maxLength", 8)),
        ("pattern", _pattern, Pattern("code", None), None),
        ("one_of", _one_of, OneOf(("red", "blue"), None), None),
        ("formula", _formula, FormulaCheck("True", "Must pass"), None),
    )
    with desk() as (session, pane):
        _select(session, pane, "emailEdit")
        section = _child(pane, QWidget, "formBuilder.checks")
        assert _child(pane, QLabel, "formBuilder.checks.title").text() == "CHECKS"
        for key, fill, expected, native in cases:
            before = len(session.log.entries())
            _add(pane, key, fill)
            assert session.log.undo_label() == "Add check to Email"
            assert "emailEdit" not in (session.log.undo_label() or "")
            assert len(session.log.entries()) == before + 1
            assert _checks(session, "emailEdit") == (expected,)
            if native is not None:
                prop, value = native
                assert _number(session, "emailEdit", prop) == value
                tag = _child(pane, QLabel, "formBuilder.checks.qt.0")
                assert tag.isVisible() and tag.text() == "Qt"
            else:
                tag = pane.findChild(QLabel, "formBuilder.checks.qt.0")
                assert tag is None or not tag.isVisible()
            row = _child(section, QWidget, "formBuilder.checks.row.0")
            assert row.accessibleName().startswith("Check 1 of 1, ")
            assert session.log.undo()
            assert _checks(session, "emailEdit") == ()
            pump()


def test_spin_between_writes_the_native_bounds_and_hides_required() -> None:
    with desk() as (session, pane):
        _select(session, pane, "qtySpin")
        add = _child(pane, QPushButton, "formBuilder.checks.add")
        add.click()
        pump()
        menu = _child(pane, QMenu, "formBuilder.checks.menu")
        labels = tuple(action.text() for action in menu.actions())
        assert "Required" not in labels
        menu.close()
        _add(pane, "range", _spin_between)
        assert session.log.undo_label() == "Add check to Qty"
        assert "qtySpin" not in (session.log.undo_label() or "")
        assert _checks(session, "qtySpin") == (Range(Bound(number=1), Bound(number=9), None),)
        assert _number(session, "qtySpin", "minimum") == 1
        assert _number(session, "qtySpin", "maximum") == 9
        tag = _child(pane, QLabel, "formBuilder.checks.qt.0")
        assert tag.isVisible() and tag.text() == "Qt"


def test_alt_up_and_alt_down_reorder_and_delete_removes() -> None:
    with desk() as (session, pane):
        _select(session, pane, "emailEdit")
        _add(pane, "email", lambda pane: None)
        _add(pane, "phone", lambda pane: None)
        assert _checks(session, "emailEdit") == (Preset("email", None), Preset("phone", None))
        second = _child(pane, QWidget, "formBuilder.checks.row.1")
        app = QApplication.instance()
        assert isinstance(app, QApplication)
        app.setActiveWindow(second.window())
        pump()
        second.setFocus()
        QTest.keyClick(second, _key("Key_Up"), _mod("AltModifier"))  # type: ignore[arg-type]
        pump()
        assert session.log.undo_label() == "Move check"
        assert _checks(session, "emailEdit") == (Preset("phone", None), Preset("email", None))
        first = _child(pane, QWidget, "formBuilder.checks.row.0")
        assert first.hasFocus()
        QTest.keyClick(first, _key("Key_Down"), _mod("AltModifier"))  # type: ignore[arg-type]
        pump()
        assert _checks(session, "emailEdit") == (Preset("email", None), Preset("phone", None))
        _add(pane, "required", lambda pane: None)
        # Required runs first, so it is the first row even though it was stored last.
        assert _child(pane, QLabel, "formBuilder.checks.words.0").text() == "Required"
        held = len(session.log.entries())
        required = _child(pane, QWidget, "formBuilder.checks.row.0")
        required.setFocus()
        QTest.keyClick(required, _key("Key_Down"), _mod("AltModifier"))  # type: ignore[arg-type]
        pump()
        assert len(session.log.entries()) == held
        assert _checks(session, "emailEdit") == (
            Preset("email", None),
            Preset("phone", None),
            Required(None),
        )
        required.setFocus()
        QTest.keyClick(required, _key("Key_Delete"))  # type: ignore[arg-type]
        pump()
        assert session.log.undo_label() == "Remove check from Email"
        assert _checks(session, "emailEdit") == (Preset("email", None), Preset("phone", None))


def test_enter_edits_and_escape_writes_nothing() -> None:
    with desk() as (session, pane):
        _select(session, pane, "emailEdit")
        _add(pane, "required", lambda pane: None)
        row = _child(pane, QWidget, "formBuilder.checks.row.0")
        row.setFocus()
        QTest.keyClick(row, _key("Key_Return"))  # type: ignore[arg-type]
        pump()
        message = _line(pane, "formBuilder.checks.message")
        message.setText("Need this")
        _child(pane, QPushButton, "formBuilder.checks.commit").click()
        pump()
        assert session.log.undo_label() == "Edit check on Email"
        assert _checks(session, "emailEdit") == (Required("Need this"),)
        before = len(session.log.entries())
        label = session.log.undo_label()
        row = _child(pane, QWidget, "formBuilder.checks.row.0")
        row.setFocus()
        QTest.keyClick(row, _key("Key_Return"))  # type: ignore[arg-type]
        pump()
        message = _line(pane, "formBuilder.checks.message")
        message.setText("Nope")
        QTest.keyClick(message, _key("Key_Escape"))  # type: ignore[arg-type]
        pump()
        assert len(session.log.entries()) == before
        assert session.log.undo_label() == label
        assert _checks(session, "emailEdit") == (Required("Need this"),)
        assert not pane.findChild(QWidget, "formBuilder.checks.page").isVisible()  # type: ignore[union-attr]


def test_add_label_inserts_under_the_field_in_the_same_step() -> None:
    with desk() as (session, pane):
        _select(session, pane, "emailEdit")
        before = len(session.log.entries())
        _add(pane, "required", lambda pane: None, label=True)
        assert len(session.log.entries()) == before + 1
        assert session.log.undo_label() == "Add check to Email"
        names = _order(session)
        assert names[names.index("emailEdit") + 1] == "emailEditError"
        assert _widget(session, "emailEdit").value("cbcsErrorLabel").text == "emailEditError"  # type: ignore[union-attr]
        assert session.log.undo()
        assert "emailEditError" not in _order(session)
        assert _checks(session, "emailEdit") == ()


def test_not_now_leaves_the_engine_message_and_the_section_sentence(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with desk() as (session, pane):
        _select(session, pane, "emailEdit")
        _add(pane, "required", lambda pane: None, label=False)
        assert "emailEditError" not in _order(session)
        assert _checks(session, "emailEdit") == (Required(None),)
        prompt = _child(pane, QLabel, "formBuilder.checks.promptText")
        assert prompt.isVisible()
        assert prompt.text() == "Email's messages show only as a tooltip. Add a label under the field?"
        scope = FormScope(
            kind="project",
            ui_path=str(tmp_path / "forms" / "mail.ui"),
            project_root=str(tmp_path),
            generated_path=str(tmp_path / "forms" / "ui_mail.py"),
            window_path=str(tmp_path / "forms" / "mail_window.py"),
            module_name="forms.ui_mail",
        )
        made = generate_form_module(session.document, scope=scope, source_bytes=None)
        assert any(
            item.code == "FB119" and item.message == "A check has no error label."
            for item in made.diagnostics
        )
        diagnostic = FormDiagnostic(
            code="FB119",
            severity=Severity.INFO,
            message="A check has no error label.",
            location=DiagnosticLocation(object_name="emailEdit", property="cbcsErrorLabel"),
            source="codegen",
        )
        fixes = default_registry().for_diagnostic(diagnostic)
        assert fixes and fixes[0].title_for(diagnostic) == "Add label"
        assert diagnostic.fixes == ()
        before = len(session.log.entries())
        _child(pane, QPushButton, "formBuilder.checks.promptAdd").click()
        pump()
        assert session.log.undo_label() == "Add error label for Email"
        assert len(session.log.entries()) == before + 1
        assert "emailEditError" in _order(session)
        assert session.log.undo()
        pump()
        assert "emailEditError" not in _order(session)
        fixes[0].run(FixContext(diagnostic, session))
        assert session.log.undo_label() == "Add error label for Email"
        assert "emailEditError" in _order(session)
        held = len(session.log.entries())
        fixes[0].run(FixContext(diagnostic, session))
        assert len(session.log.entries()) == held


def test_outline_appends_the_rule_once() -> None:
    with desk() as (session, pane):
        _select(session, pane, "emailEdit")
        line = _child(pane, QWidget, "formBuilder.checks.outlineLine")
        assert line.isHidden()
        _add(pane, "required", lambda pane: None)
        assert not line.isHidden()
        words = _child(pane, QLabel, "formBuilder.checks.outlineWords")
        assert words.text() == "Fields that fail a check get no outline yet."
        before = len(session.log.entries())
        _child(pane, QPushButton, "formBuilder.checks.outline").click()
        pump()
        assert session.log.undo_label() == "Add the red outline style"
        assert len(session.log.entries()) == before + 1
        sheet = session.document.root.value("styleSheet")
        assert isinstance(sheet, StringValue)
        assert sheet.text == _OUTLINE
        assert line.isHidden()
        _child(pane, QPushButton, "formBuilder.checks.outline").click()
        pump()
        assert len(session.log.entries()) == before + 1
        assert session.document.root.value("styleSheet").text == _OUTLINE  # type: ignore[union-attr]


def test_badge_counts_the_stored_checks() -> None:
    from app.features.form_builder.qtside.canvas.layers.badge_kinds import default_registry as badges

    with desk() as (session, pane):
        _select(session, pane, "emailEdit")
        node = _widget(session, "emailEdit")
        kind = next(item for item in badges().ordered() if item.kind_id == "checks")
        assert kind.order == 200
        assert kind.glyph == "\u2713"
        assert kind.glyph != "\u203a"
        assert kind.applies(node, None) is False
        _add(pane, "required", lambda pane: None)
        _add(pane, "email", lambda pane: None)
        node = _widget(session, "emailEdit")
        assert kind.applies(node, None) is True
        assert kind.sentence(node, None) == "2 checks"


def _between(pane: QWidget) -> None:
    _line(pane, "formBuilder.checks.min").setText("1")
    _line(pane, "formBuilder.checks.max").setText("10")


def _spin_between(pane: QWidget) -> None:
    _line(pane, "formBuilder.checks.min").setText("1")
    _line(pane, "formBuilder.checks.max").setText("9")


def _length(pane: QWidget) -> None:
    _line(pane, "formBuilder.checks.min").setText("2")
    _line(pane, "formBuilder.checks.max").setText("8")


def _pattern(pane: QWidget) -> None:
    _line(pane, "formBuilder.checks.pattern").setText("code")


def _one_of(pane: QWidget) -> None:
    _line(pane, "formBuilder.checks.values").setText("red, blue")


def _formula(pane: QWidget) -> None:
    from app.features.form_builder.qtside.formula import FormulaEditor

    page = _child(pane, QWidget, "formBuilder.checks.page")
    editors = [item for item in page.findChildren(FormulaEditor) if item.isVisible()]
    assert len(editors) == 1
    editors[0].show_text("True")
    _line(pane, "formBuilder.checks.message").setText("Must pass")
    pump()
    commit = _child(pane, QPushButton, "formBuilder.checks.commit")
    assert commit.isEnabled(), editors[0].status_text()
