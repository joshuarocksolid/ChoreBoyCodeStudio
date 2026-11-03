"""List-screen edits. Each public function is one undo step."""

from __future__ import annotations

import os
from dataclasses import replace
from typing import Optional, Sequence

from app.features.form_builder.engine.commands.catalog import SetLogic
from app.features.form_builder.engine.data.source import ListFilter, ListOpen, ListSource, write_data
from app.features.form_builder.qtside.data_panel.model import connections_of


def save_list(session: object, source: ListSource, label: str) -> None:
    with session.log.transaction(label) as txn:
        txn.execute(SetLogic(session.document.root.id, "cbcsData", write_data(source)))


def set_columns(session: object, source: ListSource, columns: Sequence[str]) -> None:
    kept = tuple(column for column in source.search if column in columns)
    save_list(session, replace(source, columns=tuple(columns), search=kept), "Columns shown")


def set_search(session: object, source: ListSource, search: Sequence[str]) -> None:
    save_list(session, replace(source, search=tuple(search)), "Search in")


def set_search_field(session: object, source: ListSource, field: str) -> None:
    save_list(session, replace(source, search_field=field), "Search box")


def set_filters(session: object, source: ListSource, filters: Sequence[ListFilter]) -> None:
    save_list(session, replace(source, filters=tuple(filters)), "Filters")


def set_order(session: object, source: ListSource, column: str, direction: str) -> None:
    order = ((column, direction),) if column else ()
    save_list(session, replace(source, order=order), "Order by")


def set_limit(session: object, source: ListSource, limit: int) -> None:
    save_list(session, replace(source, limit=limit), "At most %d records" % limit)


def set_open(session: object, source: ListSource, form: str, key: str) -> None:
    opened = ListOpen(form, key) if form and key else None
    label = "Opens %s" % form if form else "Opens"
    save_list(session, replace(source, open=opened), label)


def set_own_sql(session: object, source: ListSource, sql: str, columns: Sequence[str]) -> None:
    shown = tuple(columns) if columns else source.columns
    search = tuple(column for column in source.search if column in shown)
    save_list(
        session,
        replace(source, sql=sql, columns=shown, search=search),
        "Use my own SQL",
    )


def clear_own_sql(session: object, source: ListSource) -> None:
    save_list(session, replace(source, sql=""), "Use the table")


def connection_named(session: object, name: str, host: object = None) -> Optional[object]:
    for item in connections_of(session, host):
        if item.name == name:
            return item
    return None


def form_stems(root: str) -> tuple:
    folder = os.path.join(root, "forms")
    if not os.path.isdir(folder):
        return ()
    names = []
    for entry in sorted(os.listdir(folder)):
        if entry.endswith(".ui"):
            names.append(entry[:-3])
    return tuple(names)
