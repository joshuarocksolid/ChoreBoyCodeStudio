"""AddErrorLabel and SetChecks undo as one step each."""

from __future__ import annotations

from typing import Optional

import pytest

from app.features.form_builder.engine.commands.catalog_ext.checks import AddErrorLabel, SetChecks
from app.features.form_builder.engine.logic.checks import Length, Required, read_checks
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import NumberValue
from tests.form_builder.engine.commands._support import nid, open_log, prop_text
from tests.form_builder.engine.test_m6_1a_events import form

pytestmark = pytest.mark.unit


def _max_length(doc: UiDocument, name: str) -> Optional[int]:
    entry = doc.node(nid(doc, name)).prop("maxLength")
    if entry is None:
        return None
    assert isinstance(entry.value, NumberValue)
    return entry.value.value


def test_add_error_label_undo_and_redo() -> None:
    log = open_log(form())
    owner = nid(log.document, "nameEdit")
    log.execute(AddErrorLabel(owner))
    assert prop_text(log.document, "nameEdit", "cbcsErrorLabel") == "nameEditError"
    assert nid(log.document, "nameEditError")
    assert log.undo()
    assert prop_text(log.document, "nameEdit", "cbcsErrorLabel") is None
    assert log.document.by_name("nameEditError") == ()
    assert log.redo()
    assert prop_text(log.document, "nameEdit", "cbcsErrorLabel") == "nameEditError"
    assert nid(log.document, "nameEditError")


def test_set_checks_undo_restores_validate_and_drops_max_length() -> None:
    log = open_log(form())
    owner = nid(log.document, "nameEdit")
    log.execute(SetChecks(owner, (Required("Need a name"),)))
    log.execute(SetChecks(owner, (Length(None, 8, None),)))
    assert _max_length(log.document, "nameEdit") == 8
    stored = prop_text(log.document, "nameEdit", "cbcsValidate")
    assert stored is not None
    assert read_checks(stored).checks[0].__class__ is Length
    assert log.undo()
    assert _max_length(log.document, "nameEdit") is None
    restored = prop_text(log.document, "nameEdit", "cbcsValidate")
    assert restored is not None
    read = read_checks(restored)
    assert read.error is None
    assert isinstance(read.checks[0], Required)
    assert read.checks[0].message == "Need a name"
    assert log.redo()
    assert _max_length(log.document, "nameEdit") == 8
