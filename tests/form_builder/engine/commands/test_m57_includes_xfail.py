# pyright: reportAttributeAccessIssue=false
"""A form with every include removed should not keep an empty includes element.

The writer that emits ``<includes/>`` lives in ``engine/ui4``, which the
class-table lane owns. This test records the gap and fails if that lane
fixes it without retiring the mark.
"""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.commands.catalog_ext.form_fields import SetFormField
from tests.form_builder.engine.commands._support import open_log, saved
from tests.form_builder.engine.commands.test_m5_5b_form_fields import FULL

pytestmark = pytest.mark.unit


@pytest.mark.xfail(
    strict=True,
    reason="empty includes still writes <includes/>; engine/ui4 is owned by the class-table lane",
)
def test_clearing_every_include_omits_the_includes_element() -> None:
    log = open_log(FULL)
    log.execute(SetFormField("includes", ()))
    assert "<includes/>" not in saved(log.document)
