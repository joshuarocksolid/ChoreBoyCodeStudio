"""Form diagnostics become ordinary Problems rows."""

from __future__ import annotations

import os

import pytest

from app.features.form_builder.engine.diagnostics import (
    DiagnosticLocation,
    FormDiagnostic,
    Severity,
)
from app.features.form_builder.integration.problems_bridge import code_diagnostics_for_form

pytestmark = pytest.mark.unit


def _row(code: str, name: str = "email") -> FormDiagnostic:
    return FormDiagnostic(
        code=code,
        severity=Severity.ERROR,
        message="This name is already used.",
        location=DiagnosticLocation(object_name=name, line=12),
        source="reader",
    )


def test_a_form_diagnostic_keeps_its_code_and_names_the_widget() -> None:
    rows = code_diagnostics_for_form("/tmp/invoice.ui", (_row("FB003"),))
    assert len(rows) == 1
    row = rows[0]
    assert row.code == "FB003"
    assert row.file_path == "/tmp/invoice.ui"
    assert row.line_number == 12
    assert row.message == "email: This name is already used."
    assert row.detail is not None
    assert row.detail["location_label"] == "email"
    assert row.detail["source_label"] == "Form"
    assert row.detail["fb_object"] == "email"
    assert "node" not in row.detail


def test_internal_codes_stay_out_unless_debug_is_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CBCS_FB_DEBUG", raising=False)
    assert code_diagnostics_for_form("/tmp/invoice.ui", (_row("FB900"),)) == []
    monkeypatch.setenv("CBCS_FB_DEBUG", "1")
    assert len(code_diagnostics_for_form("/tmp/invoice.ui", (_row("FB900"),))) == 1
    os.environ.pop("CBCS_FB_DEBUG", None)
