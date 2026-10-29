"""Handler names (UX-CODE-001)."""

from __future__ import annotations

import keyword

import pytest

from app.features.form_builder.engine.project.handler_names import (
    docstring_words,
    suggest_method_name,
)

_INHERITED = frozenset({"close", "show", "update", "accept", "done", "print", "hide"})


def _name(**kwargs: str) -> str:
    taken = kwargs.pop("taken", "")
    return suggest_method_name(
        class_name=kwargs.get("class_name", "QPushButton"),
        object_name=kwargs.get("object_name", "saveButton"),
        text=kwargs.get("text", ""),
        signal=kwargs.get("signal", "clicked()"),
        form_class=kwargs.get("form_class", "Invoice"),
        taken=tuple(part for part in taken.split(",") if part),
        inherited=_INHERITED,
    )


@pytest.mark.logic("L-handler-naming")
@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"text": "Save"}, "save_invoice"),
        ({"text": "Print receipt"}, "print_receipt"),
        ({"text": "&New sale"}, "new_sale"),
        ({"text": "On hold"}, "do_on_hold"),
        ({"text": "Close"}, "close_invoice"),
        ({"text": "Print"}, "print_invoice"),
        ({"text": "Print receipt", "taken": "print_receipt"}, "print_receipt_2"),
        (
            {
                "class_name": "QCheckBox",
                "object_name": "discountCheck",
                "text": "Discount",
                "signal": "toggled(bool)",
            },
            "discount_toggled",
        ),
        (
            {
                "class_name": "QComboBox",
                "object_name": "customerCombo",
                "text": "Customer",
                "signal": "currentIndexChanged(int)",
            },
            "customer_changed",
        ),
        ({"text": "", "object_name": "saveButton"}, "save_clicked"),
        ({"text": "", "object_name": "AButton"}, "a_button_clicked"),
        ({"text": "!!!", "object_name": "saveButton"}, "save_clicked"),
    ],
)
def test_suggested_names_follow_the_spec_examples(kwargs: dict, expected: str) -> None:
    assert _name(**kwargs) == expected


@pytest.mark.logic("L-handler-naming")
def test_a_suggested_name_is_a_short_identifier() -> None:
    name = _name(text="Please save this very long invoice draft right now before lunch")
    assert name.isidentifier()
    assert not keyword.iskeyword(name)
    assert not name.startswith("on_")
    assert not name.startswith("cbcs")
    assert len(name) <= 40
    assert name.isascii()


def test_docstring_words_for_a_check_box() -> None:
    assert docstring_words("toggled(bool)") == "checked or unchecked"


def test_a_clipped_name_never_lands_on_a_qt_name() -> None:
    name = _name(text="Show " + "x" * 60)
    assert name not in _INHERITED
    assert name.isidentifier() and not keyword.iskeyword(name)
