# pyright: reportAttributeAccessIssue=false
"""A warm clean gesture on the 2,000-line window file stays off the whole file."""

from __future__ import annotations

import ast
import gc
import tokenize

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps  # noqa: E402
from app.features.form_builder.engine.logic.events_codec import call_step  # noqa: E402
from app.features.form_builder.engine.project import handler_checks  # noqa: E402
from app.features.form_builder.integration.handlers import MethodRequest  # noqa: E402
from app.features.form_builder.integration.handlers_code import SERVICE  # noqa: E402
from app.qt.QtCore import QEventLoop, QTimer  # noqa: E402
from app.qt.QtWidgets import QApplication  # noqa: E402
from app.qt.qt_compat import exec_qt  # noqa: E402
from app.shell.idle_turn import run_when_idle  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import _close, _session  # noqa: E402
from tests.form_builder.qtside.test_m6_2b_perf import _window_source  # noqa: E402
from tests.form_builder.qtside.test_m6_m6_1b_perf import _form  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(180)]


def test_one_process_events_does_not_run_an_idle_followup(qapp: QApplication) -> None:
    hits: list = []
    run_when_idle(lambda: hits.append("ran"))
    qapp.processEvents()
    assert hits == []
    loop = QEventLoop()
    QTimer.singleShot(30, loop.quit)
    exec_qt(loop)
    assert hits == ["ran"]


def test_a_warm_clean_gesture_does_not_parse_the_window_or_scan_every_method(
    tmp_path, qapp: QApplication  # type: ignore[no-untyped-def]
) -> None:
    window, kb, guard = _session(tmp_path, qapp, _form())
    try:
        path = tmp_path / "shop" / "forms" / "customer_window.py"
        path.write_text(_window_source(), encoding="utf-8")
        surface = kb.surface
        window._editor_tab_workflow.open_file_at_line(str(path), 1)
        for _ in range(4):
            qapp.processEvents()

        def one(name: str):
            return SERVICE.make_method(
                surface,
                MethodRequest(
                    "Write code",
                    (SetEventSteps("button0", "clicked", (call_step(name),), caption="Call %s" % name),),
                    name,
                    "",
                    "button0",
                    "clicked",
                ),
            )

        for index in range(2):
            warmed = one("warm_%d" % index)
            assert warmed.ok, warmed.reason
            qapp.processEvents()

        long_parses: list = []
        long_tokens: list = []
        scans: list = []
        real_parse = ast.parse
        real_tokens = tokenize.generate_tokens
        real_by_name = handler_checks._by_name_rows

        def _parse(source, *args, **kwargs):  # type: ignore[no-untyped-def]
            text = source.decode("utf-8", "replace") if isinstance(source, (bytes, bytearray)) else source
            if isinstance(text, str) and text.count("\n") > 400:
                long_parses.append(text.count("\n"))
            return real_parse(source, *args, **kwargs)

        def _tokens(readline, *args, **kwargs):  # type: ignore[no-untyped-def]
            counted = {"n": 0}

            def _read():  # type: ignore[no-untyped-def]
                line = readline()
                if line:
                    counted["n"] += 1
                return line

            tokens = real_tokens(_read, *args, **kwargs)

            def _tracked():  # type: ignore[no-untyped-def]
                for token in tokens:
                    yield token
                if counted["n"] > 400:
                    long_tokens.append(counted["n"])

            return _tracked()

        def _by_name(*args, **kwargs):  # type: ignore[no-untyped-def]
            scans.append(len(args[0]))
            return real_by_name(*args, **kwargs)

        ast.parse = _parse  # type: ignore[assignment]
        tokenize.generate_tokens = _tokens  # type: ignore[assignment]
        handler_checks._by_name_rows = _by_name  # type: ignore[assignment]
        try:
            gc.collect()
            measured = one("measured")
            assert measured.ok, measured.reason
            qapp.processEvents()
        finally:
            ast.parse = real_parse  # type: ignore[assignment]
            tokenize.generate_tokens = real_tokens  # type: ignore[assignment]
            handler_checks._by_name_rows = real_by_name  # type: ignore[assignment]
        assert long_parses == [], long_parses
        assert long_tokens == [], long_tokens
        assert scans == [], scans
    finally:
        _close(window, qapp, guard)
