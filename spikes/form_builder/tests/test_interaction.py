"""Gestures driven through real input events on the overlay, outline, and keyboard.

These check behaviour (what lands in the document), not pixels.
"""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from spikes.form_builder.model import get_property, item_content, iter_widgets, layout_items, widget_layout
from spikes.form_builder.screenshots_capture import demo_box_doc, settle
from spikes.form_builder.templates import blank_main_window, data_entry

APP = QApplication.instance() or QApplication([])


def _named(doc, name):
    return next(widget for widget in iter_widgets(doc) if widget.object_name == name)


def _mouse(widget, kind, pos, buttons=Qt.LeftButton, modifiers=Qt.NoModifier):
    button = Qt.LeftButton if kind != QEvent.MouseMove else Qt.NoButton
    event = QMouseEvent(kind, QPointF(pos), QPointF(widget.mapToGlobal(pos)), button, buttons, modifiers)
    QApplication.sendEvent(widget, event)


class InteractionTest(unittest.TestCase):
    def setUp(self):
        from spikes.form_builder.window import MainWindow

        self.window = MainWindow("light")
        self.window.resize(1400, 860)
        self.window.show()
        settle(APP)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        settle(APP)

    def load(self, doc):
        self.window.load_document(doc, None)
        settle(APP)
        self.surface = self.window.canvas.primary
        self.surface.rebuild_index()
        return self.window.doc

    def view_point(self, node_id, dx=0.5, dy=0.5) -> QPoint:
        rect = self.surface.to_view(self.surface.index.rect_of[node_id])
        return QPoint(int(rect.left() + rect.width() * dx), int(rect.top() + rect.height() * dy))

    def click(self, pos, modifiers=Qt.NoModifier):
        overlay = self.surface.overlay
        _mouse(overlay, QEvent.MouseButtonPress, pos, modifiers=modifiers)
        _mouse(overlay, QEvent.MouseButtonRelease, pos, buttons=Qt.NoButton, modifiers=modifiers)
        settle(APP)

    def drag(self, start, end, modifiers=Qt.NoModifier, steps=6):
        overlay = self.surface.overlay
        _mouse(overlay, QEvent.MouseButtonPress, start, modifiers=modifiers)
        for step in range(1, steps + 1):
            point = start + (end - start) * step / steps
            _mouse(overlay, QEvent.MouseMove, point, buttons=Qt.LeftButton, modifiers=modifiers)
        _mouse(overlay, QEvent.MouseButtonRelease, end, buttons=Qt.NoButton, modifiers=modifiers)
        settle(APP)
        self.surface.rebuild_index()

    def names(self, layout):
        return [getattr(item_content(item), "object_name", None) or getattr(item_content(item), "name", "") for item in layout_items(layout)]

    def test_click_selects_and_drag_reorders_in_a_box(self):
        doc = self.load(demo_box_doc())
        save = _named(doc, "saveButton")
        heading = _named(doc, "heading")
        self.click(self.view_point(save.id))
        self.assertEqual(self.window.canvas.selection, [save.id])
        self.assertEqual(self.window.outline.selected_ids(), [save.id])
        self.drag(self.view_point(save.id), self.view_point(heading.id, dy=0.2))
        self.assertEqual(self.names(widget_layout(doc.root))[0], "saveButton")
        self.window.undo()
        self.assertEqual(self.names(widget_layout(doc.root))[-1], "saveButton")

    def test_alt_drag_copies(self):
        doc = self.load(demo_box_doc())
        name = _named(doc, "shopName")
        save = _named(doc, "saveButton")
        self.click(self.view_point(name.id))
        self.drag(self.view_point(name.id), self.view_point(save.id, dy=0.9), modifiers=Qt.AltModifier)
        names = self.names(widget_layout(doc.root))
        self.assertIn("shopName", names)
        self.assertIn("shopName_2", names)

    def test_gap_drag_sets_spacing(self):
        doc = self.load(demo_box_doc())
        group = _named(doc, "receiptGroup")
        self.click(self.view_point(group.id, dy=0.9))
        self.assertEqual(self.window.canvas.selection, [group.id])
        inner = widget_layout(group)
        gap = self.surface.gaps(self.surface.index.layouts[inner.id])[0]
        start = self.surface.to_view(gap["rect"]).center().toPoint()
        self.drag(start, start + QPoint(14, 0))
        spacing = get_property(inner, "spacing")
        self.assertIsNotNone(spacing)
        self.assertEqual(int(spacing.body.text) % 4, 0, "plain drags snap to 4 px")
        self.assertGreater(int(spacing.body.text), 6)

    def test_resize_handle_writes_fixed_width_and_double_click_hugs(self):
        doc = self.load(demo_box_doc())
        save = _named(doc, "saveButton")
        self.click(self.view_point(save.id))
        rect = self.surface.to_view(self.surface.index.rect_of[save.id])
        handle = QPoint(int(rect.right()), int(rect.center().y()))
        self.drag(handle, handle - QPoint(300, 0))
        low = get_property(save, "minimumSize")
        high = get_property(save, "maximumSize")
        self.assertIsNotNone(low)
        self.assertEqual(low.body.children[0].text, high.body.children[0].text)
        rect = self.surface.to_view(self.surface.index.rect_of[save.id])
        handle = QPoint(int(rect.right()), int(rect.center().y()))
        _mouse(self.surface.overlay, QEvent.MouseButtonDblClick, handle)
        settle(APP)
        self.assertIsNone(get_property(save, "minimumSize"))
        self.assertEqual(get_property(save, "sizePolicy").body.attrib["hsizetype"], "Fixed")

    def test_tab_mode_click_sets_next_stop_and_escape_leaves(self):
        doc = self.load(data_entry())
        self.window.set_mode("tab")
        self.click(self.view_point(_named(doc, "notes").id))
        from spikes.form_builder.model import tabstops_of

        self.assertEqual(tabstops_of(doc).names[0], "notes")
        QTest.keyClick(self.surface, Qt.Key_Escape)
        settle(APP)
        self.assertEqual(self.window.canvas.mode, "design")

    def test_buddy_drag(self):
        doc = self.load(data_entry())
        label = _named(doc, "label_3")
        label.body = [part for part in label.body if getattr(part, "name", "") != "buddy"]
        self.window.set_mode("buddy")
        self.drag(self.view_point(label.id), self.view_point(_named(doc, "email").id))
        self.assertEqual(get_property(label, "buddy").body.text, "email")

    def test_type_here_adds_a_menu_action(self):
        doc = self.load(blank_main_window())
        menu = _named(doc, "menuFile")
        title = next(rect for rect, owner, _text in self.surface.index.menubar[2] if owner == menu.id)
        self.click(self.surface.to_view(title).center().toPoint())
        self.assertEqual(self.surface.overlay.menu_open, menu.id)
        _panel, rows = self.surface.menu_panel(menu.id)
        typehere = next(row for row in rows if row["kind"] == "typehere")
        self.click(self.surface.to_view(typehere["rect"]).center().toPoint())
        self.assertTrue(self.surface.editor.isVisible())
        QTest.keyClicks(self.surface.editor, "Save As")
        QTest.keyClick(self.surface.editor, Qt.Key_Return)
        settle(APP)
        refs = [part.name for part in menu.body if part.__class__.__name__ == "ActionRef"]
        self.assertIn("actionSaveAs", refs)

    def test_double_click_edits_text_in_place(self):
        doc = self.load(demo_box_doc())
        save = _named(doc, "saveButton")
        _mouse(self.surface.overlay, QEvent.MouseButtonDblClick, self.view_point(save.id))
        settle(APP)
        editor = self.surface.editor
        self.assertTrue(editor.isVisible())
        editor.selectAll()
        QTest.keyClicks(editor, "Apply")
        QTest.keyClick(editor, Qt.Key_Return)
        settle(APP)
        self.assertEqual(get_property(save, "text").body.text, "Apply")

    def test_outline_rename_keeps_the_keyboard(self):
        doc = self.load(demo_box_doc())
        outline = self.window.outline
        name = _named(doc, "shopName")
        self.window._select([name.id])
        outline.setFocus()
        settle(APP)
        QTest.keyClick(outline, Qt.Key_F2)
        settle(APP)
        editor = outline.focusWidget()
        self.assertIsNotNone(editor)
        editor.selectAll()
        QTest.keyClicks(editor, "shopTitle")
        QTest.keyClick(editor, Qt.Key_Return)
        settle(APP)
        self.assertEqual(name.object_name, "shopTitle")
        self.assertTrue(outline.hasFocus(), "after rename the outline still has the keyboard")
        self.assertEqual(outline.selected_ids(), [name.id])

    def test_quick_insert_lands_after_selection_and_is_selected(self):
        doc = self.load(demo_box_doc())
        name = _named(doc, "shopName")
        self.window._select([name.id])
        self.window.open_quick_insert()
        QTest.keyClicks(self.window.quick.edit, "combo")
        QTest.keyClick(self.window.quick.edit, Qt.Key_Return)
        settle(APP)
        names = self.names(widget_layout(doc.root))
        self.assertEqual(names[names.index("shopName") + 1], "comboBox")
        self.assertEqual(self.window.canvas.selection, [_named(doc, "comboBox").id])

    def test_wrap_with_keyboard_and_unwrap(self):
        doc = self.load(demo_box_doc())
        ids = [_named(doc, "heading").id, _named(doc, "shopName").id]
        self.window._select(ids)
        self.window._wrap("QWidget", "QHBoxLayout")
        container = self.window.canvas.selection[0]
        self.assertEqual(self.names(widget_layout(doc.root))[0], _named_id(doc, container).object_name)
        self.window.unwrap_selection()
        self.assertEqual(self.names(widget_layout(doc.root))[:2], ["heading", "shopName"])

    def test_delete_then_undo_keeps_selection_sane(self):
        doc = self.load(demo_box_doc())
        save = _named(doc, "saveButton")
        self.window._select([save.id])
        self.window.delete_selection()
        self.assertNotIn("saveButton", self.names(widget_layout(doc.root)))
        self.window.undo()
        self.assertIn("saveButton", self.names(widget_layout(doc.root)))

    def test_page_edge_drag_writes_window_size(self):
        doc = self.load(demo_box_doc())
        page = self.surface.index.page.adjusted(8, 8, -8, -8)
        edge = self.surface.to_view_point(QPoint(page.right(), page.center().y())).toPoint()
        self.drag(edge, edge + QPoint(40, 0))
        geometry = get_property(doc.root, "geometry")
        width = int(next(child.text for child in geometry.body.children if child.tag == "width"))
        self.assertEqual(width, 640 + 80, "the page grows from its centre, so the edge moves half the change")


def _named_id(doc, node_id):
    return next(widget for widget in iter_widgets(doc) if widget.id == node_id)


if __name__ == "__main__":
    unittest.main()
