"""Command log replay. No QApplication."""

import unittest

from spikes.form_builder.commands import (
    AddConnection,
    Delete,
    EnsureLayout,
    History,
    InsertItem,
    MoveItem,
    Rename,
    SetProperty,
    SetTabStops,
    Unwrap,
    Wrap,
    delete_targets,
    nest_command,
    unnest_command,
)
from spikes.form_builder.model import (
    Connection,
    blank_widget,
    connections_of,
    document_signature,
    get_property,
    layout_items,
    make_item,
    make_layout,
    make_widget,
    prop_cstring,
    prop_string,
    tabstops_of,
    widget_layout,
)
from spikes.form_builder.xmlio import dump_ui, load_ui


def _form_with_box():
    doc = blank_widget()
    layout = make_layout(doc, "QVBoxLayout")
    doc.root.body.append(layout)
    return doc, layout


def _button(doc, name=None):
    widget = make_widget(doc, "QPushButton", name)
    widget.body.append(prop_string("text", name or widget.object_name))
    return widget


class CommandReplayTest(unittest.TestCase):
    def test_insert_move_wrap_unwrap_delete_round_trip(self):
        doc, layout = _form_with_box()
        history = History(doc)
        start = document_signature(doc)
        first = _button(doc, "alpha")
        second = _button(doc, "beta")
        history.execute(InsertItem(layout.id, 0, make_item(doc, first)))
        history.execute(InsertItem(layout.id, 1, make_item(doc, second)))
        after_insert = document_signature(doc)

        second_item = layout_items(layout)[1]
        history.execute(MoveItem(second_item.id, layout.id, 0))
        names = [layout_items(layout)[0].body[0].object_name, layout_items(layout)[1].body[0].object_name]
        self.assertEqual(names, ["beta", "alpha"])

        item_ids = [item.id for item in layout_items(layout)]
        history.execute(Wrap(item_ids, "QGroupBox", "QVBoxLayout"))
        self.assertEqual(len(layout_items(layout)), 1)
        group = layout_items(layout)[0].body[0]
        self.assertEqual(group.class_name, "QGroupBox")
        inner = widget_layout(group)
        self.assertEqual(
            [item.body[0].object_name for item in layout_items(inner)],
            ["beta", "alpha"],
        )

        history.execute(Unwrap(group.id))
        self.assertEqual(
            [item.body[0].object_name for item in layout_items(layout)],
            ["beta", "alpha"],
        )

        target = delete_targets(doc, [layout_items(layout)[0].body[0].id])
        history.execute(Delete(target))
        self.assertEqual(
            [item.body[0].object_name for item in layout_items(layout)],
            ["alpha"],
        )
        after_delete = document_signature(doc)

        while history.undo():
            pass
        self.assertEqual(layout_items(layout), [])
        self.assertEqual(document_signature(doc), start)
        while history.redo():
            pass
        self.assertEqual(document_signature(doc), after_delete)
        self.assertNotEqual(after_insert, after_delete)

    def test_rename_rewrites_buddy_tabstop_and_connection(self):
        doc, layout = _form_with_box()
        history = History(doc)
        label = make_widget(doc, "QLabel", "nameLabel")
        label.body.append(prop_cstring("buddy", "nameEdit"))
        edit = make_widget(doc, "QLineEdit", "nameEdit")
        history.execute(InsertItem(layout.id, 0, make_item(doc, label)))
        history.execute(InsertItem(layout.id, 1, make_item(doc, edit)))
        history.execute(SetTabStops(["nameEdit"]))
        history.execute(AddConnection(Connection("nameEdit", "textChanged(QString)", "nameLabel", "setText(QString)")))
        history.execute(Rename(edit.id, "fullName"))
        self.assertEqual(get_property(label, "buddy").body.text, "fullName")
        self.assertEqual(tabstops_of(doc).names, ["fullName"])
        self.assertEqual(connections_of(doc).items[0].sender, "fullName")
        history.undo()
        self.assertEqual(edit.object_name, "nameEdit")
        self.assertEqual(get_property(label, "buddy").body.text, "nameEdit")

    def test_property_undo(self):
        doc, layout = _form_with_box()
        history = History(doc)
        button = _button(doc, "alpha")
        history.execute(InsertItem(layout.id, 0, make_item(doc, button)))
        history.execute(SetProperty(button.id, "text", prop_string("text", "After")))
        self.assertEqual(get_property(button, "text").body.text, "After")
        history.undo()
        self.assertEqual(get_property(button, "text").body.text, "alpha")
        history.redo()
        self.assertEqual(get_property(button, "text").body.text, "After")

    def test_drop_into_empty_container_creates_vbox(self):
        doc = blank_widget()
        history = History(doc)
        button = _button(doc, "alpha")
        layout_id = doc.alloc()
        from spikes.form_builder.commands import Compound

        history.execute(
            Compound(
                [
                    EnsureLayout(doc.root.id, "QVBoxLayout", layout_id, "verticalLayout"),
                    InsertItem(layout_id, 0, make_item(doc, button)),
                ]
            )
        )
        layout = widget_layout(doc.root)
        self.assertEqual(layout.class_name, "QVBoxLayout")
        self.assertEqual(layout_items(layout)[0].body[0].object_name, "alpha")
        history.undo()
        self.assertIsNone(widget_layout(doc.root))
        history.redo()
        self.assertEqual(widget_layout(doc.root).class_name, "QVBoxLayout")

    def test_nest_and_unnest(self):
        doc, layout = _form_with_box()
        history = History(doc)
        box = make_widget(doc, "QFrame", "frame")
        button = _button(doc, "alpha")
        history.execute(InsertItem(layout.id, 0, make_item(doc, box)))
        history.execute(InsertItem(layout.id, 1, make_item(doc, button)))
        history.execute(nest_command(doc, button.id))
        self.assertEqual(len(layout_items(layout)), 1)
        inner = widget_layout(box)
        self.assertEqual(layout_items(inner)[0].body[0].object_name, "alpha")
        history.execute(unnest_command(doc, button.id))
        self.assertEqual(
            [item.body[0].object_name for item in layout_items(layout)],
            ["frame", "alpha"],
        )

    def test_writer_is_deterministic(self):
        doc, layout = _form_with_box()
        button = _button(doc, "alpha")
        layout.body.append(make_item(doc, button))
        label = make_widget(doc, "QLabel", "nameLabel")
        label.body.append(prop_cstring("buddy", "alpha"))
        layout.body.append(make_item(doc, label, row="1", column="0"))
        first = dump_ui(doc)
        second = dump_ui(load_ui(first))
        third = dump_ui(load_ui(second))
        self.assertEqual(second, third)
        self.assertIn('name="alpha"', second)
        self.assertIn("<cstring>alpha</cstring>", second)

    def test_unknown_xml_survives(self):
        text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="windowTitle">
   <string>Form</string>
  </property>
  <customnote foo="1">keep</customnote>
 </widget>
 <customwidgets>
  <customwidget>
   <class>Gui::InputField</class>
   <extends>QLineEdit</extends>
   <header>Gui/InputField.h</header>
  </customwidget>
 </customwidgets>
 <resources/>
 <connections/>
</ui>
"""
        first = dump_ui(load_ui(text))
        second = dump_ui(load_ui(first))
        self.assertEqual(first, second)
        self.assertIn("Gui::InputField", second)
        self.assertIn("customnote", second)
        self.assertIn(">keep<", second)


if __name__ == "__main__":
    unittest.main()
