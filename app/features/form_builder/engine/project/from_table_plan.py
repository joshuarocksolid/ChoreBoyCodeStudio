"""What "Form from a table" will create. Qt-free.

The dialog and the search-screen action both build a ``TableRequest``.
``plan_forms`` turns that into one ``FormPlan`` per file. Applying the plan
is ``qtside`` work: this module only decides the record source, the lines,
the list, and the button sentence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from app.features.form_builder.engine.codegen.lookup_plan import suggest_lookup
from app.features.form_builder.engine.data.lines import link_position_unique
from app.features.form_builder.engine.data.schema import Column, Schema, Table
from app.features.form_builder.engine.data.source import (
    DataColumn,
    ListOpen,
    ListSource,
    RecordSource,
    Rows,
    singular,
)
from app.features.form_builder.engine.data.types import describe
from app.features.form_builder.engine.project.table_form import (
    SqliteColumn,
    default_shows_as,
    included_by_default,
    label_from_column,
)

NO_KEY = "%s has no single key column. Record forms need one."


@dataclass(frozen=True)
class ColumnChoice:
    """One mapping row the person left included, with the label they edited."""

    name: str
    shows_as: str
    label: str


@dataclass(frozen=True)
class TableRequest:
    connection: str
    table: str
    columns: Tuple[ColumnChoice, ...]
    make: str
    lines_table: str
    stem: str
    date_format: str
    open_form: str = ""
    lines_link: str = ""


@dataclass(frozen=True)
class FormPlan:
    stem: str
    kind: str
    undo_label: str
    source: object
    columns: Tuple[Column, ...]
    choices: Tuple[ColumnChoice, ...]
    lines: Optional[Rows]
    date_format: str
    placeholder: str


@dataclass(frozen=True)
class PlannedForms:
    forms: Tuple[FormPlan, ...]
    button_text: str
    disabled_reason: str


def include_column(column: Column, key: str, engine: str) -> bool:
    """An integer primary key starts unchecked. Every other column starts included."""

    primary = bool(key) and column.name == key
    if primary:
        kind = describe(column.type, engine=engine, column_name=column.name, nullable=column.nullable)
        if kind.direction == "int":
            return False
    return included_by_default(SqliteColumn(column.name, column.type, primary))


def child_tables(schema: Schema, parent: str) -> Tuple[Table, ...]:
    found = []
    for table in schema.tables:
        if table.name == parent:
            continue
        if any(_points(column, parent) for column in table.columns):
            found.append(table)
    return tuple(found)


def linking_columns(child: Table, parent: str) -> Tuple[Column, ...]:
    """Columns on ``child`` that point at ``parent``. Two of them is ambiguous."""

    return tuple(column for column in child.columns if _points(column, parent))


def position_name(child: Table) -> str:
    names = [column.name for column in child.columns]
    for candidate in ("line_no", "position", "sort"):
        if candidate in names:
            return candidate
    return ""


def default_lines(schema: Schema, parent: str, child: Table) -> bool:
    """Tick Include lines only for a real line table of this parent.

    The link is one column, not null, and either unique together with the
    position or there is no position column. A table other tables hang off
    (an invoice, not its lines) is a record, so it stays unticked.
    """

    links = linking_columns(child, parent)
    if len(links) != 1 or links[0].nullable:
        return False
    position = position_name(child)
    if position:
        return link_position_unique(child.unique_keys, links[0].name, position)
    return not child_tables(schema, child.name)


def button_sentence(table: str, count: int, make: str, lines: bool) -> str:
    """The primary button names the files it will write."""

    word = singular(table) if table else "form"
    unit = "field" if count == 1 else "fields"
    if make == "list":
        unit = "column" if count == 1 else "columns"
        noun = table or "records"
        return "Create %s list with %d %s" % (noun, count, unit)
    text = "Create %s form with %d %s" % (word, count, unit)
    if lines:
        text += " and lines"
    if make == "both":
        text += " and a list"
    return text


def plan_forms(request: TableRequest, schema: Schema) -> PlannedForms:
    table = _table(schema, request.table)
    count = len(request.columns)
    lines = bool(request.lines_table) and request.make != "list"
    sentence = button_sentence(request.table, count, request.make, lines)
    if table is None:
        return PlannedForms((), sentence, "Choose a table")
    key = table.key or ""
    if not key:
        return PlannedForms((), sentence, NO_KEY % request.table)
    if count == 0:
        return PlannedForms((), sentence, "Include at least one column")
    engine = schema.engine if schema.engine in ("sqlite", "postgres") else "sqlite"
    chosen = _chosen(table, request.columns)
    record = _record(request, table, chosen, engine)
    line_rows = (
        _lines(schema, table, request.lines_table, engine, request.lines_link) if lines else None
    )
    forms = []
    if request.make in ("record", "both"):
        forms.append(
            FormPlan(
                request.stem,
                "record",
                sentence,
                record,
                tuple(column for column, _choice in chosen),
                tuple(choice for _column, choice in chosen),
                line_rows,
                request.date_format,
                "",
            )
        )
    if request.make in ("list", "both"):
        list_stem = request.stem if request.make == "list" else request.stem + "_list"
        target = request.open_form or (request.stem if request.make == "both" else "")
        forms.append(
            FormPlan(
                list_stem,
                "list",
                sentence,
                _list(request, table, chosen, engine, target, key),
                tuple(column for column, _choice in chosen),
                tuple(choice for _column, choice in chosen),
                None,
                request.date_format,
                "Search " + request.table.replace("_", " "),
            )
        )
    return PlannedForms(tuple(forms), sentence, "")


def _table(schema: Schema, name: str) -> Optional[Table]:
    for table in schema.tables:
        if table.name == name:
            return table
    return None


def _chosen(table: Table, choices: Sequence[ColumnChoice]) -> Tuple[Tuple[Column, ColumnChoice], ...]:
    by_name = {column.name: column for column in table.columns}
    paired = []
    for choice in choices:
        column = by_name.get(choice.name)
        if column is not None:
            paired.append((column, choice))
    return tuple(paired)


def _record(request: TableRequest, table: Table, chosen: Sequence[Tuple[Column, ColumnChoice]], engine: str) -> RecordSource:
    return RecordSource(
        request.connection,
        table.name,
        table.key or "",
        record_word=singular(table.name),
        search=tuple(column.name for column, _choice in chosen if _text(column, engine)),
    )


def _list(
    request: TableRequest,
    table: Table,
    chosen: Sequence[Tuple[Column, ColumnChoice]],
    engine: str,
    target: str,
    key: str,
) -> ListSource:
    names = tuple(choice.name for _column, choice in chosen)
    search = tuple(column.name for column, _choice in chosen if _text(column, engine))
    order = ((names[0], "asc"),) if names else ()
    opened = ListOpen(target, key) if target and key else None
    return ListSource(
        request.connection,
        names,
        table=table.name,
        search=search,
        search_field="searchEdit",
        order=order,
        limit=500,
        open=opened,
    )


def _lines(schema: Schema, parent: Table, child_name: str, engine: str, link_name: str = "") -> Optional[Rows]:
    del engine
    child = _table(schema, child_name)
    if child is None:
        return None
    links = linking_columns(child, parent.name)
    chosen = None
    if link_name:
        for column in links:
            if column.name == link_name:
                chosen = column
                break
    elif len(links) == 1:
        chosen = links[0]
    if chosen is None:
        return None
    link = chosen.name
    key = child.key or ("rowid" if schema.engine == "sqlite" else "")
    if not key:
        return None
    stored_position = position_name(child)
    renumber = bool(stored_position) and link_position_unique(child.unique_keys, link, stored_position)
    position = stored_position if renumber else ""
    order = stored_position or key
    columns = []
    for column in child.columns:
        if column.name in (key, link, stored_position):
            continue
        lookup = None
        ref = getattr(column.references, "table", "") if column.references is not None else ""
        if ref and ref != parent.name:
            lookup = suggest_lookup(column, schema.tables)
        columns.append(DataColumn(column.name, _header(column.name), "", lookup))
    if not columns:
        return None
    return Rows(child.name, link, key, tuple(columns), order, position)


def _text(column: Column, engine: str) -> bool:
    kind = describe(column.type, engine=engine, column_name=column.name, nullable=column.nullable)
    return kind.direction == "text"


def _points(column: Column, parent: str) -> bool:
    ref = column.references
    return ref is not None and ref.table == parent


def _header(name: str) -> str:
    return label_from_column(name)


def choice_for(column: Column, engine: str) -> ColumnChoice:
    """The label and widget a column starts with. ``engine`` selects the type table."""

    del engine
    shows = "QComboBox" if column.references is not None and column.references.table else default_shows_as(column.type)
    return ColumnChoice(column.name, shows, label_from_column(column.name))
