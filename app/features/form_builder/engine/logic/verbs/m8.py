"""M8 record verbs (CONTRACTS.md section 19.12).

``new`` through ``openRecord`` are typed. ``refreshLookups`` reloads lookup
combos. ``addRow`` and ``deleteRow`` emit the lines methods. ``openRecord``
calls ``cbcs_open_record``; M8.3c defines that method.
"""

from __future__ import annotations

from typing import Any, Tuple

from app.features.form_builder.engine.codegen.literals import py_string
from app.features.form_builder.engine.logic.verbs import FieldSpec, VerbSpec

RECORD_VERBS = frozenset(
    {
        "new",
        "save",
        "delete",
        "revert",
        "reload",
        "first",
        "previous",
        "next",
        "last",
        "find",
        "showAll",
        "refreshLookups",
        "addRow",
        "deleteRow",
        "openRecord",
    }
)

_WORDS = {
    "new": "New record",
    "save": "Save record",
    "delete": "Delete record",
    "revert": "Undo changes",
    "reload": "Reload",
    "first": "First",
    "previous": "Previous",
    "next": "Next",
    "last": "Last",
    "find": "Find",
    "showAll": "Show all",
    "refreshLookups": "Reload lookups",
    "addRow": "Add a line",
    "deleteRow": "Delete the line",
    "openRecord": "Open record form",
}


def _words(label: str) -> Any:
    def words(step: Any, w: Any, is_form: bool = False, target_chain: Tuple[str, ...] = ()) -> str:
        del step, w, is_form, target_chain
        return label

    return words


_CALLS = {
    "new": "cbcs_new",
    "save": "cbcs_save",
    "delete": "cbcs_delete",
    "revert": "cbcs_revert",
    "reload": "cbcs_reload",
    "first": "cbcs_first",
    "previous": "cbcs_previous",
    "next": "cbcs_next",
    "last": "cbcs_last",
    "find": "cbcs_find",
    "showAll": "cbcs_show_all",
}

# LOGIC §4.12. These return False when the step fails or the clerk cancels.
# Find and Show all do not stop the list.
_STOPS = frozenset(
    {
        "cbcs_new",
        "cbcs_save",
        "cbcs_delete",
        "cbcs_revert",
        "cbcs_reload",
        "cbcs_first",
        "cbcs_previous",
        "cbcs_next",
        "cbcs_last",
    }
)


def _validate(taken: Any) -> None:
    del taken


def _validate_open(taken: Any) -> None:
    which = taken.get("which") if isinstance(taken, dict) else None
    if which not in ("new", "selected"):
        from app.features.form_builder.engine.logic.codec import _Refused

        raise _Refused(1, 'an "openRecord" step needs "which" of new or selected')


def _emit(step: Any, ctx: Any) -> Tuple[str, ...]:
    del step, ctx
    return ()


def _emit_refresh(step: Any, ctx: Any) -> Tuple[str, ...]:
    del ctx
    raw = getattr(step, "raw", None)
    value = raw.field("fields") if raw is not None else None
    names = []
    if isinstance(value, tuple):
        for item in value:
            if isinstance(item, str) and item:
                names.append(item)
    if not names:
        return ("self.cbcs_load_lookups()",)
    rendered = ", ".join(py_string(name) for name in names)
    return ("self.cbcs_load_lookups((%s,))" % rendered,)


def _emit_row(method: str):
    def emit(step: Any, ctx: Any) -> Tuple[str, ...]:
        del step, ctx
        return ("self.%s()" % method,)

    return emit


def _emit_call(method: str):
    def emit(step: Any, ctx: Any) -> Tuple[str, ...]:
        del step, ctx
        call = "self.%s()" % method
        if method not in _STOPS:
            return (call,)
        return ("if %s is False:" % call, "    return")

    return emit


def _emit_open(step: Any, ctx: Any) -> Tuple[str, ...]:
    del ctx
    which = _which(step)
    if which not in ("new", "selected"):
        return ("# (openRecord needs new or selected)",)
    return ("self.cbcs_open_record(%s)" % py_string(which),)


def _which(step: Any) -> str:
    raw = getattr(step, "raw", None)
    if raw is not None:
        value = raw.field("which", "")
        return value if isinstance(value, str) else ""
    value = getattr(step, "which", "")
    return value if isinstance(value, str) else ""


def _block(step: Any) -> bool:
    """An untyped record step keeps the whole list from generating."""

    del step
    return True


def _allow(step: Any) -> bool:
    del step
    return False


def _open_words(step: Any, w: Any, is_form: bool = False, target_chain: Tuple[str, ...] = ()) -> str:
    """List buttons say which record they open. A step with no ``which`` stays the short name."""

    del w, is_form, target_chain
    which = _which(step)
    if which == "new":
        return "Open record form (new)"
    if which == "selected":
        return "Open record form (selected)"
    return "Open record form"


def _spec(
    name: str,
    fields: Tuple[FieldSpec, ...] = (),
    *,
    editable: bool,
    emit: Any,
    block: Any,
    validate: Any = None,
    words: Any = None,
) -> VerbSpec:
    return VerbSpec(
        name,
        fields,
        False,
        validate or _validate,
        emit,
        block,
        "records",
        words or _words(_WORDS[name]),
        editable,
    )


def register(registry: Any) -> None:
    add = registry.add
    field = FieldSpec
    for name, method in _CALLS.items():
        add(_spec(name, editable=True, emit=_emit_call(method), block=_allow))
    add(_spec("refreshLookups", (field("fields", "object_name"),), editable=True, emit=_emit_refresh, block=_allow))
    add(_spec("addRow", (field("grid", "object_name", True),), editable=True, emit=_emit_row("_cbcs_add_row"), block=_allow))
    add(_spec("deleteRow", (field("grid", "object_name", False),), editable=True, emit=_emit_row("_cbcs_delete_row"), block=_allow))
    add(
        _spec(
            "openRecord",
            (field("which", "enum", True),),
            editable=True,
            emit=_emit_open,
            block=_allow,
            validate=_validate_open,
            words=_open_words,
        )
    )
