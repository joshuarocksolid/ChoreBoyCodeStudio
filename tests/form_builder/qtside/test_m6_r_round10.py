# pyright: reportAttributeAccessIssue=false
"""M6.R round 10: a step commit and a tab open stay off the whole form.

The logic badges keep their seats across a commit. The walks that a commit used to
repeat are kept until the structure moves. The status bar is read once per open.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import Any, List

import pytest

from app.features.form_builder.engine.commands.catalog import Rename
from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
from app.features.form_builder.engine.logic.events_codec import slot_step
from app.features.form_builder.engine.project.pictures import picture_uses
from app.features.form_builder.engine.query.actions import list_actions
from app.features.form_builder.qtside.canvas.layers import logic_badges
from app.features.form_builder.qtside.canvas.layers.logic_badges import badge_tip, build as build_badges
from tests.form_builder.engine.commands._support import open_log
from tests.form_builder.qtside.test_m6_1c_connections import _world, connection, form

pytestmark = pytest.mark.unit


def _tips(output: Any) -> dict:
    return {item.data[1]: item.data[2] for item in output.items if isinstance(item.data, tuple) and item.data[0] == "badge"}


def _fresh(static: Any, inputs: Any) -> Any:
    logic_badges.forget_badge_memo()
    return build_badges(static, inputs, None)


def test_a_step_commit_keeps_the_badge_seats_and_every_tip_stays_right(monkeypatch: pytest.MonkeyPatch) -> None:
    log = open_log(form(connection("clearButton", "clicked()", "nameEdit", "clear()")))
    document = log.document
    current = document.by_name("clearButton")[0]
    static, inputs = _world(log, current)
    logic_badges.forget_badge_memo()
    first = build_badges(static, inputs, None)
    assert _tips(first) == {"clearButton": "1 event: When clicked"}

    seated = {"n": 0}
    real = logic_badges.place_chips

    def _counting(*args: Any, **kwargs: Any) -> Any:
        seated["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(logic_badges, "place_chips", _counting)
    log.execute(
        SetEventSteps(
            "clearButton",
            "clicked",
            (slot_step("nameEdit", "clear()"), slot_step("nameEdit", "setFocus()")),
            caption="Two steps",
        )
    )
    log.execute(SetEventSteps("clearButton", "toggled", (slot_step("nameEdit", "clear()"),), caption="Toggled"))
    again = build_badges(static, inputs, None)
    assert seated["n"] == 0, "the same senders in the same place are not seated again"
    assert _tips(again) == {"clearButton": badge_tip(document, "clearButton")}
    assert _tips(again)["clearButton"].startswith("2 events: When clicked, When ")
    assert again.items == _fresh(static, inputs).items


def test_a_new_sender_and_a_rename_seat_again_and_match_a_fresh_build() -> None:
    log = open_log(form(connection("clearButton", "clicked()", "nameEdit", "clear()")))
    document = log.document
    current = document.by_name("clearButton")[0]
    static, inputs = _world(log, current)
    logic_badges.forget_badge_memo()
    build_badges(static, inputs, None)

    log.execute(SetEventSteps("phoneEdit", "returnPressed", (slot_step("nameEdit", "setFocus()"),), caption="Enter"))
    with_two = build_badges(static, inputs, None)
    assert set(_tips(with_two)) == {"clearButton", "phoneEdit"}
    assert with_two.items == _fresh(static, inputs).items

    log.execute(Rename(document.by_name("clearButton")[0], "okButton"))
    after = build_badges(static, inputs, None)
    tips = _tips(after)
    assert "clearButton" not in tips
    assert tips["okButton"] == badge_tip(document, "okButton") == "1 event: When clicked"
    assert after.items == _fresh(static, inputs).items

    log.undo()
    undone = build_badges(static, inputs, None)
    assert "okButton" not in _tips(undone) and "clearButton" in _tips(undone)
    assert undone.items == _fresh(static, inputs).items


def test_a_step_commit_does_not_move_the_structure_or_repeat_the_walks(monkeypatch: pytest.MonkeyPatch) -> None:
    log = open_log(form(connection("clearButton", "clicked()", "nameEdit", "clear()")))
    document = log.document
    list_actions(document)
    picture_uses(document)
    walks = {"n": 0}
    real = type(document).iter_preorder

    def _counting(self: Any, *args: Any, **kwargs: Any) -> Any:
        walks["n"] += 1
        return real(self, *args, **kwargs)

    monkeypatch.setattr(type(document), "iter_preorder", _counting)
    revision = document.revision
    structure = document.structure_revision
    log.execute(SetEventSteps("clearButton", "clicked", (slot_step("nameEdit", "setFocus()"),), caption="Focus"))
    assert document.revision > revision
    assert document.structure_revision == structure
    walks["n"] = 0
    list_actions(document)
    picture_uses(document)
    assert walks["n"] == 0

    log.execute(Rename(document.by_name("nameEdit")[0], "nameField"))
    assert document.structure_revision > structure
    list_actions(document)
    picture_uses(document)
    assert walks["n"] > 0
    log.undo()
    log.undo()
    assert document.structure_revision > structure


def test_the_local_history_connection_is_opened_once_per_thread(tmp_path: Any) -> None:
    from app.persistence.local_history_schema import LocalHistorySchema

    schema = LocalHistorySchema(state_root=str(tmp_path))
    first = schema.connect()
    assert schema.connect() is first
    with schema.connect() as connection_:
        connection_.execute("SELECT 1").fetchone()
    assert schema.connect() is first
    other: List[Any] = []
    thread = threading.Thread(target=lambda: other.append(schema.connect()))
    thread.start()
    thread.join()
    assert other and other[0] is not first
    schema.close()
    assert schema.connect() is not first


def test_opening_a_tab_reads_the_status_bar_once_per_path_and_lints_once_when_idle(qapp: Any) -> None:
    from app.shell.editor_tab_buffer_workflow import EditorTabBufferWorkflow
    from tests.form_builder.idle import pump_until_idle

    shown: List[str] = []
    linted: List[str] = []
    host = SimpleNamespace(
        status_controller=lambda: SimpleNamespace(set_editor_status=lambda **_kw: shown.append("set")),
        render_lint_diagnostics_for_file=lambda path, trigger: linted.append("%s:%s" % (path, trigger)),
        is_shutting_down=lambda: False,
    )
    workflow = EditorTabBufferWorkflow(
        host=host,  # type: ignore[arg-type]
        editor_manager=SimpleNamespace(get_tab=lambda _path: object()),  # type: ignore[arg-type]
        editor_tabs_coordinator=SimpleNamespace(),
        outline_workflow=SimpleNamespace(),
        markdown_workflow=SimpleNamespace(),
        tab_workflow=SimpleNamespace(),
    )
    workflow._host.tab_content_registry = lambda: None  # type: ignore[attr-defined]
    workflow._host.editor_widgets_by_path = lambda: {}  # type: ignore[attr-defined]
    with workflow.hold_status_updates():
        for _ in range(5):
            workflow.update_editor_status_for_path("/a.py")
        workflow.update_editor_status_for_path("/b.py")
        with workflow.hold_status_updates():
            workflow.update_editor_status_for_path("/a.py")
        assert shown == []
    assert shown == ["set", "set"]
    workflow.update_editor_status_for_path("/a.py")
    assert shown == ["set", "set", "set"]
    workflow._lint_for_tab_change("/a.py")
    assert linted == ["/a.py:tab_change"]

    linted.clear()
    with workflow.hold_status_updates():
        workflow._lint_for_tab_change("/a.py")
        workflow._lint_for_tab_change("/a.py")
        workflow._lint_for_tab_change("/b.py")
    assert linted == []
    pump_until_idle()
    assert linted == ["/a.py:tab_change", "/b.py:tab_change"]


def test_an_idle_followup_that_fails_does_not_drop_the_ones_behind_it(qapp: Any) -> None:
    from app.shell.idle_turn import run_when_idle
    from tests.form_builder.idle import pump_until_idle

    hits: List[str] = []

    def _closed_window() -> None:
        raise RuntimeError("cannot schedule new futures after shutdown")

    run_when_idle(_closed_window)
    run_when_idle(lambda: hits.append("ran"))
    pump_until_idle()
    assert hits == ["ran"]
