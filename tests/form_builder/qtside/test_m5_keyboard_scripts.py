# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportArgumentType=false, reportOptionalCall=false, reportIndexIssue=false, reportCallIssue=false
"""M5.R keyboard scripts K16-K23 (UX_SPEC 12.3) together in ONE real main window.

One ``MainWindow`` and one shop project serve the whole module, so the eight
M5 lane scripts also prove that they do not leak state into each other. Every
step is a key event sent to whatever widget has keyboard focus. A filter fails
the final test if any mouse press, release, move, wheel or double-click reached
an application widget during any script.

Setup is the only non-key step, as in the lane scripts: fixture files, the
project, opening a fixture form in a tab, ``focus_primary`` when a tab becomes
current, and the menu-bar items the offscreen platform cannot press keys into
(the lane scripts trigger the same QAction).

A step that fails because of a product bug, or because a shared window exposes
state leaking between scripts, is a ``soft`` finding: the script records it and
goes on, and the test is a strict xfail naming the finding.
"""

from __future__ import annotations

import dataclasses
import json
import os
import runpy
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, Tuple

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.ids import IdAllocator  # noqa: E402
from app.features.form_builder.engine.ipc.timing import DirectorConfig  # noqa: E402
from app.features.form_builder.engine.project.pictures import picture_uses  # noqa: E402
from app.features.form_builder.engine.project.qrc_write import parse_qrc  # noqa: E402
from app.features.form_builder.engine.ui4.reader import read_ui  # noqa: E402
from app.features.form_builder.engine.ui4.writer import write_ui  # noqa: E402
from app.features.form_builder.integration import preview_notice, template_store  # noqa: E402
from app.features.form_builder.integration.custom_registry import registry_for  # noqa: E402
from app.features.form_builder.integration.memory import PreviewOptionsStore  # noqa: E402
from app.features.form_builder.qtside.preview.launch import (  # noqa: E402
    current_runtime_python,
    python_preview_command,
    repo_root,
)
from app.features.form_builder.qtside.preview.pool import PreviewPool  # noqa: E402
from app.project.project_service import enumerate_project_entries  # noqa: E402
from app.qt.QtCore import QEvent, QObject, QPoint, QTimer  # noqa: E402
from app.qt.QtGui import QImage  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtUiTools import QUiLoader  # noqa: E402
from app.qt.QtWidgets import (  # noqa: E402
    QApplication,
    QComboBox,
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QWidget,
)
from app.qt.qt_compat import wrapper_is_valid  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402
from tests.form_builder.inspector.m5_5b_support import free_form  # noqa: E402
from tests.form_builder.inspector.test_m43c_pictures import _png_bytes  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import (  # noqa: E402
    Kb,
    _key,
    _project,
    _walk_to,
    _tab_to,
)
from tests.form_builder.qtside.test_m5_3_k18 import _SHOP as K18_FORM  # noqa: E402
from tests.form_builder.qtside.test_m5_3_k18 import _find_row, _green, _wait  # noqa: E402
from tests.form_builder.qtside.test_m5_3_k18 import _walk_to as _k18_walk_to  # noqa: E402
from tests.form_builder.qtside.test_m5_4_k19 import _SHOP as K19_FORM  # noqa: E402
from tests.form_builder.qtside.test_m5_4_k19 import _select as _k19_select  # noqa: E402
from tests.form_builder.qtside.test_m5_5a_k20 import _long_form, _menu_path  # noqa: E402
from tests.form_builder.qtside.test_m5_5c_k22 import _drive_confirm, _form_action, _tab_until as _k22_tab_until  # noqa: E402
from tests.form_builder.qtside.test_m5_6_keyboard_k23 import K23_FORM, _buddy, _focus_is, _status  # noqa: E402
from tests.form_builder.qtside.test_m5_5b_keyboard import _menu_item, _tab_until as _k21_tab_until  # noqa: E402
from tests.form_builder.qtside.test_m5_4_k19 import (  # noqa: E402
    _BROKEN,
    _TILL,
    _ImportRecorder,
    _check_line,
    _menu_pick,
    _popover,
    _ppress,
    _ptype,
    _pump_until,
)

pytestmark = [pytest.mark.unit, pytest.mark.timeout(600)]


# --------------------------------------------------------------------------
# The mouse guard (M3's filter, plus move, wheel and double-click)
# --------------------------------------------------------------------------


class _NoMouse(QObject):
    """Records any spontaneous mouse event that reaches the application (12.1 code K)."""

    def __init__(self) -> None:
        super().__init__()
        self.seen: List[str] = []
        kinds = getattr(QEvent, "Type", QEvent)
        self._kinds = {
            int(getattr(kinds, name)): name
            for name in ("MouseButtonPress", "MouseButtonRelease", "MouseButtonDblClick", "MouseMove", "Wheel")
        }

    def eventFilter(self, watched: object, event: object) -> bool:  # noqa: N802
        kind = int(event.type())  # type: ignore[attr-defined]
        if kind in self._kinds and event.spontaneous():  # type: ignore[attr-defined]
            self.seen.append(self._kinds[kind])
        return False


# --------------------------------------------------------------------------
# The shared session
# --------------------------------------------------------------------------


@dataclass
class Shop:
    window: MainWindow
    qapp: QApplication
    root: Path
    state: Path
    desktop: Path
    guard: _NoMouse
    kb: Kb
    baselines: Dict[str, Tuple[object, str]] = field(default_factory=dict)
    findings: Dict[str, List[str]] = field(default_factory=dict)
    wall: Dict[str, float] = field(default_factory=dict)
    prompts: List[str] = field(default_factory=list)
    #: Keys pressed (and texts typed) per script: the persona walkthrough's step counts.
    steps: Dict[str, int] = field(default_factory=dict)

    def surface_for(self, path: Path) -> object:
        surface = self.window._tab_content_registry.surface_for_path(str(path))  # noqa: SLF001
        assert surface is not None, path
        return surface

    def open_form(self, path: Path, text: Optional[str] = None) -> object:
        """Setup, as in the lane scripts: put a fixture form in a tab and focus it, as the shell does."""
        if text is not None:
            path.write_text(text, encoding="utf-8")
        assert self.window._editor_tab_factory.open_file_in_editor(str(path))  # noqa: SLF001
        self.window._center_stack.setCurrentIndex(1)  # noqa: SLF001
        self.window.show()
        self.window.activateWindow()
        for _ in range(8):
            self.qapp.processEvents()
        surface = self.surface_for(path)
        self.use(surface, path)
        return surface

    def use(self, surface: object, path: Path) -> None:
        self.kb.surface = surface
        self.kb.path = path
        surface.focus_primary()  # type: ignore[attr-defined]
        self.kb.pump()

    def remember(self, name: str, surface: object, path: Path) -> None:
        """Record the form's baseline bytes (what Undo all must restore)."""
        self.baselines[name] = (surface, self.kb.text())


@pytest.fixture(scope="module")
def shop(tmp_path_factory: pytest.TempPathFactory, qapp: QApplication) -> Iterator[Shop]:
    if not __import__("app.features.form_builder.install", fromlist=["x"]).form_builder_enabled():
        pytest.skip("form builder is registered on PySide6")
    base = tmp_path_factory.mktemp("m5r")
    root = base / "shop"
    state = base / "state"
    desktop = base / "desktop"
    desktop.mkdir()
    (desktop / "logo.png").write_bytes(_png_bytes())
    # The fixtures of the lane scripts: widgets/till_display.py and widgets/broken.py.
    folder = root / "widgets"
    folder.mkdir(parents=True)
    (folder / "__init__.py").write_text("", encoding="utf-8")
    (folder / "till_display.py").write_text(_TILL, encoding="utf-8")
    (folder / "broken.py").write_text(_BROKEN, encoding="utf-8")
    # Templates and the preview options live in the isolated state dir, not the user's.
    template_store.use_state_root(str(state.resolve()))
    # M5.R persona walkthrough: CBCS_FB_PERSONA_THEME picks the shell theme (light, high_contrast_dark ...).
    theme = os.environ.get("CBCS_FB_PERSONA_THEME", "")
    if theme:
        state.mkdir(parents=True, exist_ok=True)
        (state / "settings.json").write_text(json.dumps({"theme": {"mode": theme}}), encoding="utf-8")
    window = MainWindow(state_root=str(state.resolve()))
    _project(window, root)
    window.resize(1400, 900)
    window.show()
    window.activateWindow()
    guard = _NoMouse()
    qapp.installEventFilter(guard)
    kb = Kb(window, qapp, None, root / "forms" / "x.ui")
    kb.pump()
    window._center_stack.setCurrentIndex(1)  # noqa: SLF001
    kb.pump()
    session = Shop(window, qapp, root, state, desktop, guard, kb)
    # The shell's external-change poll asks "Reload the file from disk?" in a modal box when a script's own step
    # rewrote an open tab's file (K17: the picture rename rewrites till.ui, adopting a picture rewrites resources.qrc).
    # A modal box would block a keys-only script forever, so answer No and keep the file name in ``prompts``.
    from app.shell import external_file_change_workflow as efc

    patch = pytest.MonkeyPatch()
    current: List[str] = []
    original_check = efc.ExternalFileChangeWorkflow.check_and_handle

    def check(self: object, file_path: str, **kwargs: object) -> object:
        current.append(file_path)
        try:
            return original_check(self, file_path, **kwargs)  # type: ignore[arg-type]
        finally:
            current.pop()

    def decline(self: object) -> bool:
        session.prompts.append(current[-1] if current else "?")
        kb.log.append("RELOAD PROMPT for %s" % Path(session.prompts[-1]).name)
        return False

    patch.setattr(efc.ExternalFileChangeWorkflow, "check_and_handle", check)
    patch.setattr(efc.MainWindowExternalFileChangeHost, "confirm_clean_tab_reload", decline)
    try:
        yield session
    finally:
        patch.undo()
        qapp.removeEventFilter(guard)
        template_store.use_state_root(None)
        PreviewPool.reset_shared()
        shutdown_main_window_for_test(window, qapp)


class Findings(AssertionError):
    """The soft findings of one script. A test that expects them is ``xfail(strict=True, raises=Findings)``."""


class Script:
    """Per-script state: the shared Kb, a timer and the soft findings."""

    def __init__(self, shop: Shop, name: str) -> None:
        self.shop = shop
        self.name = name
        self.kb = shop.kb
        self.kb.findings = []
        self.kb.log = []
        self.started = time.monotonic()
        _SHOTS[:] = [name, 0]

    def finish(self) -> None:
        self.shop.wall[self.name] = time.monotonic() - self.started
        self.shop.steps[self.name] = sum(1 for line in self.kb.log if not line.startswith(("FINDING", "RELOAD")))
        self.shop.findings[self.name] = list(self.kb.findings)
        print("%s keys:\n%s" % (self.name, self.kb.history()))
        if self.kb.findings:
            raise Findings("%s findings:\n%s" % (self.name, "\n".join(self.kb.findings)))


#: The running script and how many shots it took (CBCS_FB_SCREENSHOT_DIR only).
_SHOTS: List[object] = ["", 0]


def _shot(kb: Kb) -> None:
    """Grab the window before an undo-all, the state the script built (persona walkthrough evidence)."""
    folder = os.environ.get("CBCS_FB_SCREENSHOT_DIR") or ""
    if not folder:
        return
    _SHOTS[1] = int(_SHOTS[1]) + 1  # type: ignore[call-overload]
    theme = os.environ.get("CBCS_FB_PERSONA_THEME", "") or "default"
    scale = os.environ.get("QT_SCALE_FACTOR", "1")
    Path(folder).mkdir(parents=True, exist_ok=True)
    kb.pump()
    window = kb.window if hasattr(kb, "window") else None
    if window is None:
        return
    name = "m5r_%s_%d_%s_%sx.png" % (str(_SHOTS[0]).lower(), _SHOTS[1], theme, scale)
    window.grab().save(str(Path(folder) / name))


def undo_all(kb: Kb, limit: int = 60) -> None:
    _shot(kb)
    kb.press("Key_3", "Alt")
    for _ in range(limit):
        if not kb.session.log.can_undo():
            return
        kb.press("Key_Z", "Control")
    kb.check(not kb.session.log.can_undo(), "undo all reaches the bottom of the stack")


def redo_all(kb: Kb, limit: int = 60) -> None:
    for _ in range(limit):
        if not kb.session.log.can_redo():
            return
        kb.press("Key_Z", "Control", "Shift")
    kb.check(not kb.session.log.can_redo(), "redo all reaches the top of the stack")


def undo_all_and_back(kb: Kb, baseline: str) -> None:
    """Undo all restores the baseline bytes; then Redo all restores what the script made."""
    made = kb.text()
    undo_all(kb)
    kb.check(kb.text() == baseline, "undo all returns the baseline bytes")
    redo_all(kb)
    kb.check(kb.text() == made, "redo all returns the bytes the script made")


# --------------------------------------------------------------------------
# K16 Main window
# --------------------------------------------------------------------------


def _new_form(shop: Shop, name: str, card: str) -> object:
    """File > New Form…, the name, arrows to the card, Enter. Returns the new form's surface."""
    kb = shop.kb
    window = shop.window
    kb.surface = None  # the new tab has no form session yet
    action = window.menu_registry.action("shell.action.file.newForm")  # type: ignore[attr-defined]
    kb.check(action is not None and action.isEnabled(), "File > New Form… exists")
    # No menu mnemonics on macOS (as K1): the item is triggered the way Enter on the menu row would.
    action.trigger()
    kb.pump()
    kb.check(isinstance(kb.focus(), QLineEdit), "the name field has focus, got %s" % kb.focus_name())
    kb.press("Key_A", "Control")
    kb.type(name)
    panel = window.findChild(QWidget, "formBuilder.newForm")
    kb.check(panel is not None, "the New form tab is open")
    target = panel.card(card)
    for _ in range(14):
        if kb.focus() is target:
            break
        kb.press("Key_Tab")
    for _ in range(14):
        if kb.focus() is target:
            break
        kb.press("Key_Right")
    kb.check(kb.focus() is target, "keys reach the %s card" % card)
    kb.press("Key_Return")
    kb.pump(12)
    path = shop.root / "forms" / ("%s.ui" % name)
    kb.check(path.is_file(), "Enter on the card creates %s" % path.name)
    surface = shop.surface_for(path)
    kb.surface = surface
    kb.path = path
    kb.pump()
    return surface


def _go_to(kb: Kb, name: str) -> None:
    """Ctrl+R, the name, Enter (Go to widget)."""
    kb.press("Key_R", "Control")
    kb.type(name)
    kb.press("Key_Return")
    kb.check(kb.current() == name, "Ctrl+R goes to %s, selected %s" % (name, kb.selected()))


def _ctx_menu_path(kb: Kb, titles: Tuple[str, ...]) -> None:
    """Shift+F10 is already pressed: Down to each title, Right opens a submenu, Enter on the last."""
    for position, title in enumerate(titles):
        menu = QApplication.activePopupWidget()
        kb.check(isinstance(menu, QMenu), "a context menu is open for %r" % title)
        found = False
        for _ in range(80):
            active = menu.activeAction()
            if active is not None and active.text().split("\t")[0].startswith(title) and active.isVisible():
                found = True
                break
            kb.press("Key_Down")
        kb.check(found, "no menu row %r in %s" % (title, [a.text() for a in menu.actions()]))
        kb.press("Key_Right" if position < len(titles) - 1 else "Key_Return")


def _toast(kb: Kb) -> str:
    toast = kb.surface._command_toast
    return str(toast._text.text()) if toast.isVisible() else ""


def test_k16_main_window(shop: Shop) -> None:
    script = Script(shop, "K16")
    kb = script.kb
    surface = _new_form(shop, "shop_window", "main_window")
    path = kb.path
    kb.check(kb.session.document.root.object_name == "ShopWindow", "root is ShopWindow")
    baseline = kb.text()
    shop.remember("K16", surface, path)
    kb.check(
        baseline.index('name="menubar"') < baseline.index('name="centralwidget"') < baseline.index('name="statusbar"'),
        "the form has menubar, centralwidget, statusbar in that order",
    )
    from app.features.form_builder.engine.query import actions as q

    session = kb.session
    doc = session.document
    editor = surface._menu_edit.editor

    def entries(name: str) -> List[object]:
        return list(q.entries(doc, doc.by_name(name)[0]))

    def levels() -> int:
        return len(editor.levels)

    _go_to(kb, "menubar")
    kb.press("Key_Return")
    kb.check(editor.active and levels() == 1, "Enter starts menu editing on the menu bar")
    kb.type("&File")
    kb.press("Key_Return")
    kb.check("menuFile" in doc.names(), "typing &File and Enter makes menuFile")
    kb.press("Key_Down")
    kb.check(levels() == 2 and editor.levels[-1].slot == 0, "Down opens File with focus on its Type here")
    kb.type("New sale")
    kb.press("Key_Return")
    kb.type("Print receipt")
    kb.press("Key_Return")
    kb.check(editor.levels[-1].slot == 2, "focus is back on Type here after each entry")
    kb.press("Key_Down")
    kb.press("Key_Return")
    kb.check([e.kind for e in entries("menuFile")] == ["action", "action", "separator"], "Down, Enter adds a separator")
    kb.press("Key_Up")
    kb.type("Quit")
    kb.press("Key_Return")
    kb.press("Key_Up")
    kb.press("Key_Up", "Alt")
    kb.check(
        [e.name for e in entries("menuFile")] == ["actionNew_sale", "actionPrint_receipt", "actionQuit", "separator"],
        "Alt+Up puts Quit above the separator",
    )
    kb.press("Key_Down", "Alt")
    kb.check([e.kind for e in entries("menuFile")] == ["action", "action", "separator", "action"], "Alt+Down puts it back")
    kb.press("Key_Escape")
    kb.check(levels() == 1 and editor.levels[0].slot == 0, "Esc closes File, its title has focus")
    kb.press("Key_Right")
    kb.type("Help")
    kb.press("Key_Return")
    kb.check([e.name for e in entries("menubar")] == ["menuFile", "menuHelp"], "Right, Help, Enter adds menuHelp")
    kb.press("Key_Escape")
    kb.check(not editor.active, "Esc ends menu editing")
    # Esc until the window is selected, Shift+F10, Main window > Add toolbar.
    for _ in range(6):
        if kb.selected() == ("ShopWindow",):
            break
        kb.press("Key_Escape")
    kb.check(kb.selected() == ("ShopWindow",), "Esc walks up to the window, got %s" % (kb.selected(),))
    kb.press("Key_F10", "Shift")
    _ctx_menu_path(kb, ("Main window", "Add toolbar"))
    kb.check("toolBar" in doc.names() and kb.selected() == ("toolBar",), "toolBar exists and is selected, got %s" % (kb.selected(),))
    kb.press("Key_Return")
    kb.check(editor.active, "Enter edits the toolbar")
    kb.type("Pri")
    view = editor.view().levels[-1]
    kb.check(
        view.reuse[0].label == "New action \u201cPri\u201d" and view.reuse[1].label == "Print receipt",
        "the reuse list shows New action Pri current and Print receipt under it",
    )
    kb.press("Key_Down")
    kb.press("Key_Return")
    kb.check([e.name for e in entries("toolBar")] == ["actionPrint_receipt"], "the toolbar references actionPrint_receipt")
    kb.check("actionPrint_receipt" in [e.name for e in entries("menuFile")], "the File menu still has actionPrint_receipt")
    info = {item.name: item for item in q.list_actions(doc)}
    kb.check(info["actionPrint_receipt"].used_line == "File menu, toolBar", "used line: %s" % info["actionPrint_receipt"].used_line)
    # Alt+5: the Actions section is focused; its Print receipt row says where it is used.
    pane = surface.workbench.section_widget("actions")

    def in_actions() -> bool:
        focus = kb.focus()
        return focus is not None and (focus is pane or pane.isAncestorOf(focus))

    kb.press("Key_5", "Alt")
    kb.soft(
        in_actions(),
        "F-k16-alt5",
        "Alt+5 while the toolbar is being edited is swallowed by the menu editor (focus stays %s, editor active=%s); "
        "MenuEditGlue.eventFilter returns True for any key with text, Alt+digit included" % (kb.focus_name(), editor.active),
    )
    if not in_actions():
        # What the user does next: Esc ends the editing, then Alt+5 works.
        kb.press("Key_Escape")
        kb.press("Key_5", "Alt")
    kb.check(in_actions(), "Alt+5 focuses Actions, got %s" % kb.focus_name())
    rows = {row[0]: row[2] for row in pane.row_texts()}
    kb.check(rows.get("Print receipt") == "File menu, toolBar", "the Print receipt row says %r" % (rows,))
    # Back on the toolbar (Alt+3, Enter), Delete on Print receipt.
    kb.press("Key_3", "Alt")
    kb.check(kb.selected() == ("toolBar",), "Alt+3 is back on the toolbar, got %s" % (kb.selected(),))
    kb.press("Key_Return")
    kb.press("Key_Delete")
    kb.check(
        "from toolBar. It's still on the File menu." in _toast(kb) and "actionPrint_receipt" in doc.names(),
        "the toast says it is still on the File menu: %r" % _toast(kb),
    )
    kb.press("Key_Escape")
    kb.check(not editor.active, "Esc ends menu editing")
    kb.check(
        [entry.label for entry in session.log.entries()]
        == [
            "Add menu File",
            "Add New sale to the File menu",
            "Add Print receipt to the File menu",
            "Add separator",
            "Add Quit to the File menu",
            "Move Quit",
            "Move Quit",
            "Add menu Help",
            "Add toolbar",
            "Add Print receipt to toolBar",
            "Remove Print receipt",
        ],
        "one undo step per edit with its 13.2.10 name: %s" % [entry.label for entry in session.log.entries()],
    )
    undo_all_and_back(kb, baseline)
    script.finish()


# --------------------------------------------------------------------------
# K17 Pictures
# --------------------------------------------------------------------------

_ICON_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Pay</class>
 <widget class="QWidget" name="Pay">
  <property name="geometry"><rect><x>0</x><y>0</y><width>320</width><height>200</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QPushButton" name="payButton">
     <property name="text"><string>Pay</string></property>
     <property name="icon"><iconset><normaloff>art/pay.png</normaloff></iconset></property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _quick_open(shop: Shop, words: str) -> None:
    """Ctrl+P, the words, Enter (the shell's Quick Open)."""
    kb = shop.kb
    # Setup, not a key: the shell's project rescan lists the files the script made since the project opened.
    loaded = shop.window._loaded_project  # noqa: SLF001
    shop.window._loaded_project = dataclasses.replace(  # noqa: SLF001
        loaded, entries=enumerate_project_entries(loaded.project_root)
    )
    kb.press("Key_P", "Control")
    dialog = kb.shop_window._quick_open_dialog  # type: ignore[attr-defined]
    kb.check(dialog is not None and dialog.isVisible(), "Ctrl+P opens Quick Open")
    kb.type(words)
    _pump_until(kb.qapp, lambda: False, 0.4)
    kb.press("Key_Return")
    kb.pump(12)


@pytest.mark.xfail(
    strict=True,
    raises=Findings,
    reason="F-k17-qrc-focus: opening resources.qrc from Quick Open leaves focus off the pictures grid (the shell never calls focus_primary)",
)
def test_k17_pictures(shop: Shop, monkeypatch: pytest.MonkeyPatch) -> None:
    script = Script(shop, "K17")
    kb = script.kb
    kb.shop_window = shop.window  # type: ignore[attr-defined]
    surface = _new_form(shop, "till", "widget")
    path = kb.path
    baseline = kb.text()
    shop.remember("K17", surface, path)
    # Insert a label: / , "label", Enter.
    kb.press("Key_Slash")
    kb.log.append("quick insert focus: %s" % kb.focus_name())
    kb.type("label")
    kb.press("Key_Return")
    kb.check(kb.current().startswith("label"), "a label is inserted and selected, got %s" % (kb.selected(),))
    logo = kb.current()
    session = kb.session
    steps = len(session.log.entries())
    # Alt+4 to Picture, Enter: the picker opens; Tab to Add picture…, Enter; the dialog gets the fixture path.
    _find_row(kb, "picture", "pixmap")
    kb.press("Key_Return")
    footer = [w for w in QApplication.allWidgets() if w.objectName() == "formBuilder.pictureAdd" and w.isVisible()]
    kb.check(bool(footer), "Enter on the Picture row opens the picker")
    for _ in range(12):
        if kb.focus_name() == "formBuilder.pictureAdd":
            break
        kb.press("Key_Tab")
    kb.check(kb.focus_name() == "formBuilder.pictureAdd", "Tab reaches Add picture…, got %s" % kb.focus_name())
    fixture = str(shop.desktop / "logo.png")
    asked: List[str] = []
    # The file dialog takes the typed path of logo.png: the static dialog is answered with that path.
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileNames",
        staticmethod(lambda *a, **k: asked.append("asked") or ([fixture], "")),
    )
    kb.press("Key_Return")
    kb.pump(12)
    kb.soft(
        asked == ["asked"],
        "F-k17-enter-button",
        "Enter on the focused Add picture… button does nothing (a plain QPushButton in the popover activates on Space only), "
        "UX_SPEC K17 says Enter; picture_picker.py formBuilder.pictureAdd",
    )
    if not asked:
        kb.press("Key_Space")
        kb.pump(12)
    kb.check(asked == ["asked"], "Enter or Space on Add picture… opens the file dialog")
    qrc = shop.root / "forms" / "resources.qrc"
    kb.check(qrc.is_file() and "<file>pictures/logo.png</file>" in qrc.read_text(encoding="utf-8"), "forms/resources.qrc lists pictures/logo.png")
    kb.check((shop.root / "forms" / "pictures" / "logo.png").read_bytes() == _png_bytes(), "forms/pictures/logo.png is a byte copy")
    kb.check('location="resources.qrc"' in kb.text(), "the form includes the .qrc")
    kb.check("<pixmap>:/pictures/logo.png</pixmap>" in kb.text(), "the label's picture is :/pictures/logo.png")
    kb.check(len(session.log.entries()) == steps + 1, "one undo step")
    kb.check(session.log.undo_label() == "Add picture logo.png", "named Add picture logo.png, got %r" % session.log.undo_label())
    # Ctrl+S: resources_rc.py exists and a QUiLoader preview shows the picture.
    kb.press("Key_3", "Alt")
    kb.press("Key_S", "Control")
    rc = shop.root / "forms" / "resources_rc.py"
    kb.check(rc.is_file(), "Ctrl+S writes resources_rc.py")
    kb.check(path.read_text(encoding="utf-8") == kb.text(), "Ctrl+S saved the form")
    namespace = runpy.run_path(str(rc))
    try:
        loaded = QUiLoader().load(str(path))
        label = loaded.findChild(QLabel, logo)
        kb.check(label is not None and not label.pixmap().isNull(), "a QUiLoader preview shows the picture")
        loaded.deleteLater()
    finally:
        namespace["qCleanupResources"]()
    # Undo: the property and the include are gone, the files stay; Redo.
    kb.press("Key_Z", "Control")
    kb.check("logo.png" not in kb.text() and "resources.qrc" not in kb.text(), "Undo removes the property and the include")
    kb.check(qrc.is_file() and (shop.root / "forms" / "pictures" / "logo.png").is_file(), "the files stay")
    kb.press("Key_Z", "Control", "Shift")
    kb.check("<pixmap>:/pictures/logo.png</pixmap>" in kb.text(), "Redo brings the picture back")
    # Ctrl+P, "resources.qrc", Enter: the resource editor.
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("shop_logo.png", True)))
    _quick_open(shop, "resources.qrc")
    editor = shop.window._tab_content_registry.surface_for_path(str(qrc))  # noqa: SLF001
    kb.check(editor is not None, "Quick Open opened resources.qrc as a tab; focus %s" % kb.focus_name())
    kb.surface = editor
    kb.check(hasattr(editor, "grid"), "Ctrl+P, resources.qrc, Enter opens the resource editor")
    kb.soft(
        kb.focus() is editor.grid,
        "F-k17-qrc-focus",
        "Quick Open of resources.qrc leaves focus on %s, not the pictures grid, so the script's arrow keys have no picture to move to "
        "(qtside/resources/editor.py focus_primary)" % kb.focus_name(),
    )
    for _ in range(14):
        if kb.focus() is editor.grid:
            break
        kb.press("Key_Tab")
    kb.check(kb.focus() is editor.grid, "Tab reaches the pictures grid, got %s" % kb.focus_name())
    kb.press("Key_Return")
    source = editor.content_source()
    kb.check(source.undo_label() == "Rename logo.png", "Enter renames the picture: %r" % source.undo_label())
    kb.press("Key_S", "Control")
    # The shell's own poll timer runs this on its next tick; run it now so the result does not depend on timing.
    kb.check('<file alias="shop_logo.png">pictures/logo.png</file>' in qrc.read_text(encoding="utf-8"), "the alias is written")
    rc_text = rc.read_text(encoding="utf-8")
    kb.check("shop_logo.png" in rc_text or rc.read_bytes() != b"", "resources_rc.py is rewritten")
    # The fixture form whose button icon is a file path.
    art = shop.root / "forms" / "art"
    art.mkdir(parents=True, exist_ok=True)
    (art / "pay.png").write_bytes(_png_bytes())
    pay_path = shop.root / "forms" / "pay.ui"
    pay_path.write_text(_ICON_FORM, encoding="utf-8")
    shop.window._editor_tab_factory.open_file_in_editor(str(pay_path))  # noqa: SLF001
    kb.pump(12)
    pay = shop.surface_for(pay_path)
    shop.use(pay, pay_path)
    pay_baseline = kb.text()
    shop.remember("K17 icon form", pay, pay_path)
    kb.press("Key_3", "Alt")
    _walk_to(kb, "payButton")
    kb.check(
        any(d.code == "FB031" for d in kb.session.diagnostics.all()),
        "FB031 is raised for the file-path icon: %s" % [d.code for d in kb.session.diagnostics.all()],
    )
    _find_row(kb, "icon", "icon")
    for _ in range(12):
        if kb.focus_name() == "formBuilder.pictureAdopt":
            break
        kb.press("Key_Tab")
    kb.check(kb.focus_name() == "formBuilder.pictureAdopt", "Tab reaches Add to project pictures, got %s" % kb.focus_name())
    kb.press("Key_Return")
    kb.soft(
        "<normaloff>:/art/pay.png</normaloff>" in kb.text(),
        "F-k17-enter-button",
        "Enter on the focused Add to project pictures button does nothing (Space activates it)",
    )
    if "<normaloff>:/art/pay.png</normaloff>" not in kb.text():
        kb.press("Key_Space")
    kb.check("<normaloff>:/art/pay.png</normaloff>" in kb.text(), "the icon is a resource path")
    kb.check(not any(d.code == "FB031" for d in kb.session.diagnostics.all()), "FB031 is gone")
    kb.check(kb.session.log.undo_label() == "Add picture pay.png", "one step: Add picture pay.png")
    undo_all_and_back(kb, pay_baseline)
    # Back to the logo form for its own undo all.
    shop.window._editor_tab_factory.open_file_in_editor(str(path))  # noqa: SLF001
    kb.pump(12)
    shop.use(surface, path)
    undo_all_and_back(kb, baseline)
    script.finish()


# --------------------------------------------------------------------------
# K18 Style
# --------------------------------------------------------------------------


def test_k18_style(shop: Shop) -> None:
    script = Script(shop, "K18")
    kb = script.kb
    path = shop.root / "forms" / "style.ui"
    surface = shop.open_form(path, K18_FORM)
    original = kb.text()
    shop.remember("K18", surface, path)
    session = kb.session
    _k18_walk_to(kb, "okButton")
    _find_row(kb, "style", "styleSheet")
    kb.check(kb.focus_name() == "formBuilder.styleEdit", "Tab reaches the Style sheet row's Edit button")
    kb.press("Key_Return")
    drawer = surface.workbench._under_widget
    kb.check(surface.workbench.under_canvas_key() == "style", "Enter opens the style sheet drawer")
    kb.check(QApplication.focusWidget() is drawer.editor, "focus is in the drawer's editor")
    kb.type("QPushButton#okButton { background: #1A7F37; }")
    _wait(kb, 400)
    kb.check(_green(surface, "okButton"), "after 300 ms the canvas button is green")
    kb.check(drawer.status_text().endswith("Looks right"), "the status reads Looks right")
    kb.check([chip[1] for chip in drawer.chips()] == ["1 widget"], "the chip reads 1 widget")
    kb.press("Key_Backspace")
    _wait(kb, 400)
    kb.check(drawer.status_text().endswith("Line 1: a } is missing."), "the status names the line")
    kb.check(_green(surface, "okButton"), "the button stays green")
    kb.type("}")
    _wait(kb, 400)
    kb.press("Key_Escape")
    kb.check(surface.workbench.under_canvas_key() == "", "Esc closes the drawer")
    kb.check(kb.focus_name() == "formBuilder.styleEdit", "focus is on the Style sheet row")
    kb.check(session.log.undo_label() == "Change style sheet of okButton", "one step: Change style sheet of okButton")
    _k18_walk_to(kb, "titleLabel")
    for words, row, color in (
        ("text colour", "textColour", "#FFFFFF"),
        ("background", "backgroundColour", "#1A7F37"),
    ):
        _find_row(kb, words, row)
        kb.press("Key_Return")
        for _ in range(12):
            if kb.focus_name() == "formBuilder.colorHex":
                break
            kb.press("Key_Tab")
        kb.check(kb.focus_name() == "formBuilder.colorHex", "Tab reaches Hex in the %s popover" % words)
        kb.press("Key_A", "Control")
        kb.type(color)
        kb.press("Key_Return")
        popover = [w for w in surface.findChildren(QWidget, "formBuilder.rowPopover") if w.isVisible()]
        if popover:
            kb.press("Key_Escape")
        kb.check(
            not [w for w in surface.findChildren(QWidget, "formBuilder.rowPopover") if w.isVisible()],
            "the %s popover is closed" % words,
        )
    text = kb.text()
    kb.check("color: #FFFFFF;" in text, "the label's style sheet has the text colour")
    kb.check(text.count('<colorrole role="Window">') == 3 and "autoFillBackground" in text, "the XML has the Window role and the fill")
    kb.press("Key_3", "Alt")
    for _ in range(8):
        if kb.selected() == ("Shop",):
            break
        kb.press("Key_Escape")
    kb.check(kb.selected() == ("Shop",), "Esc selects the form")
    _wait(kb, 80)
    kb.press("Key_4", "Alt")
    kb.press("Key_F", "Control")
    kb.press("Key_Backspace")
    for _ in range(30):
        kb.press("Key_Tab")
        if kb.focus_name() == "formBuilder.textSize":
            break
    kb.check(kb.focus_name() == "formBuilder.textSize", "Tab reaches Text size")
    kb.press("Key_A", "Control")
    kb.type("12")
    kb.press("Key_Return")
    _wait(kb, 100)
    kb.check("<pointsize>12</pointsize>" in kb.text(), "Text size 12 is on the form's font")
    undo_all(kb)
    kb.check(kb.text() == original, "undo all returns the original bytes")
    script.finish()


# --------------------------------------------------------------------------
# K19 Your own class
# --------------------------------------------------------------------------


def _preview_pool() -> PreviewPool:
    pool = PreviewPool(
        command=python_preview_command(current_runtime_python(), repo_root()),
        config=DirectorConfig(handshake_timeout=20.0, request_timeout=15.0, shutdown_grace=0.4, ping_interval=30.0, prewarm=True),
        root=repo_root(),
    )
    PreviewPool._shared = pool
    return pool


def test_k19_your_own_class(shop: Shop) -> None:
    script = Script(shop, "K19")
    kb = script.kb
    qapp = shop.qapp
    path = shop.root / "forms" / "till_class.ui"
    surface = shop.open_form(path, K19_FORM)
    original = kb.text()
    shop.remember("K19", surface, path)
    recorder = _ImportRecorder(shop.root)
    sys.meta_path.insert(0, recorder)
    _preview_pool()
    preview_notice.forget_noted()
    try:
        notices = surface.own_class_preview
        _k19_select(kb, "totalLabel")
        kb.press("Key_F10", "Shift")
        _menu_pick(kb, "Use my own class")
        popover = _popover(kb)
        kb.check(popover.focusWidget().objectName() == "formBuilder.ownClassName", "the popover opens with focus on Class")
        _ptype(kb, popover, "TillDisplay")
        _ppress(kb, popover, "Key_Tab")
        kb.check(popover.focusWidget().objectName() == "formBuilder.ownClassModule", "Tab goes to the module")
        _ptype(kb, popover, "widgets.till_display")
        _check_line(kb, popover, "Found TillDisplay in widgets/till_display.py.")
        _ppress(kb, popover, "Key_Tab")
        kb.check(popover.focusWidget().objectName() == "formBuilder.ownClassUse", "Tab goes to [Use TillDisplay]")
        kb.check(popover._use.text() == "Use TillDisplay", "the button names the class")
        _ppress(kb, popover, "Key_Return")
        text = kb.text()
        kb.check('<widget class="TillDisplay" name="totalLabel">' in text, "the label now has the class")
        kb.check('<header location="local">widgets/till_display.h</header>' in text, "the header is the module as a path")
        kb.check(kb.session.log.undo_label() == "Use class TillDisplay for totalLabel", "one step with its name")
        header = kb.pane("formBuilder.inspectorHeader")
        kb.check(
            header._class_full == "TillDisplay \u00b7 your class, based on Label" and header._class_short == "TillDisplay (QLabel)",
            "the inspector header names the base: %r / %r" % (header._class_full, header._class_short),
        )
        kb.check(recorder.seen == [], "no module of widgets/ was imported in the editor: %s" % recorder.seen)
        kb.check(not any(name.split(".")[0] in ("widgets", "till_display") for name in sys.modules), "sys.modules has none")
        kb.check("CBCS_TILL_IMPORTED" not in __import__("os").environ, "the module did not run")
        kb.check(
            [entry.class_name for entry in registry_for(str(shop.root.resolve())).entries()] == ["TillDisplay"],
            "the class is saved for the project's other forms",
        )
        kb.press("Key_R", "Control", "Shift")
        kb.check(_pump_until(qapp, lambda: notices.last_response is not None), "the preview child answered")
        response = notices.last_response
        kb.check(response.ok, "preview opened: %s" % response.detail)
        kb.check(response.result["texts"]["totalLabel"] == "till:Total", "the child built the real TillDisplay")
        kb.check("totalLabel" not in response.result["stubs"], "no stand-in for TillDisplay")
        bar = surface._notice
        kb.check(bar.isVisible(), "the security info bar shows")
        kb.check(
            bar._label.text()
            == "Preview runs code from this project: TillDisplay (widgets/till_display.py). "
            "Code Studio runs it only in the preview window, never in the editor.",
            bar._label.text(),
        )
        kb.check([b.text() for b in bar._buttons] == ["Got it"], "the bar has [Got it]")
        bar._buttons[0].click()
        kb.pump()
        kb.check(not bar.isVisible(), "Got it closes the bar")
        kb.check(recorder.seen == [], "still nothing imported in the editor after Preview")
        _k19_select(kb, "noteLabel")
        kb.press("Key_F10", "Shift")
        _menu_pick(kb, "Use my own class")
        popover = _popover(kb)
        _ptype(kb, popover, "Broken")
        _ppress(kb, popover, "Key_Tab")
        _ptype(kb, popover, "widgets.broken")
        _check_line(kb, popover, "Found Broken in widgets/broken.py.")
        _ppress(kb, popover, "Key_Tab")
        _ppress(kb, popover, "Key_Return")
        kb.check('<widget class="Broken" name="noteLabel">' in kb.text(), "noteLabel uses Broken")
        surface.request_preview(str(kb.path))
        kb.check(
            _pump_until(qapp, lambda: notices.last_response is not None and "noteLabel" in notices.last_response.result.get("stubs", [])),
            "the stand-in shows in the answer",
        )
        kb.check(notices.last_response.ok, "the preview opens although Broken raises")
        kb.check(notices.last_response.result["texts"]["totalLabel"] == "till:Total", "TillDisplay is still the real class")
        rows = [d for d in kb.session.diagnostics.all() if d.code == "FB602"]
        kb.check(len(rows) == 1, "one FB602 row: %s" % [d.message for d in kb.session.diagnostics.all()])
        kb.check(
            rows[0].message == "Preview used a stand-in for Broken: RuntimeError in widgets/broken.py line 7.",
            rows[0].message,
        )
        toast = surface._command_toast
        kb.check(toast.isVisible() and "Preview used a plain label for Broken." in toast._text.text(), "the stand-in toast shows")
        kb.check(toast._action.text() == "Show problem", "the toast offers Show problem")
        kb.check(not kb.surface._notice.isVisible(), "the security note is not shown twice in a session")
        kb.check(recorder.seen == [], "the editor still imported nothing")
        _k19_select(kb, "noteLabel")
        kb.press("Key_F2")
        kb.press("Key_A", "Control")
        kb.type("receiptLabel")
        kb.press("Key_Return")
        kb.check('name="receiptLabel"' in kb.text() and 'name="noteLabel"' not in kb.text(), "the rename works")
        kb.press("Key_F10", "Shift")
        _menu_pick(kb, "Back to label")
        text = kb.text()
        kb.check("<class>Broken</class>" not in text, "the Broken declaration is gone")
        kb.check("<class>TillDisplay</class>" in text, "the TillDisplay declaration stays")
        kb.check('<widget class="QLabel" name="receiptLabel">' in text, "the label is a label again")
        undo_all(kb, 20)
        kb.check(kb.text() == original, "undo all gives the original bytes")
        script.finish()
    finally:
        sys.meta_path.remove(recorder)
        PreviewPool.reset_shared()


# --------------------------------------------------------------------------
# K20 Preview options and code
# --------------------------------------------------------------------------


def test_k20_preview_options_and_code(shop: Shop) -> None:
    script = Script(shop, "K20")
    kb = script.kb
    qapp = shop.qapp
    path = shop.root / "forms" / "customer.ui"
    surface = shop.open_form(path, _long_form())
    # Setup, not a key: the canvas keeps 360 px beside the code only in a wide window (UX-PREV-004).
    shop.window.resize(1900, 900)
    kb.pump()
    pool = _preview_pool()
    try:
        notices = surface.own_class_preview
        control = surface.preview_control
        original = kb.text()
        shop.remember("K20", surface, path)
        file_bytes = kb.path.read_bytes()
        steps = len(kb.session.log.entries())
        _menu_path(kb, ("Preview options", "Screen", "Small screen"))
        kb.check(control.choices.screen == "Small screen", "the Small screen row was chosen: %s" % control.choices.screen)
        saved = PreviewOptionsStore(str(shop.state)).load()[0]
        kb.check(saved.screen == "Small screen", "the choice is kept per user, outside the form")
        kb.press("Key_R", "Control", "Shift")
        kb.check(_pump_until(qapp, lambda: notices.last_response is not None), "the preview child answered")
        response = notices.last_response
        kb.check(response.ok, "preview opened: %s" % response.detail)
        kb.check(response.result["title"] == "Preview \u00b7 customer.ui \u00b7 Small screen", response.result["title"])
        width, height = response.result["size"]
        kb.check(width <= 1024 and height <= 600, "the window fits the small screen: %s x %s" % (width, height))
        kb.check(control.is_open, "the editor knows the preview is open")
        # Esc closes the window: the key goes to the preview child process, which this process cannot press;
        # the host's close_view is the same request the editor sees (as in the lane script).
        from app.features.form_builder.engine.ipc.protocol import CloseView
        import uuid

        pool.request(CloseView(request_id=uuid.uuid4().hex, view_id=notices.view_id), lambda _r: None)
        kb.check(_pump_until(qapp, lambda: not control.is_open), "the preview window closed")
        _menu_path(kb, ("Save image",))
        dialog = next(
            (w for w in QApplication.topLevelWidgets() if w.objectName() == "formBuilder.saveImageDialog" and w.isVisible()),
            None,
        )
        kb.check(dialog is not None, "the save dialog is open")
        kb.check(isinstance(dialog, QFileDialog), "it is the shell file dialog")
        kb.check(
            dialog.directory().absolutePath() == str((shop.root / "forms").resolve()),
            "it opens in the form's folder: %s" % dialog.directory().absolutePath(),
        )
        dialog.activateWindow()
        qapp.processEvents()
        field = dialog.findChild(QLineEdit, "fileNameEdit")
        kb.check(field is not None and field.text() == "customer.png", "the default name is customer.png")
        field.setFocus()
        kb.press("Key_Return")
        target = shop.root / "forms" / "customer.png"
        kb.check(_pump_until(qapp, target.exists, 8.0), "customer.png exists")
        image = QImage(str(target))
        page = surface.page_widget()
        ratio = image.devicePixelRatio() or 1.0
        kb.check(
            (image.width(), image.height()) == (page.width(), page.height())
            or (round(image.width() / ratio), round(image.height() / ratio)) == (page.width(), page.height()),
            "the image has the page's size: %sx%s vs %sx%s" % (image.width(), image.height(), page.width(), page.height()),
        )
        toast = surface._command_toast
        kb.check(toast.isVisible() and "Saved customer.png." in toast._text.text(), "the saved toast shows")
        kb.check(toast._action.text() == "Show", "the toast offers Show")
        kb.press("Key_K", "Control")
        kb.press("Key_C")
        workbench = surface._workbench
        kb.check(workbench.beside_canvas_key() == "code", "the code split is open")
        view = workbench.code_view
        panel = view.panel
        kb.check(_pump_until(qapp, lambda: "class Ui_Customer" in panel.text()), "the generated module is shown")
        kb.check(panel.editor.isReadOnly(), "the code is read only")
        kb.check(panel._title.text() == "ui_customer.py \u00b7 as it will be saved", panel._title.text())
        kb.press("Key_1", "Alt")
        kb.press("Key_End")
        selected = kb.selected()
        kb.check(len(selected) == 1 and selected[0].startswith("row"), "a row widget is selected: %s" % (selected,))
        line = view._index.first_line(selected[0])
        kb.check(line is not None, "the generated code creates %s" % selected[0])
        kb.check(
            _pump_until(qapp, lambda: panel.first_visible_line() <= line <= panel.last_visible_line()),
            "the code scrolled to line %s (shows %s-%s)" % (line, panel.first_visible_line(), panel.last_visible_line()),
        )
        kb.check(line in panel.marked_lines(), "the widget's lines are marked")
        kb.press("Key_Up")
        previous = kb.selected()[0]
        kb.check(previous != selected[0], "Up selects another widget")
        kb.check(view._index.first_line(previous) in panel.marked_lines(), "the marks follow the selection")
        kb.press("Key_K", "Control")
        kb.press("Key_C")
        kb.check(workbench.beside_canvas_key() == "", "the split is closed")
        kb.check(kb.focus_in("formBuilder.canvas"), "focus is back on the canvas: %s" % kb.focus_name())
        kb.check(len(kb.session.log.entries()) == steps, "the undo stack did not change")
        kb.check(kb.text() == original, "the form did not change")
        kb.check(kb.path.read_bytes() == file_bytes, "the file bytes did not change")
        undo_all(kb)
        kb.check(kb.text() == original, "undo all (nothing to undo) keeps the bytes")
        script.finish()
    finally:
        PreviewPool.reset_shared()
        shop.window.resize(1400, 900)
        kb.pump()


# --------------------------------------------------------------------------
# K21 Form settings
# --------------------------------------------------------------------------


def test_k21_form_settings(shop: Shop) -> None:
    script = Script(shop, "K21")
    kb = script.kb
    path = shop.root / "forms" / "settings.ui"
    surface = shop.open_form(path, free_form(' stdsetdef="1"'))
    original = kb.text()
    shop.remember("K21", surface, path)
    steps = len(kb.session.log.entries())

    def added() -> int:
        return len(kb.session.log.entries()) - steps

    _menu_item(shop.window, "Form settings\u2026").trigger()
    kb.pump()
    kb.check(kb.focus_name() == "formBuilder.formSetting.author.edit", "Code is open and Author has focus")
    kb.type("Shop")
    kb.press("Key_Return")
    kb.check("<author>Shop</author>" in kb.text(), "Author is written")
    kb.check(added() == 1 and kb.session.log.undo_label() == "Change form setting: author", "one step, named for the row")
    _k21_tab_until(kb, "formBuilder.formSetting.layoutdefault.check")
    kb.press("Key_Space")
    kb.check('<layoutdefault spacing="8" margin="8"/>' in kb.text(), "Default gaps on writes 8 and 8")
    kb.check(added() == 2 and kb.session.log.undo_label() == "Change form setting: default gaps", "one step for Default gaps")
    kb.press("Key_Tab")
    kb.check(kb.focus_name() == "formBuilder.formSetting.layoutdefault.gap", "Tab reaches Gap")
    kb.type("6")
    kb.press("Key_Return")
    kb.check('<layoutdefault spacing="6" margin="8"/>' in kb.text(), "Gap 6 is written")
    kb.check(added() == 3, "Gap is one step")
    _k21_tab_until(kb, "formBuilder.group.translation")
    kb.press("Key_Space")
    kb.press("Key_Tab")
    kb.check(kb.focus_name() == "formBuilder.formSetting.idbasedtr.check", "Tab reaches Translate by ID")
    kb.press("Key_Space")
    kb.check('idbasedtr="true"' in kb.text(), "Translate by ID is written")
    kb.check(added() == 4 and kb.session.log.undo_label() == "Change form setting: translate by id", "one step for Translate by ID")
    _k21_tab_until(kb, "formBuilder.group.freePlacement")
    kb.press("Key_Space")
    kb.press("Key_Tab")
    kb.check(kb.focus_name() == "formBuilder.formSetting.grid.show", "Tab reaches Show grid")
    kb.press("Key_Tab")
    kb.check(kb.focus_name() == "formBuilder.formSetting.grid.across", "Tab reaches Step across")
    kb.type("16")
    kb.press("Key_Return")
    kb.check("gridDeltaX" in kb.text() and "<number>16</number>" in kb.text(), "Step across 16 is written")
    kb.check(added() == 5 and kb.session.log.undo_label() == "Change form setting: step across", "one step for Step across")
    for _ in range(40):
        if kb.focus_name() == "formBuilder.formSetting.stdsetdef.remove":
            break
        kb.press("Key_Tab", "Shift")
    kb.check(kb.focus_name() == "formBuilder.formSetting.stdsetdef.remove", "Shift+Tab reaches [Remove]")
    kb.press("Key_Return")
    kb.check("stdsetdef" not in kb.text(), "the older file setting is removed")
    kb.check(added() == 6 and kb.session.log.undo_label() == "Remove older file setting", "one step for Remove")
    kb.press("Key_3", "Alt")
    kb.check(kb.focus_in("formBuilder.canvas"), "Alt+3 focuses the canvas")
    for _ in range(12):
        if kb.current() == "payButton":
            break
        kb.press("Key_Tab")
    kb.check(kb.current() == "payButton", "Tab reaches payButton")
    kb.press("Key_Right", "Alt")
    kb.check("<x>32</x>" in kb.text(), "Alt+Right moves payButton 16 px (16 -> 32)")
    kb.check(added() == 7 and kb.session.log.undo_label() == "Nudge", "one step for the nudge")
    undo_all(kb)
    kb.check(kb.text() == original, "Undo all restores the original bytes")
    script.finish()


# --------------------------------------------------------------------------
# K22 Templates
# --------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    raises=Findings,
    reason="F-k22-duplicate-picture: New Form from a template adds a second pictures/logo.png entry when the qrc lists that file under an alias",
)
def test_k22_templates(shop: Shop) -> None:
    script = Script(shop, "K22")
    kb = script.kb
    window = shop.window
    # K16's window (redone to the state K16 left it) plus a logo label: the label is inserted and given the
    # project's logo picture by keys in K16's own form, the way K17 does it in its Widget form.
    surface16, baseline16 = shop.baselines["K16"]
    path16 = shop.root / "forms" / "shop_window.ui"
    window._editor_tab_factory.open_file_in_editor(str(path16))  # noqa: SLF001
    kb.pump(12)
    shop.use(surface16, path16)
    kb.press("Key_3", "Alt")
    _go_to(kb, "centralwidget")
    kb.press("Key_Slash")
    kb.type("label")
    kb.press("Key_Return")
    kb.check(kb.current().startswith("label"), "a label is inserted and selected, got %s" % (kb.selected(),))
    logo = kb.current()
    _find_row(kb, "picture", "pixmap")
    kb.press("Key_Return")
    kb.check(kb.focus_name() == "formBuilder.pictureSearch", "the picker opens on its search, got %s" % kb.focus_name())
    kb.type("logo")
    kb.press("Key_Down")
    kb.press("Key_Return")
    kb.check("<pixmap" in kb.text(), "the logo picture is on %s" % logo)
    kb.press("Key_3", "Alt")
    kb.press("Key_S", "Control")
    state = shop.state
    form_text = kb.text()
    _form_action(window, "Save as template\u2026").trigger()
    kb.pump()
    kb.check(kb.focus_name() == "formBuilder.saveTemplate.name", "the popover opens with Name focused")
    kb.type("Shop window")
    kb.press("Key_Tab")
    kb.check(kb.focus_name() == "formBuilder.saveTemplate.description", "Tab reaches Description")
    kb.type("Till and receipts")
    kb.press("Key_Return")
    kb.check(QApplication.activePopupWidget() is None, "Enter saves and closes the popover")
    folder = state / "form_templates" / "shop_window"
    names = sorted(p.name for p in folder.iterdir())
    kb.check(
        names == ["form.ui", "pictures", "resources.qrc", "template.json", "thumbnail.png"],
        "the folder holds form.ui, template.json, thumbnail.png and pictures: %s" % names,
    )
    kb.log.append("template files: %s; form.ui pictures %s" % (sorted(str(p.relative_to(folder)) for p in folder.rglob("*")), [u.path for u in picture_uses(read_ui((folder / "form.ui").read_text(encoding="utf-8"), allocator=IdAllocator()).document)]))
    kb.check((folder / "pictures" / "logo.png").is_file() and (folder / "pictures" / "logo.png").read_bytes() == _png_bytes(), "pictures/logo.png is the logo")
    meta = json.loads((folder / "template.json").read_text(encoding="utf-8"))
    kb.check(meta["name"] == "Shop window" and meta["description"] == "Till and receipts", "name and description kept")
    kb.check((folder / "thumbnail.png").stat().st_size > 0, "the thumbnail has a picture")
    kb.check(kb.text() == form_text, "saving a template does not change the form")
    # File > New Form…: Your templates first; back_office; Tab to the card; Enter.
    kb.surface = None
    window._open_new_form()
    kb.pump()
    registry = window._tab_content_registry  # noqa: SLF001
    panel = registry.surface_for_path(str(shop.root / "cbcs" / "new-form.cbcs-tab")).widget()
    kb.check(panel.user_template_keys() == ("template:user:shop_window",), "Your templates has the card")
    groups = [
        w
        for w in panel.findChildren(QLabel)
        if w.objectName().startswith("formBuilder.newForm.group.") and w.isVisible()
    ]
    kb.check(groups[0].text() == "Your templates", "Your templates is the first group")
    kb.check(kb.focus_name() == "formBuilder.newForm.name", "the name row has focus")
    kb.type("back_office")
    card = panel.card("template:user:shop_window")
    _k22_tab_until(kb, lambda: QApplication.focusWidget() is card, "Tab reaches the Shop window card")
    kb.press("Key_Return")
    kb.pump(12)
    made = shop.root / "forms" / "back_office.ui"
    kb.check(made.is_file(), "forms/back_office.ui exists")
    document = read_ui(made.read_text(encoding="utf-8"), allocator=IdAllocator()).document
    kb.check(document.root.object_name == "BackOffice" and document.form_class_name() == "BackOffice", "the root is renamed")
    uses = [use.path for use in picture_uses(document)]
    qrc = parse_qrc((shop.root / "forms" / "resources.qrc").read_text(encoding="utf-8"))
    listed = [entry.path for group in qrc.groups for entry in group.entries]
    qrc_text = (shop.root / "forms" / "resources.qrc").read_text(encoding="utf-8")
    kb.log.append("back_office pictures %s; forms/resources.qrc:\n%s" % (uses, qrc_text))
    kb.check(len(uses) == 1 and uses[0].startswith(":/"), "the picture is a resource path: %s" % uses)
    kb.check("pictures/logo.png" in listed, "the picture resolves through forms/resources.qrc: %s" % listed)
    kb.soft(
        listed.count("pictures/logo.png") == 1,
        "F-k22-duplicate-picture",
        "New Form from the template adds a second <file>pictures/logo.png</file> to forms/resources.qrc because K17 gave "
        "the first entry an alias (shop_logo.png); expected one entry for the file, got %s" % listed,
    )
    kb.check((shop.root / "forms" / "pictures" / "logo.png").read_bytes() == _png_bytes(), "the picture file is in place")
    opened = registry.surface_for_path(str(made))
    kb.check(opened is not None and hasattr(opened, "workbench"), "the Workbench is open on the new form")
    kb.check(
        tuple(opened.session.selection.state.ids) == (opened.session.document.root.id,),
        "the root is selected (UX-TMPL-003)",
    )
    shop.baselines["K22 back_office"] = (opened, str(write_ui(opened.session.document).text))
    before = made.read_bytes()
    other = state / "form_templates" / "unrelated"
    other.mkdir()
    (other / "keep.txt").write_text("x", encoding="utf-8")
    # File > New Form…, Tab to the card, Shift+F10, Delete template…, Enter on [Delete template].
    kb.surface = None
    window._open_new_form()
    kb.pump()
    panel = registry.surface_for_path(str(shop.root / "cbcs" / "new-form.cbcs-tab")).widget()
    card = panel.card("template:user:shop_window")
    _k22_tab_until(kb, lambda: QApplication.focusWidget() is card, "Tab reaches the card again")
    kb.press("Key_F10", "Shift")
    menu = QApplication.activePopupWidget()
    kb.check(isinstance(menu, QMenu), "Shift+F10 opens the card menu")
    for _ in range(3):
        kb.press("Key_Down")
    kb.check(menu.activeAction().text() == "Delete template\u2026", "Down x3 reaches Delete template…")
    said: List[str] = []
    _drive_confirm(kb, "Delete template", said)
    kb.press("Key_Return")
    kb.pump(12)
    kb.check(
        said[:1] == ["Delete the template \u201cShop window\u201d? Forms made from it don't change."],
        "the confirm says what it deletes: %s" % said,
    )
    kb.check(said[1:3] == ["default=Cancel", "focus=Delete template"], "Cancel is the default; Tab reached [Delete template]")
    kb.check(not folder.exists(), "the template folder is gone")
    kb.check(made.read_bytes() == before, "back_office.ui is unchanged")
    kb.check((shop.root / "forms" / "pictures" / "logo.png").is_file(), "the picture the form uses is still there")
    kb.check((other / "keep.txt").is_file(), "only that template's folder went")
    # Undo all in K16's window (menu bar, toolbar, label) returns K16's baseline.
    shop.use(surface16, path16)
    window._editor_tab_factory.open_file_in_editor(str(path16))  # noqa: SLF001
    kb.pump(12)
    undo_all(kb)
    kb.check(kb.text() == baseline16, "undo all returns K16's window to the bytes it had when it was created")
    script.finish()


# --------------------------------------------------------------------------
# K23 Tab order and buddies
# --------------------------------------------------------------------------


def test_k23_tab_order_and_buddies(shop: Shop) -> None:
    script = Script(shop, "K23")
    kb = script.kb
    path = shop.root / "forms" / "contact.ui"
    surface = shop.open_form(path, K23_FORM)
    original = kb.text()
    shop.remember("K23", surface, path)
    doc = kb.session.document
    kb.check(doc.tabstops() is None, "the form starts without tabstops")
    modes = surface.modes
    kb.press("Key_F8")
    kb.check(modes.active == "tab_order", "F8 opens the Tab order overlay")
    kb.check(kb.focus_in("formBuilder.canvas"), "focus is on the canvas")
    _walk_to(kb, "nameEdit", limit=12)
    kb.check("Press Enter to make nameEdit number 1." in _status(kb), "status offers number 1: %r" % _status(kb))
    kb.press("Key_Return")
    kb.check(modes.picked == ("nameEdit",), "Enter gives nameEdit number 1")
    _walk_to(kb, "emailEdit", limit=6)
    kb.press("Key_Return")
    kb.check(modes.picked == ("nameEdit", "emailEdit"), "number 2 is emailEdit")
    kb.check(doc.tabstops() == ("nameEdit", "emailEdit", "phoneEdit"), "tabstops follow the numbers")
    _walk_to(kb, "nameEdit", key="Key_Backtab", limit=6)
    kb.press("Key_Return", "Shift")
    kb.check(modes.picked == ("nameEdit",), "Shift+Enter continues from nameEdit")
    _walk_to(kb, "phoneEdit", limit=8)
    kb.press("Key_Return")
    kb.check(doc.tabstops() == ("nameEdit", "phoneEdit", "emailEdit"), "the order continues from the first")
    kb.press("Key_Backspace")
    kb.check(modes.picked == ("nameEdit",), "Backspace takes back the last number")
    kb.check(doc.tabstops() == ("nameEdit", "emailEdit", "phoneEdit"), "the order is back")
    kb.press("Key_Escape")
    kb.check(modes.active == "", "Esc closes the overlay")
    for _ in range(6):
        if kb.current() == "Contact":
            break
        kb.press("Key_Escape")
    kb.check(kb.current() == "Contact", "Esc walks up to the form")
    kb.press("Key_4", "Alt")
    surface.focus_tab_order_list()
    kb.pump()
    rows = surface.findChild(QWidget, "formBuilder.tabOrderRows")
    kb.check(rows is not None and rows.count() == 3, "the Tab order group lists three rows")
    kb.check(_focus_is(kb, rows), "focus is in the list")
    before = doc.tabstops()
    kb.press("Key_Down", "Alt")
    after = doc.tabstops()
    kb.check(after is not None and after != before and after[0] == before[1], "Alt+Down moves row 1 down: %r" % (after,))
    reset = surface.findChild(QWidget, "formBuilder.tabOrderReset")
    kb.check(reset is not None and reset.isVisible(), "Use reading order is offered")
    kb.press("Key_Tab")
    kb.check(_focus_is(kb, reset), "Tab reaches Use reading order")
    kb.press("Key_Return")
    kb.check(doc.tabstops() is None, "tabstops is gone")
    kb.press("Key_Escape")
    surface._workbench.canvas.setFocus()
    kb.pump()
    kb.press("Key_F7")
    kb.check(modes.active == "buddies", "F7 opens the Buddies overlay")
    _walk_to(kb, "emailLabel", limit=12)
    kb.press("Key_Return")
    kb.check("Choose the field for \u201cEmail\u201d, then press Enter." in _status(kb), "status: %r" % _status(kb))
    for _ in range(4):
        if modes._candidate == "emailEdit":
            break
        kb.press("Key_Tab")
    kb.check(modes._candidate == "emailEdit", "Tab reaches emailEdit")
    kb.press("Key_Return")
    kb.check(_buddy(kb, "emailLabel") == "emailEdit", "buddy of emailLabel is emailEdit")
    kb.press("Key_Escape")
    kb.check(modes.active == "", "Esc closes the Buddies overlay")
    _walk_to(kb, "phoneLabel", limit=12)
    surface._focus_inspector_pane()
    kb.pump()
    combo: Optional[QComboBox] = None
    for _ in range(60):
        combo = surface.findChild(QComboBox, "formBuilder.buddyPicker")
        if combo is not None and _focus_is(kb, combo):
            break
        kb.press("Key_Tab")
    kb.check(combo is not None and _focus_is(kb, combo), "Tab reaches the Buddy drop-down")
    kb.type("phone")
    kb.press("Key_Return")
    kb.check(_buddy(kb, "phoneLabel") == "phoneEdit", "buddy of phoneLabel is phoneEdit")
    surface._workbench.canvas.setFocus()
    kb.pump()
    kb.press("Key_F1")
    card = surface.findChild(QWidget, "formBuilder.widgetHelp")
    kb.check(card is not None and card.isVisible(), "F1 opens the help card")
    kb.check("Qt class: QLabel" in card.text(), "the card names the Qt class: %r" % card.text())
    kb.press("Key_Escape")
    kb.check(card is None or not wrapper_is_valid(card) or not card.isVisible(), "Esc closes the card")
    from app.features.form_builder.integration.widget_help import show_keys_page

    dialog = show_keys_page(surface)
    kb.pump()
    page = dialog.findChild(QWidget, "formBuilder.keysPage")
    kb.check(_focus_is(kb, page), "the filter has focus when the page opens")
    kb.type("wrap")
    kb.check(page.first_row_keys() == "Ctrl+Shift+G", "the first row for wrap is Ctrl+Shift+G: %r" % page.first_row_keys())
    dialog.close()
    surface._workbench.canvas.setFocus()
    undo_all(kb, 40)
    kb.check(kb.text() == original, "undo all returns the original bytes")
    script.finish()


# --------------------------------------------------------------------------
# The whole module
# --------------------------------------------------------------------------


def test_the_scripts_used_no_mouse_and_every_form_ends_at_its_baseline(shop: Shop) -> None:
    print("steps per script: %s; reload prompts: %s" % (shop.steps, [Path(p).name for p in shop.prompts]))
    kb = shop.kb
    ran = sorted(shop.wall)
    assert ran == ["K%d" % n for n in range(16, 24)], "every script ran: %s" % ran
    assert shop.guard.seen == [], "mouse events reached the application: %s" % shop.guard.seen[:10]
    assert len(shop.baselines) >= 8, sorted(shop.baselines)
    bad: List[str] = []
    for name, (surface, baseline) in sorted(shop.baselines.items()):
        session = surface.session
        while session.log.can_undo():
            session.log.undo()
        if str(write_ui(session.document).text) != baseline:
            bad.append(name)
    assert not bad, "forms that do not return to their baseline bytes after undo all: %s" % bad
    print("wall times: %s" % {name: round(value, 1) for name, value in sorted(shop.wall.items())})
    del kb
