# pyright: reportAttributeAccessIssue=false
"""M7.0s run-console links: a new file supplies the match, the panel only asks the registry."""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.integration.run_links_ext import (  # noqa: E402
    install_console_hook,
    load_run_links,
)
from app.qt.QtCore import Qt  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import QApplication  # noqa: E402
from app.shell.run_log_panel import RunLogPanel, set_run_link_resolver  # noqa: E402
from app.shell.theme_tokens import ShellThemeTokens  # noqa: E402
from tests.form_builder.m5_0s_support import forget_package, make_package  # noqa: E402

pytestmark = pytest.mark.unit

_LINE = '  File "forms/sale_window.py", line 14, in show_total'

_PROBE = {
    "probe": """
        from app.features.form_builder.integration.run_links_ext import RunLink

        def match(line):
            if 'sale_window.py' in line and line.lstrip().startswith("File "):
                return "forms/sale_window.py:14"
            return None

        def activate(target):
            match.calls.append(target)

        match.calls = []

        def register(registry):
            registry.add(RunLink(match, activate))
    """,
}


def _tokens() -> ShellThemeTokens:
    return ShellThemeTokens(
        window_bg="#FFFFFF",
        panel_bg="#FFFFFF",
        editor_bg="#FFFFFF",
        text_primary="#1F2937",
        text_muted="#64748B",
        border="#1F2937",
        accent="#2563EB",
        gutter_bg="#FFFFFF",
        gutter_text="#64748B",
        line_highlight="#EEEEEE",
        is_dark=False,
        icon_primary="#1F2937",
        icon_muted="#64748B",
        diag_error_color="#B91C1C",
        debug_running_color="#15803D",
    )


def _href_at(panel: RunLogPanel, needle: str) -> str:
    found = panel._text.document().find(needle)
    if found.isNull():
        return ""
    return str(found.charFormat().anchorHref() or "")


def test_an_empty_package_loads_no_links_and_the_console_has_no_anchors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qapp: QApplication
) -> None:
    del qapp
    package = make_package(tmp_path, monkeypatch, "m70s_empty_links", {})
    try:
        assert load_run_links(package).all() == ()
    finally:
        forget_package("m70s_empty_links")
    panel = RunLogPanel()
    panel.append_live_line(_LINE)
    assert _href_at(panel, "sale_window.py") == ""


def test_a_traceback_line_is_an_anchor_and_activation_calls_the_contributor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qapp: QApplication
) -> None:
    package = make_package(tmp_path, monkeypatch, "m70s_link_probe", _PROBE)
    try:
        from m70s_link_probe import probe as probe_module

        registry = load_run_links(package)
        monkeypatch.setattr(
            "app.features.form_builder.integration.run_links_ext.default_registry", lambda: registry
        )
        install_console_hook()
        panel = RunLogPanel()
        panel.resize(640, 240)
        panel.show()
        text = "Traceback (most recent call last):\n%s\nNameError: name" % _LINE
        panel.set_log_content(text)
        assert _href_at(panel, "sale_window.py") == "forms/sale_window.py:14"
        panel.apply_theme(_tokens())
        assert _href_at(panel, "sale_window.py") == "forms/sale_window.py:14"

        found = panel._text.document().find("sale_window.py")
        rect = panel._text.cursorRect(found)
        qapp.processEvents()
        QTest.mouseClick(panel._text.viewport(), Qt.LeftButton, Qt.NoModifier, rect.center())
        qapp.processEvents()
        clicked: List[str] = list(probe_module.match.calls)
        if not clicked:
            assert panel.activate_run_link(_LINE) is True
        assert probe_module.match.calls == ["forms/sale_window.py:14"]
    finally:
        set_run_link_resolver(None)
        forget_package("m70s_link_probe")
