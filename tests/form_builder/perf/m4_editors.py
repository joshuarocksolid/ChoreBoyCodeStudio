# pyright: reportAttributeAccessIssue=false
"""UX-M4-007 scenarios for the speed harness: popovers, item editors, Insert search.

Each ``*_group`` builds what one family of rows needs and returns the specs to
time plus a teardown. ``harness._m4_rows`` times the specs with ``_timed``
(prepare and cleanup run outside the clock) and always runs the teardown.

Opening a popover is 50 ms. One live change from a popover, one keystroke in an
item editor and one keystroke in Insert search are 16 ms (UX-M4-007).
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Sequence, Tuple

OPEN_BUDGET_MS = 50.0
LIVE_BUDGET_MS = 16.0


@dataclass(frozen=True)
class Spec:
    point: str
    widgets: Optional[int]
    budget_ms: float
    fn: Callable[[], None]
    prepare: Optional[Callable[[], None]] = None
    cleanup: Optional[Callable[[], None]] = None


@dataclass(frozen=True)
class Group:
    """``names`` are the points the group yields, so a failed build can report each as skipped."""

    names: Tuple[Tuple[str, Optional[int], float], ...]
    build: Callable[[], Tuple[List[Spec], Callable[[], None]]]


_RICH_TEXT = "&lt;html&gt;&lt;head/&gt;&lt;body&gt;&lt;p&gt;Orders &lt;b&gt;today&lt;/b&gt;&lt;/p&gt;&lt;/body&gt;&lt;/html&gt;"
_BANNER_PROPS = """
<property name="color"><color><red>255</red><green>0</green><blue>0</blue></color></property>
<property name="brush">
 <brush brushstyle="LinearGradientPattern">
  <gradient type="LinearGradient" spread="PadSpread" coordinatemode="ObjectBoundingMode" startx="0" starty="0" endx="1" endy="0">
   <gradientstop position="0"><color><red>0</red><green>0</green><blue>0</blue></color></gradientstop>
   <gradientstop position="1"><color><red>255</red><green>255</green><blue>255</blue></color></gradientstop>
  </gradient>
 </brush>
</property>
<property name="textFormat"><enum>Qt::RichText</enum></property>
"""


def _flush(app: object) -> None:
    """Run the deleteLater calls a closed popover or editor queued.

    ``processEvents`` does not deliver them outside an event loop, and the live
    widgets they leave behind slow the next opening, which the editor never sees.
    """
    from app.qt.QtCore import QCoreApplication, QEvent

    app.processEvents()
    QCoreApplication.sendPostedEvents(None, int(QEvent.Type.DeferredDelete.value))


def _qrc(folder: str, count: int) -> None:
    from app.qt.QtCore import QBuffer, QIODevice
    from app.qt.QtGui import QColor, QImage

    image = QImage(8, 8, getattr(getattr(QImage, "Format", QImage), "Format_ARGB32"))
    image.fill(QColor(20, 120, 200))
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    payload = bytes(buffer.data())
    lines = []
    for index in range(count):
        name = "pic%02d.png" % index
        with open(os.path.join(folder, name), "wb") as handle:
            handle.write(payload)
        lines.append(" <file>%s</file>" % name)
    with open(os.path.join(folder, "app.qrc"), "w", encoding="utf-8") as handle:
        handle.write('<RCC version="1.0"><qresource prefix="/icons">\n%s\n</qresource></RCC>\n' % "\n".join(lines))


def _reference_xml(folder: str) -> str:
    from tests.form_builder.perf.reference import DEFAULT_SEED, reference_form

    xml = reference_form(300, DEFAULT_SEED).xml
    needle = '<widget class="QLabel" name="banner">'
    if needle not in xml:
        raise RuntimeError("reference form has no banner label")
    xml = xml.replace(needle, needle + _BANNER_PROPS, 1)
    text = '<property name="text"><string>Orders</string></property>'
    if text not in xml:
        raise RuntimeError("banner text moved")
    xml = xml.replace(text, '<property name="text"><string>%s</string></property>' % _RICH_TEXT, 1)
    if "<resources/>" not in xml:
        raise RuntimeError("reference form resources moved")
    return xml.replace("<resources/>", '<resources><include location="app.qrc"/></resources>', 1)


class _Inspector:
    """The 300 reference form with an InspectorPane, All properties expanded."""

    def __init__(self) -> None:
        from app.features.form_builder.qtside.inspector import InspectorPane
        from app.features.form_builder.qtside.inspector.api import GroupId
        from app.qt.QtWidgets import QApplication, QVBoxLayout, QWidget
        from tests.form_builder.qtside.support import realize

        self.folder = tempfile.mkdtemp(prefix="cbcs-m4-perf-")
        _qrc(self.folder, 50)
        self.app = QApplication.instance() or QApplication([])
        self.session, self.realizer = realize(_reference_xml(self.folder), os.path.join(self.folder, "speed.ui"))
        self.window = QWidget()
        self.pane = InspectorPane(self.session, self.realizer, data_tab=False, on_leave=lambda: None, parent=self.window)
        layout = QVBoxLayout(self.window)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.pane)
        self.window.resize(420, 900)
        self.window.show()
        self.app.processEvents()
        self.pane.set_group_expanded(GroupId.ALL, True)
        self.selected = ""
        self.open_key = ""
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
        if self.selected == name:
            return
        from app.features.form_builder.engine.query.selection import SelectionSource

        self.close_popover()
        node = self.session.document.by_name(name)[0]
        self.session.selection.set((node,), source=SelectionSource.PROGRAM)
        self.pane.flush()
        self.app.processEvents()
        self.selected = name

    def visible(self, name: str):
        from app.qt.QtWidgets import QApplication

        found = [w for w in QApplication.allWidgets() if w.objectName() == name and w.isVisible()]
        if not found:
            raise RuntimeError("missing %s" % name)
        return found[-1]

    def named_text(self, accessible: str):
        from app.qt.QtWidgets import QApplication

        found = [w for w in QApplication.allWidgets() if w.accessibleName() == accessible and w.isVisible()]
        if not found:
            raise RuntimeError("missing %s" % accessible)
        return found[-1]

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
        self.open_key = key

    def close_popover(self) -> None:
        from app.qt.QtWidgets import QApplication

        done = [
            w for w in QApplication.allWidgets() if w.objectName() == "formBuilder.popoverDone" and w.isVisible()
        ]
        if done:
            done[-1].click()
            _flush(self.app)
        self.open_key = ""


def _open_spec(bench: _Inspector, point: str, owner: str, key: str) -> Spec:
    def prepare() -> None:
        bench.select(owner)
        bench.close_popover()

    return Spec(point, 300, OPEN_BUDGET_MS, lambda: bench.open_row(key), prepare=prepare, cleanup=bench.close_popover)


def _opened(bench: _Inspector, owner: str, key: str) -> Callable[[], None]:
    """Prepare for a live change: the popover for ``key`` is open on ``owner``."""

    def prepare() -> None:
        bench.select(owner)
        if bench.open_key != key:
            bench.close_popover()
            bench.open_row(key)

    return prepare


def inspector_group() -> Tuple[List[Spec], Callable[[], None]]:
    from app.qt.QtCore import QPoint, Qt
    from app.qt.QtTest import QTest
    from app.qt.QtWidgets import QCheckBox, QToolButton

    bench = _Inspector()
    specs: List[Spec] = []

    # Scalar / flags / size policy -------------------------------------------------
    specs.append(_open_spec(bench, "m4 open flags popover", "banner", "textInteractionFlags"))
    flag_prepare = _opened(bench, "banner", "textInteractionFlags")

    def toggle_flag() -> None:
        box = _first_flag(bench)
        QTest.keyClick(box, Qt.Key.Key_Space)
        bench.app.processEvents()

    specs.append(Spec("m4 flags live toggle", 300, LIVE_BUDGET_MS, toggle_flag, prepare=_focus_flag(bench, flag_prepare)))
    specs.append(_open_spec(bench, "m4 open size policy popover", "banner", "sizePolicy"))

    # Font -------------------------------------------------------------------------
    specs.append(_open_spec(bench, "m4 open font popover", "banner", "font"))
    font_prepare = _opened(bench, "banner", "font")

    def font_step() -> None:
        QTest.keyClick(bench.visible("formBuilder.fontSize"), Qt.Key.Key_Up)
        bench.app.processEvents()

    specs.append(Spec("m4 font size step", 300, LIVE_BUDGET_MS, font_step, prepare=font_prepare))

    # Colour, brush/gradient, palette ------------------------------------------------
    specs.append(_open_spec(bench, "m4 open colour popover", "banner", "color"))
    specs.append(_open_spec(bench, "m4 open brush popover", "banner", "brush"))
    specs.append(_open_spec(bench, "m4 open palette popover", "banner", "palette"))
    specs.append(_drag_spec(bench, "m4 colour square drag", "color", "formBuilder.colorSquare"))
    specs.append(_drag_spec(bench, "m4 gradient stop drag", "brush", "formBuilder.gradientBar"))
    specs.append(_palette_spec(bench))

    # Text / translation -------------------------------------------------------------
    specs.append(_open_spec(bench, "m4 open rich text popover", "banner", "text"))
    text_prepare = _opened(bench, "banner", "text")
    letters = ["x", "y"]
    state = {"n": 0}

    def keystroke() -> None:
        edit = bench.named_text("Text: formatted text")
        state["n"] += 1
        QTest.keyClicks(edit, letters[state["n"] % 2])
        bench.app.processEvents()

    def text_focus() -> None:
        text_prepare()
        bench.named_text("Text: formatted text").setFocus()

    specs.append(Spec("m4 rich text keystroke", 300, LIVE_BUDGET_MS, keystroke, prepare=text_focus))

    def translation_prepare() -> None:
        bench.select("banner")
        bench.close_popover()
        toggle = _toggle(bench)
        if toggle.isChecked():
            toggle.click()
            bench.app.processEvents()

    def translation_open() -> None:
        _toggle(bench).click()
        bench.app.processEvents()

    specs.append(Spec("m4 open translation panel", 300, OPEN_BUDGET_MS, translation_open, prepare=translation_prepare))

    # Picture picker ------------------------------------------------------------------
    specs.append(_open_spec(bench, "m4 open icon picker", "field0009", "icon"))
    picker_prepare = _opened(bench, "field0009", "icon")
    sign = {"n": 0}

    def arrow() -> None:
        grid = bench.visible("formBuilder.pictureGrid")
        sign["n"] += 1
        QTest.keyClick(grid, Qt.Key.Key_Right if sign["n"] % 2 else Qt.Key.Key_Left)
        bench.app.processEvents()

    def picker_focus() -> None:
        picker_prepare()
        bench.visible("formBuilder.pictureGrid").setFocus()

    specs.append(Spec("m4 icon grid arrow", 300, LIVE_BUDGET_MS, arrow, prepare=picker_focus))
    del QPoint, QCheckBox, QToolButton
    return specs, bench.dispose


def _toggle(bench: _Inspector):
    from app.qt.QtWidgets import QToolButton, QWidget

    row = bench.pane.findChild(QWidget, "formBuilder.row.text")
    toggle = row.findChild(QToolButton, "formBuilder.translationToggle")
    if toggle is None:
        raise RuntimeError("missing translation toggle")
    return toggle


def _first_flag(bench: _Inspector):
    from app.qt.QtWidgets import QApplication, QCheckBox

    pops = [w for w in QApplication.allWidgets() if w.objectName() == "formBuilder.rowPopover" and w.isVisible()]
    if not pops:
        raise RuntimeError("no flags popover")
    boxes = [b for b in pops[-1].findChildren(QCheckBox) if b.isVisible()]
    if not boxes:
        raise RuntimeError("no flag checkbox")
    return boxes[0]


def _focus_flag(bench: _Inspector, opened: Callable[[], None]) -> Callable[[], None]:
    def prepare() -> None:
        opened()
        _first_flag(bench).setFocus()

    return prepare


def _drag_spec(bench: _Inspector, point: str, key: str, surface: str) -> Spec:
    """Press outside the clock, one timed move, release outside the clock."""
    from app.qt.QtCore import QPoint, Qt
    from app.qt.QtTest import QTest

    opened = _opened(bench, "banner", key)
    held = {"widget": None, "n": 0, "at": None}

    def prepare() -> None:
        opened()
        widget = bench.visible(surface)
        held["widget"] = widget
        # A gradient bar adds a stop when a press misses every stop, so grab the first one.
        stops = getattr(widget, "stops", None)
        grab = widget.rect().center()
        if stops is not None:
            grab = QPoint(widget._x_at(stops()[0].position), grab.y())
        held["at"] = grab
        QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=grab)
        bench.app.processEvents()

    def move() -> None:
        widget = held["widget"]
        held["n"] += 1
        target = QPoint(12 + (held["n"] % 6) * 8, widget.rect().center().y())
        QTest.mouseMove(widget, target)
        held["at"] = target
        bench.app.processEvents()

    def cleanup() -> None:
        widget = held["widget"]
        if widget is not None:
            QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=held["at"])
            bench.app.processEvents()
            held["widget"] = None

    return Spec(point, 300, LIVE_BUDGET_MS, move, prepare=prepare, cleanup=cleanup)


def _palette_spec(bench: _Inspector) -> Spec:
    """One palette role change: the hex field of the open role's brush editor."""
    from app.qt.QtCore import Qt
    from app.qt.QtTest import QTest

    opened = _opened(bench, "banner", "palette")
    state = {"n": 0}

    def prepare() -> None:
        opened()
        roles = bench.visible("formBuilder.paletteRoles")
        roles.setFocus()
        QTest.keyClick(roles, Qt.Key.Key_Return)
        bench.app.processEvents()
        bench.visible("formBuilder.colorHex").setFocus()

    def change() -> None:
        field = bench.visible("formBuilder.colorHex")
        state["n"] += 1
        field.setText("#1A7F37" if state["n"] % 2 else "#7F1A37")
        QTest.keyClick(field, Qt.Key.Key_Return)
        bench.app.processEvents()

    def cleanup() -> None:
        try:
            QTest.keyClick(bench.visible("formBuilder.colorHex"), Qt.Key.Key_Escape)
            bench.app.processEvents()
        except RuntimeError:
            pass

    return Spec("m4 palette role change", 300, LIVE_BUDGET_MS, change, prepare=prepare, cleanup=cleanup)


# Item editors ---------------------------------------------------------------------------

def _prop(text: str) -> str:
    return '<property name="text"><string>%s</string></property>' % text


def _combo_xml(count: int) -> str:
    items = "".join("<item>%s</item>" % _prop("Item %d" % n) for n in range(count))
    return '<widget class="QComboBox" name="subject">%s</widget>' % items


def _table_xml(rows: int, columns: int) -> str:
    parts = ["<column>%s</column>" % _prop("C%d" % c) for c in range(columns)]
    parts += ["<row>%s</row>" % _prop("R%d" % r) for r in range(rows)]
    for r in range(rows):
        for c in range(columns):
            parts.append('<item row="%d" column="%d">%s</item>' % (r, c, _prop("%d,%d" % (r, c))))
    return '<widget class="QTableWidget" name="subject">%s</widget>' % "".join(parts)


def _tree_xml(rows: int) -> str:
    parts = ["<column>%s</column>" % _prop("Node")]
    roots = max(1, rows // 5)
    for root in range(roots):
        children = "".join("<item>%s</item>" % _prop("Child %d.%d" % (root, n)) for n in range(4))
        parts.append("<item>%s%s</item>" % (_prop("Root %d" % root), children))
    return '<widget class="QTreeWidget" name="subject">%s</widget>' % "".join(parts)


def _items_form(widget_xml: str) -> str:
    from tests.form_builder.qtside.support import form

    return form(
        'class="QWidget" name="Form"',
        '  <layout class="QVBoxLayout" name="box">\n   <item>%s</item>\n  </layout>' % widget_xml,
    )


class _Items:
    """A small form with one item widget and a parent window to open its editor under."""

    def __init__(self, widget_xml: str) -> None:
        from app.features.form_builder.engine.query.selection import SelectionSource
        from app.qt.QtWidgets import QApplication, QWidget
        from tests.form_builder.qtside.support import realize

        self.app = QApplication.instance() or QApplication([])
        self.session, self.realizer = realize(_items_form(widget_xml))
        self.parent = QWidget()
        self.parent.resize(900, 700)
        self.parent.show()
        self.node = self.session.document.by_name("subject")[0]
        self.session.selection.set((self.node,), current=self.node, source=SelectionSource.PROGRAM)
        self.editor: Any = None

    def open(self) -> None:
        from app.features.form_builder.qtside.items.editor import open_editor

        self.editor = open_editor(self.session, self.node, self.parent)
        if self.editor is None:
            raise RuntimeError("no item editor")
        self.app.processEvents()

    def close(self) -> None:
        editor = self.editor
        self.editor = None
        if editor is not None:
            editor.revert()
            _flush(self.app)

    def dispose(self) -> None:
        self.close()
        self.realizer.dispose()
        self.session.dispose()
        self.parent.close()
        _flush(self.app)


def _open_close(box: _Items, point: str, widgets: int) -> Spec:
    return Spec(point, widgets, OPEN_BUDGET_MS, box.open, prepare=box.close, cleanup=box.close)


def _row_fields(box: _Items) -> list:
    from app.qt.QtWidgets import QLineEdit

    return [w for w in box.editor.findChildren(QLineEdit) if w.isVisible()]


def _key_spec(box: _Items, point: str, widgets: int, field: Callable[[], object]) -> Spec:
    from app.qt.QtTest import QTest

    def prepare() -> None:
        if box.editor is None:
            box.open()
        field().setFocus()

    def keystroke() -> None:
        QTest.keyClick(field(), "a")
        box.app.processEvents()

    return Spec(point, widgets, LIVE_BUDGET_MS, keystroke, prepare=prepare)


def combo_group() -> Tuple[List[Spec], Callable[[], None]]:
    from app.qt.QtCore import Qt
    from app.qt.QtTest import QTest
    from app.qt.QtWidgets import QToolButton

    box = _Items(_combo_xml(500))
    specs = [
        _open_close(box, "m4 open item editor combo 500", 500),
        _key_spec(box, "m4 item editor combo keystroke", 500, lambda: _row_fields(box)[0]),
    ]

    def more_prepare() -> None:
        if box.editor is None:
            box.open()
        field = _row_fields(box)[0]
        field.setFocus()
        QTest.keyClick(field, Qt.Key.Key_Left, Qt.KeyboardModifier.AltModifier)
        QTest.keyClick(field, Qt.Key.Key_Right, Qt.KeyboardModifier.AltModifier)
        _flush(box.app)

    def more_open() -> None:
        button = box.editor.findChild(QToolButton, "formBuilder.itemMore")
        if button is None:
            raise RuntimeError("no More properties button")
        button.click()
        box.app.processEvents()

    specs.append(Spec("m4 open item more properties", 500, OPEN_BUDGET_MS, more_open, prepare=more_prepare))
    return specs, box.dispose


def table_group() -> Tuple[List[Spec], Callable[[], None]]:
    from app.qt.QtCore import Qt
    from app.qt.QtTest import QTest
    from app.qt.QtWidgets import QTableWidget

    box = _Items(_table_xml(30, 8))

    def grid() -> object:
        found = box.editor.findChild(QTableWidget, "formBuilder.itemCells")
        if found is None:
            raise RuntimeError("no cell grid")
        return found

    def prepare() -> None:
        if box.editor is None:
            box.open()
        grid().setFocus()

    def keystroke() -> None:
        # One typed character, then the commit that carries it to the form.
        cells = grid()
        QTest.keyClick(cells, "a")
        QTest.keyClick(cells.viewport().focusWidget() or cells, Qt.Key.Key_Return)
        box.app.processEvents()

    specs = [
        _open_close(box, "m4 open item editor table 30x8", 240),
        Spec("m4 item editor table cell keystroke", 240, LIVE_BUDGET_MS, keystroke, prepare=prepare),
    ]
    return specs, box.dispose


def tree_group(rows: int) -> Callable[[], Tuple[List[Spec], Callable[[], None]]]:
    def build() -> Tuple[List[Spec], Callable[[], None]]:
        box = _Items(_tree_xml(rows))
        specs = [
            _open_close(box, "m4 open item editor tree %d" % rows, rows),
            _key_spec(box, "m4 item editor tree %d keystroke" % rows, rows, lambda: _row_fields(box)[0]),
        ]
        return specs, box.dispose

    return build


ITEM_NAMES: Tuple[Tuple[str, Optional[int], float], ...] = (
    ("m4 open item editor combo 500", 500, OPEN_BUDGET_MS),
    ("m4 item editor combo keystroke", 500, LIVE_BUDGET_MS),
    ("m4 open item more properties", 500, OPEN_BUDGET_MS),
)
TABLE_NAMES: Tuple[Tuple[str, Optional[int], float], ...] = (
    ("m4 open item editor table 30x8", 240, OPEN_BUDGET_MS),
    ("m4 item editor table cell keystroke", 240, LIVE_BUDGET_MS),
)
TREE_ROWS = (100, 500)


def _tree_names(rows: int) -> Tuple[Tuple[str, Optional[int], float], ...]:
    return (
        ("m4 open item editor tree %d" % rows, rows, OPEN_BUDGET_MS),
        ("m4 item editor tree %d keystroke" % rows, rows, LIVE_BUDGET_MS),
    )


# Insert search -------------------------------------------------------------------------

def insert_group() -> Tuple[List[Spec], Callable[[], None]]:
    """One keystroke into the Insert pane filter and the outline's quick-insert filter.

    Each sample starts from an empty filter, so the keystroke searches the whole catalog.
    """
    from app.features.form_builder.integration.insert_memory import InMemoryInsertMemory
    from app.features.form_builder.integration.workbench import OutlinePane, _PieceOps
    from app.features.form_builder.qtside.insert.pane import InsertPane
    from app.qt.QtTest import QTest
    from app.qt.QtWidgets import QApplication, QLineEdit, QWidget

    app = QApplication.instance() or QApplication([])
    window = QWidget()
    window.resize(360, 700)
    pane = InsertPane(lambda _collapsed: None, window, memory=InMemoryInsertMemory(), pieces=_PieceOps())
    pane.setGeometry(0, 0, 360, 700)
    outline = OutlinePane(lambda _node: None, lambda _collapsed: None, window)
    outline.setGeometry(0, 0, 360, 700)
    outline.hide()
    window.show()
    app.processEvents()
    chars = ["b", "t", "c", "s"]
    state = {"n": 0}

    def pane_prepare() -> None:
        outline.hide()
        pane.show()
        pane.filter.setText("")
        pane.filter.setFocus()

    def pane_key() -> None:
        state["n"] += 1
        QTest.keyClick(pane.filter, chars[state["n"] % len(chars)])
        app.processEvents()

    def quick_prepare() -> None:
        pane.hide()
        outline.show()
        outline.show_insert()
        quick_filter().setText("")
        quick_filter().setFocus()

    def quick_filter() -> QLineEdit:
        found = outline.findChild(QLineEdit, "formBuilder.outlineInsertFilter")
        if found is None:
            raise RuntimeError("no quick insert filter")
        return found

    def quick_key() -> None:
        state["n"] += 1
        QTest.keyClick(quick_filter(), chars[state["n"] % len(chars)])
        app.processEvents()

    def dispose() -> None:
        window.close()
        _flush(app)

    specs = [
        Spec("m4 insert pane keystroke", None, LIVE_BUDGET_MS, pane_key, prepare=pane_prepare),
        Spec("m4 quick insert keystroke", None, LIVE_BUDGET_MS, quick_key, prepare=quick_prepare),
    ]
    return specs, dispose


INSERT_NAMES: Tuple[Tuple[str, Optional[int], float], ...] = (
    ("m4 insert pane keystroke", None, LIVE_BUDGET_MS),
    ("m4 quick insert keystroke", None, LIVE_BUDGET_MS),
)


INSPECTOR_NAMES: Tuple[Tuple[str, Optional[int], float], ...] = (
    ("m4 open flags popover", 300, OPEN_BUDGET_MS),
    ("m4 flags live toggle", 300, LIVE_BUDGET_MS),
    ("m4 open size policy popover", 300, OPEN_BUDGET_MS),
    ("m4 open font popover", 300, OPEN_BUDGET_MS),
    ("m4 font size step", 300, LIVE_BUDGET_MS),
    ("m4 open colour popover", 300, OPEN_BUDGET_MS),
    ("m4 open brush popover", 300, OPEN_BUDGET_MS),
    ("m4 open palette popover", 300, OPEN_BUDGET_MS),
    ("m4 colour square drag", 300, LIVE_BUDGET_MS),
    ("m4 gradient stop drag", 300, LIVE_BUDGET_MS),
    ("m4 palette role change", 300, LIVE_BUDGET_MS),
    ("m4 open rich text popover", 300, OPEN_BUDGET_MS),
    ("m4 rich text keystroke", 300, LIVE_BUDGET_MS),
    ("m4 open translation panel", 300, OPEN_BUDGET_MS),
    ("m4 open icon picker", 300, OPEN_BUDGET_MS),
    ("m4 icon grid arrow", 300, LIVE_BUDGET_MS),
)

GROUPS: Sequence[Group] = (
    Group(INSPECTOR_NAMES, inspector_group),
    Group(ITEM_NAMES, combo_group),
    Group(TABLE_NAMES, table_group),
    Group(INSERT_NAMES, insert_group),
) + tuple(Group(_tree_names(rows), tree_group(rows)) for rows in TREE_ROWS)
