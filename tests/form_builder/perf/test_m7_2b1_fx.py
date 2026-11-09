# pyright: reportAttributeAccessIssue=false
"""Keystroke cost of a 200-character formula on a 300-widget form."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.features.form_builder.engine.logic.formula import SlotKind
from app.features.form_builder.engine.logic.formula.types import WHOLE
from app.features.form_builder.engine.logic.formula_env import env_for
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.qtside.formula.editor import FormulaEditor
from app.qt.QtWidgets import QLabel
from tests.form_builder.perf.reference import DEFAULT_SEED, reference_form
from tests.form_builder.perf.stats import measure
from tests.form_builder.qtside.support import open_session

pytestmark = pytest.mark.perf

_FORMULA = "1" + (" + 1" * 49) + "   "


def test_a_keystroke_stays_within_16ms(qapp: object) -> None:
    del qapp
    assert len(_FORMULA) == 200
    built = reference_form(300, DEFAULT_SEED)
    session = open_session(built.xml)
    editor = FormulaEditor()
    label = QLabel()
    try:
        env = env_for(session.document, None, QtClassTable.shared())
        editor.set_status_label(label)
        editor.set_context(env, SlotKind.value(WHOLE), SimpleNamespace())

        def prepare() -> None:
            editor.setPlainText("0")

        def keystroke() -> None:
            editor.setPlainText(_FORMULA)

        dist = measure(keystroke, warmup=5, samples=30, prepare=prepare)
        p95 = dist.cpu_p95 * 1000.0
        assert label.text()
        assert "now:" in label.text()
        assert p95 <= 16, "p95 %.3f ms" % p95
    finally:
        editor.deleteLater()
        label.deleteLater()
        session.dispose()
