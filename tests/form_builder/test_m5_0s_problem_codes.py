# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""Problems fix buttons by FB code, and diagnostic code module discovery."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, List

import pytest

from app.features.form_builder.engine import diagnostic_codes
from app.features.form_builder.engine.diagnostics import CODES, DiagnosticLocation, FormDiagnostic, Severity
from app.features.form_builder.integration import problem_fixes
from app.features.form_builder.integration.problems_bridge import code_diagnostics_for_form, fixes_for, run_fix
from tests.form_builder.m5_0s_support import forget_package, make_package

pytestmark = [pytest.mark.unit]

_FIXES = """
    from app.features.form_builder.integration.problem_fixes import ProblemFix

    RAN = []

    def register(registry):
        registry.add(ProblemFix(
            "FB031", "add-picture",
            lambda diagnostic: "Add %s to project pictures" % diagnostic.location.object_name,
            lambda context: RAN.append(context.diagnostic.location.object_name),
            offered=lambda diagnostic: diagnostic.location.property == "pixmap",
        ))
        registry.add(ProblemFix("FB031", "open-qrc", "Open resources.qrc", lambda context: RAN.append("qrc")))
"""

_CODE = """
    from app.features.form_builder.engine.diagnostics import Severity, declare

    declare("FB998", Severity.WARNING, "A probe code.")
"""


def _diagnostic(code: str, prop: str = "pixmap") -> FormDiagnostic:
    return FormDiagnostic(
        code=code,
        severity=Severity.WARNING,
        message="logo uses a picture from a file path.",
        location=DiagnosticLocation(object_name="logo", property=prop, line=3),
        source="codegen",
    )


@pytest.fixture()
def fixes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[object]:
    package = make_package(tmp_path, monkeypatch, "m5_fix_probe", {"resources": _FIXES, "_helper": "raise SystemExit"})
    yield package
    forget_package("m5_fix_probe")


def test_a_fix_module_adds_buttons_for_its_code_and_they_ride_in_the_problem_row(fixes) -> None:  # type: ignore[no-untyped-def]
    registry = problem_fixes.load_fixes(fixes)
    assert registry.codes() == ("FB031",)
    assert fixes_for(_diagnostic("FB031"), registry) == (
        ("add-picture", "Add logo to project pictures"),
        ("open-qrc", "Open resources.qrc"),
    )
    assert fixes_for(_diagnostic("FB031", prop="icon"), registry) == (("open-qrc", "Open resources.qrc"),)
    assert fixes_for(_diagnostic("FB032"), registry) == ()
    rows = code_diagnostics_for_form("/work/a.ui", (_diagnostic("FB031"), _diagnostic("FB032")), registry)
    first, second = rows[0].detail or {}, rows[1].detail or {}
    assert json.loads(first["fb_fixes"])[0] == ["add-picture", "Add logo to project pictures"]
    assert "fb_fixes" not in second


def test_running_a_fix_goes_through_its_code_only(fixes) -> None:  # type: ignore[no-untyped-def]
    registry = problem_fixes.load_fixes(fixes)
    seen: List[str] = []
    context = problem_fixes.FixContext(_diagnostic("FB031"), session=None)
    assert run_fix(_diagnostic("FB031"), "add-picture", context, registry)
    assert fixes.resources.RAN == ["logo"]
    assert not run_fix(_diagnostic("FB031", prop="icon"), "add-picture", context, registry)
    assert not run_fix(_diagnostic("FB032"), "open-qrc", context, registry) and seen == []
    with pytest.raises(ValueError):
        registry.add(problem_fixes.ProblemFix("FB031", "open-qrc", "Again", lambda c: None))
    with pytest.raises(ValueError):
        problem_fixes.ProblemFix("QR031", "x", "x", lambda c: None)


def test_a_code_module_is_declared_by_discovery_and_twice_is_safe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = make_package(tmp_path, monkeypatch, "m5_code_probe", {"fb99x_probe": _CODE, "_skipped": "raise SystemExit"})
    try:
        assert diagnostic_codes.discover(package) == ("fb99x_probe",)
        assert CODES["FB998"].title == "A probe code."
        assert diagnostic_codes.discover(package) == ("fb99x_probe",)
    finally:
        CODES.pop("FB998", None)
        forget_package("m5_code_probe")


def test_the_product_codes_are_all_declared_after_discovery() -> None:
    names = diagnostic_codes.discover()
    assert {"fb0xx", "fb5xx", "fb6xx"} <= set(names)
    assert {"FB001", "FB601"} <= set(CODES)
