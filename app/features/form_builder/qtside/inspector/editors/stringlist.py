"""String list row (UX-PED-043).

The summary is "3 items: Red, Green, Blue" or "No items". The popover is the
shared list editor plus one Translation disclosure for the whole list.
"""

from __future__ import annotations

from typing import Optional

from app.features.form_builder.engine.ui4.values import StringListValue
from app.features.form_builder.qtside.inspector.api import (
    EditorHost,
    EditorKey,
    Mixed,
    Registrar,
    RowValue,
    Written,
)
from app.features.form_builder.qtside.inspector.editors._list_editor import ListEditor, summarize
from app.features.form_builder.qtside.inspector.editors._popover import RowPopover, SummaryButton
from app.features.form_builder.qtside.inspector.editors._translation import TranslationDisclosure
from app.features.form_builder.qtside.inspector.translatable import shows_translation
from app.qt.QtWidgets import QWidget


def _change_label(label: str) -> str:
    if not label:
        return "Change value"
    return "Change " + label[0].lower() + label[1:]


def _translation_label(label: str) -> str:
    if not label:
        return "Change translation of value"
    return "Change translation of " + label[0].lower() + label[1:]


class StringListEditor:
    def __init__(self, spec: object, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._value = StringListValue(())
        self._mixed = False
        self._popover: Optional[RowPopover] = None
        self._button = SummaryButton(host.label, parent)
        self._button.set_opener(self._open)

    @property
    def widget(self) -> QWidget:
        return self._button

    def show(self, value: RowValue) -> None:
        self._value = _value_of(value)
        self._mixed = isinstance(value, Mixed)
        text = "Mixed" if isinstance(value, Mixed) else summarize(self._value.items)
        self._button.set_row_label(self._host.label)
        self._button.set_summary(text)

    def _open(self) -> None:
        if self._popover is not None and not self._popover.closed:
            return
        popover = RowPopover(
            self._host.row_widget,
            self._host,
            row_label=self._host.label,
            session_label=_change_label(self._host.label),
            qt_name=self._host.qt_name,
            anchor=self._button,
        )
        self._popover = popover
        editor = ListEditor(name=self._host.label or "List")
        editor.set_texts(self._value.items)
        editor.set_on_texts(self._commit_items)
        editor.set_on_close(popover.done)
        editor.set_on_revert(popover.revert)
        popover.body().addWidget(editor)
        if not self._mixed and shows_translation(self._host.qt_name, StringListValue.ELEMENT):
            disclosure = TranslationDisclosure()
            names = getattr(self._host, "qt_names", None)
            disclosure.set_values(
                notr=self._value.notr,
                comment=self._value.comment,
                extracomment=self._value.extracomment,
                ident=self._value.id,
                show_id=bool(names()) if callable(names) else False,
            )
            disclosure.set_on_change(self._commit_attr)
            popover.body().addWidget(disclosure)
        popover.open_popover()

    def _commit_items(self, items: tuple) -> None:
        self._value = StringListValue(
            tuple(items),
            self._value.notr,
            self._value.comment,
            self._value.extracomment,
            self._value.id,
        )
        if self._popover is not None:
            self._host.commit(self._value, session=self._popover.session)

    def _commit_attr(self, field: str, raw: object) -> None:
        current = self._value
        updated = StringListValue(
            current.items,
            raw if field == "notr" else current.notr,  # type: ignore[arg-type]
            raw if field == "comment" else current.comment,  # type: ignore[arg-type]
            raw if field == "extracomment" else current.extracomment,  # type: ignore[arg-type]
            raw if field == "id" else current.id,  # type: ignore[arg-type]
        )
        self._value = updated
        session = self._host.begin_session(_translation_label(self._host.label))
        self._host.commit(updated, session=session)
        session.close()


def _value_of(value: RowValue) -> StringListValue:
    if isinstance(value, Written) and isinstance(value.value, StringListValue):
        return value.value
    return StringListValue(())


def register(registrar: Registrar) -> None:
    registrar.editor(EditorKey(StringListValue.ELEMENT), StringListEditor)
