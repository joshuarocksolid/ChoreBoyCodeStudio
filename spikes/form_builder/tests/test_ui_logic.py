"""Behaviour behind the workbench: sizing words, paste, tab order, cells, menus, reconcile.

Each test is a pain point from docs/form_builder/research/P_user_pain_points.md.
"""

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

from spikes.form_builder import sizing
from spikes.form_builder.commands import (
    History,
    InsertItem,
    RemoveLayout,
    SetProperty,
    Unwrap,
    Wrap,
    add_action_command,
    add_menu_command,
    insert_near,
    morph_layout,
    next_cell,
    pair_buddies,
    with_tab_splice,
)
from spikes.form_builder.generate import generate_ui
from spikes.form_builder.model import (
    blank_widget,
    clone_widget,
    document_signature,
    get_property,
    item_content,
    iter_widgets,
    layout_items,
    make_item,
    make_layout,
    make_widget,
    prop_string,
    tabstops_of,
    widget_layout,
)
from spikes.form_builder.templates import blank_main_window, data_entry
from spikes.form_builder.xmlio import dump_ui, load_ui

APP = QApplication.instance() or QApplication([])
LINE_EDIT = ("Expanding", "Fixed")


def _named(doc, name):
    return next(widget for widget in iter_widgets(doc) if widget.object_name == name)


def _box(names=("one", "two", "three"), cls="QPushButton"):
    doc = blank_widget()
    layout = make_layout(doc, "QVBoxLayout", "verticalLayout")
    doc.root.body.append(layout)
    for name in names:
        widget = make_widget(doc, cls, name)
        widget.body.append(prop_string("text", name))
        layout.body.append(make_item(doc, widget))
    return doc, layout


def _run_generated(doc, host_cls=QWidget):
    from spikes.form_builder.generate import _py_name
    from spikes.form_builder.model import form_class_name

    code = generate_ui(doc, "form.ui")
    folder = Path(tempfile.mkdtemp())
    path = folder / "ui_form.py"
    path.write_text(code, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("ui_form_" + str(abs(hash(code))), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    host = host_cls()
    getattr(module, "Ui_" + _py_name(form_class_name(doc)))().setupUi(host)
    return host, code


class SizingWordsTest(unittest.TestCase):
    """Pain 2: three size words, and Reset deletes the line."""

    def test_fixed_then_hug_leaves_no_size_lines(self):
        doc = data_entry()
        history = History(doc)
        name = _named(doc, "name")
        history.execute(sizing.set_axis(name, "h", "fixed", LINE_EDIT, 200))
        self.assertEqual(sizing.axis_mode(name, "h", LINE_EDIT)[:2], ("fixed", 200))
        self.assertIn("<width>200</width>", dump_ui(doc))
        history.execute(sizing.set_axis(name, "h", "hug", LINE_EDIT))
        self.assertEqual(sizing.axis_mode(name, "h", LINE_EDIT)[0], "hug")
        self.assertIsNone(get_property(name, "minimumSize"))
        self.assertIsNone(get_property(name, "maximumSize"))
        history.execute(sizing.set_axis(name, "h", "auto", LINE_EDIT))
        self.assertIsNone(get_property(name, "sizePolicy"), "back at the class default, the policy line is gone")

    def test_reset_minimum_removes_the_property(self):
        doc = data_entry()
        name = _named(doc, "name")
        History(doc).execute(SetProperty(name.id, "minimumSize", sizing.size_property("minimumSize", 0, 40)))
        History(doc).execute(sizing.reset_size_property(name, "minimumSize"))
        self.assertNotIn("minimumSize", dump_ui(doc))

    def test_share_implies_fill(self):
        doc, _layout = _box()
        button = _named(doc, "two")
        History(doc).execute(sizing.set_share(button, "v", 1, ("Minimum", "Fixed")))
        self.assertEqual(sizing.axis_mode(button, "v", ("Minimum", "Fixed"))[0], "fill")
        self.assertEqual(sizing.share_of(button, "v"), 1)


class PasteIntoLayoutTest(unittest.TestCase):
    """Pain 3: paste goes into the layout after the selection; undo restores."""

    def test_paste_after_middle_button(self):
        doc, layout = _box()
        history = History(doc)
        before = document_signature(doc)
        middle = _named(doc, "two")
        copy = clone_widget(doc, middle)
        history.execute(insert_near(doc, [middle.id], copy))
        names = [item_content(item).object_name for item in layout_items(layout)]
        self.assertEqual(names, ["one", "two", copy.object_name, "three"])
        history.undo()
        self.assertEqual(document_signature(doc), before)

    def test_paste_with_layout_selected_appends(self):
        doc, layout = _box()
        copy = clone_widget(doc, _named(doc, "one"))
        History(doc).execute(insert_near(doc, [layout.id], copy))
        self.assertIs(item_content(layout_items(layout)[-1]), copy)


class TabOrderTest(unittest.TestCase):
    """Pain 20: a new input joins the saved tab order where it sits, not at the end."""

    def test_insert_between_two_fields_splices(self):
        doc, layout = _box(("first", "second"), "QLineEdit")
        from spikes.form_builder.model import ensure_tabstops

        ensure_tabstops(doc).names = ["first", "second"]
        middle = make_widget(doc, "QLineEdit", "middle")
        command = with_tab_splice(doc, InsertItem(layout.id, 1, make_item(doc, middle)), middle)
        history = History(doc)
        history.execute(command)
        self.assertEqual(tabstops_of(doc).names, ["first", "middle", "second"])
        history.undo()
        self.assertEqual(tabstops_of(doc).names, ["first", "second"])


class CellsTest(unittest.TestCase):
    """Delighter 11: the next control fills the next cell."""

    def test_field_after_label_fills_the_row(self):
        doc = blank_widget()
        form = make_layout(doc, "QFormLayout")
        doc.root.body.append(form)
        label = make_widget(doc, "QLabel", "priceLabel")
        form.body.append(make_item(doc, label, row="0", column="0"))
        field = make_widget(doc, "QDoubleSpinBox", "price")
        History(doc).execute(insert_near(doc, [label.id], field))
        holder = next(item for item in layout_items(form) if item_content(item) is field)
        self.assertEqual((holder.attrib["row"], holder.attrib["column"]), ("0", "1"))

    def test_grid_next_cell_is_first_gap(self):
        doc = blank_widget()
        grid = make_layout(doc, "QGridLayout")
        for row, col in ((0, 0), (0, 1), (1, 0)):
            grid.body.append(make_item(doc, make_widget(doc, "QPushButton"), row=str(row), column=str(col)))
        self.assertEqual(next_cell(grid), {"row": "1", "column": "1"})


class BuddyAndMorphTest(unittest.TestCase):
    def test_pair_buddies_in_form_rows(self):
        doc = data_entry()
        for widget in iter_widgets(doc):
            if widget.class_name == "QLabel":
                widget.body = [part for part in widget.body if getattr(part, "name", "") != "buddy"]
        History(doc).execute(__import__("spikes.form_builder.commands", fromlist=["Compound"]).Compound(pair_buddies(doc)))
        self.assertEqual(get_property(_named(doc, "label_3"), "buddy").body.text, "notes")

    def test_vbox_to_form_pairs_labels_and_undo_restores(self):
        doc = blank_widget()
        box = make_layout(doc, "QVBoxLayout")
        doc.root.body.append(box)
        for cls, name in (("QLabel", "nameLabel"), ("QLineEdit", "nameEdit"), ("QPushButton", "save")):
            box.body.append(make_item(doc, make_widget(doc, cls, name)))
        history = History(doc)
        before = document_signature(doc)
        history.execute(morph_layout(doc, box.id, "QFormLayout"))
        cells = {item_content(item).object_name: (item.attrib["row"], item.attrib["column"]) for item in layout_items(box)}
        self.assertEqual(cells["nameLabel"], ("0", "0"))
        self.assertEqual(cells["nameEdit"], ("0", "1"))
        self.assertEqual(cells["save"][0], "1")
        history.undo()
        self.assertEqual(document_signature(doc), before)


class MenuTest(unittest.TestCase):
    """Type here on a main window menu writes Designer's XML and runs."""

    def test_type_here_menu_and_action(self):
        doc = blank_main_window()
        history = History(doc)
        bar = _named(doc, "menubar")
        command, menu_id = add_menu_command(doc, bar.id, "Edit")
        history.execute(command)
        command, _action = add_action_command(doc, menu_id, "Copy")
        history.execute(command)
        command, _none = add_action_command(doc, menu_id, "-")
        history.execute(command)
        xml = dump_ui(doc)
        self.assertIn('<addaction name="menuEdit"/>', xml)
        self.assertIn('<addaction name="actionCopy"/>', xml)
        self.assertIn('<addaction name="separator"/>', xml)
        window, _code = _run_generated(load_ui(xml), QMainWindow)
        titles = [action.text() for action in window.menuBar().actions()]
        self.assertEqual(titles, ["File", "Edit"])


class GeneratorTest(unittest.TestCase):
    def test_freecad_widget_falls_back_to_base_and_keeps_properties(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0"><class>PartGui::Task</class>
 <widget class="QWidget" name="PartGui::Task">
  <layout class="QVBoxLayout" name="v">
   <property name="leftMargin"><number>3</number></property>
   <item><widget class="Gui::InputField" name="length"><property name="unit" stdset="0"><string>mm</string></property></widget></item>
  </layout>
 </widget>
 <customwidgets><customwidget><class>Gui::InputField</class><extends>QLineEdit</extends><header>Gui/InputField.h</header></customwidget></customwidgets>
 <resources/><connections/>
</ui>"""
        host, code = _run_generated(load_ui(xml))
        self.assertIn("_cbcs_custom", code)
        self.assertIn("setContentsMargins(3, -1, -1, -1)", code)
        field = host.findChild(QWidget, "length")
        self.assertEqual(field.metaObject().className(), "QLineEdit")


class ReconcileTest(unittest.TestCase):
    """Wrap, unwrap, and the first layout move live widgets; the tree matches a fresh build."""

    def _shape(self, realization):
        def walk(widget):
            layout = widget.layout()
            children = []
            if layout is not None:
                for index in range(layout.count()):
                    child = layout.itemAt(index).widget()
                    if child is not None:
                        children.append(walk(child))
            return (widget.property("formId") or "holder", widget.metaObject().className(), tuple(children))

        return walk(realization.root)

    def test_wrap_unwrap_reuse_widgets(self):
        from spikes.form_builder.realize import Realization

        doc, layout = _box()
        live = Realization()
        live.build(doc)
        first = live.widgets[_named(doc, "one").id]
        history = History(doc)
        items = [item.id for item in layout_items(layout)[:2]]
        wrap = Wrap(items, "QGroupBox", "QHBoxLayout")
        history.execute(wrap)
        self.assertTrue(live.reconcile())
        self.assertIs(live.widgets[_named(doc, "one").id], first, "wrap moved the widget instead of rebuilding it")
        fresh = Realization()
        fresh.build(doc)
        self.assertEqual(self._shape(live), self._shape(fresh))
        history.execute(Unwrap(wrap.container.id))
        self.assertTrue(live.reconcile())
        self.assertIs(live.widgets[_named(doc, "one").id], first)
        history.undo()
        history.undo()
        self.assertTrue(live.reconcile())
        fresh.build(doc)
        self.assertEqual(self._shape(live), self._shape(fresh))

    def test_first_layout_on_empty_group_and_remove_layout(self):
        from spikes.form_builder.canvas import Slot, Surface
        from spikes.form_builder.realize import Realization

        doc, layout = _box(("one",))
        group = make_widget(doc, "QGroupBox", "group")
        History(doc).execute(InsertItem(layout.id, 1, make_item(doc, group)))
        live = Realization()
        live.build(doc)
        surface = Surface()
        surface.doc = doc
        button = make_widget(doc, "QPushButton", "inside")
        history = History(doc)
        history.execute(surface.commands_for_drop(button, Slot("newlayout", widget_id=group.id)))
        self.assertIsNotNone(widget_layout(group))
        self.assertTrue(live.reconcile())
        self.assertIs(live.widgets[button.id].parentWidget(), live.widgets[group.id])
        history.execute(RemoveLayout(group.id))
        self.assertTrue(live.reconcile())
        self.assertIsNone(live.widgets[group.id].layout())
        history.undo()
        history.undo()
        self.assertTrue(live.reconcile())
        self.assertNotIn(button.id, live.widgets)


class CanvasMoveTest(unittest.TestCase):
    """Pain 21: moving one grid item changes only that item's cell."""

    def test_grid_move_touches_only_the_moved_item(self):
        from spikes.form_builder.canvas import Slot, Surface

        doc = blank_widget()
        grid = make_layout(doc, "QGridLayout")
        doc.root.body.append(grid)
        buttons = []
        for row, col in ((0, 0), (0, 1), (1, 0)):
            button = make_widget(doc, "QPushButton")
            grid.body.append(make_item(doc, button, row=str(row), column=str(col)))
            buttons.append(button)
        others = {item.id: dict(item.attrib) for item in layout_items(grid)[1:]}
        surface = Surface()
        surface.doc = doc
        history = History(doc)
        history.execute(surface.commands_for_move(buttons[0].id, Slot("cell", grid.id, attrib={"row": "1", "column": "2"})))
        moved = next(item for item in layout_items(grid) if item_content(item) is buttons[0])
        self.assertEqual((moved.attrib["row"], moved.attrib["column"]), ("1", "2"))
        for item in layout_items(grid):
            if item.id in others:
                self.assertEqual(item.attrib, others[item.id])
        history.undo()
        moved = next(item for item in layout_items(grid) if item_content(item) is buttons[0])
        self.assertEqual((moved.attrib["row"], moved.attrib["column"]), ("0", "0"))

    def test_drop_slot_in_live_box_layout(self):
        from spikes.form_builder.window import MainWindow

        window = MainWindow("light")
        window.resize(1200, 800)
        window.show()
        doc, _layout = _box()
        window.load_document(doc, None)
        APP.processEvents()
        surface = window.canvas.primary
        surface.rebuild_index()
        one = surface.index.rect_of[_named(doc, "one").id]
        two = surface.index.rect_of[_named(doc, "two").id]
        slot = surface.slot_at(QPoint(one.center().x(), (one.bottom() + two.top()) // 2), "QLineEdit")
        self.assertEqual((slot.mode, slot.index), ("insert", 1))
        content = make_widget(doc, "QLineEdit", "fresh")
        window.history.execute(surface.commands_for_drop(content, slot))
        names = [item_content(item).object_name for item in layout_items(widget_layout(doc.root))]
        self.assertEqual(names, ["one", "fresh", "two", "three"])
        window.close()


if __name__ == "__main__":
    unittest.main()
