# pyright: reportAttributeAccessIssue=false
"""A window with open forms exits 0, and each surface releases (K5, M10)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.form_builder.qtside.support import run_module

pytestmark = pytest.mark.unit


@pytest.mark.timeout(90)
@pytest.mark.parametrize("scenario", ["quit", "editor", "discard"])
def test_open_forms_shut_down_cleanly(tmp_path: Path, scenario: str) -> None:
    log_path = tmp_path / "released.txt"
    result = run_module(
        "tests.form_builder.qtside.tools.form_shutdown_probe",
        [scenario, str(tmp_path), str(log_path)],
    )
    assert result.returncode == 0, result.stderr[-2000:]
    released = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    assert "one.ui" in released
    if scenario == "discard":
        assert "two.ui" in released
