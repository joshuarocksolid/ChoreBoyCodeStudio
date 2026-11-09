"""RefIndex matches references_to, and asks only for the spoken roles."""

from __future__ import annotations

from typing import FrozenSet, Tuple

import pytest

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import (
    AddActionRef,
    AddConnection,
    CreateAction,
    DeleteNodes,
    Rename,
    SetBuddy,
    SetButtonGroup,
    SetTabStops,
    SetZOrder,
)
from app.features.form_builder.engine.commands.log import CommandLog
from app.features.form_builder.engine.commands.placement import InActionList
from app.features.form_builder.engine.ids import IdAllocator, NodeId
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.query.ref_index import NameUse, RefIndex
from app.features.form_builder.engine.query.tree import references_to
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.spec import NodeSpec
from tests.form_builder.engine.commands._support import BOX, FREE, SHARED, nid, open_log

_SPOKEN = frozenset({"buddy", "connection.sender", "connection.receiver", "promoted_page"})
_SILENT = frozenset({"tabstop", "zorder", "action.menu", "addaction", "buttonGroup"})
_REPORTED = _SILENT | frozenset({"buddy", "connection.sender", "connection.receiver"})


def _read(text: str) -> UiDocument:
    return read_ui(text, allocator=IdAllocator()).document


def _snapshot(index: RefIndex) -> FrozenSet[Tuple[object, ...]]:
    found = []
    for name in index.targeted_names():
        for use in index.uses(name):
            found.append(
                (
                    name,
                    int(use.owner),
                    use.role,
                    use.target,
                    use.signal,
                    use.slot,
                    use.direction,
                    use.promoted_class,
                    use.page_number,
                    use.page_title,
                )
            )
    return frozenset(found)


def _referenced() -> CommandLog:
    log = open_log(FREE)
    doc = log.document
    button = nid(doc, "okButton")
    label = nid(doc, "label")
    log.execute(SetBuddy(label, "okButton"))
    log.execute(SetTabStops(("okButton",)))
    log.execute(SetZOrder(doc.root.id, ("okButton", "label")))
    log.execute(AddConnection("okButton", "clicked", "label", "clear"))
    log.execute(AddActionRef(InActionList(doc.root.id, 0), "okButton"))
    log.execute(CreateAction(NodeSpec("action", None, (("name", "openFile"), ("menu", "okButton")))))
    log.execute(SetButtonGroup((button,), "groupA"))
    return log


def test_every_references_to_hit_is_a_use() -> None:
    doc = _referenced().document
    reported = []
    for name in sorted(doc.names()):
        for owner, role in references_to(doc, name):
            reported.append((name, owner, role))
    assert {role for _name, _owner, role in reported} == _REPORTED
    index = RefIndex()
    index.rebuild(doc)
    for name, owner, role in reported:
        assert (owner, role) in {(use.owner, use.role) for use in index.uses(name)}


def test_confirmable_asks_only_for_spoken_roles() -> None:
    doc = _referenced().document
    index = RefIndex()
    index.rebuild(doc)
    for name in doc.names():
        asked = {(use.owner, use.role) for use in index.confirmable(name)}
        for use in index.uses(name):
            pair = (use.owner, use.role)
            if use.role in _SILENT:
                assert pair not in asked
            if use.role in _SPOKEN:
                assert pair in asked


def _host_form(host_class: str, attr: str, extra_custom: str) -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <widget class="%s" name="tabs">
   <widget class="QWidget" name="plainPage">
    <attribute name="title"><string>Plain</string></attribute>
   </widget>
   <widget class="InvoicePage" name="settingsPage">
    <attribute name="%s"><string>Settings</string></attribute>
   </widget>
  </widget>
 </widget>
 <customwidgets>
  <customwidget>
   <class>InvoicePage</class>
   <extends>QWidget</extends>
   <header>invoice.h</header>
  </customwidget>
  %s
 </customwidgets>
 <resources/>
 <connections/>
</ui>
""" % (host_class, attr, extra_custom)


_MY_TABS = """<customwidget>
   <class>MyTabs</class>
   <extends>QTabWidget</extends>
   <header>tabs.h</header>
  </customwidget>"""


@pytest.mark.parametrize(
    ("host_class", "attr", "extra"),
    [
        ("QTabWidget", "title", ""),
        ("MyTabs", "title", _MY_TABS),
        ("QToolBox", "label", ""),
    ],
)
def test_promoted_page_is_confirmable(host_class: str, attr: str, extra: str) -> None:
    doc = _read(_host_form(host_class, attr, extra))
    index = RefIndex()
    index.rebuild(doc)
    assert index.uses("plainPage") == ()
    uses = index.uses("settingsPage")
    assert len(uses) == 1
    use = uses[0]
    custom = doc.custom_widget("InvoicePage")
    assert custom is not None
    assert use == NameUse(
        custom.id,
        "promoted_page",
        "settingsPage",
        promoted_class="InvoicePage",
        page_number=2,
        page_title="Settings",
    )
    assert index.confirmable("settingsPage") == uses
    assert references_to(doc, "settingsPage") == ()


_EMAIL = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <widget class="QLabel" name="emailLabel">
   <property name="text"><string>Email:</string></property>
   <property name="buddy"><cstring>email</cstring></property>
  </widget>
  <widget class="QLineEdit" name="email"/>
  <widget class="QPushButton" name="Invoice">
   <property name="text"><string>Save</string></property>
  </widget>
  <widget class="QLineEdit" name="spare"/>
 </widget>
 <tabstops>
  <tabstop>email</tabstop>
  <tabstop>spare</tabstop>
 </tabstops>
 <resources/>
 <connections>
  <connection>
   <sender>email</sender>
   <signal>returnPressed()</signal>
   <receiver>Invoice</receiver>
   <slot>accept()</slot>
  </connection>
  <connection>
   <sender>email</sender>
   <signal>textChanged(QString)</signal>
   <receiver>Invoice</receiver>
   <slot>clear()</slot>
  </connection>
 </connections>
</ui>
"""


_SECOND_CONNECTION = """  <connection>
   <sender>email</sender>
   <signal>textChanged(QString)</signal>
   <receiver>Invoice</receiver>
   <slot>clear()</slot>
  </connection>
"""


def _email_index(text: str) -> Tuple[UiDocument, RefIndex]:
    doc = _read(text)
    index = RefIndex()
    index.rebuild(doc)
    return doc, index


def test_confirm_prose_for_a_sender() -> None:
    doc, index = _email_index(_EMAIL.replace(_SECOND_CONNECTION, ""))
    prose = index.ask_sentence(doc, "email", ())
    assert prose == (
        "email is used by: the buddy of \u201cEmail:\u201d, "
        "1 connection (email \u00b7 returnPressed \u2192 Invoice \u00b7 accept)"
    )


def test_confirm_prose_for_a_receiver() -> None:
    doc, index = _email_index(_EMAIL.replace(_SECOND_CONNECTION, ""))
    prose = index.ask_sentence(doc, "Invoice", ())
    assert prose == "Invoice is used by: 1 connection (email \u00b7 returnPressed \u2192 Invoice \u00b7 accept)"


def test_confirm_prose_pluralizes_connections() -> None:
    doc = _read(_EMAIL)
    index = RefIndex()
    index.rebuild(doc)
    prose = index.ask_sentence(doc, "email", ())
    assert prose == (
        "email is used by: the buddy of \u201cEmail:\u201d, "
        "2 connections (email \u00b7 returnPressed \u2192 Invoice \u00b7 accept; "
        "email \u00b7 textChanged \u2192 Invoice \u00b7 clear)"
    )


class _Rules:
    def references(self, doc: UiDocument, name: str) -> Tuple[Tuple[NodeId, str], ...]:
        if name != "spare":
            return ()
        return ((nid(doc, "emailLabel"), "cbcsValidate"),)


def test_a_tab_stop_alone_does_not_ask() -> None:
    doc = _read(_EMAIL)
    index = RefIndex()
    index.rebuild(doc)
    assert any(use.role == "tabstop" for use in index.uses("spare"))
    assert index.ask_sentence(doc, "spare", ()) == ""


def test_a_participant_line_asks() -> None:
    doc = _read(_EMAIL)
    index = RefIndex()
    index.rebuild(doc)
    prose = index.ask_sentence(doc, "spare", (_Rules(),))
    assert prose == "spare is used by: a rule on \u201cEmail:\u201d (cbcsValidate)"


def _check(index: RefIndex, log: CommandLog, pending: list) -> None:
    assert pending
    index.apply(log.document, pending[-1])
    fresh = RefIndex()
    fresh.rebuild(log.document)
    assert _snapshot(index) == _snapshot(fresh)


def test_index_matches_a_rebuild_after_each_edit() -> None:
    log = open_log(FREE)
    index = RefIndex()
    index.rebuild(log.document)
    pending: list = []
    log.subscribe(lambda change_set: pending.append(change_set), priority=0)
    label = nid(log.document, "label")
    button = nid(log.document, "okButton")
    log.execute(SetBuddy(label, "okButton"))
    _check(index, log, pending)
    log.execute(AddConnection("okButton", "clicked", "label", "clear"))
    _check(index, log, pending)
    log.execute(Rename(button, "submitButton"))
    _check(index, log, pending)
    assert any(use.role == "buddy" and use.target == "submitButton" for use in index.uses("submitButton"))
    log.execute(DeleteNodes((label,)))
    _check(index, log, pending)
    assert log.undo()
    _check(index, log, pending)


def test_shared_rename_keeps_the_edge_on_the_old_name() -> None:
    log = open_log(SHARED)
    index = RefIndex()
    index.rebuild(log.document)
    pending: list = []
    log.subscribe(lambda change_set: pending.append(change_set), priority=0)
    target = log.document.by_name("same")[0]
    log.execute(Rename(target, "other"))
    _check(index, log, pending)
    assert any(use.role == "buddy" and use.target == "same" for use in index.uses("same"))
    assert all(use.role != "buddy" for use in index.uses("other"))


def test_session_index_follows_a_rename() -> None:
    session = FormSession.open(FREE, path="/tmp/outline-refs.ui", scope=FormScope(kind="external", ui_path="/tmp/outline-refs.ui"))
    try:
        label = nid(session.document, "label")
        button = nid(session.document, "okButton")
        session.log.execute(SetBuddy(label, "okButton"))
        session.log.execute(Rename(button, "submitButton"))
        fresh = RefIndex()
        fresh.rebuild(session.document)
        assert _snapshot(session.refs) == _snapshot(fresh)
        assert any(use.role == "buddy" for use in session.refs.uses("submitButton"))
        assert session.refs.uses("okButton") == ()
    finally:
        session.dispose()


def test_session_base_methods_refuse_close() -> None:
    session = FormSession.open(BOX, path="/tmp/outline-names.ui", scope=FormScope(kind="external", ui_path="/tmp/outline-names.ui"))
    try:
        session.set_base_methods(frozenset({"close", "show", "update", "accept", "reject", "done", "print"}))
        with pytest.raises(CommandRejected) as caught:
            session.log.execute(Rename(nid(session.document, "label"), "close"))
        assert caught.value.code == "FB204"
        assert str(caught.value) == "\u201cclose\u201d would replace a method of the window. Try closeButton."
        assert session.document.by_name("label")
    finally:
        session.dispose()
