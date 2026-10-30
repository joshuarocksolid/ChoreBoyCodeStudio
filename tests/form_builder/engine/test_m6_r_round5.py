# pyright: reportAttributeAccessIssue=false
"""M6.R round 5: the event cache and the patched window reading match a full read."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from app.features.form_builder.engine.codegen.window_template import TextEdit, plan_stub
from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import DeleteNodes, Rename
from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
from app.features.form_builder.engine.logic.events import _read_events, read_events
from app.features.form_builder.engine.ui4.schema import SlotsDecl
from app.features.form_builder.engine.logic.events_codec import call_step, slot_step
from app.features.form_builder.engine.project import window_file
from tests.form_builder.engine.commands._support import open_log

pytestmark = [pytest.mark.unit]

_SALE = Path(__file__).resolve().parents[1] / "fixtures" / "m6" / "forms" / "sale.ui"


class _Plan:
    def __init__(self, edit: TextEdit, method_name: str) -> None:
        self.edit = edit
        self.method_name = method_name
        self.stub_hash = ""


def _source(body: str, trailing: str = "", newline: str = "\n") -> str:
    text = (
        "from PySide6.QtWidgets import QDialog\n"
        "\n"
        "class SaleWindow(QDialog):\n"
        "    def __init__(self, parent=None):\n"
        "        super().__init__(parent)\n"
        "        self.ui = Ui_Sale()\n"
        "        self.ui.setupUi(self)\n"
        "\n"
        "%s%s"
    ) % (body, trailing)
    if newline != "\n":
        text = text.replace("\n", newline)
    return text


def _method(name: str, newline: str) -> str:
    lines = [
        "    def %s(self):" % name,
        '        """Runs when the button is clicked."""',
        "        pass",
        "",
    ]
    return newline.join(lines)


def _install(tmp_path: Path, source: str, plan: object) -> None:
    folder = tmp_path / "forms"
    folder.mkdir()
    target = folder / "sale_window.py"
    target.write_bytes(source.encode("utf-8"))
    relative = "forms/sale_window.py"
    root = str(tmp_path)
    read = window_file.read_window(root, relative)
    assert read.status == "ok", read.reason
    patched = window_file.install_inserted_method(root, relative, read, plan, "token")
    assert isinstance(patched.source, str)
    fresh = window_file.read_window(str(tmp_path / "oracle"), relative, text=patched.source)
    assert patched.facts == fresh.facts


def test_a_patched_window_matches_a_fresh_parse(tmp_path: Path) -> None:
    newline = "\n"
    body = "    def show_total(self):\n        return 1\n"
    read_root = tmp_path / "class-end"
    read_root.mkdir()
    _install(
        read_root,
        _source(body),
        _pending_plan(read_root, _source(body)),
    )
    between = tmp_path / "between"
    between.mkdir()
    between_source = _source(
        "    def show_total(self):\n        return 1\n\n    def second(self):\n        return 2\n"
    )
    _install(between, between_source, _insert_before(between_source, "    def second(self):", "between_us", newline))
    trailing = tmp_path / "trailing"
    trailing.mkdir()
    trailing_source = _source(body, "\ndef helper():\n    return 0\n")
    _install(trailing, trailing_source, _pending_plan(trailing, trailing_source))
    crlf = tmp_path / "crlf"
    crlf.mkdir()
    crlf_source = _source(body, newline="\r\n")
    _install(crlf, crlf_source, _pending_plan(crlf, crlf_source))
    replaced = tmp_path / "replaced"
    replaced.mkdir()
    replaced_source = _source(
        "    def show_total(self):\n"
        "        return 1\n"
        "\n"
        "    # keep\n"
        "    # this\n"
        "\n"
        "    @decorator\n"
        "    def later(self):\n"
        "        return 2\n"
    )
    _install(replaced, replaced_source, _replace_comments(replaced_source, newline))
    decorated = tmp_path / "decorated"
    decorated.mkdir()
    decorated_source = _source(
        "    def show_total(self):\n"
        "        return 1\n"
        "\n"
        "    @staticmethod\n"
        "    def decorated(self):\n"
        "        return 2\n"
    )
    _install(
        decorated,
        decorated_source,
        _insert_before(decorated_source, "    @staticmethod\n", "before_decorated", newline),
    )


def _pending_plan(tmp_path: Path, source: str) -> object:
    folder = tmp_path / "plan"
    folder.mkdir()
    target = folder / "sale_window.py"
    target.write_bytes(source.encode("utf-8"))
    read = window_file.read_window(str(tmp_path), "plan/sale_window.py")
    assert read.status == "ok", read.reason
    return plan_stub(read, method_name="print_receipt", params=(), sender="printButton", event_words="clicked")


def _insert_before(source: str, marker: str, name: str, newline: str) -> _Plan:
    start = source.index(marker)
    inserted = newline + _method(name, newline) + newline
    return _Plan(TextEdit(start, start, inserted), name)


def _replace_comments(source: str, newline: str) -> _Plan:
    marker = "    # keep%s    # this%s" % (newline, newline)
    start = source.index(marker)
    inserted = _method("replaced_note", newline) + newline
    return _Plan(TextEdit(start, start + len(marker), inserted), "replaced_note")


def _widgets(doc: object) -> tuple:
    names = []
    buttons = []
    root = doc.root  # type: ignore[attr-defined]
    root_id = root.id if root is not None else None
    for node in doc.iter_preorder():  # type: ignore[attr-defined]
        if getattr(node, "kind", "") != "widget" or node.id == root_id:
            continue
        name = node.field("object_name")
        if not isinstance(name, str) or not name:
            continue
        names.append(name)
        if getattr(node, "class_name", "") == "QPushButton":
            buttons.append(name)
    return names, buttons


def _slots(doc: object) -> tuple:
    declared = doc.ui.field("form_slots")  # type: ignore[attr-defined]
    if isinstance(declared, SlotsDecl):
        return tuple(declared.slots)
    return ()


def _check(doc: object, label: object) -> None:
    got = read_events(doc)  # type: ignore[arg-type]
    full = _read_events(doc)  # type: ignore[arg-type]
    if got == full:
        return
    got_keys = [(state.sender, state.signal_name) for state in got]
    full_keys = [(state.sender, state.signal_name) for state in full]
    raise AssertionError("%s keys %s vs %s" % (label, got_keys, full_keys))


def _apply(log: object, doc: object, command: object, done: dict, kind: str) -> bool:
    try:
        log.execute(command)  # type: ignore[attr-defined]
    except CommandRejected:
        _check(doc, kind)
        return False
    done[kind] += 1
    _check(doc, kind)
    return True


def test_declaring_a_slot_rereads_an_untouched_sender_that_already_uses_it() -> None:
    log = open_log(_SALE.read_text(encoding="utf-8"))
    doc = log.document
    root = doc.root.object_name
    log.execute(
        SetEventSteps("clearButton", "clicked", (slot_step(root, "close()"),), caption="Close the form")
    )
    read_events(doc)
    log.execute(SetEventSteps("printButton", "clicked", (call_step("close"),), caption="Call close"))
    _check(doc, "close")
    clear = read_events(doc)
    matched = [state for state in clear if state.sender == "clearButton" and state.signal_name == "clicked"]
    assert matched and any(step.verb == "call" and step.method == "close" for step in matched[0].steps)


def test_read_events_matches_a_full_read_across_a_random_session() -> None:
    rng = random.Random(20261030)
    log = open_log(_SALE.read_text(encoding="utf-8"))
    doc = log.document
    done = {"undo": 0, "redo": 0, "rename": 0, "root": 0, "delete": 0, "call": 0, "uncall": 0, "slot": 0}
    _check(doc, "start")
    for step in range(220):
        names, buttons = _widgets(doc)
        senders = buttons or names
        roll = rng.randrange(8)
        if roll == 0:
            if log.undo():
                done["undo"] += 1
            _check(doc, step)
        elif roll == 1:
            if log.redo():
                done["redo"] += 1
            _check(doc, step)
        elif roll == 2 and names:
            _apply(log, doc, Rename(doc.by_name(rng.choice(names))[0], "n%d" % step), done, "rename")
        elif roll == 3 and doc.root is not None:
            _apply(log, doc, Rename(doc.root.id, "Root%d" % step), done, "root")
        elif roll == 4 and len(names) > 3:
            _apply(log, doc, DeleteNodes((doc.by_name(rng.choice(names))[0],)), done, "delete")
        elif roll == 5 and senders:
            method = "m%d" % step
            sender = rng.choice(senders)
            _apply(
                log,
                doc,
                SetEventSteps(sender, "clicked", (call_step(method),), caption="Call %s" % method),
                done,
                "call",
            )
        elif roll == 6 and senders:
            method = "u%d" % step
            sender = rng.choice(senders)
            if _apply(
                log,
                doc,
                SetEventSteps(sender, "clicked", (call_step(method),), caption="Call %s" % method),
                done,
                "call",
            ):
                added = _slots(doc)
                if log.undo():
                    done["undo"] += 1
                    if len(_slots(doc)) < len(added):
                        done["uncall"] += 1
                _check(doc, "undo-slot")
                if log.redo():
                    done["redo"] += 1
                _check(doc, "redo-slot")
        elif senders:
            sender = rng.choice(senders)
            target = rng.choice(names) if names else sender
            _apply(
                log,
                doc,
                SetEventSteps(
                    sender,
                    "clicked",
                    (slot_step(target, "clear()", enabled=False),),
                    caption="Step",
                ),
                done,
                "slot",
            )
        else:
            _check(doc, step)
    assert done["call"] and done["uncall"] and done["undo"] and done["redo"]
    assert done["rename"] and done["root"] and done["delete"] and done["slot"]


def test_an_fb4xx_problem_shows_after_one_turn_and_clears_on_undo(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from app.qt.QtWidgets import QWidget
    from tests.unit.features.form_builder.test_workbench import _open

    class _Rows:
        def __init__(self) -> None:
            self.rows: list = []

        def apply_lint_diagnostics_result(self, _path: str, diagnostics: list) -> None:
            self.rows = list(diagnostics)

    host = QWidget()
    host.setObjectName("shell.window")
    rows = _Rows()
    host._problems_controller = rows  # type: ignore[attr-defined]
    surface = _open(host, _SALE.read_text(encoding="utf-8"), tmp_path / "sale.ui")
    host.show()
    qapp.processEvents()
    doc = surface.session.document
    log = surface.session.log
    log.execute(
        SetEventSteps(
            "clearButton",
            "clicked",
            (slot_step("nameEdit", "clear()", enabled=False),),
            caption="Disable clear",
        )
    )
    log.execute(DeleteNodes((doc.by_name("nameEdit")[0],)))
    qapp.processEvents()
    codes = [row.code for row in rows.rows]
    assert any(code.startswith("FB4") for code in codes), codes
    assert log.undo()
    qapp.processEvents()
    codes = [row.code for row in rows.rows]
    assert not any(code.startswith("FB4") for code in codes), codes
