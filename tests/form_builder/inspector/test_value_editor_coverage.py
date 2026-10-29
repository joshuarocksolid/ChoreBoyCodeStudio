"""UX-PED-001: every ui4 value class has an inspector editor other than the raw one."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.ui4.values import VALUE_CLASSES
from app.features.form_builder.qtside.inspector.api import STYLESHEET, EditorKey
from app.features.form_builder.qtside.inspector.editors import default_catalog
from app.features.form_builder.qtside.inspector.editors.raw import RawXmlEditor

pytestmark = pytest.mark.unit


def test_every_value_class_has_an_editor_other_than_the_raw_one() -> None:
    """UX-PED-001. Style sheet (deferred to M5.3) and unknown elements (kept as is) are the two exceptions."""
    catalog = default_catalog()
    bare = sorted(
        element
        for element in VALUE_CLASSES
        if catalog.editor(EditorKey(element)) in (None, RawXmlEditor)
    )
    assert bare == [], "value classes without a real editor: %s" % ", ".join(bare)
    assert catalog.editor(STYLESHEET) is RawXmlEditor
