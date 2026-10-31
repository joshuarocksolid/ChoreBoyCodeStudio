# pyright: reportAttributeAccessIssue=false
"""M6.R round 6: a warm step commit does not walk the form or split the window file."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.features.form_builder.engine.codegen.window_template import plan_stub
from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
from app.features.form_builder.engine.logic.events import read_events
from app.features.form_builder.engine.logic.events_codec import slot_step
from app.features.form_builder.engine.project import window_file
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.project.window_file import install_inserted_method, read_window
from app.features.form_builder.engine.session import FormSession

pytestmark = [pytest.mark.unit]


def _reference() -> str:
    items = []
    conns = []
    for index in range(150):
        items.append('<item><widget class="QLineEdit" name="edit%d"/></item>' % index)
    for index in range(145):
        extra = ""
        if 80 <= index < 120:
            extra = (
                '<property name="cbcsOnClicked" stdset="0"><string>'
                '[{"do":"slot","target":"edit%d","slot":"clear()"}]</string></property>' % (index % 150)
            )
        items.append(
            '<item><widget class="QPushButton" name="button%d">%s</widget></item>' % (index, extra)
        )
    for index in range(4):
        items.append('<item><widget class="QLabel" name="label%d"/></item>' % index)
    items.append('<item><widget class="QListWidget" name="bigList"/></item>')
    for index in range(60):
        conns.append(
            "<connection><sender>button%d</sender><signal>clicked()</signal>"
            "<receiver>edit%d</receiver><slot>clear()</slot></connection>" % (index, index)
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?><ui version="4.0"><class>Ref</class>'
        '<widget class="QDialog" name="Ref"><layout class="QVBoxLayout" name="verticalLayout">%s</layout></widget>'
        "<resources/><connections>%s</connections></ui>"
    ) % ("".join(items), "".join(conns))


def _window() -> str:
    lines = [
        "from PySide6.QtWidgets import QDialog",
        "",
        "class RefWindow(QDialog):",
        "    def __init__(self, parent=None):",
        "        super().__init__(parent)",
        "        self.ui = Ui_Ref()",
        "        self.ui.setupUi(self)",
        "",
    ]
    for index in range(40):
        lines.append("    def method_%d(self):" % index)
        lines.append("        return %d" % index)
        lines.append("")
    return "\n".join(lines) + "\n"


def test_a_warm_step_commit_does_not_walk_inside_read_events(tmp_path: Path) -> None:
    path = tmp_path / "customer.ui"
    session = FormSession.open(
        _reference(),
        path=str(path),
        scope=FormScope(kind="external", ui_path=str(path)),
    )
    doc = session.document
    read_events(doc)
    session.log.execute(SetEventSteps("button0", "clicked", (), caption="Clear"))
    read_events(doc)
    seen = {"n": 0}
    real = doc.iter_preorder

    def wrapped(*args, **kwargs):  # type: ignore[no-untyped-def]
        frame = sys._getframe()
        while frame is not None:
            if frame.f_code.co_name == "read_events":
                seen["n"] += 1
                break
            frame = frame.f_back
        return real(*args, **kwargs)

    doc.iter_preorder = wrapped  # type: ignore[method-assign]
    session.log.execute(
        SetEventSteps("button0", "clicked", (slot_step("edit0", "clear()"),), caption="Clear name")
    )
    assert seen["n"] == 0


def test_install_inserted_method_does_not_split_the_file(tmp_path: Path) -> None:
    text = _window()
    root = str(tmp_path)
    read = read_window(root, "customer_window.py", text=text, token="t0")
    plan = plan_stub(read, method_name="probe_1", params=(), sender="button1", event_words="")
    calls = {"n": 0}
    real = window_file.source_lines

    def wrapped(source: str, keepends: bool = False):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return real(source, keepends)

    window_file.source_lines = wrapped  # type: ignore[assignment]
    try:
        install_inserted_method(root, "customer_window.py", read, plan, "t1")
    finally:
        window_file.source_lines = real
    assert calls["n"] == 0


def test_install_remembers_the_written_file(tmp_path: Path) -> None:
    text = _window()
    root = str(tmp_path)
    relative = "customer_window.py"
    read = read_window(root, relative, text=text, token="t0")
    plan = plan_stub(read, method_name="probe_1", params=(), sender="button1", event_words="")
    edit = plan.edit
    written = text[: int(edit.start)] + str(edit.text) + text[int(edit.end):]
    (tmp_path / relative).write_bytes(written.encode("utf-8"))
    install_inserted_method(root, relative, read, plan, None)
    calls = {"n": 0}
    real = window_file._read_text

    def wrapped(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return real(*args, **kwargs)

    window_file._read_text = wrapped  # type: ignore[assignment]
    try:
        again = read_window(root, relative)
    finally:
        window_file._read_text = real
    assert calls["n"] == 0
    assert again.facts.method("probe_1") is not None
