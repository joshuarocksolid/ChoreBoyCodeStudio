"""Grab every state the owner should see. Offscreen, then read the PNGs back.

Run:  QT_QPA_PLATFORM=offscreen <FreeCAD python> spikes/form_builder/screenshots_capture.py [name ...]

Overlays and popups are separate widgets (and popups are separate windows), so
each grab is the window plus every visible overlay and popup painted on top at
its real position.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = Path(__file__).resolve().parent / "screenshots"
SIZE = (1440, 880)


def settle(app, rounds: int = 4):
    from PySide6.QtCore import QCoreApplication, QEvent

    for _ in range(rounds):
        QCoreApplication.sendPostedEvents(None, QEvent.LayoutRequest)
        app.processEvents()


def grab(window, name: str, popups=(), crop=None) -> None:
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QPainter
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    settle(app)
    image = window.grab().toImage()
    painter = QPainter(image)
    canvas = getattr(window, "canvas", None)
    if canvas is not None and window.stack.currentWidget() is window.work:
        for surface in canvas.surfaces():
            if surface.isVisible():
                surface.overlay.repaint()
                painter.drawImage(surface.overlay.mapTo(window, QPoint(0, 0)), surface.overlay.grab().toImage())
                if surface.editor.isVisible():
                    painter.drawImage(surface.editor.mapTo(window, QPoint(0, 0)), surface.editor.grab().toImage())
        if window.toast.isVisible():
            painter.drawImage(window.toast.mapTo(window, QPoint(0, 0)), window.toast.grab().toImage())
    for popup in popups:
        offset = popup.mapToGlobal(QPoint(0, 0)) - window.mapToGlobal(QPoint(0, 0))
        painter.drawImage(offset, popup.grab().toImage())
    painter.end()
    if crop is not None:
        image = image.copy(*crop)
    path = OUT / name
    image.save(str(path))
    print(f"{name} {image.width()}x{image.height()}")


def find(doc, name):
    from spikes.form_builder.model import iter_nodes

    for node in iter_nodes(doc):
        if getattr(node, "object_name", None) == name or getattr(node, "name", None) == name:
            return node
    raise KeyError(name)


def point_between(surface, first_id, second_id):
    """Host point halfway between two widgets."""
    from PySide6.QtCore import QPoint

    a = surface.index.rect_of[first_id]
    b = surface.index.rect_of[second_id]
    return QPoint((a.center().x() + b.center().x()) // 2, (a.bottom() + b.top()) // 2)


def demo_box_doc():
    from spikes.form_builder.model import blank_widget, make_item, make_layout, make_spacer, make_widget, prop_string, set_property

    doc = blank_widget("QWidget", "Settings")
    set_property(doc.root, prop_string("windowTitle", "Settings"), "windowTitle")
    outer = make_layout(doc, "QVBoxLayout", "verticalLayout")
    doc.root.body.append(outer)
    title = make_widget(doc, "QLabel", "heading")
    title.body.append(prop_string("text", "Shop settings"))
    name = make_widget(doc, "QLineEdit", "shopName")
    name.body.append(prop_string("placeholderText", "Shop name"))
    group = make_widget(doc, "QGroupBox", "receiptGroup")
    group.body.append(prop_string("title", "Receipts"))
    inner = make_layout(doc, "QHBoxLayout", "receiptRow")
    group.body.append(inner)
    for text, obj in (("Print a copy", "printCopy"), ("Email it", "emailIt")):
        box = make_widget(doc, "QCheckBox", obj)
        box.body.append(prop_string("text", text))
        inner.body.append(make_item(doc, box))
    save = make_widget(doc, "QPushButton", "saveButton")
    save.body.append(prop_string("text", "Save settings"))
    for widget in (title, name, group):
        outer.body.append(make_item(doc, widget))
    outer.body.append(make_item(doc, make_spacer(doc, "Qt::Vertical")))
    outer.body.append(make_item(doc, save))
    return doc


def demo_grid_doc():
    from spikes.form_builder.model import blank_widget, make_item, make_layout, make_widget, prop_string, set_property

    doc = blank_widget("QWidget", "Keypad")
    set_property(doc.root, prop_string("windowTitle", "Quantities"), "windowTitle")
    grid = make_layout(doc, "QGridLayout", "gridLayout")
    doc.root.body.append(grid)
    for text, row, col in (("Small", 0, 0), ("Medium", 0, 1), ("Large", 1, 0)):
        button = make_widget(doc, "QPushButton", text.lower() + "Button")
        button.body.append(prop_string("text", text))
        grid.body.append(make_item(doc, button, row=str(row), column=str(col)))
    return doc


def main(only=()) -> None:
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QApplication

    from spikes.form_builder.screens import TableDialog, blank_page
    from spikes.form_builder.templates import blank_main_window, data_entry
    from spikes.form_builder.theme import ensure_style
    from spikes.form_builder.window import MainWindow, WrapPopover

    OUT.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    ensure_style(app)
    window = MainWindow("light")
    window.resize(*SIZE)
    window.show()
    settle(app)

    def want(name):
        return not only or name in only

    if want("start"):
        grab(window, "start.png")

    if want("from-table"):
        dialog = TableDialog(window)
        dialog.show()
        settle(app)
        dialog.tables.setCurrentRow(1)
        settle(app)
        dialog.preview._fit()
        grab(dialog, "from-table.png")
        dialog.hide()

    if want("workbench-light") or want("inspector-size"):
        window.load_document(data_entry(), None)
        settle(app)
        window._select([find(window.doc, "name").id])
        settle(app)
        grab(window, "workbench-light.png")
        scroll = window.inspector.scrolls[0]
        size_section = next((child for child in scroll.widget().children() if getattr(child, "key", "") == "size"), None)
        if size_section is not None:
            scroll.verticalScrollBar().setValue(size_section.y())
        settle(app)
        grab(window, "inspector-size.png", crop=(SIZE[0] - 520, 0, 520, SIZE[1]))

    if want("empty-form"):
        window.load_document(blank_page(), None)
        settle(app)
        grab(window, "empty-form.png")

    if want("drag-box"):
        window.load_document(demo_box_doc(), None)
        settle(app)
        doc = window.doc
        surface = window.canvas.primary
        surface.rebuild_index()
        pos = point_between(surface, find(doc, "shopName").id, find(doc, "receiptGroup").id)
        surface.overlay.slot = surface.slot_at(pos, "QComboBox")
        window._hint(surface.overlay.slot.label)
        grab(window, "drag-box.png")
        surface.overlay.slot = None

    if want("layout-selected"):
        window.load_document(demo_box_doc(), None)
        settle(app)
        doc = window.doc
        window._select([find(doc, "receiptGroup").id])
        settle(app)
        surface = window.canvas.primary
        surface.rebuild_index()
        gaps = surface.gaps(surface.index.layouts[find(doc, "receiptRow").id])
        if gaps:
            surface.overlay.gap_hover = gaps[0]
        grab(window, "layout-selected.png")
        surface.overlay.gap_hover = None

    if want("inspector-behavior"):
        window.load_document(demo_box_doc(), None)
        settle(app)
        window._select([find(window.doc, "saveButton").id])
        window.inspector.show_tab("behavior")
        settle(app)
        grab(window, "inspector-behavior.png", crop=(SIZE[0] - 520, 0, 520, SIZE[1]))
        window.inspector.show_tab("data")
        settle(app)
        grab(window, "inspector-data.png", crop=(SIZE[0] - 520, 0, 520, SIZE[1]))
        window.inspector.show_tab("properties")

    if want("empty-group"):
        from spikes.form_builder.canvas import content_for
        from spikes.form_builder.catalog import CATALOG
        from spikes.form_builder.commands import insert_near

        window.load_document(demo_box_doc(), None)
        settle(app)
        entry = next(item for item in CATALOG if item.class_name == "QGroupBox")
        content = content_for(window.doc, entry)
        window.history.execute(insert_near(window.doc, [find(window.doc, "receiptGroup").id], content))
        window._select([content.id])
        settle(app)
        surface = window.canvas.primary
        surface.rebuild_index()
        surface.overlay.hover = find(window.doc, "shopName").id
        grab(window, "empty-group.png")
        surface.overlay.hover = None

    if want("drag-grid"):
        window.load_document(demo_grid_doc(), None)
        settle(app)
        doc = window.doc
        surface = window.canvas.primary
        surface.rebuild_index()
        large = surface.index.rect_of[find(doc, "largeButton").id]
        medium = surface.index.rect_of[find(doc, "mediumButton").id]
        surface.overlay.slot = surface.slot_at(QPoint(medium.center().x(), large.center().y()), "QPushButton")
        window._hint(surface.overlay.slot.label)
        grab(window, "drag-grid.png")
        surface.overlay.slot = None

    if want("drag-form"):
        window.load_document(data_entry(), None)
        settle(app)
        doc = window.doc
        surface = window.canvas.primary
        surface.rebuild_index()
        email = surface.index.rect_of[find(doc, "email").id]
        notes = surface.index.rect_of[find(doc, "notes").id]
        pos = QPoint(email.center().x(), (email.bottom() + notes.top()) // 2 + 1)
        surface.overlay.slot = surface.slot_at(pos, "QLineEdit")
        window._hint(surface.overlay.slot.label)
        grab(window, "drag-form.png")
        surface.overlay.slot = None

    if want("wrap-menu"):
        window.load_document(demo_box_doc(), None)
        settle(app)
        doc = window.doc
        window._select([find(doc, "heading").id, find(doc, "shopName").id])
        settle(app)
        window.canvas.primary.rebuild_index()
        popover = WrapPopover(window, window._wrap)
        popover.title.setText("Wrap 2 items in…")
        rect = window._selection_global_rect()
        popover.move(rect.bottomLeft() + QPoint(0, 30))
        popover.show()
        settle(app)
        grab(window, "wrap-menu.png", popups=[popover])
        popover.close()

    if want("tab-order"):
        window.load_document(data_entry(), None)
        settle(app)
        window.set_mode("tab")
        window.canvas.primary.overlay.tab_next = 3
        window.canvas.primary.rebuild_index()
        window.canvas.primary.overlay.hover = find(window.doc, "notes").id
        grab(window, "tab-order.png")
        window.canvas.primary.overlay.hover = None
        window.set_mode("design")

    if want("buddy"):
        window.load_document(data_entry(), None)
        settle(app)
        from spikes.form_builder.commands import SetProperty

        window.history.execute(SetProperty(find(window.doc, "label_3").id, "buddy", None))
        settle(app)
        window.set_mode("buddy")
        surface = window.canvas.primary
        surface.rebuild_index()
        notes = surface.index.rect_of[find(window.doc, "notes").id]
        surface.overlay.buddy_drag = (find(window.doc, "label_3").id, notes.center())
        grab(window, "buddy.png")
        surface.overlay.buddy_drag = None
        window.set_mode("design")

    if want("main-window-menu"):
        window.load_document(blank_main_window(), None)
        settle(app)
        surface = window.canvas.primary
        surface.rebuild_index()
        menu = find(window.doc, "menuFile")
        window._select([find(window.doc, "actionQuit").id])
        surface.overlay.menu_open = menu.id
        settle(app)
        surface.rebuild_index()
        _panel, rows = surface.menu_panel(menu.id)
        typehere = next(row for row in rows if row["kind"] == "typehere")
        surface.editor.open(surface.to_view(typehere["rect"]).adjusted(4, 2, -4, -2), "Open…", lambda _text: None, "Action text")
        grab(window, "main-window-menu.png")
        surface.editor.callback = None
        surface.editor.hide()

    if want("two-widths"):
        window.load_document(data_entry(), None)
        settle(app)
        window.top.widths.setChecked(True)
        settle(app)
        grab(window, "two-widths.png")
        window.top.widths.setChecked(False)

    if want("quick-insert"):
        window.load_document(demo_box_doc(), None)
        settle(app)
        window._select([find(window.doc, "shopName").id])
        window.outline.setFocus()
        settle(app)
        window.open_quick_insert()
        window.quick.edit.setText("com")
        settle(app)
        grab(window, "quick-insert.png", popups=[window.quick])
        window.quick.close()

    if want("workbench-dark"):
        window.set_theme("dark")
        window.load_document(data_entry(), None)
        settle(app)
        window._select([find(window.doc, "email").id])
        settle(app)
        grab(window, "workbench-dark.png")
        window.load_document(demo_box_doc(), None)
        settle(app)
        window._select([find(window.doc, "receiptGroup").id])
        settle(app)
        grab(window, "workbench-dark-layout.png")
        window.show_start()
        settle(app)
        grab(window, "start-dark.png")
        window.set_theme("light")


if __name__ == "__main__":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    main(tuple(sys.argv[1:]))
