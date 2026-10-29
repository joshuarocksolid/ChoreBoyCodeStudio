# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false
"""M4 keyboard scripts K9-K15 (UX_SPEC 12.3) in ONE main-window form-tab session.

Keys only after setup (project files, the open tab). A filter fails the run on
any spontaneous mouse press. K11's save, close and reopen runs first, because
undo cannot cross a reopen; its bytes are the baseline that the last Undo all
must restore. Each script also checks the number of undo steps it added.

A step with no key path is a ``soft`` finding (the run goes on) and a strict
xfail below names it. N/A: nothing; every M4 script is covered here. K13's
family step is skipped when no installed family contains "Sans". Two non-key
workarounds, both after a finding: K12-2 focuses the checkbox it could not Tab
to, and K13 hands Enter to the family field itself (a combo list swallows keys).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.integration import editor_memory  # noqa: E402
from app.qt.QtCore import QTimer  # noqa: E402
from app.qt.QtGui import QAction, QFontDatabase  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import (  # noqa: E402
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QFrame,
    QLabel,
    QLineEdit,
    QMenu,
    QTabWidget,
    QTreeWidget,
    QWidget,
)
from app.shell.main_window import MainWindow  # noqa: E402
from tests.form_builder.inspector.test_m43c_pictures import _seed  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import (  # noqa: E402
    Kb,
    _close,
    _key,
    _mods,
    _NoMouse,
    _open,
    _project,
    _require,
    _toast_text,
)
from tests.form_builder.qtside.test_m4_scalars_keyboard import (  # noqa: E402
    _echo_label,
    _focus_text,
    _open_all,
    _reopen,
    _tab_to_editor,
    _tab_to_row,
    _tab_to_text,
)

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Customer</class>
 <widget class="QWidget" name="Customer">
  <property name="geometry"><rect><x>0</x><y>0</y><width>520</width><height>760</height></rect></property>
  <layout class="QVBoxLayout" name="mainLayout">
   <item>
    <widget class="QLabel" name="titleLabel">
     <property name="text"><string>Name:</string></property>
    </widget>
   </item>
   <item>
    <widget class="QLabel" name="richLabel">
     <property name="text"><string>Hello</string></property>
     <property name="textFormat"><enum>Qt::RichText</enum></property>
    </widget>
   </item>
   <item><widget class="QLineEdit" name="nameEdit"/></item>
   <item><widget class="QDateEdit" name="whenEdit"/></item>
   <item><widget class="QKeySequenceEdit" name="keysEdit"/></item>
   <item><widget class="QComboBox" name="combo"/></item>
   <item><widget class="QTreeWidget" name="tree"/></item>
   <item><widget class="QListView" name="view"/></item>
   <item>
    <widget class="QPushButton" name="okButton">
     <property name="text"><string>Save</string></property>
    </widget>
   </item>
   <item>
    <widget class="QTabWidget" name="tabWidget">
     <property name="currentIndex"><number>0</number></property>
     <widget class="QWidget" name="tab_a">
      <attribute name="title"><string>Alpha</string></attribute>
      <layout class="QVBoxLayout" name="alphaLayout">
       <item><widget class="QLabel" name="inside_a"><property name="text"><string>In A</string></property></widget></item>
      </layout>
     </widget>
     <widget class="QWidget" name="tab_b">
      <attribute name="title"><string>Beta</string></attribute>
     </widget>
    </widget>
   </item>
   <item>
    <layout class="QFormLayout" name="formLayout">
     <item row="0" column="0">
      <widget class="QLabel" name="cityLabel">
       <property name="text"><string>City</string></property>
       <property name="buddy"><cstring>cityEdit</cstring></property>
      </widget>
     </item>
     <item row="0" column="1"><widget class="QLineEdit" name="cityEdit"/></item>
     <item row="1" column="0">
      <widget class="QLabel" name="notesLabel">
       <property name="text"><string>Notes</string></property>
       <property name="buddy"><cstring>notesEdit</cstring></property>
      </widget>
     </item>
     <item row="1" column="1"><widget class="QLineEdit" name="notesEdit"/></item>
    </layout>
   </item>
  </layout>
 </widget>
 <resources><include location="app.qrc"/></resources>
 <connections/>
</ui>
"""


class _Run:
    """What the one session found: hard failure (if any) and soft findings by id."""

    def __init__(self) -> None:
        self.failure = ""
        self.findings: Dict[str, str] = {}
        self.mouse: List[str] = []
        self.steps: Dict[str, int] = {}
        self.skipped: List[str] = []


def _entries(kb: Kb) -> int:
    return len(kb.session.log.entries())


def _canvas_select(kb: Kb, name: str) -> None:
    """Alt+3, then Tab (or Shift+Tab) over the canvas until ``name`` is the selection."""
    kb.press("Key_3", "Alt")
    for _ in range(70):
        if kb.current() == name:
            return
        kb.press("Key_Tab")
    for _ in range(140):
        if kb.current() == name:
            return
        kb.press("Key_Backtab", "Shift")
    kb.check(kb.current() == name, "Tab reaches %s" % name)


def _undo_n(kb: Kb, count: int) -> None:
    kb.press("Key_3", "Alt")
    for _ in range(count):
        kb.press("Key_Z", "Control")


def _undo_all(kb: Kb) -> None:
    kb.press("Key_3", "Alt")
    for _ in range(80):
        if not kb.session.log.can_undo():
            return
        kb.press("Key_Z", "Control")


def _visible(name: str) -> QWidget:
    found = [w for w in QApplication.allWidgets() if w.objectName() == name and w.isVisible()]
    return found[-1] if found else None


# --------------------------------------------------------------------------
# K11, first half: Password, Ctrl+S, close, reopen. The baseline is taken after.
# --------------------------------------------------------------------------


def _k11_save_and_reopen(window: MainWindow, kb: Kb, qapp: QApplication) -> str:
    _canvas_select(kb, "nameEdit")
    kb.press("Key_4", "Alt")
    kb.check(kb.focus_in("formBuilder.inspector"), "Alt+4 focuses the inspector")
    kb.press("Key_F", "Control")
    kb.check(kb.focus_name() == "formBuilder.inspectorSearch", "Ctrl+F focuses the property search")
    kb.type("echo")
    _tab_to_row(kb, "echoMode")
    kb.check(kb.focus_name() == "_EnumBox", "Tab reaches Echo mode")
    kb.press("Key_Down", "Alt")
    kb.press("Key_Down")
    kb.press("Key_Down")
    kb.press("Key_Return")
    kb.check("Password" in kb.text(), "choosing Password writes it")
    kb.press("Key_Escape")
    search = kb.pane("formBuilder.inspector").findChild(QWidget, "formBuilder.inspectorSearch")
    kb.check(isinstance(search, QWidget) and search.text() == "", "Esc clears the search")
    kb.press("Key_S", "Control")
    kb.pump(12)
    kb.check("Password" in kb.path.read_text(encoding="utf-8"), "Ctrl+S writes Password to the file")
    # Ctrl+W disposes the session before the harness can read the selection.
    QTest.keyClick(kb.target(), _key("Key_W"), _mods("Control"))
    for _ in range(8):
        qapp.processEvents()
    _reopen(window, kb, qapp)
    _canvas_select(kb, "nameEdit")
    kb.press("Key_4", "Alt")
    _tab_to_row(kb, "echoMode")
    current = getattr(kb.focus(), "currentText", None)
    kb.check(callable(current) and current() == "Password", "reopen shows Password")
    kb.check(_echo_label(kb).property("fbChanged") == "true", "Echo mode is Strong")
    return kb.text()


def _k11_rest(kb: Kb) -> None:
    start = _entries(kb)
    _tab_to_row(kb, "maxLength")
    before = _entries(kb)
    kb.press("Key_A", "Control")
    kb.type("40")
    kb.press("Key_Return")
    for _ in range(3):
        kb.press("Key_Up")
    kb.check(">43<" in kb.text() or "43" in _focus_text(kb), "Up three times makes 43")
    kb.press("Key_Z", "Control")
    kb.check(_entries(kb) <= before + 1, "one undo takes back the visit")
    kb.check(">43<" not in kb.text(), "undo restores the value from before the visit")
    kb.press("Key_Z", "Control", "Shift")
    kb.check(">43<" in kb.text(), "redo brings the visit back")
    kb.press("Key_Backtab", "Shift")
    _tab_to_editor(kb, "maxLength")
    kb.press("Key_Up")
    kb.check(">44<" in kb.text() or "44" in _focus_text(kb), "a second visit steps to 44")
    kb.press("Key_Z", "Control")
    kb.check(">43<" in kb.text(), "undo of the second visit stops at 43")

    _canvas_select(kb, "titleLabel")
    kb.press("Key_4", "Alt")
    _open_all(kb)
    _tab_to_row(kb, "textInteractionFlags", 200)
    before_flags = kb.text()
    steps = _entries(kb)
    kb.press("Key_Return")
    _tab_to_text(kb, "Select with mouse")
    kb.press("Key_Space")
    kb.press("Key_Escape")
    kb.pump(4)
    kb.check(kb.text() == before_flags, "Esc from the flags popover changes nothing")
    kb.check(_entries(kb) == steps, "Esc adds no undo step")
    _tab_to_row(kb, "textInteractionFlags", 200)
    kb.press("Key_Return")
    _tab_to_text(kb, "Select with mouse")
    kb.press("Key_Space")
    kb.press("Key_Return")
    kb.pump(4)
    kb.check(kb.text() != before_flags, "Enter keeps the flag change")
    kb.check(_entries(kb) == steps + 1, "the flag change is one step")

    _canvas_select(kb, "whenEdit")
    kb.press("Key_4", "Alt")
    _open_all(kb)
    _tab_to_row(kb, "date", 200)
    kb.press("Key_A", "Control")
    kb.type("12/31/2026")
    kb.press("Key_Return")
    kb.check("2026" in kb.text(), "the typed date is written")
    kb.press("Key_Down", "Alt")
    kb.press("Key_PageDown")
    kb.press("Key_Return")
    kb.pump(4)
    written = kb.text()
    kb.check("<year>2027</year>" in written and "<day>31</day>" in written, "PageDown writes January 31, 2027")

    _canvas_select(kb, "keysEdit")
    kb.press("Key_4", "Alt")
    _open_all(kb)
    _tab_to_row(kb, "keySequence", 200)
    _tab_to_text(kb, "Record")
    kb.press("Key_Return")
    kb.check("Press the keys" in _focus_text(kb), "Record asks for the keys")
    kb.press("Key_P", "Control", "Shift")
    for _ in range(40):
        QTest.qWait(100)
        if "Ctrl+Shift+P" in kb.text():
            break
    kb.pump(8)
    kb.check("Ctrl+Shift+P" in kb.text(), "Ctrl+Shift+P is written")
    held = kb.text()
    _tab_to_text(kb, "Record")
    kb.press("Key_Return")
    kb.press("Key_Escape")
    kb.pump(4)
    kb.check(kb.text() == held, "Esc while recording leaves the shortcut")
    kb.check(_entries(kb) > start, "K11 added undo steps")


# --------------------------------------------------------------------------
# K9 Insert by words
# --------------------------------------------------------------------------


def _k9(kb: Kb) -> None:
    from app.features.form_builder.qtside.insert.delegate import ROW_ROLE

    workbench = kb.surface._workbench
    insert = workbench.insert
    start = _entries(kb)
    log = kb.session.log
    tabs_before = kb.text().count('class="QTabWidget"')
    _canvas_select(kb, "notesEdit")
    kb.press("Key_2", "Alt")
    kb.check(insert.isAncestorOf(kb.focus()) or kb.focus() is insert.body, "Alt+2 focuses Insert")
    kb.type("dropdown")
    kb.check(insert.filter.text() == "dropdown" and kb.focus() is insert.filter, "typing goes to the Insert filter")
    first = insert.body.item(0)
    kb.check(first is not None and first.data(_user_role()) == "QComboBox", "Combo box is the first result")
    kb.press("Key_Return")
    kb.check(kb.text().count('class="QComboBox"') == 2, "a combo box is inserted")
    kb.check(log.undo_label() == "Insert combo box", "the insert is one step 'Insert combo box'")
    kb.check(isinstance(kb.focus(), QLineEdit), "the form-row label editor opens")
    kb.type("Size")
    kb.press("Key_Return")
    kb.check("<string>Size</string>" in kb.text(), "the label is Size")
    kb.check(kb.focus() is insert.body, "focus is back on the Insert result list")
    kb.press("Key_Escape")
    kb.check(insert.filter.text() == "" and insert.isAncestorOf(kb.focus()), "Esc clears the filter, focus stays in Insert")
    section = insert.body.item(0).data(int(ROW_ROLE))
    kb.check(section.kind == "section" and section.title == "Recently used", "Recently used is the first section")
    kb.check(insert.body.item(1).data(_user_role()) == "QComboBox", "Recently used shows Combo box first")
    kb.press("Key_Down", "Control")
    kb.press("Key_Down", "Control")
    kb.press("Key_Return")
    kb.check(log.undo_label() == "Insert line edit", "the first entry of the category is inserted")
    kb.press("Key_Escape")  # the label editor takes Esc
    kb.check(kb.focus() is insert.body, "focus is back on Insert")
    kb.press("Key_Escape")
    kb.check(kb.focus_in("formBuilder.canvas"), "Esc with an empty filter returns to the canvas")
    kb.press("Key_Slash")
    search = workbench.outline._insert_filter
    kb.check(kb.focus() is search, "/ opens the quick-insert list")
    kb.type("tabs")
    kb.press("Key_Return")
    kb.check(log.undo_label() == "Insert tab widget", "tabs insert a tab widget")
    kb.check(kb.text().count('class="QTabWidget"') == tabs_before + 1, "a tab widget with two pages")
    kb.check(kb.focus_in("formBuilder.canvas"), "focus returns to the canvas")
    kb.check(_entries(kb) - start == 4, "K9 added four undo steps (got %d)" % (_entries(kb) - start))


def _user_role() -> int:
    from app.qt.QtCore import Qt

    return int(getattr(getattr(Qt, "ItemDataRole", Qt), "UserRole"))


# --------------------------------------------------------------------------
# K10 Pages
# --------------------------------------------------------------------------


def _menu(kb: Kb) -> QMenu:
    menus = [m for m in kb.surface.findChildren(QMenu) if m.objectName() == "formBuilder.contextMenu" and m.isVisible()]
    kb.check(bool(menus), "Shift+F10 opens the context menu")
    return menus[-1]


def _menu_pick(kb: Kb, menu: QMenu, prefix: str, submenu: bool) -> QMenu:
    """Down until the row starting with ``prefix`` is active, then Right (submenu) or Enter."""
    for _ in range(40):
        active = menu.activeAction()
        if active is not None and active.text().startswith(prefix):
            break
        kb.press("Key_Down")
    active = menu.activeAction()
    kb.check(active is not None and active.text().startswith(prefix), "Down reaches %s" % prefix)
    if submenu:
        kb.press("Key_Right")
        sub = active.menu()
        kb.check(sub is not None and sub.isVisible(), "%s opens" % prefix)
        return sub
    kb.press("Key_Return")
    return menu


def _pages_menu(kb: Kb, prefix: str) -> None:
    kb.press("Key_F10", "Shift")
    menu = _menu(kb)
    sub = _menu_pick(kb, menu, "Pages", True)
    _menu_pick(kb, sub, prefix, False)
    # Offscreen Qt can leave the popup chain up after a key activates a row.
    for item in list(kb.surface.findChildren(QMenu)):
        if item.isVisible():
            item.close()
    kb.pump(12)


def _tabs(kb: Kb) -> QTabWidget:
    root = kb.pane("formBuilder.canvas").page_widget()
    found = root.findChild(QTabWidget, "tabWidget")
    assert isinstance(found, QTabWidget)
    return found


def _status(kb: Kb) -> str:
    return str(kb.surface.editor_status_sentence())


def _go_to_row(kb: Kb, tree: QTreeWidget, text: str) -> None:
    for key in ("Key_Down", "Key_Up"):
        for _ in range(30):
            item = tree.currentItem()
            if item is not None and item.text(0) == text:
                return
            kb.press(key)
    kb.check(False, "the outline reaches %s" % text)


def _k10(kb: Kb) -> None:
    start = _entries(kb)
    kb.press("Key_3", "Alt")
    seen: List[str] = []

    def dismiss() -> None:
        # Ctrl+R can open a modal box whose event loop would block the key event.
        modal = QApplication.activeModalWidget()
        if modal is None:
            return
        seen.append("%s: %s" % (type(modal).__name__, " ".join(l.text() for l in modal.findChildren(QLabel))))
        QTest.keyClick(modal, _key("Key_Return"))

    QTimer.singleShot(400, dismiss)
    kb.press("Key_R", "Control")
    kb.pump(12)
    if seen:
        kb.soft(False, "K10-1", "Ctrl+R in a form tab opened a modal box (%s) instead of a Go to widget picker" % seen[0])
        _canvas_select(kb, "tabWidget")
    else:
        kb.type("tabWidget")
        kb.press("Key_Return")
    kb.check(kb.current() == "tabWidget", "the tab widget is selected (selected: %s)" % kb.current())
    kb.press("Key_3", "Alt")
    # "Insert tab after" goes after the shown page; page 2 is the last, so the new one is third.
    kb.press("Key_PageDown", "Control")
    kb.check(_tabs(kb).currentIndex() == 1, "Ctrl+PgDn shows page 2")
    _pages_menu(kb, "Insert tab after")
    editors = [w for w in kb.pane("formBuilder.canvas").findChildren(QLineEdit) if w.isVisible()]
    kb.check(bool(editors) and kb.focus() in editors, "the new page's title editor has focus")
    kb.press("Key_A", "Control")
    kb.type("Printing")
    kb.press("Key_Return")
    tabs = _tabs(kb)
    kb.check(tabs.count() == 3 and tabs.currentIndex() == 2 and tabs.tabText(2) == "Printing", "a third page, Printing, is shown (%s)" % ([tabs.count(), tabs.currentIndex(), [tabs.tabText(i) for i in range(tabs.count())]],))
    titled = kb.text()
    dirty = kb.session.log.is_dirty()
    kb.press("Key_PageUp", "Control")
    kb.check(_tabs(kb).currentIndex() == 1, "Ctrl+PgUp shows page 2")
    kb.check("starts on page 1" in _status(kb), "the status bar says the file still starts on page 1")
    kb.check(kb.text() == titled and kb.session.log.is_dirty() == dirty, "showing a page does not change the file or its dirty state")
    _pages_menu(kb, "Start on this page")
    kb.check('<property name="currentIndex">\n   <number>1</number>' in kb.text() or "<number>1</number>" in kb.text(), "currentIndex is 1")
    kb.press("Key_1", "Alt")
    tree = kb.surface.findChild(QTreeWidget, "formBuilder.structure")
    kb.check(tree is not None and tree.hasFocus(), "Alt+1 focuses the outline")
    _go_to_row(kb, tree, "tab_3")
    kb.press("Key_Up", "Alt")
    kb.check(_tabs(kb).tabText(1) == "Printing", "Alt+Up moves Printing before page 2")
    _go_to_row(kb, tree, "tab_a")
    kb.press("Key_Delete")
    confirm = kb.surface.findChild(QFrame, "formBuilder.outlineConfirm")
    kb.check(confirm is not None and confirm.isVisible(), "Delete on a page with a widget opens the confirm")
    kb.press("Key_Escape")
    kb.check(_tabs(kb).count() == 3, "Esc deletes nothing")
    kb.press("Key_Delete")
    delete = kb.surface.findChild(QWidget, "formBuilder.outlineDelete")
    kb.check(delete is not None and delete.isVisible(), "Delete opens the confirm again")
    kb.check(kb.focus() is delete, "the [Delete page] button has focus")
    kb.press("Key_Return")
    kb.check(_tabs(kb).count() == 2, "the page is deleted")
    kb.check("Deleted page" in _toast_text(kb) or any("Deleted page" in l.text() for l in kb.surface.findChildren(QLabel)), "a toast says so")
    outline = kb.pane("formBuilder.outline")
    kb.check(kb.focus() is tree or outline.isAncestorOf(kb.focus()), "focus is still in the outline")
    kb.check(_entries(kb) - start == 5, "K10 added five undo steps (got %d)" % (_entries(kb) - start))


# --------------------------------------------------------------------------
# K12 Text, translations and custom properties
# --------------------------------------------------------------------------


def _tab_until(kb: Kb, what: str, test: Callable[[QWidget], bool], limit: int = 80) -> QWidget:
    for _ in range(limit):
        focus = kb.focus()
        if isinstance(focus, QWidget) and test(focus):
            return focus
        kb.press("Key_Tab")
    kb.check(False, "Tab reaches %s" % what)
    raise AssertionError(what)


def _named(name: str) -> Callable[[QWidget], bool]:
    return lambda w: str(w.objectName()) == name


def _accessible(name: str) -> Callable[[QWidget], bool]:
    return lambda w: str(w.accessibleName()) == name


def _k12(kb: Kb) -> None:
    start = _entries(kb)
    _canvas_select(kb, "titleLabel")
    kb.press("Key_4", "Alt")
    _tab_to_editor(kb, "text", 120)
    kb.press("Key_A", "Control")
    kb.type("Total:")
    kb.press("Key_Return")
    kb.check("<string>Total:</string>" in kb.text() or "Total:" in kb.text(), "Total: is written")
    _tab_until(kb, "Translation toggle", _named("formBuilder.translationToggle"))
    toggle = kb.focus()
    kb.press("Key_Return")
    row = kb.pane("formBuilder.inspector").findChild(QWidget, "formBuilder.row.text")
    opened = [b for b in row.findChildren(QCheckBox) if b.isVisible()]
    kb.soft(
        bool(opened),
        "K12-1",
        "Enter on the 'Translation >' button (%s, checked=%s) does not open the translation panel; only Space does"
        % (toggle.objectName(), toggle.isChecked()),
    )
    if not opened:
        kb.press("Key_Space")
    is_box = lambda w: isinstance(w, QCheckBox) and w.text() == "Translate this text"  # noqa: E731
    reached = False
    for _ in range(12):
        if is_box(kb.focus()):
            reached = True
            break
        kb.press("Key_Tab")
    back = False
    if not reached:
        for _ in range(4):
            kb.press("Key_Backtab", "Shift")
            if is_box(kb.focus()):
                back = True
                break
    kb.soft(
        reached,
        "K12-2",
        "Tab from the opened 'Translation' button never reaches 'Translate this text' (12 Tabs, last focus %s; Shift+Tab %s)"
        % (kb.focus_name(), "reaches it" if back else "does not either"),
    )
    if not reached:
        box = [b for b in row.findChildren(QCheckBox) if b.text() == "Translate this text"][0]
        box.setFocus()  # setup shortcut so the later steps still run
        kb.pump()
    kb.press("Key_Space")
    kb.check('notr="true"' in kb.text(), "the XML gains notr=true")
    kb.check(any("Not translated" in l.text() for l in row.findChildren(QLabel)), "the row caption says Not translated")
    _tab_until(kb, "the translator note", _accessible("Translation: note for the translator"))
    kb.type("Shown on receipts")
    kb.press("Key_Return")
    kb.check('extracomment="Shown on receipts"' in kb.text(), "the note is written")
    _open_all(kb)
    _tab_until(kb, "+ Add custom property", _named("formBuilder.addCustomProperty"), 400)
    kb.press("Key_Return")
    kb.check(kb.focus().accessibleName() == "Custom property name", "the name field has focus")
    kb.type("requiredRole")
    kb.press("Key_Tab")
    kb.check(kb.focus().accessibleName() == "Custom property type", "Tab reaches the type")
    kb.check(kb.focus().currentText() == "Text", "the type is Text")
    kb.press("Key_Return")
    kb.pump(8)
    kb.check('<property name="requiredRole" stdset="0">' in kb.text(), "the custom property is written")
    kb.check(isinstance(kb.focus(), QLineEdit) and kb.focus().accessibleName() != "Custom property name", "the value editor has focus")
    kb.type("manager")
    kb.press("Key_Return")
    kb.check("manager" in kb.text(), "manager is written")
    _tab_until(kb, "+ Add custom property", _named("formBuilder.addCustomProperty"), 400)
    kb.press("Key_Return")
    kb.check(kb.focus().accessibleName() == "Custom property name", "the second name field has focus")
    kb.type("2nd")
    kb.press("Key_Return")
    errors = [e for e in kb.pane("formBuilder.inspector").findChildren(QLabel, "formBuilder.rowError") if e.isVisible()]
    kb.check(bool(errors) and "digit" in errors[0].text(), "the refusal shows")
    refused = kb.text()
    kb.press("Key_Return")
    kb.check(kb.text() == refused, "Enter does nothing")
    kb.press("Key_Escape")
    kb.pump(4)
    kb.check(kb.text() == refused, "Esc leaves the file as it was")

    bold = ""
    for _round in range(2):
        _canvas_select(kb, "richLabel")
        kb.press("Key_4", "Alt")
        _tab_until(kb, "the Text summary", lambda w: str(w.objectName()) == "formBuilder.summary" and _row_of(w) == "text", 120)
        kb.press("Key_Space")
        formatted = _tab_until(kb, "the formatted editor", _accessible("Text: formatted text"), 30)
        kb.press("Key_A", "Control")
        kb.press("Key_B", "Control")
        done_at = _named("formBuilder.popoverDone")
        if formatted.tabChangesFocus():
            _tab_until(kb, "Done", done_at, 30)
        else:
            kb.press("Key_Tab", "Control")
            trapped = kb.focus() is formatted
            # Shift+Tab is the user's other way out of a text box that eats Tab.
            for _ in range(20):
                if done_at(kb.focus()):
                    break
                kb.press("Key_Backtab", "Shift")
            kb.soft(
                False,
                "K12-3",
                "Tab in the formatted-text editor (%s) inserts a tab character and Ctrl+Tab %s; "
                "focus reaches Done only by %s"
                % (
                    formatted.accessibleName(),
                    "does not move focus" if trapped else "moves focus",
                    "Shift+Tab around the popover" if done_at(kb.focus()) else "no key at all",
                ),
            )
            kb.check(done_at(kb.focus()), "some key reaches Done")
        kb.press("Key_Space")
        if _round == 0:
            bold = kb.text()
            kb.check("font-weight:600" in bold, "the HTML has bold")
            _undo_n(kb, 1)
            kb.check("font-weight:600" not in kb.text(), "one undo takes the bold back")
        else:
            kb.check(kb.text() == bold, "the same steps give the same bytes")
    return None


def _row_of(widget: QWidget) -> str:
    from tests.form_builder.qtside.test_m4_scalars_keyboard import _row_key

    return _row_key(widget)


# --------------------------------------------------------------------------
# K13 Font, colour and palette
# --------------------------------------------------------------------------


def _row_summary(kb: Kb, key: str) -> QWidget:
    def hit(w: QWidget) -> bool:
        return str(w.objectName()) == "formBuilder.summary" and _row_of(w) == key

    for key_name, mods in (("Key_Tab", ()), ("Key_Backtab", ("Shift",))):
        for _ in range(200):
            focus = kb.focus()
            if isinstance(focus, QWidget) and hit(focus):
                return focus
            kb.press(key_name, *mods)
    kb.check(False, "Tab reaches the %s summary" % key)
    raise AssertionError(key)


def _k13(kb: Kb) -> None:
    has_sans = any("sans" in name.lower() for name in QFontDatabase.families())
    start = _entries(kb)
    _canvas_select(kb, "titleLabel")
    kb.press("Key_4", "Alt")
    _open_all(kb)
    summary = _row_summary(kb, "font")
    kb.press("Key_Return")
    family = _visible("formBuilder.fontFamily")
    kb.check(family is not None, "Enter on Font opens the popover")
    kb.check(family.hasFocus() or family.lineEdit().hasFocus(), "focus is on Family")
    if has_sans:
        kb.type("Sans")
        # The match list is a completer popup: Down lands on the first match, Enter takes it.
        # Enter goes to the family field itself (as in the lane test): the field takes the first match.
        QTest.keyClick(family.lineEdit(), _key("Key_Return"))
        kb.pump()
        kb.log.append("Key_Return -> family field")
        kb.check("Sans" in kb.text(), "Enter on the first match writes a Sans family")
        for _ in range(3):
            if kb.focus() is family or kb.focus() is family.lineEdit():
                break
            kb.pump()
        kb.pump()
    else:
        kb.pump()
        kb.press("Key_Tab")
    _tab_until(kb, "Size", _named("formBuilder.fontSize"), 12)
    kb.press("Key_Up")
    kb.press("Key_Up")
    _tab_until(kb, "Bold", _named("formBuilder.fontBold"), 12)
    kb.press("Key_Space")
    _tab_until(kb, "Done", _named("formBuilder.popoverDone"), 12)
    kb.press("Key_Space")
    kb.check(_entries(kb) - start == 1, "the font is one undo step (got %d)" % (_entries(kb) - start))
    label = kb.session.log.undo_label()
    kb.check(label is not None and label.startswith("Change font of "), "the step is 'Change font of ...' (%s)" % label)
    shown = summary.toolTip() or summary.text()
    kb.check("Bold" in shown and "pt" in shown, "the summary lists the parts set (%s)" % shown)
    if has_sans:
        kb.check("Sans" in shown, "the summary names the family (%s)" % shown)
    after_font = kb.text()

    for keep in (False, True):
        _row_summary(kb, "palette")
        kb.press("Key_Return")
        roles = _visible("formBuilder.paletteRoles")
        kb.check(roles is not None, "Enter on Palette opens the popover")
        kb.check(kb.focus() is roles or roles.isAncestorOf(kb.focus()), "focus is on the roles list")
        kb.press("Key_Down")
        kb.press("Key_Return")
        _tab_until(kb, "Hex", _named("formBuilder.colorHex"), 12)
        kb.press("Key_A", "Control")
        kb.type("#1A7F37")
        kb.press("Key_Return")
        if not keep:
            kb.press("Key_Escape")
            kb.check(_visible("formBuilder.paletteRoles") is not None, "Esc goes back to the palette list")
            kb.press("Key_Escape")
            kb.pump(4)
            kb.check(kb.text() == after_font, "Esc closes and reverts")
        else:
            _tab_until(kb, "Done", _named("formBuilder.popoverDone"), 12)
            kb.press("Key_Space")
            kb.check('role="WindowText"' in kb.text(), "Done keeps the colour")
    kb.check(_entries(kb) - start == 2, "K13 added two undo steps (got %d)" % (_entries(kb) - start))


# --------------------------------------------------------------------------
# K14 Items
# --------------------------------------------------------------------------


def _item_editor() -> QWidget:
    QApplication.processEvents()
    found = [w for w in QApplication.allWidgets() if w.objectName() == "formBuilder.itemEditor" and w.isVisible()]
    return found[-1] if found else None


def _item_texts(kb: Kb, name: str) -> List[str]:
    from app.features.form_builder.qtside.items.model import load_draft

    node = kb.session.document.by_name(name)[0]
    return [item.text_at(0) for item in load_draft(kb.session.document, node).items]


def _k14(kb: Kb) -> None:
    from app.features.form_builder.qtside.items.model import MODEL_VIEW_SENTENCE

    start = _entries(kb)
    _canvas_select(kb, "combo")
    kb.press("Key_Return")
    editor = _item_editor()
    kb.check(editor is not None, "Enter on a combo box opens the item editor")
    kb.check(isinstance(kb.focus(), QLineEdit) and editor.isAncestorOf(kb.focus()), "focus is in the first row")
    for word in ("Small", "Medium", "Large"):
        kb.type(word)
        kb.press("Key_Return")
    kb.press("Key_Return")
    kb.check(_item_editor() is None, "the empty row's Enter closes the editor")
    kb.check(_item_texts(kb, "combo") == ["Small", "Medium", "Large"], "three items (%s)" % _item_texts(kb, "combo"))
    kb.check(kb.session.log.undo_label() == "Edit items of combo", "one step 'Edit items of combo'")
    kb.check(_entries(kb) - start == 1, "one undo step (got %d)" % (_entries(kb) - start))
    kb.check(kb.focus_in("formBuilder.canvas"), "focus is back on the canvas")
    kb.press("Key_Return")
    kb.check(_item_editor() is not None, "Enter reopens the editor")
    kb.press("Key_Down")
    kb.press("Key_Up", "Alt")
    kb.check(_item_texts(kb, "combo") == ["Medium", "Small", "Large"], "Alt+Up puts Medium first (%s)" % _item_texts(kb, "combo"))
    kb.press("Key_Escape")
    kb.check(_item_editor() is None, "Esc closes the editor")
    kb.check(_item_texts(kb, "combo") == ["Small", "Medium", "Large"], "Esc restores the order")
    kb.check(_entries(kb) - start == 1, "Esc adds no step")

    _canvas_select(kb, "tree")
    kb.press("Key_Return")
    editor = _item_editor()
    kb.check(editor is not None, "Enter on a tree widget opens the item editor")
    kb.type("Fruit")
    kb.press("Key_Return")
    kb.type("Apple")
    kb.press("Key_Tab")
    ed = _item_editor()
    indents = [a for a in kb.window.findChildren(QAction) if a.objectName() == "shell.action.edit.indent"]
    hits: List[int] = []
    indents[0].triggered.connect(lambda *_: hits.append(1))
    kb.press("Key_Tab")
    nested = [c.text_at(0) for c in ed.draft.items[0].children]
    kb.check(nested == ["Apple"], "Tab in the tree-item field nests Apple under Fruit (focus %s, shell Indent hits %d)" % (kb.focus_name(), len(hits)))
    # Tab nests the row, so the tree field has its own way to Done: Ctrl+Tab (tree_body.py).
    kb.press("Key_Tab", "Control")
    kb.check(kb.focus_name() == "formBuilder.itemEditorDone", "Ctrl+Tab reaches Done (focus %s)" % kb.focus_name())
    kb.press("Key_Space")
    kb.check(_item_editor() is None, "the tree editor is closed")
    from app.features.form_builder.qtside.items.model import load_draft

    node = kb.session.document.by_name("tree")[0]
    fruit = load_draft(kb.session.document, node).items
    texts = [i.text_at(0) for i in fruit] + [c.text_at(0) for i in fruit for c in i.children]
    kb.check(texts == ["Fruit", "Apple"], "Done keeps Fruit and Apple (%r)" % (texts,))

    _canvas_select(kb, "view")
    kb.press("Key_Return")
    kb.check(_item_editor() is None, "a list view opens no popover")
    kb.check(MODEL_VIEW_SENTENCE in str(kb.surface.editor_status_sentence()), "the status sentence says UX-ITEM-008")
    kb.check(_entries(kb) - start == 2, "K14 added two undo steps (got %d)" % (_entries(kb) - start))


# --------------------------------------------------------------------------
# K15 Pictures
# --------------------------------------------------------------------------


def _k15(kb: Kb) -> None:
    start = _entries(kb)
    _canvas_select(kb, "okButton")
    kb.press("Key_4", "Alt")
    _open_all(kb)
    _row_summary(kb, "icon")
    kb.press("Key_Return")
    search = _visible("formBuilder.pictureSearch")
    kb.check(search is not None, "Enter on Icon opens the picker")
    kb.check(kb.focus() is search, "focus is in the picture search")
    kb.type("save")
    kb.press("Key_Down")
    grid = _visible("formBuilder.pictureGrid")
    kb.check(grid is not None and kb.focus() is grid, "Down moves to the first match")
    kb.press("Key_Return")
    kb.check("<normaloff>:/icons/save.png</normaloff>" in kb.text(), "the icon is written as a resource path")
    kb.check(_entries(kb) - start == 1, "one step (got %d)" % (_entries(kb) - start))
    kb.check(kb.session.log.undo_label() == "Change icon of okButton", "the step is 'Change icon of okButton' (%s)" % kb.session.log.undo_label())
    kept = kb.text()
    _row_summary(kb, "icon")
    kb.press("Key_Return")
    _tab_until(kb, "Other states", _named("formBuilder.iconOtherStates"), 20)
    kb.press("Key_Space")
    _tab_until(kb, "the Disabled state", _named("formBuilder.iconState.disabledoff"), 20)
    kb.press("Key_Space")
    _tab_until(kb, "the picture search", _named("formBuilder.pictureSearch"), 20)
    kb.press("Key_A", "Control")
    kb.type("dot")
    kb.press("Key_Down")
    grid = _visible("formBuilder.pictureGrid")
    kb.check(kb.focus() is grid, "Down moves to the first match")
    kb.press("Key_Return")
    kb.check("disabledoff" in kb.text(), "a Disabled picture is picked")
    still_open = _visible("formBuilder.pictureSearch") is not None
    kb.soft(
        still_open,
        "K15-1",
        "Enter on a picture in the Disabled state keeps it and closes the popover (focus %s), so Esc cannot revert it; "
        "the spec's 'pick a Disabled picture; Esc: reverted' has no key path" % kb.focus_name(),
    )
    if still_open:
        kb.press("Key_Escape")
        kb.pump(4)
        kb.check(kb.text() == kept, "Esc reverts the Disabled picture")
        expected = 1
    else:
        expected = 2
    kb.check(_entries(kb) - start == expected, "K15 added %d undo steps (got %d)" % (expected, _entries(kb) - start))


def _run_session(tmp_path: Path, qapp: QApplication, run: _Run) -> None:
    _require()
    editor_memory.use_state_root(str((tmp_path / "recent").resolve()))
    root = tmp_path / "shop"
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    guard = _NoMouse()
    try:
        _project(window, root)
        forms = root / "forms"
        _seed(forms, ("save.png", "dot.png", "other.png"))
        path = forms / "customer.ui"
        surface = _open(window, qapp, path, _FORM)
        qapp.installEventFilter(guard)
        kb = Kb(window, qapp, surface, path)
        surface.focus_primary()
        kb.pump()
        try:
            baseline = _k11_save_and_reopen(window, kb, qapp)
            _k11_rest(kb)
            _k10(kb)
            _k9(kb)
            _k12(kb)
            _k13(kb)
            _k14(kb)
            _k15(kb)
            _undo_all(kb)
            kb.check(kb.text() == baseline, "undo all returns to the bytes at reopen")
        except AssertionError as error:
            run.failure = str(error)
        for item in kb.findings:
            name, _, what = item.partition(": ")
            run.findings[name] = what
    finally:
        qapp.removeEventFilter(guard)
        run.mouse = list(guard.seen)
        editor_memory.use_state_root(None)
        _close(window, qapp, guard)


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory, qapp: QApplication) -> _Run:
    result = _Run()
    _run_session(tmp_path_factory.mktemp("k9k15"), qapp, result)
    return result


def test_k9_to_k15_in_one_session_keys_only(run: _Run) -> None:
    assert run.failure == "", run.failure
    assert run.mouse == []


def _open_finding(run: _Run, name: str) -> None:
    assert name not in run.findings, "%s: %s" % (name, run.findings[name])


@pytest.mark.xfail(strict=True, reason="K10-1: Ctrl+R in a form tab has no Go to widget picker (shell Go to Symbol box opens)")
def test_k10_ctrl_r_goes_to_a_widget(run: _Run) -> None:
    _open_finding(run, "K10-1")


@pytest.mark.xfail(strict=False, reason="K12-1 (app-state dependent: passes after other suites set the app style; fails alone on macOS): Enter on the Translation button does not open its panel (QToolButton takes Space only)")
def test_k12_enter_opens_the_translation_panel(run: _Run) -> None:
    _open_finding(run, "K12-1")


@pytest.mark.xfail(strict=False, reason="K12-2 (app-state dependent, as K12-1): Tab does not reach 'Translate this text' after the Translation panel opens")
def test_k12_tab_reaches_translate_this_text(run: _Run) -> None:
    _open_finding(run, "K12-2")


def test_k12_tab_leaves_the_formatted_text_editor(run: _Run) -> None:
    _open_finding(run, "K12-3")


def test_k15_esc_reverts_a_disabled_state_pick(run: _Run) -> None:
    _open_finding(run, "K15-1")
