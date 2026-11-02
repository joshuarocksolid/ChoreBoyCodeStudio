"""M8 record verbs, registered read-only (CONTRACTS.md section 19.1 and 19.12).

They stay out of the typed-verb set (``editable`` is false) so a file that
already contains one is kept and reported as FB403. The lane that types a verb
replaces that entry. This module does not emit them.
"""

from __future__ import annotations

from typing import Any, Tuple

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


def _validate(taken: Any) -> None:
    del taken


def _emit(step: Any, ctx: Any) -> Tuple[str, ...]:
    del step, ctx
    return ()


def _block(step: Any) -> bool:
    """An untyped record step keeps the whole list from generating, as an unknown verb does."""

    del step
    return True


def _spec(name: str, fields: Tuple[FieldSpec, ...] = ()) -> VerbSpec:
    return VerbSpec(
        name,
        fields,
        False,
        _validate,
        _emit,
        _block,
        "records",
        _words(_WORDS[name]),
        False,
    )


def register(registry: Any) -> None:
    add = registry.add
    field = FieldSpec
    for name in (
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
    ):
        add(_spec(name))
    add(_spec("refreshLookups", (field("fields", "object_name"),)))
    add(_spec("addRow", (field("grid", "object_name", True),)))
    add(_spec("deleteRow"))
    add(_spec("openRecord", (field("which", "enum", True),)))
