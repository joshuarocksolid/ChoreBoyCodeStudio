# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""One clean-tab gesture parses the window file once, and later edits still check."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
from app.features.form_builder.engine.logic.events_codec import call_step
from app.features.form_builder.integration.handler_checks_bridge import arm
from app.features.form_builder.integration.handlers_code import SERVICE
from tests.form_builder.test_m6_2b_gesture import FIXTURE, _codes, _open, _request

pytestmark = [pytest.mark.unit]


def test_a_clean_tab_gesture_parses_the_window_file_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    text = (FIXTURE / "sale_window.py").read_text(encoding="utf-8")
    surface, window, _port = _open(tmp_path, text)
    arm(surface)
    import app.features.form_builder.engine.project.window_file as window_file

    parses: list = []
    original = window_file._read_text

    def _count(project_root: str, relative: str, source: str, *args: object, **kwargs: object):
        if relative.replace("\\", "/").endswith("sale_window.py"):
            parses.append(relative)
        return original(project_root, relative, source, *args, **kwargs)

    monkeypatch.setattr(window_file, "_read_text", _count)
    outcome = SERVICE.make_method(surface, _request())
    assert outcome.ok, outcome.reason
    assert parses == ["forms/sale_window.py"]
    surface.code_bridge.notify_saved(str(window))
    assert parses == ["forms/sale_window.py"]


def test_fb201_follows_a_form_change_and_a_text_edit(tmp_path: Path) -> None:
    text = (FIXTURE / "sale_window.py").read_text(encoding="utf-8")
    surface, window, port = _open(tmp_path, text)
    arm(surface)
    assert SERVICE.make_method(surface, _request()).ok
    assert "FB201" not in _codes(surface)
    surface.session.log.execute(
        SetEventSteps(
            "printButton",
            "clicked",
            (call_step("not_a_method"),),
            caption="Call not_a_method()",
        )
    )
    assert "FB201" in _codes(surface)
    port.tabs[str(window)] = port.tabs[str(window)].replace(
        "    def show_total(self):",
        "    def not_a_method(self):\n        pass\n\n    def show_total(self):",
        1,
    )
    surface.code_bridge.notify_saved(str(window))
    assert "FB201" not in _codes(surface)
