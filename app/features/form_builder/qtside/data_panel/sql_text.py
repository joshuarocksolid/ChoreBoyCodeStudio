"""The five statements Show SQL displays. The text is ``sql.py``'s, not a second renderer."""

from __future__ import annotations

from typing import Any, List, Sequence

from app.features.form_builder.qtside.data_panel.model import (
    dialect_of,
    load_columns,
    order_of,
    record_source,
    record_word,
    writable_columns,
)

_SQL: Any = None
_MISSING = "Show SQL could not be executed."


def load_sql() -> Any:
    """The parallel lane's module, or None while it is still being written."""

    global _SQL
    if _SQL is not None:
        return _SQL
    try:
        from app.features.form_builder.engine.data import sql as module
    except ImportError:
        return None
    _SQL = module
    return module


def statements_for(session: object, host: object = None) -> List[Any]:
    """select keys, load one, insert, update changed, delete. No lookup or line SQL."""

    module = load_sql()
    if module is None:
        raise RuntimeError(_MISSING)
    document = session.document
    source = record_source(document)
    if source is None:
        return []
    dialect = dialect_of(session, source.connection, host)
    table = source.table
    key = source.key
    order = order_of(source)
    noun = record_word(source)
    columns = load_columns(document, source)
    writable = writable_columns(document, source)
    check = source.conflicts in (None, "check")
    made = [
        module.select_keys(dialect, table, key, order),
        module.load_one(dialect, table, columns, key, noun),
        module.insert_row(dialect, table, writable, key),
        module.update_changed(dialect, table, key, writable, writable, check),
        module.delete_row(dialect, table, key),
    ]
    return made


def render(statements: Sequence[Any]) -> str:
    blocks = []
    for statement in statements:
        caption = str(getattr(statement, "caption", "") or "")
        text = str(getattr(statement, "text", "") or "")
        blocks.append("%s\n%s" % (caption, text) if caption else text)
    return "\n\n".join(blocks)


def sql_text(session: object, host: object = None) -> str:
    try:
        return render(statements_for(session, host))
    except RuntimeError as exc:
        return str(exc)
    except Exception as exc:
        return "%s\n%s" % (_MISSING, exc)


def missing_sentence() -> str:
    return _MISSING
