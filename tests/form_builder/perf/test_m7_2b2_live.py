# pyright: reportAttributeAccessIssue=false
"""Live preview of a short Enabled when formula on a 300-widget form."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.features.form_builder.engine.logic.formula_env import env_for
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.qtside.formula.live_plate import plate_for
from app.features.form_builder.qtside.realize import Realizer
from tests.form_builder.perf.reference import EDIT_NAME, reference_form
from tests.form_builder.perf.stats import measure
from tests.form_builder.qtside.support import open_session

pytestmark = pytest.mark.perf


def test_revising_enabled_when_stays_within_16ms(qapp: object) -> None:
    del qapp
    built = reference_form(300)
    session = open_session(built.xml)
    realizer = Realizer(session)
    try:
        realizer.build()
        found = session.document.by_name(EDIT_NAME)
        assert found
        node = session.document.node(found[0])
        env = env_for(session.document, None, QtClassTable.shared())
        values = {}
        for name in env.widgets:
            widget = realizer.widget_named(name)
            if widget is not None:
                values[name] = widget
        reader = SimpleNamespace(**values)
        plate = plate_for(realizer)
        plate.arm(node, "cbcsEnabledWhen", "True", env, reader)

        def revise() -> None:
            plate.revise("False", reader)

        dist = measure(revise, warmup=5, samples=30)
        assert dist.cpu_p95 * 1000.0 <= 16, "p95 %.3f ms" % (dist.cpu_p95 * 1000.0)
    finally:
        realizer.dispose()
        session.dispose()
