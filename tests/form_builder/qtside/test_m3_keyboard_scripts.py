# pyright: reportAttributeAccessIssue=false
"""M3.7 keyboard-only scripts K1-K8 (UX_SPEC 12.3) in a real main window.

Every step is a key event sent to whatever widget has keyboard focus, the
way a keyboard user works. No mouse event is sent (a filter fails the script
on any). Setup is the only non-key step: the tab is opened and the shell's
``focus_primary`` puts focus in it, as when the tab becomes current; on macOS
K1 triggers File > New Form… because Qt has no menu mnemonics there.

After each step the script checks focus, selection and the file text (the
bytes Save would write). A failed M3-owned step that the review filed is a
``soft`` finding: the script records it and goes on, and the test is a strict
xfail naming the finding, so it turns red once the finding is fixed.

N/A here, with owners: K1's typed search ("date") and the Date edit tile
(M4.1 Insert search and catalog), K6 tab order and buddies (now K23, M5.6), K8's
Preview window (M2.5 preview process).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.core.models import LoadedProject, ProjectMetadata  # noqa: E402
from app.features.form_builder.engine.ui4.writer import write_ui  # noqa: E402
from app.features.form_builder.install import form_builder_enabled  # noqa: E402
from app.qt.QtCore import QEvent, QObject, Qt  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import QApplication, QLabel, QLineEdit, QMenu, QWidget  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]

_CUSTOMER = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Customer</class>
 <widget class="QWidget" name="Customer">
  <property name="geometry"><rect><x>0</x><y>0</y><width>480</width><height>420</height></rect></property>
  <layout class="QVBoxLayout" name="mainLayout">
   <item>
    <widget class="QLabel" name="nameLabel">
     <property name="text"><string>Name:</string></property>
     <property name="buddy"><cstring>nameEdit</cstring></property>
    </widget>
   </item>
   <item><widget class="QLineEdit" name="nameEdit"/></item>
   <item><widget class="QLineEdit" name="phoneEdit"/></item>
   <item><widget class="QLineEdit" name="emailEdit"/></item>
   <item><widget class="QLineEdit" name="cityEdit"/></item>
   <item><widget class="QLineEdit" name="zipEdit"/></item>
   <item><widget class="QPlainTextEdit" name="notesEdit"/></item>
   <item>
    <widget class="QCheckBox" name="newsCheck">
     <property name="text"><string>Send news</string></property>
    </widget>
   </item>
   <item>
    <widget class="QPushButton" name="saveButton">
     <property name="text"><string>Save</string></property>
    </widget>
   </item>
   <item>
    <widget class="QPushButton" name="cancelButton">
     <property name="text"><string>Cancel</string></property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


class _NoMouse(QObject):
    """Records any mouse event that reaches the application (12.1 code K)."""

    def __init__(self) -> None:
        super().__init__()
        self.seen: List[str] = []
        kinds = getattr(QEvent, "Type", QEvent)
        self._kinds = {
            int(getattr(kinds, name)): name
            for name in ("MouseButtonPress", "MouseButtonRelease", "MouseButtonDblClick")
        }

    def eventFilter(self, watched: object, event: object) -> bool:  # noqa: N802
        kind = int(event.type())  # type: ignore[attr-defined]
        if kind in self._kinds and event.spontaneous():  # type: ignore[attr-defined]
            self.seen.append(self._kinds[kind])
        return False


def _key(name: str) -> object:
    return getattr(getattr(Qt, "Key", Qt), name)


def _mods(*names: str) -> object:
    enum = getattr(Qt, "KeyboardModifier", Qt)
    value = getattr(enum, "NoModifier")
    for name in names:
        value = value | getattr(enum, name + "Modifier")
    return value


class Kb:
    """A keyboard user at a real main window with one form tab."""

    def __init__(self, window: MainWindow, qapp: QApplication, surface: object, path: Path) -> None:
        self.window = window
        self.qapp = qapp
        self.surface = surface
        self.path = path
        self.log: List[str] = []
        self.findings: List[str] = []

    # ---- input ---------------------------------------------------------
    def target(self) -> QWidget:
        # Qt sends a key to the focus widget, or to the open popup when focus
        # is outside it (a menu has no focus child).
        focus = QApplication.focusWidget()
        popup = QApplication.activePopupWidget()
        if popup is not None and (focus is None or not (focus is popup or popup.isAncestorOf(focus))):
            return popup
        return focus if focus is not None else self.window

    def press(self, key: str, *mods: str) -> None:
        widget = self.target()
        QTest.keyClick(widget, _key(key), _mods(*mods))
        self.pump()
        self.log.append("%s%s -> focus=%s sel=%s" % ("+".join(mods + (key,)), "", self.focus_name(), self.selected()))

    def type(self, text: str) -> None:
        QTest.keyClicks(self.target(), text)
        self.pump()
        self.log.append("type %r -> focus=%s" % (text, self.focus_name()))

    def pump(self, rounds: int = 6) -> None:
        for _ in range(rounds):
            self.qapp.processEvents()
        # The offscreen platform has no window manager: when a popup closes
        # no window becomes active again, so focus reads as None although the
        # window still remembers its focus widget. A real X11 session keeps
        # the main window active (popups are override-redirect). Emulate that.
        if (
            QApplication.activeWindow() is None
            and QApplication.activePopupWidget() is None
            and QApplication.activeModalWidget() is None
            and self.window.isVisible()
        ):
            self.window.activateWindow()
            for _ in range(2):
                self.qapp.processEvents()

    # ---- observation ---------------------------------------------------
    @property
    def session(self) -> object:
        return self.surface.session  # type: ignore[attr-defined]

    def selected(self) -> Tuple[str, ...]:
        if self.surface is None or not hasattr(self.surface, "session"):
            return ()
        session = self.session
        names = []
        for node_id in session.selection.state.ids:  # type: ignore[attr-defined]
            node = session.document.get(node_id)  # type: ignore[attr-defined]
            names.append(_node_name(node))
        return tuple(names)

    def current(self) -> str:
        if self.surface is None or not hasattr(self.surface, "session"):
            return ""
        session = self.session
        node_id = session.selection.state.current  # type: ignore[attr-defined]
        if node_id is None:
            return ""
        return _node_name(session.document.get(node_id))  # type: ignore[attr-defined]

    def focus(self) -> Optional[QWidget]:
        return QApplication.focusWidget()

    def focus_name(self) -> str:
        widget = self.focus()
        if widget is None:
            return "(none)"
        return str(widget.objectName()) or type(widget).__name__

    def pane(self, name: str) -> QWidget:
        found = self.surface.findChild(QWidget, name)  # type: ignore[attr-defined]
        assert isinstance(found, QWidget), name
        return found

    def focus_in(self, pane_name: str) -> bool:
        widget = self.focus()
        pane = self.pane(pane_name)
        return widget is not None and (widget is pane or pane.isAncestorOf(widget))

    def text(self) -> str:
        """The bytes Save would write now (writer-canonical)."""
        return str(write_ui(self.session.document).text)  # type: ignore[attr-defined]

    def history(self) -> str:
        return "\n".join(self.log)

    def check(self, condition: bool, what: str) -> None:
        assert condition, "%s\n-- keys so far --\n%s" % (what, self.history())

    def soft(self, condition: bool, finding: str, what: str) -> None:
        """A failed M3-owned step that the review filed as a finding. The script goes on."""
        if not condition:
            self.findings.append("%s: %s" % (finding, what))
            self.log.append("FINDING %s: %s" % (finding, what))

    def done(self, guard: "_NoMouse") -> None:
        self.check(guard.seen == [], "no mouse event reached the window")
        assert not self.findings, "M3.7 findings:\n" + "\n".join(self.findings) + "\n-- keys --\n" + self.history()


def _node_name(node: object) -> str:
    if node is None:
        return "?"
    for field in ("object_name", "name"):
        value = getattr(node, field, None)
        if callable(value):
            value = value()
        if value:
            return str(value)
    try:
        value = node.field("name")  # type: ignore[attr-defined]
    except (KeyError, AttributeError):
        value = None
    return str(value) if value else type(node).__name__


def _require() -> None:
    if not form_builder_enabled():
        pytest.skip("form builder is registered on PySide6")


def _project(window: MainWindow, root: Path) -> None:
    (root / "forms").mkdir(parents=True, exist_ok=True)
    (root / "cbcs").mkdir(exist_ok=True)
    (root / "main.py").write_text("print('shop')\n", encoding="utf-8")
    manifest = root / "cbcs" / "project.json"
    manifest.write_text(
        json.dumps({"schema_version": 2, "name": "Shop", "default_entry": "main.py"}) + "\n",
        encoding="utf-8",
    )
    window._loaded_project = LoadedProject(  # noqa: SLF001
        project_root=str(root.resolve()),
        manifest_path=str(manifest.resolve()),
        metadata=ProjectMetadata(schema_version=2, name="Shop", default_entry="main.py"),
        entries=[],
    )


def _open(window: MainWindow, qapp: QApplication, path: Path, text: str) -> object:
    path.write_text(text, encoding="utf-8")
    assert window._editor_tab_factory.open_file_in_editor(str(path))  # noqa: SLF001
    stack = window._center_stack  # noqa: SLF001
    assert stack is not None
    stack.setCurrentIndex(1)
    window.resize(1400, 900)
    window.show()
    window.activateWindow()
    for _ in range(8):
        qapp.processEvents()
    surface = window._tab_content_registry.surface_for_path(str(path))  # noqa: SLF001
    assert surface is not None
    return surface


def _session(tmp_path: Path, qapp: QApplication, text: str = _CUSTOMER) -> Tuple[MainWindow, Kb, _NoMouse]:
    _require()
    root = tmp_path / "shop"
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    _project(window, root)
    path = root / "forms" / "customer.ui"
    surface = _open(window, qapp, path, text)
    guard = _NoMouse()
    qapp.installEventFilter(guard)
    kb = Kb(window, qapp, surface, path)
    # The script starts with focus in the form tab (12.3). surface.focus_primary
    # is what the shell calls when the tab becomes current.
    surface.focus_primary()  # type: ignore[attr-defined]
    kb.pump()
    return window, kb, guard


def _close(window: MainWindow, qapp: QApplication, guard: _NoMouse) -> None:
    qapp.removeEventFilter(guard)
    shutdown_main_window_for_test(window, qapp)


# --------------------------------------------------------------------------
# K2 Structure
# --------------------------------------------------------------------------


def test_k2_structure(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp)
    try:
        original = kb.text()
        kb.press("Key_3", "Alt")
        kb.check(kb.focus_in("formBuilder.canvas"), "Alt+3 focuses the canvas")
        # Walk to phoneEdit by Tab (UX-SEL-006).
        for _ in range(12):
            if kb.current() == "phoneEdit":
                break
            kb.press("Key_Tab")
        kb.check(kb.current() == "phoneEdit", "Tab reaches phoneEdit")
        kb.press("Key_Down", "Shift")
        kb.check(set(kb.selected()) == {"phoneEdit", "emailEdit"}, "Shift+Down adds emailEdit")
        kb.press("Key_1", "Control")
        kb.check("QHBoxLayout" in kb.text() and kb.text() != original, "Ctrl+1 wraps in a horizontal layout")
        kb.check(kb.focus_in("formBuilder.canvas"), "focus stays on the canvas after Ctrl+1")
        kb.check(kb.current() == "horizontalLayout", "the new layout is selected (UX-WRAP-003)")
        kb.press("Key_B", "Control", "Shift")
        kb.check("QHBoxLayout" not in kb.text(), "Ctrl+Shift+B unwraps")
        kb.check(set(kb.selected()) == {"phoneEdit", "emailEdit"}, "unwrap keeps the two fields selected")
        kb.check(kb.focus_in("formBuilder.canvas"), "focus stays on the canvas after unwrap")
        kb.press("Key_G", "Control", "Shift")
        popup = kb.focus_name()
        kb.check(popup == "formBuilder.wrapTile.vertical", "the popover opens with its first tile focused")
        # The popover applies a digit at once (wrap_popover._digit), so the
        # script's "7, Enter" is "7" here; Enter then goes to the canvas.
        kb.press("Key_7")
        kb.check("QGroupBox" in kb.text(), "Ctrl+Shift+G, 7 wraps in a group box")
        kb.check(QApplication.activePopupWidget() is None, "the popover closed")
        kb.check(kb.focus_in("formBuilder.canvas"), "focus returns to the canvas after the wrap popover")
        group = kb.current()
        kb.check(group.startswith("groupBox"), "the new group box is selected (UX-WRAP-003)")
        kb.press("Key_Return")
        inner = kb.current()
        kb.check(inner != group, "Enter on the group selects its first child (UX-SEL-005)")
        for _ in range(3):
            if kb.current() == group:
                break
            kb.press("Key_Escape")
        kb.check(kb.current() == group, "Esc walks back up to the group (UX-SEL-004)")
        before = kb.text()
        order_before = before.index("nameEdit") < before.index(group)
        kb.press("Key_Up", "Alt")
        after = kb.text()
        kb.check(after != before, "Alt+Up moves the group")
        kb.check(order_before and after.index(group) < after.index('name="nameEdit"'), "the group moved above nameEdit")
        kb.check(kb.current() == group and kb.focus_in("formBuilder.canvas"), "selection and focus stay")
        for _ in range(12):
            if kb.text() == original:
                break
            kb.press("Key_Z", "Control")
        import difflib
        kb.check(kb.text() == original, "undo all returns the original bytes\n" + "".join(difflib.unified_diff(original.splitlines(True), kb.text().splitlines(True))))
        print(kb.history())
        kb.done(guard)
    finally:
        _close(window, qapp, guard)


def _walk_to(kb: Kb, name: str, key: str = "Key_Tab", limit: int = 20) -> None:
    for _ in range(limit):
        if kb.current() == name:
            return
        kb.press(key)
    kb.check(kb.current() == name, "%s reaches %s" % (key, name))


def _tab_to(kb: Kb, object_name: str, limit: int = 80, back: bool = False, pane: str = "formBuilder.inspector") -> None:
    """Tab through ``pane`` until ``object_name`` has focus (a keyboard user scanning).

    When Tab leaves the pane the user turns round with Shift+Tab.
    """
    for _ in range(limit):
        if kb.focus_name() == object_name:
            return
        if not kb.focus_in(pane):
            back = not back
        if back:
            kb.press("Key_Backtab", "Shift")
        else:
            kb.press("Key_Tab")
    kb.check(kb.focus_name() == object_name, "Tab reaches %s" % object_name)


def _toast_text(kb: Kb) -> str:
    toast = kb.surface.findChild(QWidget, "formBuilder.commandToast")  # type: ignore[attr-defined]
    if toast is None or not toast.isVisible():
        return ""
    labels = [w.text() for w in toast.findChildren(QLabel) if w.isVisible()]
    return " ".join(str(t) for t in labels)


# --------------------------------------------------------------------------
# K3 Clipboard
# --------------------------------------------------------------------------


def test_k3_clipboard(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp)
    try:
        kb.press("Key_3", "Alt")
        _walk_to(kb, "emailEdit")
        kb.press("Key_C", "Control")
        kb.check(kb.current() == "emailEdit", "copy keeps the selection")
        before = kb.text()
        kb.press("Key_V", "Control")
        after = kb.text()
        # UX-CLIP-003 says email -> email2; the engine follows Designer (email_2).
        copy = "emailEdit2" if 'name="emailEdit2"' in after else "emailEdit_2"
        kb.check(('name="%s"' % copy) in after and after != before, "Ctrl+V pastes a renamed copy")
        kb.check(
            after.index('name="emailEdit"') < after.index('name="%s"' % copy) < after.index('name="cityEdit"'),
            "the copy lands right after emailEdit (UX-CLIP-002)",
        )
        kb.check(kb.current() == copy, "the pasted copy is selected (UX-CLIP-003)")
        kb.check(kb.focus_in("formBuilder.canvas"), "focus stays on the canvas after paste")
        kb.press("Key_D", "Control")
        dup = kb.text()
        third = kb.current()
        kb.check(third not in (copy, "emailEdit") and ('name="%s"' % third) in dup, "Ctrl+D duplicates and selects the copy")
        kb.soft(third in ("emailEdit3", "emailEdit_3"), "F-names", "a duplicate of %s takes the next free number, got %s (UX-CLIP-003)" % (copy, third))
        kb.check(dup.index('name="%s"' % copy) < dup.index('name="%s"' % third), "the duplicate goes after the original")
        # nameEdit is the buddy of nameLabel, so deleting it asks first.
        _walk_to(kb, "nameEdit", key="Key_Backtab")
        held = kb.text()
        kb.press("Key_Delete")
        shown = kb.surface.findChild(QWidget, "formBuilder.outlineConfirm")  # type: ignore[attr-defined]
        asked = kb.text() == held and (
            QApplication.activePopupWidget() is not None or (shown is not None and shown.isVisible())
        )
        kb.soft(asked, "F-delete-confirm", "canvas Delete on nameEdit (buddy of nameLabel) deletes at once; no references confirm (UX-OUT-012)")
        if asked:
            confirm_focus = kb.focus_name()
            kb.press("Key_Escape")
            kb.check(kb.text() == held, "Esc deletes nothing")
            kb.check(kb.focus_in("formBuilder.canvas"), "Esc returns focus to the canvas")
            kb.check(kb.current() == "nameEdit", "the selection is unchanged after Esc")
            kb.press("Key_Delete")
            for _ in range(4):
                if kb.focus_name().endswith("Delete"):
                    break
                kb.press("Key_Tab")
            kb.log.append("confirm focus at open: %s; before Enter: %s" % (confirm_focus, kb.focus_name()))
            kb.press("Key_Return")
        gone = kb.text()
        kb.soft("<cstring>nameEdit</cstring>" not in gone, "F-delete-confirm", "the deleted field is still named as nameLabel's buddy")
        kb.check('name="nameEdit"' not in gone, "Enter on Delete deletes nameEdit")
        kb.soft("Deleted" in _toast_text(kb), "F-delete-toast", "a toast confirms the delete (UX-OUT-012, FEED-001): %r" % _toast_text(kb))
        kb.check(kb.focus_in("formBuilder.canvas"), "focus is on the canvas after the delete")
        print(kb.history())
        kb.done(guard)
    finally:
        _close(window, qapp, guard)


# --------------------------------------------------------------------------
# K4 Rename ten
# --------------------------------------------------------------------------


def test_k4_rename_ten(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp)
    try:
        kb.press("Key_1", "Alt")
        kb.check(kb.focus_in("formBuilder.outline"), "Alt+1 focuses the outline")
        # Down to nameLabel (Customer, mainLayout, nameLabel).
        for _ in range(4):
            if kb.current() == "nameLabel":
                break
            kb.press("Key_Down")
        kb.check(kb.current() == "nameLabel", "Down reaches nameLabel")
        kb.press("Key_F2")
        kb.check(isinstance(kb.focus(), QLineEdit) and kb.focus_in("formBuilder.outline"), "F2 opens the rename editor")
        renamed = []
        for index in range(10):
            editor = kb.focus()
            kb.check(isinstance(editor, QLineEdit), "step %d: the rename editor has focus" % index)
            old = kb.current()
            new = "field%02d" % index
            kb.press("Key_A", "Control")
            kb.type(new)
            kb.press("Key_Tab")
            renamed.append((old, new))
            kb.check(kb.focus_in("formBuilder.outline"), "step %d: focus stays in the outline (pain 25)" % index)
            kb.check(('name="%s"' % new) in kb.text(), "step %d: %s renamed to %s" % (index, old, new))
        kb.press("Key_Escape")
        kb.check(kb.focus_in("formBuilder.outline"), "Esc closes the editor and keeps focus in the outline")
        print(kb.history())
        kb.done(guard)
    finally:
        _close(window, qapp, guard)


# --------------------------------------------------------------------------
# K5 Sizing
# --------------------------------------------------------------------------


def test_k5_sizing(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp)
    try:
        kb.press("Key_3", "Alt")
        _walk_to(kb, "saveButton")
        clean = kb.text()
        kb.press("Key_4", "Alt")
        kb.check(kb.focus_in("formBuilder.inspector"), "Alt+4 focuses the inspector")
        start = len(kb.log)
        _tab_to(kb, "formBuilder.size.width.Fill")
        kb.log.append("Tabs from Alt+4 to Width Fill: %d" % (len(kb.log) - start))
        kb.press("Key_Space")
        kb.check("QSizePolicy::Policy::Expanding" in kb.text() or "Expanding" in kb.text(), "Width Fill writes Expanding")
        kb.check(kb.focus_name() == "formBuilder.size.width.Fill", "focus stays on the Fill segment")
        # The Reset size button appears after the edit. Tab past it must stay in the inspector.
        _tab_to(kb, "formBuilder.size.reset")
        kb.press("Key_Tab")
        kb.soft(
            kb.focus_in("formBuilder.inspector"),
            "F-inspector-chain",
            "Tab from Reset size leaves the form tab (to %s), skipping Placement, Accessibility and All properties (UX-A11Y-009)"
            % kb.focus_name(),
        )
        kb.press("Key_Backtab", "Shift")
        # Share sits under Height in a vertical layout (UX-SIZE-005).
        _tab_to(kb, "formBuilder.size.share.v.value")
        kb.press("Key_A", "Control")
        kb.type("1")
        kb.press("Key_Tab")
        import difflib
        kb.check('stretch="' in kb.text(), "Share 1 writes the layout stretch\n" + "".join(difflib.unified_diff(clean.splitlines(True), kb.text().splitlines(True))))
        _tab_to(kb, "formBuilder.size.height.Fixed")
        kb.press("Key_Space")
        kb.check(kb.focus_in("formBuilder.inspector"), "focus stays in the inspector after Fixed")
        _tab_to(kb, "formBuilder.size.height.pixels")
        kb.press("Key_A", "Control")
        kb.type("120")
        kb.press("Key_Return")
        kb.check("<height>120</height>" in kb.text(), "Height Fixed 120 writes 120 px")
        kb.check(kb.focus_name() in ("formBuilder.size.height.pixels", "QLineEdit"), "Enter keeps focus in the pixel field")
        _tab_to(kb, "formBuilder.size.minimumSize.width")
        kb.press("Key_A", "Control")
        kb.type("200")
        kb.press("Key_Return")
        kb.check("<width>200</width>" in kb.text(), "At least width 200 writes a minimum width")
        # Reset each: At least, then the words, then the share.
        _tab_to(kb, "formBuilder.size.minimumSize.reset")
        kb.press("Key_Space")
        _tab_to(kb, "formBuilder.size.reset")
        kb.press("Key_Space")
        _tab_to(kb, "formBuilder.size.share.v.value", back=True)
        kb.press("Key_A", "Control")
        kb.type("0")
        kb.press("Key_Tab")
        import difflib
        kb.soft(
            kb.text() == clean,
            "F-reset-fixed",
            "after Reset at least and Reset size a Fixed height's maximumSize line stays in the file:\n"
            + "".join(difflib.unified_diff(clean.splitlines(True), kb.text().splitlines(True))),
        )
        kb.check(kb.focus_in("formBuilder.inspector"), "focus stays in the inspector through the resets")
        # Shift+Tab walks back through the inspector header and out of it.
        _tab_to(kb, "formBuilder.inspectorCrumbs", back=True)
        for _ in range(4):
            if kb.focus_name() != "formBuilder.inspectorCrumbs":
                break
            kb.press("Key_Backtab", "Shift")
        kb.soft(
            kb.focus_name() != "formBuilder.inspectorCrumbs",
            "F-crumb-trap",
            "Shift+Tab on the breadcrumb never leaves it (UX-A11Y-009)",
        )
        kb.check(
            kb.focus_name() == "formBuilder.inspectorName",
            "Shift+Tab from the breadcrumb lands on the name field above it (UX-A11Y-009)",
        )
        # Ctrl+Shift+Right twice on the canvas: Fixed width + 16 (UX-RESIZE-006).
        kb.press("Key_3", "Alt")
        kb.check(kb.current() == "saveButton" and kb.focus_in("formBuilder.canvas"), "Alt+3 back on the canvas")
        canvas = kb.pane("formBuilder.canvas")
        live = canvas.page_widget().findChild(QWidget, "saveButton")
        width = int(live.width())
        kb.press("Key_Right", "Control", "Shift")
        kb.press("Key_Right", "Control", "Shift")
        kb.check("<width>%d</width>" % (width + 16) in kb.text(), "Ctrl+Shift+Right twice writes Fixed %d" % (width + 16))
        kb.check(kb.focus_in("formBuilder.canvas"), "focus stays on the canvas")
        print(kb.history())
        kb.done(guard)
    finally:
        _close(window, qapp, guard)


# --------------------------------------------------------------------------
# K6 Overlays: tab order and buddies are M5.6
# --------------------------------------------------------------------------


# K6 became K23 in M5.6: tests/form_builder/qtside/test_m5_6_keyboard_k23.py.


# --------------------------------------------------------------------------
# K7 Text
# --------------------------------------------------------------------------


def test_k7_text(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp)
    try:
        kb.press("Key_3", "Alt")
        _walk_to(kb, "saveButton")
        original = kb.text()
        kb.press("Key_Return")
        editor = kb.focus()
        kb.check(isinstance(editor, QLineEdit) and kb.focus_in("formBuilder.canvas"), "Enter opens the in-place editor")
        kb.check(editor.selectedText() == "Save", "the editor selects all text (UX-TEXT-002)")  # type: ignore[union-attr]
        kb.type("Store")
        kb.press("Key_Tab")
        kb.check("<string>Store</string>" in kb.text(), "Tab commits the first text")
        nxt = kb.focus()
        kb.check(isinstance(nxt, QLineEdit), "Tab opens the editor on the next text widget (UX-TEXT-003)")
        kb.check(kb.current() == "cancelButton", "the next text widget in outline order is selected")
        kb.type("Close")
        kb.press("Key_Return")
        kb.check("<string>Close</string>" in kb.text(), "Enter commits the second text")
        kb.check(kb.focus_name() == "formBuilder.canvas", "Enter returns focus to the canvas")
        kb.press("Key_Z", "Control")
        kb.press("Key_Z", "Control")
        kb.check(kb.text() == original, "two undos restore both texts")
        print(kb.history())
        kb.done(guard)
    finally:
        _close(window, qapp, guard)


# --------------------------------------------------------------------------
# K8 Views
# --------------------------------------------------------------------------


def _zoom_label(kb: Kb) -> str:
    button = kb.surface.findChild(QWidget, "formBuilder.zoomMenu")  # type: ignore[attr-defined]
    return "" if button is None else str(button.text())


def test_k8_views(tmp_path: Path, qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.shell.run_launch_workflow import RunLaunchWorkflow

    runs: List[str] = []
    monkeypatch.setattr(RunLaunchWorkflow, "handle_run_project_action", lambda self: runs.append("run") or True)
    window, kb, guard = _session(tmp_path, qapp)
    try:
        kb.press("Key_3", "Alt")
        label = kb.surface._toolbar.zoom_label  # type: ignore[attr-defined]  # noqa: SLF001

        def zoom() -> float:
            return float(str(label.text()).rstrip("%")) / 100.0

        kb.press("Key_9", "Control")
        fit = zoom()
        kb.press("Key_Equal", "Control")
        kb.press("Key_Equal", "Control")
        kb.check(zoom() > fit, "Ctrl+= twice zooms in (%s -> %s)" % (fit, zoom()))
        kb.press("Key_Minus", "Control")
        kb.press("Key_0", "Control")
        kb.check(zoom() == 1.0, "Ctrl+0 is 100%% (%s)" % zoom())
        kb.check(kb.focus_in("formBuilder.canvas"), "zoom keys keep focus on the canvas")
        # XML round trip (UX-XML-001..003).
        before = kb.text()
        kb.press("Key_V", "Control", "Shift")
        editor = kb.focus()
        kb.check(editor is not None and editor is kb.surface.source_editor(), "Ctrl+Shift+V shows XML with the editor focused")  # type: ignore[attr-defined]
        shown = editor.toPlainText()  # type: ignore[union-attr]
        line = next(i for i, text in enumerate(shown.splitlines()) if "<string>Save</string>" in text)
        tail = shown.splitlines()[line]
        tail = tail[tail.index("<string>Save</string>") + len("<string>Save"):]
        kb.press("Key_Home", "Control")
        for _ in range(line):
            kb.press("Key_Down")
        kb.press("Key_End")
        for _ in range(len(tail)):
            kb.press("Key_Left")
        for _ in range(4):
            kb.press("Key_Backspace")
        kb.type("Store")
        kb.press("Key_Escape")  # close any completion popup
        kb.press("Key_V", "Control", "Shift")
        after = kb.text()
        kb.check("<string>Store</string>" in after, "back in Design the title changed")
        kb.check(kb.focus() is not editor, "focus left the XML editor")
        kb.log.append("focus after XML back: %s" % kb.focus_name())
        kb.soft(kb.focus_in("formBuilder.canvas") or kb.focus_in("formBuilder.outline"), "F-xml-focus", "focus after leaving XML is %s" % kb.focus_name())
        kb.press("Key_3", "Alt")
        kb.press("Key_Z", "Control")
        kb.check(kb.text() == before, "one undo step restores the title (UX-XML-003)")
        # Preview (Ctrl+Shift+R) is the M2.5 preview process: N/A for M3.
        kb.press("Key_R", "Control", "Shift")
        kb.log.append("Ctrl+Shift+R status: %s" % kb.surface.editor_status_sentence())  # type: ignore[attr-defined]
        kb.press("Key_Escape")
        # F5 saves the project form and runs the entry (UX-RUN-001, M2.4).
        kb.press("Key_F5")
        kb.check(runs == ["run"], "F5 runs the project entry")
        kb.check(kb.path.read_text(encoding="utf-8") == kb.text(), "F5 saved the form first")
        kb.check(kb.focus_in("formBuilder.canvas"), "focus stays on the canvas after F5")
        print(kb.history())
        kb.done(guard)
    finally:
        _close(window, qapp, guard)


# --------------------------------------------------------------------------
# K1 Create and fill a data-entry form
# --------------------------------------------------------------------------


def test_k1_create_and_fill(tmp_path: Path, qapp: QApplication) -> None:
    _require()
    root = tmp_path / "shop"
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    _project(window, root)
    window.resize(1400, 900)
    window.show()
    window.activateWindow()
    guard = _NoMouse()
    qapp.installEventFilter(guard)
    kb = Kb(window, qapp, None, root / "forms" / "invoice.ui")
    try:
        kb.pump()
        # A real project open shows the editor stack; the test loads the project
        # by hand, so show it the way the other real-window tests do.
        window._center_stack.setCurrentIndex(1)  # type: ignore[union-attr]  # noqa: SLF001
        kb.pump()
        # File > New Form... by keyboard: Alt+F opens File, Down to the item, Enter.
        # Qt has no menu mnemonics on macOS, so there the action is triggered
        # the way Enter on the menu row would. On X11 (ChoreBoy) the keys run.
        import sys

        if sys.platform == "darwin":
            action = window.menu_registry.action("shell.action.file.newForm")  # type: ignore[attr-defined]
            kb.check(action is not None and action.isEnabled(), "File > New Form… exists")
            action.trigger()  # type: ignore[union-attr]
            kb.pump()
            kb.log.append("File > New Form… (triggered: no mnemonics on macOS)")
        else:
            kb.press("Key_F", "Alt")
            menu = QApplication.activePopupWidget()
            kb.check(isinstance(menu, QMenu), "Alt+F opens the File menu")
            for _ in range(12):
                active = menu.activeAction()  # type: ignore[union-attr]
                if active is not None and active.text() == "New Form…":
                    break
                kb.press("Key_Down")
            kb.press("Key_Return")
        kb.check(isinstance(kb.focus(), QLineEdit), "the name field has focus (UX-START-003), got %s" % kb.focus_name())
        kb.press("Key_A", "Control")
        kb.type("invoice")
        # Arrow to "Data entry form": from the name row, Tab should reach the
        # folder and then the cards, and arrows move between cards.
        panel = window.findChild(QWidget, "formBuilder.newForm")
        kb.check(panel is not None, "the New form tab is open")

        def on_card() -> bool:
            focus = kb.focus()
            return focus is not None and panel.isAncestorOf(focus) and str(focus.accessibleName()).startswith("Data entry")  # type: ignore[union-attr]

        def in_panel() -> bool:
            focus = kb.focus()
            return focus is not None and panel.isAncestorOf(focus)  # type: ignore[union-attr]

        chain = []
        for _ in range(6):
            kb.press("Key_Tab")
            chain.append(kb.focus_name())
            if on_card() or not in_panel():
                break
        kb.soft(on_card(), "F-start-tab", "Tab from the name field leaves the New form tab (chain %s) instead of reaching the cards" % chain)
        if not on_card():
            for _ in range(12):
                kb.press("Key_Backtab", "Shift")
                if on_card():
                    break
            kb.log.append("Shift+Tab path reached card: %s" % on_card())
        for _ in range(6):
            if on_card():
                break
            kb.press("Key_Right")
        kb.log.append("card focus: %s / %s" % (kb.focus_name(), kb.focus().accessibleName() if kb.focus() else ""))  # type: ignore[union-attr]
        kb.press("Key_Return")
        kb.pump(12)
        path = root / "forms" / "invoice.ui"
        kb.check(path.is_file(), "Enter on the card creates forms/invoice.ui")
        surface = window._tab_content_registry.surface_for_path(str(path))  # noqa: SLF001
        kb.check(surface is not None, "the Workbench opens")
        kb.surface = surface
        kb.soft(kb.current() == "nameEdit", "F-start-select", "the first input is selected after create (UX-START-004), got %r" % kb.current())
        kb.soft(kb.focus_in("formBuilder.canvas"), "F-start-focus", "the canvas is focused after create, got %s" % kb.focus_name())
        # Put the keyboard on the canvas and select the last field, then quick insert.
        kb.press("Key_3", "Alt")
        _walk_to(kb, "notesEdit")
        kb.press("Key_Slash")
        opened = kb.focus_name() != "formBuilder.canvas"
        kb.soft(opened, "F-canvas-slash", "/ on the canvas opens nothing although the empty canvas says 'press / to search' (UX-KEY-004, EMPTY-001)")
        if not opened:
            # The outline's / is the M3.5 path. Use it to finish the script.
            kb.press("Key_1", "Alt")
            kb.check(kb.current() == "notesEdit", "Alt+1 keeps the selection")
            kb.press("Key_Slash")
        kb.log.append("quick insert focus: %s" % kb.focus_name())
        # M4.1: the quick list has a search field. Type the words; Enter inserts the first result.
        before_edits = kb.text().count('class="QLineEdit"')
        kb.type("line edit")
        kb.press("Key_Return")
        text = kb.text()
        kb.check(text.count('class="QLineEdit"') == before_edits + 1, "/ then Enter on Line edit inserts a field")
        added = next(name for name in kb.selected() if "lineEdit" in name or "Edit" in name)
        editor = kb.focus()
        kb.soft(isinstance(editor, QLineEdit), "F-k1-label", "the new row's label editor is open (UX-FORML-002), focus %s" % kb.focus_name())
        if isinstance(editor, QLineEdit):
            kb.type("Issued")
            kb.press("Key_Return")
        text = kb.text()
        kb.soft("<string>Issued</string>" in text, "F-k1-label", "the row label reads Issued")
        kb.soft(("<cstring>%s</cstring>" % added) in text, "F-k1-buddy", "the new label is the new field's buddy (%s)" % added)
        kb.soft(text.index('name="notesEdit"') < text.index('name="%s"' % added), "F-k1-row", "the new row comes after Notes")
        kb.log.append("focus at the end: %s" % kb.focus_name())
        print(kb.history())
        kb.done(guard)
    finally:
        qapp.removeEventFilter(guard)
        shutdown_main_window_for_test(window, qapp)
