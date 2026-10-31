# pyright: reportAttributeAccessIssue=false
"""M6.R round 9: a step commit leaves the geometry alone, and the highlight queries compile once."""

from __future__ import annotations

from typing import Iterator, Tuple

import pytest

from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
from app.features.form_builder.engine.events import PRIORITY_HIT_INDEX
from app.features.form_builder.engine.logic.events_codec import slot_step
from app.features.form_builder.engine.query.hit_index import HitIndex
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.qtside.canvas.geometry import HitIndexInvalidator, LiveGeometrySource
from app.features.form_builder.qtside.realize import Realizer
from app.qt.QtWidgets import QApplication
from tests.form_builder.qtside.support import opened
from tests.form_builder.qtside.test_geometry import NESTED
from tests.form_builder.qtside.test_hit_index_incremental_repro import _assert_matches_full

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def live() -> Iterator[Tuple[FormSession, Realizer, HitIndex]]:
    with opened(NESTED) as (session, realizer):
        root = realizer.root_widget
        assert root is not None
        root.show()
        QApplication.processEvents()
        index = HitIndex(LiveGeometrySource(realizer))
        subscription = session.log.subscribe(HitIndexInvalidator(index).on_changeset, priority=PRIORITY_HIT_INDEX)
        try:
            index.ensure_fresh()
            yield session, realizer, index
        finally:
            subscription.close()
            root.hide()


def test_a_step_commit_refreshes_the_hit_index_without_a_full_walk(
    live: Tuple[FormSession, Realizer, HitIndex]
) -> None:
    session, realizer, index = live
    steps = (slot_step("label", "clear()"),)
    for caption, edit in (("add", steps), ("remove", ())):
        session.log.execute(SetEventSteps("button", "clicked", edit, caption=caption))
        index.ensure_fresh()
        # None would mean the refresh walked the whole form. () means nothing moved.
        assert index.last_changed == (), caption
        _assert_matches_full(realizer, index)


def test_compiled_highlight_queries_are_shared_per_language() -> None:
    pytest.importorskip("tree_sitter")
    from app.treesitter.highlighter_core import shared_compiled_query
    from app.treesitter.language_registry import default_tree_sitter_language_registry
    from app.treesitter.loader import initialize_tree_sitter_runtime

    initialize_tree_sitter_runtime()
    resolved = default_tree_sitter_language_registry().resolve_for_path(file_path="x.py")
    if resolved is None:
        pytest.skip("python grammar missing")
    first = shared_compiled_query(resolved.language_key, resolved.language, resolved.highlights_query_source)
    second = shared_compiled_query(resolved.language_key, resolved.language, resolved.highlights_query_source)
    assert first is second


def test_the_window_checks_wait_for_the_idle_turn_after_a_new_method(tmp_path, qapp: QApplication) -> None:  # type: ignore[no-untyped-def]
    from app.features.form_builder.engine.logic.events_codec import call_step
    from app.features.form_builder.integration import handler_checks_bridge
    from app.features.form_builder.integration.handlers import MethodRequest
    from app.features.form_builder.integration.handlers_code import SERVICE
    from app.qt.QtCore import QEventLoop, QTimer
    from app.qt.qt_compat import exec_qt
    from tests.form_builder.qtside.test_m3_keyboard_scripts import _close, _session
    from tests.form_builder.qtside.test_m6_2b_perf import _window_source
    from tests.form_builder.qtside.test_m6_m6_1b_perf import _form

    window, kb, guard = _session(tmp_path, qapp, _form())
    try:
        path = tmp_path / "shop" / "forms" / "customer_window.py"
        path.write_text(_window_source(), encoding="utf-8")
        surface = kb.surface
        for _ in range(4):
            qapp.processEvents()
        calls = {"n": 0}
        real = handler_checks_bridge.check_handlers

        def counting(*args, **kwargs):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            return real(*args, **kwargs)

        handler_checks_bridge.check_handlers = counting
        try:
            outcome = SERVICE.make_method(
                surface,
                MethodRequest(
                    "Write code",
                    (SetEventSteps("button0", "clicked", (call_step("later"),), caption="Call later"),),
                    "later",
                    "",
                    "button0",
                    "clicked",
                ),
            )
            assert outcome.ok, outcome.reason
            assert calls["n"] == 0
            loop = QEventLoop()
            QTimer.singleShot(40, loop.quit)
            exec_qt(loop)
            assert calls["n"] >= 1
        finally:
            handler_checks_bridge.check_handlers = real
    finally:
        _close(window, qapp, guard)
