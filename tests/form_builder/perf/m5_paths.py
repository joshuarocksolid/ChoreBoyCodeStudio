# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportArgumentType=false
"""UX-M5-009 scenarios for the speed harness: the M5 paths a person sees.

Each ``*_group`` builds what one family of rows needs (fixtures live in a temp
folder) and returns the specs to time plus a teardown. ``harness._m5_rows``
times the specs with ``_timed`` (prepare and cleanup run outside the clock) and
always runs the teardown. A group that cannot build reports its rows as "skip".

Budgets (p95, UX-M5-009): a keystroke is 16 ms; opening a popover, a menu or an
overlay, a drop, or committing an entry is 50 ms; the heavier steps carry their
own number. Run only these rows with ``python -m tests.form_builder.perf.m5_paths``.
"""

from __future__ import annotations

import os
import shutil
import struct
import sys
import tempfile
import time
import zlib
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

KEY_BUDGET_MS = 16.0
OPEN_BUDGET_MS = 50.0

Name = Tuple[str, Optional[int], float]


@dataclass(frozen=True)
class Spec:
    point: str
    widgets: Optional[int]
    budget_ms: float
    fn: Callable[[], None]
    prepare: Optional[Callable[[], None]] = None
    cleanup: Optional[Callable[[], None]] = None
    #: Judge wall time, not process CPU: the step waits on another process.
    wall: bool = False
    #: What the row times, written into the table's notes.
    note: str = ""


@dataclass(frozen=True)
class Group:
    """``names`` are the points the group yields, so a failed build can report each as skipped."""

    key: str
    names: Tuple[Name, ...]
    build: Callable[[], Tuple[List[Spec], Callable[[], None]]]


# ---------------------------------------------------------------------------- helpers


def _app() -> Any:
    from app.qt.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _flush(app: object) -> None:
    """Run the deleteLater calls a closed popover or editor queued (see ``m4_editors._flush``)."""
    from app.qt.QtCore import QCoreApplication, QEvent

    app.processEvents()
    QCoreApplication.sendPostedEvents(None, int(QEvent.Type.DeferredDelete.value))


def _pump(app: object, rounds: int = 4) -> None:
    for _ in range(rounds):
        app.processEvents()


def _pump_until(app: object, predicate: Callable[[], bool], seconds: float = 25.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.001)
    return False


def _reference_xml(widgets: int = 300) -> str:
    from tests.form_builder.perf.reference import DEFAULT_SEED, reference_form

    return reference_form(widgets, DEFAULT_SEED).xml


def _png(side: int, noisy: bool) -> bytes:
    """A real PNG. ``noisy`` stores incompressible rows, so ``side`` 580 is about 1 MB."""
    rows = []
    seed = os.urandom(64)
    for y in range(side):
        if noisy:
            body = (seed * ((side * 3) // 64 + 1))[: side * 3]
            body = bytes((b + y * 7 + i) & 0xFF for i, b in enumerate(body))
        else:
            body = bytes((20, 120, 200)) * side
        rows.append(b"\x00" + body)
    data = zlib.compress(b"".join(rows), 0 if noisy else 6)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        crc = zlib.crc32(tag + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", side, side, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", data) + chunk(b"IEND", b"")


def _require_form_builder() -> None:
    from app.features.form_builder.install import form_builder_enabled

    if not form_builder_enabled():
        raise RuntimeError("form builder is registered on PySide6")


# ---------------------------------------------------------------------------- menus and toolbars


class _Host:
    def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
        return lambda *args, **kwargs: None


class _Menus:
    """The 300 reference form made a main window of 6 menus, 2 toolbars and 40 actions, on a canvas."""

    def __init__(self) -> None:
        from app.features.form_builder.engine.commands.catalog_ext.actions import NewAction
        from app.features.form_builder.engine.commands.catalog_ext.main_window import (
            AddEntry,
            AddMainWindowPart,
            AddMenu,
        )
        from app.features.form_builder.engine.query import actions as q
        from app.features.form_builder.integration.canvas import FormCanvas
        from app.features.form_builder.qtside.actions.glue import MenuEditGlue
        from app.qt.QtWidgets import QWidget
        from tests.form_builder.qtside.support import realize

        self.q = q
        self.app = _app()
        self.session, self.realizer = realize(_reference_xml(), "/tmp/cbcs-m5-menus.ui")
        doc = self.session.document
        run = self.session.log.execute
        self.bar = q.parts(doc)["menubar"][0].id
        for index, title in enumerate(("&Edit", "&View", "&Insert", "&Tools", "&Help")):
            menu = run(AddMenu(self.bar, index + 1, title)).result
            for entry in range(7):
                run(AddEntry(menu, entry, "%s item %d" % (title.strip("&"), entry), None, "the menu"))
        run(NewAction("Spare"))
        run(AddMainWindowPart("toolbar"))
        self.menu_count = len(q.entries(doc, self.bar))
        toolbars = q.parts(doc)["toolbar"]
        self.toolbar = toolbars[0].id
        self.toolbar2 = toolbars[-1].id
        if self.toolbar == self.toolbar2:
            raise RuntimeError("the second toolbar was not made")
        for index, name in enumerate(("actionNew", "actionSave", "actionRefresh")):
            run(AddEntry(self.toolbar2, index, "", name, "the toolbar"))
        self.actions = len(q.all_actions(doc))
        self.parent = QWidget()
        self.parent.resize(1000, 760)
        self.canvas = FormCanvas(self.session, self.realizer, _Host(), self.parent)
        self.canvas.resize(1000, 760)
        self.parent.show()
        _pump(self.app)
        self.glue = MenuEditGlue(
            self.session, self.realizer, self.canvas, lambda _s: None, lambda _s: None, lambda _s, _o: True, self.parent
        )
        _pump(self.app)
        self.line_name = "formBuilder.menuEditLine"
        self.base_undo = self.session.log.undo_label()

    def dispose(self) -> None:
        try:
            self.glue.dispose()
            self.canvas.dispose()
            self.realizer.dispose()
            self.session.dispose()
            self.parent.close()
        finally:
            _flush(self.app)

    # keys on the canvas -------------------------------------------------------
    def key(self, key: object, repeat: int = 1) -> None:
        from app.qt.QtTest import QTest

        for _ in range(repeat):
            QTest.keyClick(self.canvas.viewport(), key)
        _pump(self.app)

    def leave(self) -> None:
        self.glue.editor.leave()
        self.glue.refresh()
        _pump(self.app)

    def start(self, node: object) -> None:
        from app.features.form_builder.engine.query.selection import SelectionSource
        from app.qt.QtCore import Qt

        self.leave()
        self.canvas.setFocus()
        self.session.selection.set((node,), source=SelectionSource.PROGRAM)
        _pump(self.app)
        self.key(Qt.Key.Key_Return)
        if not self.glue.editor.active:
            raise RuntimeError("Enter did not start menu editing")

    def line(self) -> Any:
        from app.qt.QtWidgets import QLineEdit

        found = self.canvas.viewport().findChild(QLineEdit, self.line_name)
        if found is None:
            raise RuntimeError("no in-place line edit")
        return found

    def entries_of(self, host: object) -> int:
        return len(self.q.entries(self.session.document, host))

    def open_type_here(self, host: object, menu_index: Optional[int]) -> None:
        """Editing on ``host`` with the line edit open on its Type here row."""
        from app.qt.QtCore import Qt

        self.start(host)
        if menu_index is not None:
            self.key(Qt.Key.Key_Right, menu_index)
            self.key(Qt.Key.Key_Down)  # opens the menu under the title
            host = self.glue.editor.levels[-1].host
            self.key(Qt.Key.Key_Down, self.entries_of(host))
        else:
            self.key(Qt.Key.Key_Right, self.entries_of(host))
        self.key(Qt.Key.Key_Return)  # an empty editor on Type here
        self.line()


def menus_group() -> Tuple[List[Spec], Callable[[], None]]:
    from app.qt.QtCore import QByteArray, QMimeData, QPoint, QPointF, Qt
    from app.qt.QtGui import QDropEvent
    from app.qt.QtTest import QTest
    from app.features.form_builder.qtside.actions.glue import MIME_ACTIONS

    bench = _Menus()
    app = bench.app
    state: Dict[str, Any] = {"undo": ""}

    def clear_line() -> None:
        line = bench.line()
        if not line.text().startswith("a") or bench.glue.editor.editor is None:
            raise RuntimeError("the key did not reach the line edit")
        while line.text():
            QTest.keyClick(line, Qt.Key.Key_Backspace)
        _pump(app)

    # keystroke in the Type here line edit --------------------------------------
    def title_prepare() -> None:
        try:
            line = bench.line()
        except RuntimeError:
            bench.open_type_here(bench.bar, bench.menu_count)
            line = bench.line()
        line.setFocus()

    def title_key() -> None:
        QTest.keyClick(bench.line(), "a")
        app.processEvents()

    # keystroke in the toolbar reuse list ---------------------------------------
    def toolbar_prepare() -> None:
        try:
            line = bench.line()
            if bench.glue.editor.levels[-1].host != bench.toolbar2:
                raise RuntimeError("other host")
        except RuntimeError:
            bench.open_type_here(bench.toolbar2, None)
            line = bench.line()
        line.setFocus()

    def toolbar_key() -> None:
        QTest.keyClick(bench.line(), "a")
        app.processEvents()

    # open a menu on the canvas ---------------------------------------------------
    def open_prepare() -> None:
        bench.start(bench.bar)
        bench.key(Qt.Key.Key_Right)

    def open_menu() -> None:
        QTest.keyClick(bench.canvas.viewport(), Qt.Key.Key_Down)
        app.processEvents()
        app.processEvents()

    def open_cleanup() -> None:
        if len(bench.glue.editor.levels) != 2:
            raise RuntimeError("the menu did not open")
        bench.leave()

    # commit a new menu entry -------------------------------------------------------
    def commit_prepare() -> None:
        bench.open_type_here(bench.bar, 1)
        QTest.keyClicks(bench.line(), "Copy")
        _pump(app)
        state["undo"] = bench.session.log.undo_label()
        state["count"] = bench.entries_of(bench.glue.editor.levels[-1].host)

    def commit() -> None:
        QTest.keyClick(bench.line(), Qt.Key.Key_Return)
        app.processEvents()
        app.processEvents()

    def commit_cleanup() -> None:
        if bench.entries_of(bench.glue.editor.levels[-1].host) != state["count"] + 1:
            raise RuntimeError("Enter did not add the entry")
        bench.glue.editor.leave()
        if bench.session.log.undo_label() != state["undo"]:
            bench.session.log.undo()
        bench.leave()

    # drops ---------------------------------------------------------------------------
    drop_state: Dict[str, Any] = {"event": None, "map": None}

    def _drop(mime: Any, at: Any) -> Any:
        return QDropEvent(
            QPointF(at), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
        )

    def _viewport_point(rect: Any, fx: float, fy: float) -> Any:
        ox, oy, factor = bench.glue._page_to_viewport() or (0, 0, 1.0)
        return QPoint(
            int(ox + (rect.x + rect.width * fx) * factor), int(oy + (rect.y + rect.height * fy) * factor)
        )

    def drop_prepare(host_of: Callable[[], object], menu_open: bool) -> Callable[[], None]:
        def prepare() -> None:
            bench.leave()
            host = host_of()
            if menu_open:
                bench.start(host)
            bench.glue.refresh()
            _pump(app)
            found = [m for m in bench.glue._maps if m.host == host]
            if not found:
                raise RuntimeError("the canvas drew no drop target for the host")
            mime = QMimeData()
            mime.setData(MIME_ACTIONS, QByteArray(b"actionNew"))
            spot = _viewport_point(found[0].rect, 0.2, 0.5)
            drop_state["event"] = (mime, spot)
            bench.canvas.dragEnterEvent(_drop(mime, spot))
            state["undo"] = bench.session.log.undo_label()
            state["host"] = host
            state["count"] = bench.entries_of(host)

        return prepare

    def do_drop() -> None:
        mime, spot = drop_state["event"]
        bench.canvas.dropEvent(_drop(mime, spot))
        app.processEvents()
        app.processEvents()

    def drop_cleanup() -> None:
        if bench.entries_of(state["host"]) != state["count"] + 1:
            raise RuntimeError("the drop added nothing")
        if bench.session.log.undo_label() != state["undo"]:
            bench.session.log.undo()
        bench.leave()

    def menu_host() -> object:
        return bench.q.entries(bench.session.document, bench.bar)[1].target

    specs = [
        Spec(
            "m5 menu Type here keystroke",
            300,
            KEY_BUDGET_MS,
            title_key,
            prepare=title_prepare,
            cleanup=clear_line,
            note="a key in the in-place line edit on the menu bar's Type here (6 menus)",
        ),
        Spec(
            "m5 toolbar reuse list keystroke",
            300,
            KEY_BUDGET_MS,
            toolbar_key,
            prepare=toolbar_prepare,
            cleanup=clear_line,
            note="a key in the toolbar line edit; the reuse list filters %d actions" % bench.actions,
        ),
        Spec(
            "m5 open menu on canvas",
            300,
            OPEN_BUDGET_MS,
            open_menu,
            prepare=open_prepare,
            cleanup=open_cleanup,
            note="Down on a menu title with 6 menus, 40 actions: opens the 7-entry menu",
        ),
        Spec(
            "m5 commit menu entry",
            300,
            OPEN_BUDGET_MS,
            commit,
            prepare=commit_prepare,
            cleanup=commit_cleanup,
            note="Enter in the line edit: AddEntry, one undo step, canvas redrawn",
        ),
        Spec(
            "m5 drop action on toolbar",
            300,
            OPEN_BUDGET_MS,
            do_drop,
            prepare=drop_prepare(lambda: bench.toolbar2, False),
            cleanup=drop_cleanup,
            note="dropEvent with the Actions row mime on the second toolbar",
        ),
        Spec(
            "m5 drop action on menu",
            300,
            OPEN_BUDGET_MS,
            do_drop,
            prepare=drop_prepare(menu_host, True),
            cleanup=drop_cleanup,
            note="dropEvent with the Actions row mime on an open menu",
        ),
    ]
    return specs, bench.dispose


MENU_NAMES: Tuple[Name, ...] = (
    ("m5 menu Type here keystroke", 300, KEY_BUDGET_MS),
    ("m5 toolbar reuse list keystroke", 300, KEY_BUDGET_MS),
    ("m5 open menu on canvas", 300, OPEN_BUDGET_MS),
    ("m5 commit menu entry", 300, OPEN_BUDGET_MS),
    ("m5 drop action on toolbar", 300, OPEN_BUDGET_MS),
    ("m5 drop action on menu", 300, OPEN_BUDGET_MS),
)


# ---------------------------------------------------------------------------- Actions pane


def actions_group() -> Tuple[List[Spec], Callable[[], None]]:
    from app.features.form_builder.engine.commands.catalog_ext.actions import NewAction
    from app.features.form_builder.qtside.actions.pane import ActionsPane
    from app.qt.QtTest import QTest
    from app.qt.QtWidgets import QVBoxLayout, QWidget
    from tests.form_builder.qtside.support import realize

    app = _app()
    session, realizer = realize(_reference_xml(), "/tmp/cbcs-m5-actions.ui")
    for number in range(200):
        session.log.execute(NewAction("Action %03d" % number))
    window = QWidget()
    pane = ActionsPane(session, lambda _s: None, lambda _s, _o: True, window)
    layout = QVBoxLayout(window)
    layout.addWidget(pane)
    window.resize(320, 700)
    window.show()
    _pump(app)

    def prepare() -> None:
        pane._filter.setText("")
        pane._filter.setFocus()
        _pump(app)

    def key() -> None:
        QTest.keyClick(pane._filter, "a")

    def dispose() -> None:
        pane.dispose()
        realizer.dispose()
        session.dispose()
        window.close()
        _flush(app)

    return [
        Spec(
            "m5 actions filter keystroke",
            300,
            KEY_BUDGET_MS,
            key,
            prepare=prepare,
            note="a key in the Actions filter: the 200-action list is rebuilt",
        )
    ], dispose


ACTIONS_NAMES: Tuple[Name, ...] = (("m5 actions filter keystroke", 300, KEY_BUDGET_MS),)


# ---------------------------------------------------------------------------- pictures


class _Pictures:
    """A project of 500 pictures in 3 ``.qrc`` files and the 300 form, with the Inspector open."""

    COUNTS = (200, 150, 150)

    def __init__(self) -> None:
        from app.features.form_builder.engine.project.forms import classify_form
        from app.features.form_builder.engine.session import FormSession
        from app.features.form_builder.qtside.inspector import InspectorPane
        from app.features.form_builder.qtside.inspector.api import GroupId
        from app.features.form_builder.qtside.realize import Realizer
        from app.qt.QtWidgets import QVBoxLayout, QWidget
        from tests.form_builder.inspector.test_m43c_pictures import _CHROME

        self.app = _app()
        self.folder = tempfile.mkdtemp(prefix="cbcs-m5-pictures-")
        self.root = os.path.join(self.folder, "shop")
        forms = os.path.join(self.root, "forms")
        os.makedirs(os.path.join(forms, "pictures"))
        os.makedirs(os.path.join(self.root, "cbcs"))
        with open(os.path.join(self.root, "cbcs", "project.json"), "w", encoding="utf-8") as handle:
            handle.write('{"schema_version": 2, "name": "Shop"}\n')
        payload = _png(8, False)
        number = 0
        self.qrcs: List[str] = []
        for index, count in enumerate(self.COUNTS):
            lines = []
            for _ in range(count):
                name = "pic%03d.png" % number
                number += 1
                with open(os.path.join(forms, "pictures", name), "wb") as handle:
                    handle.write(payload)
                lines.append(" <file>pictures/%s</file>" % name)
            qrc = "set%d.qrc" % (index + 1)
            self.qrcs.append(qrc)
            with open(os.path.join(forms, qrc), "w", encoding="utf-8") as handle:
                handle.write('<RCC version="1.0"><qresource prefix="/pictures">\n%s\n</qresource></RCC>\n' % "\n".join(lines))
        self.desktop = os.path.join(self.folder, "desktop")
        os.makedirs(self.desktop)
        self.big = _png(580, True)
        xml = _reference_xml()
        if "<resources/>" not in xml:
            raise RuntimeError("reference form resources moved")
        xml = xml.replace("<resources/>", '<resources><include location="set1.qrc"/></resources>', 1)
        ui = os.path.join(forms, "speed.ui")
        with open(ui, "w", encoding="utf-8") as handle:
            handle.write(xml)
        scope = classify_form(ui, project_root=self.root)
        self.session = FormSession.open(xml, path=ui, scope=scope)
        self.realizer = Realizer(self.session)
        self.realizer.build()
        self.window = QWidget()
        self.pane = InspectorPane(self.session, self.realizer, data_tab=False, on_leave=lambda: None, parent=self.window)
        self.pane.apply_chrome(_CHROME)
        layout = QVBoxLayout(self.window)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.pane)
        self.window.resize(420, 900)
        self.window.show()
        self.app.processEvents()
        self.pane.set_group_expanded(GroupId.ALL, True)
        self.selected = ""
        self.sent = 0
        self.select("banner")

    def dispose(self) -> None:
        try:
            self.close_popover()
        finally:
            self.pane.dispose()
            self.realizer.dispose()
            self.session.dispose()
            self.window.close()
            _flush(self.app)
            shutil.rmtree(self.folder, ignore_errors=True)

    def select(self, name: str) -> None:
        from app.features.form_builder.engine.query.selection import SelectionSource

        if self.selected == name:
            return
        self.close_popover()
        node = self.session.document.by_name(name)[0]
        self.session.selection.set((node,), source=SelectionSource.PROGRAM)
        self.pane.flush()
        self.app.processEvents()
        self.selected = name

    def open_row(self, key: str) -> None:
        from app.qt.QtWidgets import QWidget

        row = self.pane.findChild(QWidget, "formBuilder.row.%s" % key)
        if row is None:
            raise RuntimeError("missing row %s" % key)
        summary = row.findChild(QWidget, "formBuilder.summary")
        if summary is None:
            raise RuntimeError("missing summary %s" % key)
        summary.click()
        self.app.processEvents()

    def close_popover(self) -> None:
        from app.qt.QtWidgets import QApplication

        done = [w for w in QApplication.allWidgets() if w.objectName() == "formBuilder.popoverDone" and w.isVisible()]
        if done:
            done[-1].click()
            _flush(self.app)

    def picker(self) -> Any:
        from app.qt.QtWidgets import QApplication

        found = [w for w in QApplication.allWidgets() if w.objectName() == "formBuilder.pictureSearch" and w.isVisible()]
        if not found:
            raise RuntimeError("the picture picker is not open")
        return found[-1].parent()

    def new_source(self) -> str:
        self.sent += 1
        path = os.path.join(self.desktop, "big%03d.png" % self.sent)
        with open(path, "wb") as handle:
            handle.write(self.big)
        return path


def pictures_group() -> Tuple[List[Spec], Callable[[], None]]:
    from app.features.form_builder.engine.project.pictures import clear_picture_cache

    bench = _Pictures()
    app = bench.app

    def open_picker() -> None:
        bench.open_row("pixmap")

    def cold_prepare() -> None:
        bench.select("banner")
        bench.close_popover()
        clear_picture_cache()

    def warm_prepare() -> None:
        bench.select("banner")
        bench.close_popover()
        bench.open_row("pixmap")  # index it once
        bench.close_popover()

    state: Dict[str, Any] = {"undo": ""}

    def add_prepare() -> None:
        bench.select("banner")
        bench.close_popover()
        bench.open_row("pixmap")
        state["source"] = bench.new_source()
        state["undo"] = bench.session.log.undo_label()

    def add_one() -> None:
        stored = bench.picker().add_pictures([state["source"]])
        if not stored:
            raise RuntimeError("the picture was not added")

    def add_cleanup() -> None:
        bench.close_popover()
        if bench.session.log.undo_label() != state["undo"]:
            bench.session.log.undo()
        app.processEvents()

    specs = [
        Spec(
            "m5 picture picker first index",
            300,
            300.0,
            open_picker,
            prepare=cold_prepare,
            cleanup=bench.close_popover,
            note="popover opens with the picture index cleared (clear_picture_cache): 3 .qrc files, 500 pictures",
        ),
        Spec(
            "m5 open picture picker warm",
            300,
            OPEN_BUDGET_MS,
            open_picker,
            prepare=warm_prepare,
            cleanup=bench.close_popover,
            note="popover opens with the parsed .qrc files cached: 500 pictures",
        ),
        Spec(
            "m5 add 1 MB picture",
            300,
            200.0,
            add_one,
            prepare=add_prepare,
            cleanup=add_cleanup,
            note="PicturePicker.add_pictures: copy 1 MB into the project, .qrc write, include, row set",
        ),
    ]
    return specs, bench.dispose


PICTURE_NAMES: Tuple[Name, ...] = (
    ("m5 picture picker first index", 300, 300.0),
    ("m5 open picture picker warm", 300, OPEN_BUDGET_MS),
    ("m5 add 1 MB picture", 300, 200.0),
)


# ---------------------------------------------------------------------------- your own class


def own_class_group() -> Tuple[List[Spec], Callable[[], None]]:
    from app.features.form_builder.engine.project.forms import FormScope
    from app.features.form_builder.engine.session import FormSession
    from app.features.form_builder.integration.custom_registry import registry_for
    from app.features.form_builder.qtside.dialogs.promote import open_popover
    from app.features.form_builder.qtside.realize import Realizer
    from app.qt.QtWidgets import QWidget

    app = _app()
    folder = tempfile.mkdtemp(prefix="cbcs-m5-own-")
    root = os.path.realpath(os.path.join(folder, "shop"))
    os.makedirs(os.path.join(root, "cbcs"))
    os.makedirs(os.path.join(root, "forms"))
    os.makedirs(os.path.join(root, "widgets"))
    with open(os.path.join(root, "cbcs", "project.json"), "w", encoding="utf-8") as handle:
        handle.write('{"schema_version": 2, "name": "Shop"}\n')
    module = os.path.join(root, "widgets", "big.py")

    def write_module(variant: int) -> None:
        parts = ["from PySide6.QtWidgets import QLabel, QWidget\n\n"]
        index = 0
        while sum(len(p) for p in parts) < 100_000 - 400:
            parts.append(
                "class Helper%d(QWidget):\n    \"\"\"Helper %d.\"\"\"\n\n    def run(self):\n        return %d  # %s\n\n"
                % (index, index, index, "x" * 20)
            )
            index += 1
        parts.append("class TillDisplay(QLabel):\n    pass  # %s\n" % ("v" * variant))
        with open(module, "w", encoding="utf-8") as handle:
            handle.write("".join(parts))

    write_module(0)
    xml = _reference_xml()
    ui = os.path.join(root, "forms", "speed.ui")
    scope = FormScope(
        kind="project",
        ui_path=ui,
        project_root=root,
        generated_path=os.path.join(root, "forms", "ui_speed.py"),
        window_path=os.path.join(root, "forms", "speed_window.py"),
        module_name="forms.ui_speed",
    )
    session = FormSession.open(xml, path=ui, scope=scope)
    realizer = Realizer(session)
    realizer.build()
    registry = registry_for(root)
    host = QWidget()
    host.resize(900, 700)
    host.show()
    banner = session.document.by_name("banner")[0]
    held: Dict[str, Any] = {"pop": None, "variant": 0}

    def close() -> None:
        pop = held["pop"]
        held["pop"] = None
        if pop is not None:
            pop.cancel()
            _flush(app)

    def open_pop() -> None:
        held["pop"] = open_popover(session, (banner,), registry, host)
        if held["pop"] is None:
            raise RuntimeError("no popover for the banner label")
        app.processEvents()

    def check_prepare() -> None:
        if held["pop"] is None:
            open_pop()
        held["pop"].set_fields("TillDisplay", "widgets.big")
        held["pop"]._timer.stop()
        held["variant"] = (held["variant"] + 1) % 50
        write_module(held["variant"])  # a new mtime and size: the file is read and scanned again

    def check_one() -> None:
        held["pop"].update_check()

    def dispose() -> None:
        try:
            close()
        finally:
            realizer.dispose()
            session.dispose()
            host.close()
            _flush(app)
            shutil.rmtree(folder, ignore_errors=True)

    specs = [
        Spec(
            "m5 open own class popover",
            300,
            OPEN_BUDGET_MS,
            open_pop,
            prepare=close,
            cleanup=close,
            note="open_popover on a label",
        ),
        Spec(
            "m5 own class module check",
            300,
            30.0,
            check_one,
            prepare=check_prepare,
            cleanup=None,
            note="OwnClassPopover.update_check on a 100 KB module changed since the last check (read + class scan)",
        ),
    ]
    return specs, dispose


OWN_CLASS_NAMES: Tuple[Name, ...] = (
    ("m5 open own class popover", 300, OPEN_BUDGET_MS),
    ("m5 own class module check", 300, 30.0),
)


# ---------------------------------------------------------------------------- Start


def start_group() -> Tuple[List[Spec], Callable[[], None]]:
    from app.features.form_builder.engine.project import user_templates as ut
    from app.features.form_builder.engine.project.fs import OsFileSystem
    from app.features.form_builder.qtside.start.panel import NewFormPanel
    from app.qt.QtGui import QColor, QPixmap
    from tests.unit.features.form_builder.test_new_form import _chrome

    app = _app()
    folder = tempfile.mkdtemp(prefix="cbcs-m5-start-")
    state = os.path.join(folder, "state")
    root = os.path.join(folder, "shop")
    os.makedirs(os.path.join(root, "forms"))
    ui_text = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Till</class>\n'
        ' <widget class="QWidget" name="Till"/>\n <resources/>\n <connections/>\n</ui>\n'
    )
    for number in range(20):
        info = ut.save_template(
            scope=ut.SCOPE_USER,
            state_root=state,
            project_root=None,
            name="Template %d" % number,
            description="One of twenty",
            ui_text=ui_text,
            thumbnail=b"",
        )
        picture = QPixmap(200, 120)
        picture.fill(QColor("#336699"))
        if not picture.save(os.path.join(info.folder, "thumbnail.png"), "PNG"):
            raise RuntimeError("could not save a template thumbnail")
    found = ut.list_templates(state, None)
    if len(found) != 20:
        raise RuntimeError("expected 20 templates, found %d" % len(found))
    held: Dict[str, Any] = {"panel": None}

    def show() -> None:
        panel = NewFormPanel(project_root=root, directory=os.path.join(root, "forms"), fs=OsFileSystem(), chrome=_chrome())
        held["panel"] = panel
        panel.resize(1000, 800)
        panel.show()
        panel.set_user_templates(found)
        app.processEvents()
        panel.grab()

    def close() -> None:
        panel = held["panel"]
        held["panel"] = None
        if panel is not None:
            panel.close()
            panel.deleteLater()
            _flush(app)

    def dispose() -> None:
        close()
        shutil.rmtree(folder, ignore_errors=True)

    return [
        Spec(
            "m5 start with 20 templates",
            None,
            150.0,
            show,
            cleanup=close,
            note="NewFormPanel built, shown, 20 saved templates set, events run, panel.grab() (first paint)",
        )
    ], dispose


START_NAMES: Tuple[Name, ...] = (("m5 start with 20 templates", None, 150.0),)


# ---------------------------------------------------------------------------- a real shell


class _Shell:
    """A MainWindow in a project with the 300 form open in a tab (as ``harness._inspector_shell_row``)."""

    def __init__(self) -> None:
        _require_form_builder()
        import json
        from pathlib import Path

        from app.core.models import LoadedProject, ProjectMetadata
        from app.shell.main_window import MainWindow

        self.app = _app()
        self._previous = os.environ.get("CBCS_DISABLE_BACKGROUND_RUNTIME")
        os.environ["CBCS_DISABLE_BACKGROUND_RUNTIME"] = "1"
        self.folder = tempfile.mkdtemp(prefix="cbcs-m5-shell-")
        root = Path(self.folder).resolve() / "shop"
        (root / "forms").mkdir(parents=True)
        (root / "cbcs").mkdir()
        (root / "main.py").write_text("print('shop')\n", encoding="utf-8")
        manifest = root / "cbcs" / "project.json"
        manifest.write_text(
            json.dumps({"schema_version": 2, "name": "Shop", "default_entry": "main.py"}) + "\n", encoding="utf-8"
        )
        self.window = MainWindow(state_root=str((Path(self.folder) / "state").resolve()))
        self.window._loaded_project = LoadedProject(
            project_root=str(root),
            manifest_path=str(manifest.resolve()),
            metadata=ProjectMetadata(schema_version=2, name="Shop", default_entry="main.py"),
            entries=[],
        )
        path = root / "forms" / "speed.ui"
        path.write_text(_reference_xml(), encoding="utf-8")
        if not self.window._editor_tab_factory.open_file_in_editor(str(path)):
            raise RuntimeError("the shell did not open the form")
        self.window._center_stack.setCurrentIndex(1)
        self.window.resize(1900, 900)
        self.window.show()
        self.window.activateWindow()
        _pump(self.app, 8)
        self.surface = self.window._tab_content_registry.surface_for_path(str(path))
        if self.surface is None:
            raise RuntimeError("no form tab")
        self.session = self.surface._session
        self.path = path
        self.surface.focus_primary()
        _pump(self.app)

    def dispose(self) -> None:
        from testing.main_window_shutdown import shutdown_main_window_for_test

        try:
            shutdown_main_window_for_test(self.window, self.app)
        finally:
            self.app.processEvents()
            shutil.rmtree(self.folder, ignore_errors=True)
            if self._previous is None:
                os.environ.pop("CBCS_DISABLE_BACKGROUND_RUNTIME", None)
            else:
                os.environ["CBCS_DISABLE_BACKGROUND_RUNTIME"] = self._previous


def _sheet(rules: int) -> str:
    classes = (
        "QLineEdit", "QComboBox", "QSpinBox", "QCheckBox", "QDateEdit",
        "QDoubleSpinBox", "QSlider", "QRadioButton", "QTextEdit", "QPushButton",
    )
    lines = []
    for index in range(rules):
        lines.append(
            "%s#field%04d { color: #%02x%02x%02x; padding: %dpx; }"
            % (classes[index % len(classes)], index, 20 + index % 200, 40 + index % 150, 60 + index % 100, 1 + index % 4)
        )
    return "\n".join(lines) + "\n"


def shell_group() -> Tuple[List[Spec], Callable[[], None]]:
    from app.features.form_builder.integration.widget_help import show_keys_page
    from app.features.form_builder.qtside.style import gateway
    from app.features.form_builder.qtside.style.drawer import StyleDrawer
    from app.qt.QtCore import Qt
    from app.qt.QtTest import QTest
    from app.qt.QtWidgets import QWidget

    shell = _Shell()
    app = shell.app
    surface = shell.surface
    session = shell.session
    specs: List[Spec] = []

    # style sheet drawer -----------------------------------------------------------
    root_id = session.document.root.id
    sheet = _sheet(200)
    sheet_b = sheet.replace("padding: 1px", "padding: 2px", 40)
    if not gateway.open_drawer(session, root_id):
        raise RuntimeError("the style sheet drawer did not open")
    _pump(app)
    drawer: StyleDrawer = surface.workbench._under_widget
    drawer.editor.setPlainText(sheet)
    drawer._timer.stop()
    drawer._apply()  # writes the 200 rules to the form: the canvas is styled, the check is cached
    _pump(app)
    hold = {"flip": False}

    def drawer_prepare() -> None:
        drawer._timer.stop()
        cursor = drawer.editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        drawer.editor.setTextCursor(cursor)
        drawer.editor.setFocus()

    def drawer_key() -> None:
        QTest.keyClick(drawer.editor, "x")
        app.processEvents()

    def drawer_key_cleanup() -> None:
        drawer._timer.stop()
        QTest.keyClick(drawer.editor, Qt.Key.Key_Backspace)
        drawer._timer.stop()

    def check_prepare() -> None:
        # New text each time, so the check does not meet text it has already read.
        hold["flip"] = not hold["flip"]
        drawer.editor.setPlainText(sheet_b if hold["flip"] else sheet)
        drawer._timer.stop()
        drawer._written = drawer.editor.toPlainText()  # nothing to write: the pause fires the check only

    def check_pause() -> None:
        drawer._apply()

    def apply_prepare() -> None:
        drawer._timer.stop()
        hold["flip"] = not hold["flip"]

    def apply_sheet() -> None:
        drawer._write(drawer._target, sheet_b if hold["flip"] else sheet)
        app.processEvents()

    specs += [
        Spec(
            "m5 style sheet keystroke",
            300,
            KEY_BUDGET_MS,
            drawer_key,
            prepare=drawer_prepare,
            cleanup=drawer_key_cleanup,
            note="a key in the drawer editor holding 200 rules (the 300 ms timer is not waited for)",
        ),
        Spec(
            "m5 style sheet check and matches",
            300,
            OPEN_BUDGET_MS,
            check_pause,
            prepare=check_prepare,
            note="StyleDrawer._apply after the pause on text it has not read: check_text, shared_index, match_sheet, chips",
        ),
        Spec(
            "m5 style sheet apply to canvas",
            300,
            100.0,
            apply_sheet,
            prepare=apply_prepare,
            note="StyleDrawer._write of a valid 200-rule sheet on the form (one undo step) and events run, which include the Inspector's refresh; the check is not in it",
        ),
    ]

    # View code refresh -----------------------------------------------------------------
    def close_drawer() -> None:
        drawer.close_drawer()
        _pump(app)

    code_view = surface._workbench.code_view
    code_state: Dict[str, Any] = {"n": 0}
    label = session.document.by_name("banner")[0]

    def code_prepare() -> None:
        from app.features.form_builder.engine.commands.catalog import SetProperty
        from app.features.form_builder.engine.ui4.values import StringValue

        if not code_view.is_open():
            close_drawer()
            if not code_view.open():
                raise RuntimeError("the code split did not open")
        code_state["n"] += 1
        session.log.execute(SetProperty(label, "text", StringValue("Orders %d" % code_state["n"])))
        code_view._timer.stop()

    def code_refresh() -> None:
        code_view.refresh()

    specs.append(
        Spec(
            "m5 view code refresh",
            300,
            100.0,
            code_refresh,
            prepare=code_prepare,
            note="CodeViewController.refresh after an edit: generate_view of the 300 form and show_code",
        )
    )

    # Form designer keys page -----------------------------------------------------------------
    keys: Dict[str, Any] = {"dialog": None}

    def keys_close() -> None:
        dialog = keys["dialog"]
        keys["dialog"] = None
        if dialog is not None:
            dialog.close()
            dialog.deleteLater()
            _flush(app)

    def keys_open() -> None:
        keys["dialog"] = show_keys_page(surface)
        app.processEvents()

    def keys_prepare() -> None:
        if keys["dialog"] is None:
            keys_open()
        page = keys["dialog"].findChild(QWidget, "formBuilder.keysPage")
        page.filter.clear()
        page.filter.setFocus()
        app.processEvents()

    def keys_key() -> None:
        page = keys["dialog"].findChild(QWidget, "formBuilder.keysPage")
        QTest.keyClick(page.filter, "w")
        app.processEvents()

    specs += [
        Spec(
            "m5 open form designer keys",
            300,
            100.0,
            keys_open,
            prepare=keys_close,
            cleanup=keys_close,
            note="show_keys_page: the dialog is rebuilt from the registered form commands",
        ),
        Spec(
            "m5 keys page filter keystroke",
            300,
            KEY_BUDGET_MS,
            keys_key,
            prepare=keys_prepare,
            note="a key in the keys page filter",
        ),
    ]

    # Tab order and buddies overlays ------------------------------------------------------------
    modes = surface.modes
    names = [n for n in ("field0001", "field0002", "field0003") if session.document.by_name(n)]
    if len(names) < 2:
        raise RuntimeError("reference form has no fields to number")
    over = {"n": 0}

    def overlay_close() -> None:
        modes.close()
        _pump(app)

    def open_kind(kind: str) -> Callable[[], None]:
        def run() -> None:
            if not modes.open(kind):
                raise RuntimeError("the %s overlay did not open" % kind)
            app.processEvents()
            app.processEvents()

        return run

    def tab_prepare() -> None:
        overlay_close()

    def assign_prepare() -> None:
        if modes.active != "tab_order":
            overlay_close()
            modes.open("tab_order")
            _pump(app)

    def assign_one() -> None:
        over["n"] += 1
        over["ok"] = modes.assign(names[over["n"] % len(names)])
        app.processEvents()

    def assign_cleanup() -> None:
        if not over["ok"]:
            raise RuntimeError("the overlay gave no number")
        modes.undo_last()
        _pump(app)

    specs += [
        Spec(
            "m5 open tab order overlay",
            300,
            OPEN_BUDGET_MS,
            open_kind("tab_order"),
            prepare=tab_prepare,
            cleanup=overlay_close,
            note="ModeController.open('tab_order'): banner, badges and flow line drawn",
        ),
        Spec(
            "m5 assign tab order number",
            300,
            KEY_BUDGET_MS,
            assign_one,
            prepare=assign_prepare,
            cleanup=assign_cleanup,
            note="ModeController.assign: one number given, tabstops written",
        ),
        Spec(
            "m5 open buddies overlay",
            300,
            OPEN_BUDGET_MS,
            open_kind("buddies"),
            prepare=tab_prepare,
            cleanup=overlay_close,
            note="ModeController.open('buddies')",
        ),
    ]

    def dispose() -> None:
        try:
            keys_close()
            overlay_close()
        finally:
            shell.dispose()

    return specs, dispose


SHELL_NAMES: Tuple[Name, ...] = (
    ("m5 style sheet keystroke", 300, KEY_BUDGET_MS),
    ("m5 style sheet check and matches", 300, OPEN_BUDGET_MS),
    ("m5 style sheet apply to canvas", 300, 100.0),
    ("m5 view code refresh", 300, 100.0),
    ("m5 open form designer keys", 300, 100.0),
    ("m5 keys page filter keystroke", 300, KEY_BUDGET_MS),
    ("m5 open tab order overlay", 300, OPEN_BUDGET_MS),
    ("m5 assign tab order number", 300, KEY_BUDGET_MS),
    ("m5 open buddies overlay", 300, OPEN_BUDGET_MS),
)


# ---------------------------------------------------------------------------- Preview


def preview_group() -> Tuple[List[Spec], Callable[[], None]]:
    from app.features.form_builder.engine.ipc.timing import DirectorConfig
    from app.features.form_builder.qtside.preview.launch import current_runtime_python, python_preview_command, repo_root
    from app.features.form_builder.qtside.preview.pool import PreviewPool

    shell = _Shell()
    app = shell.app
    surface = shell.surface
    pool = PreviewPool(
        command=python_preview_command(current_runtime_python(), repo_root()),
        config=DirectorConfig(
            handshake_timeout=30.0, request_timeout=20.0, shutdown_grace=0.4, ping_interval=30.0, prewarm=True
        ),
        root=repo_root(),
    )
    PreviewPool._shared = pool
    control = surface.preview_control
    notices = surface.own_class_preview

    def dispose() -> None:
        try:
            PreviewPool.reset_shared()
        finally:
            shell.dispose()

    try:
        surface.preview_form()
        if not _pump_until(app, lambda: notices.last_response is not None, 40.0):
            raise RuntimeError("the preview child did not answer in 40 s")
        if not notices.last_response.ok:
            raise RuntimeError("the preview child refused: %s" % (notices.last_response.detail,))
        profiles = control.profiles
        if len(profiles) < 2:
            raise RuntimeError("fewer than two screen profiles")
    except Exception:
        dispose()
        raise
    spawned = len(pool.spawn_monotonic)
    turn = {"n": 0, "title": ""}

    def pick_screen() -> None:
        turn["n"] += 1
        profile = profiles[1 + turn["n"] % 2]
        turn["title"] = profile.name
        control.last_look = {}
        control.set_screen(profile.name)
        if not _pump_until(app, lambda: str(control.last_look.get("title", "")).endswith(turn["title"]), 20.0):
            raise RuntimeError("the preview window did not show %s" % turn["title"])
        if len(pool.spawn_monotonic) != spawned:
            raise RuntimeError("the child was restarted: not a warm change")

    # Fusion and Windows exist in every runtime; the child dies on "macOS" under the offscreen plugin.
    listed = {name.casefold(): name for name in control.styles()}
    styles = [listed[name] for name in ("fusion", "windows") if name in listed]

    def pick_style() -> None:
        turn["n"] += 1
        name = styles[turn["n"] % len(styles)]
        control.last_look = {}
        control.set_style(name)
        if not _pump_until(app, lambda: str(control.last_look.get("style", "")).casefold() == name.casefold(), 20.0):
            raise RuntimeError("the preview window did not show the %s style" % name)
        if len(pool.spawn_monotonic) != spawned:
            raise RuntimeError("the child was restarted: not a warm change")

    specs = [
        Spec(
            "m5 preview change screen warm",
            300,
            300.0,
            pick_screen,
            wall=True,
            note="wall time of PreviewControl.set_screen to the child's answer (IPC round trip, warm child, 300 form)",
        )
    ]
    if len(styles) >= 2:
        specs.append(
            Spec(
                "m5 preview change style warm",
                300,
                300.0,
                pick_style,
                wall=True,
                note="wall time of PreviewControl.set_style to the child's answer (IPC round trip, warm child)",
            )
        )
    return specs, dispose


PREVIEW_NAMES: Tuple[Name, ...] = (
    ("m5 preview change screen warm", 300, 300.0),
    ("m5 preview change style warm", 300, 300.0),
)


GROUPS: Sequence[Group] = (
    Group("menus", MENU_NAMES, menus_group),
    Group("actions", ACTIONS_NAMES, actions_group),
    Group("pictures", PICTURE_NAMES, pictures_group),
    Group("own_class", OWN_CLASS_NAMES, own_class_group),
    Group("start", START_NAMES, start_group),
    Group("shell", SHELL_NAMES, shell_group),
    Group("preview", PREVIEW_NAMES, preview_group),
)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Print the M5 rows as the speed table: ``python -m tests.form_builder.perf.m5_paths [--samples N] [--only key,...]``."""
    import argparse

    from tests.form_builder.perf import harness

    parser = argparse.ArgumentParser(description="UX-M5-009 speed rows")
    parser.add_argument("--samples", type=int, default=15)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--only", default="", help="comma list of group keys: " + ",".join(g.key for g in GROUPS))
    args = parser.parse_args(list(argv) if argv is not None else sys.argv[1:])
    only = tuple(item for item in args.only.split(",") if item)
    report = harness.run_m5_speed(samples=args.samples, warmup=args.warmup, only=only)
    sys.stdout.write(harness.format_table(report))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
