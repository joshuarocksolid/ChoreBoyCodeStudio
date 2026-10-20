"""Build the sample database and the 300-widget form."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spikes.form_builder.model import (
    blank_widget,
    make_item,
    make_layout,
    make_widget,
    prop_string,
    set_attribute,
)
from spikes.form_builder.xmlio import save_path

ROOT = Path(__file__).resolve().parent


def shop_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT,
            notes TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            since DATE
        );
        CREATE TABLE invoices (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            number TEXT NOT NULL,
            total REAL,
            paid INTEGER NOT NULL DEFAULT 0,
            issued DATE,
            notes TEXT
        );
        INSERT INTO customers (name, email, notes, is_active, since) VALUES
            ('North Mill', 'hello@northmill.example', 'Standing order', 1, '2024-03-01'),
            ('Cedar Grove', 'ap@cedargrove.example', '', 0, '2025-11-12');
        INSERT INTO invoices (customer_id, number, total, paid, issued, notes) VALUES
            (1, '1001', 240.50, 1, '2026-01-15', 'Net 30'),
            (2, '1002', 80, 0, '2026-02-02', '');
        """
    )
    connection.commit()
    connection.close()


def big_form():
    doc = blank_widget("QWidget", "BigForm")
    tabs = make_widget(doc, "QTabWidget", "pages")
    for page_index in range(6):
        page = make_widget(doc, "QWidget", f"page{page_index + 1}")
        set_attribute(page, "title", f"Page {page_index + 1}")
        outer = make_layout(doc, "QVBoxLayout", f"pageLayout{page_index + 1}")
        page.body.append(outer)
        group = make_widget(doc, "QGroupBox", f"group{page_index + 1}")
        group.body.append(prop_string("title", f"Group {page_index + 1}"))
        if page_index % 2 == 0:
            form = make_layout(doc, "QFormLayout", f"form{page_index + 1}")
            group.body.append(form)
            for row in range(24):
                field = make_widget(doc, "QLineEdit", f"p{page_index + 1}f{row + 1}")
                field.body.append(prop_string("placeholderText", f"Field {row + 1}"))
                label = make_widget(doc, "QLabel", f"p{page_index + 1}l{row + 1}")
                label.body.append(prop_string("text", f"Field {row + 1}"))
                form.body.append(make_item(doc, label, row=str(row), column="0"))
                form.body.append(make_item(doc, field, row=str(row), column="1"))
        else:
            grid = make_layout(doc, "QGridLayout", f"grid{page_index + 1}")
            group.body.append(grid)
            for row in range(12):
                for column in range(4):
                    field = make_widget(doc, "QLineEdit", f"p{page_index + 1}c{row}_{column}")
                    grid.body.append(make_item(doc, field, row=str(row), column=str(column)))
        outer.body.append(make_item(doc, group))
        tabs.body.append(page)
    root_layout = make_layout(doc, "QVBoxLayout", "verticalLayout")
    doc.root.body.append(root_layout)
    root_layout.body.append(make_item(doc, tabs))
    return doc


def main() -> None:
    from spikes.form_builder.model import iter_widgets

    shop_database(ROOT / "shop.sqlite")
    doc = big_form()
    save_path(doc, str(ROOT / "big_form.ui"))
    print(sum(1 for _ in iter_widgets(doc)))


if __name__ == "__main__":
    main()
