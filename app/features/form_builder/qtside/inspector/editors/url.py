"""URL row (UX-PED-046).

The field shows the address. A value with no scheme still writes, and the
caption says it does not look like a web or file address. Translation edits
the inner string.
"""

from __future__ import annotations

from typing import Optional

from app.features.form_builder.engine.ui4.values import StringValue, UrlValue
from app.features.form_builder.qtside.inspector.api import (
    MIXED_TEXT,
    NOT_SET_TEXT,
    EditorHost,
    EditorKey,
    Mixed,
    Registrar,
    RowValue,
    Unset,
    Written,
    mark,
)
from app.features.form_builder.qtside.inspector.editors._translation import TranslationDisclosure
from app.features.form_builder.qtside.inspector.translatable import shows_translation
from app.qt.QtWidgets import QLabel, QLineEdit, QSizePolicy, QVBoxLayout, QWidget

_WARNING = "This doesn't look like a web or file address."


def _translation_label(label: str) -> str:
    if not label:
        return "Change translation of value"
    return "Change translation of " + label[0].lower() + label[1:]


def _ignore_width(widget: QWidget) -> None:
    policy = getattr(QSizePolicy, "Policy", QSizePolicy)
    widget.setMinimumWidth(0)
    widget.setSizePolicy(getattr(policy, "Ignored"), getattr(policy, "Preferred"))


def has_scheme(text: str) -> bool:
    """True for an empty value, a scheme, or a file path."""
    stripped = text.strip()
    if not stripped:
        return True
    if "://" in stripped:
        return True
    if stripped.startswith("/") or stripped.startswith("\\\\"):
        return True
    if len(stripped) > 2 and stripped[0].isalpha() and stripped[1] == ":":
        return True
    return False


class UrlEditor:
    def __init__(self, spec: object, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._shown = ""
        self._value = UrlValue(StringValue(""))
        self._box = QWidget(parent)
        self._edit = QLineEdit(self._box)
        self._edit.editingFinished.connect(self._commit)
        _ignore_width(self._edit)
        self._warning = QLabel(self._box)
        self._warning.setObjectName("formBuilder.rowWarning")
        self._warning.setWordWrap(True)
        self._warning.hide()
        self._translation = TranslationDisclosure(self._box)
        self._translation.set_on_change(self._change_attr)
        layout = QVBoxLayout(self._box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self._edit)
        layout.addWidget(self._warning)
        layout.addWidget(self._translation)

    @property
    def widget(self) -> QWidget:
        return self._box

    def show(self, value: RowValue) -> None:
        self._value = _url_of(value)
        self._shown = "" if not isinstance(value, Written) else self._value.string.text
        mark(self._edit, value)
        self._edit.blockSignals(True)
        self._edit.setText(self._shown)
        if not self._edit.hasFocus():
            self._edit.setCursorPosition(0)
        if isinstance(value, Mixed):
            self._edit.setPlaceholderText(MIXED_TEXT)
        elif isinstance(value, Unset):
            self._edit.setPlaceholderText(NOT_SET_TEXT)
        else:
            self._edit.setPlaceholderText("")
        self._edit.blockSignals(False)
        self._paint_warning(self._shown)
        if shows_translation(self._host.qt_name, UrlValue.ELEMENT) and isinstance(value, Written):
            names = getattr(self._host, "qt_names", None)
            self._translation.show()
            inner = self._value.string
            self._translation.set_values(
                notr=inner.notr,
                comment=inner.comment,
                extracomment=inner.extracomment,
                ident=inner.id,
                show_id=bool(names()) if callable(names) else False,
            )
        else:
            self._translation.hide()

    def is_dirty(self) -> bool:
        return self._edit.text() != self._shown

    def _commit(self) -> None:
        text = self._edit.text()
        self._paint_warning(text)
        if text == self._shown:
            return
        inner = self._value.string
        self._host.commit(UrlValue(StringValue(text, inner.notr, inner.comment, inner.extracomment, inner.id)))

    def _paint_warning(self, text: str) -> None:
        if text and not has_scheme(text):
            self._warning.setText(_WARNING)
            self._warning.show()
            return
        self._warning.hide()

    def _change_attr(self, field: str, raw: object) -> None:
        inner = self._value.string
        updated = StringValue(
            inner.text,
            raw if field == "notr" else inner.notr,  # type: ignore[arg-type]
            raw if field == "comment" else inner.comment,  # type: ignore[arg-type]
            raw if field == "extracomment" else inner.extracomment,  # type: ignore[arg-type]
            raw if field == "id" else inner.id,  # type: ignore[arg-type]
        )
        self._value = UrlValue(updated)
        session = self._host.begin_session(_translation_label(self._host.label))
        self._host.commit(self._value, session=session)
        session.close()


def _url_of(value: RowValue) -> UrlValue:
    if isinstance(value, Written) and isinstance(value.value, UrlValue):
        return value.value
    return UrlValue(StringValue(""))


def register(registrar: Registrar) -> None:
    registrar.editor(EditorKey(UrlValue.ELEMENT), UrlEditor)
