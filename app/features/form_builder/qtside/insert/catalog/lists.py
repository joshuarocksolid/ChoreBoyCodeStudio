"""UX-CAT-002: Lists and tables."""

from __future__ import annotations

from typing import Callable, Tuple

from app.features.form_builder.engine.ui4.spec import Fragment
from app.features.form_builder.qtside.insert.catalog._build import fragment, header_column, leaf_entry, widget
from app.features.form_builder.qtside.insert.catalog._model import WIDGET, Entry, Registry

CATEGORY = "Lists and tables"


def _tree_widget() -> Callable[[], Fragment]:
    def build() -> Fragment:
        return fragment(widget("QTreeWidget", "treeWidget", columns=(header_column("Name"),)))

    return build


def entries() -> Tuple[Entry, ...]:
    tree = Entry(
        "QTreeWidget", "Tree widget", "QTreeWidget", CATEGORY, "treeWidget",
        "Rows that fold open, typed here.", ("tree", "hierarchy", "folders"), "tree_widget",
        WIDGET, _tree_widget(),
    )
    return (
        leaf_entry("QListWidget", "List widget", "QListWidget", CATEGORY, "listWidget",
                   "A list of rows you type here.", ("list", "listbox"), "list_widget"),
        tree,
        leaf_entry("QTableWidget", "Table widget", "QTableWidget", CATEGORY, "tableWidget",
                   "A grid of cells you type here.", ("table", "spreadsheet", "cells"), "table_widget"),
        leaf_entry("QListView", "List view", "QListView", CATEGORY, "listView",
                   "A list your code fills from a model.", ("list", "listbox"), "list_view"),
        leaf_entry("QTreeView", "Tree view", "QTreeView", CATEGORY, "treeView",
                   "A tree your code fills from a model.", ("tree", "hierarchy", "folders"), "tree_view"),
        leaf_entry("QTableView", "Table view", "QTableView", CATEGORY, "tableView",
                   "A table your code fills from a model.", ("table", "spreadsheet", "cells"), "table_view"),
        leaf_entry("QColumnView", "Column view", "QColumnView", CATEGORY, "columnView",
                   "Columns that drill down, filled by your code.", ("columns", "drill down"), "column_view"),
        leaf_entry("QUndoView", "Undo view", "QUndoView", CATEGORY, "undoView",
                   "Shows the steps of an undo stack from your code.", ("undo", "history"), "undo_view"),
    )


def register(registry: Registry) -> None:
    for entry in entries():
        registry.add(entry)

