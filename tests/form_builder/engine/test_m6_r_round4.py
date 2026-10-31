# pyright: reportAttributeAccessIssue=false
"""M6.R round 4: a step commit and a new method stay off the whole form and the whole file."""

from __future__ import annotations

from pathlib import Path

from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
from app.features.form_builder.engine.logic.events_codec import slot_step
from app.features.form_builder.engine.logic.events import read_events
from app.features.form_builder.engine.codegen.window_template import plan_stub
from app.features.form_builder.engine.project import window_file
from tests.form_builder.engine.commands._support import open_log
from tests.form_builder.idle import pump_until_idle

_WINDOW = """from PySide6.QtWidgets import QDialog

from forms.ui_sale import Ui_Sale


class SaleWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_Sale()
        self.ui.setupUi(self)

    def show_total(self):
        pass
"""


def _many_events() -> str:
    buttons = []
    links = []
    for index in range(40):
        name = "button%d" % index
        buttons.append(
            '  <widget class="QPushButton" name="%s">'
            '   <property name="text"><string>%s</string></property>'
            "  </widget>" % (name, name)
        )
        links.append(
            "  <connection><sender>%s</sender><signal>clicked()</signal>"
            "<receiver>Form</receiver><slot>accept()</slot></connection>" % name
        )
    return (
        '<?xml version="1.0"?><ui version="4.0"><class>Form</class>'
        '<widget class="QDialog" name="Form">'
        + "".join(buttons)
        + "</widget><connections>"
        + "".join(links)
        + "</connections></ui>"
    )


def test_one_step_commit_rereads_only_the_touched_sender() -> None:
    import app.features.form_builder.engine.commands.catalog_ext.events as catalog
    import app.features.form_builder.engine.logic.events as events

    log = open_log(_many_events())
    doc = log.document
    read_events(doc)
    calls = []
    real = events.read_event

    def _wrapped(document, sender, signal_name):  # type: ignore[no-untyped-def]
        calls.append((sender, signal_name))
        return real(document, sender, signal_name)

    events.read_event = _wrapped  # type: ignore[assignment]
    catalog.read_event = _wrapped  # type: ignore[assignment]
    try:
        log.execute(SetEventSteps("button0", "clicked", (), caption="Clear steps"))
        read_events(doc)
    finally:
        events.read_event = real  # type: ignore[assignment]
        catalog.read_event = real  # type: ignore[assignment]
    assert calls
    assert {sender for sender, _signal in calls} == {"button0"}
    assert len(calls) < 10


def test_an_inserted_method_is_remembered_without_another_parse(tmp_path: Path) -> None:
    folder = tmp_path / "forms"
    folder.mkdir()
    target = folder / "sale_window.py"
    target.write_text(_WINDOW, encoding="utf-8")
    relative = "forms/sale_window.py"
    root = str(tmp_path)
    read = window_file.read_window(root, relative)
    assert read.status == "ok"
    plan = plan_stub(read, method_name="print_receipt", params=(), sender="printButton", event_words="clicked")
    patched = window_file.install_inserted_method(root, relative, read, plan, "9")
    fresh = window_file.read_window(root, relative, text=patched.source, token=None)
    remembered = patched.facts.method("print_receipt")
    parsed = fresh.facts.method("print_receipt")
    assert remembered is not None and parsed is not None
    assert remembered.line == parsed.line

    def _refuse(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("the gesture parsed the window file")

    original = window_file._read_text
    window_file._read_text = _refuse  # type: ignore[assignment]
    try:
        hit = window_file.read_window(root, relative, text=patched.source, token="9")
    finally:
        window_file._read_text = original  # type: ignore[assignment]
    assert hit.facts.method("print_receipt") is not None
    assert hit.facts.method("print_receipt").line == parsed.line  # type: ignore[union-attr]


def test_a_step_commit_checks_handlers_on_the_next_turn_and_skips_a_hidden_toast(
    qapp, tmp_path: Path  # type: ignore[no-untyped-def]
) -> None:
    from app.features.form_builder.integration import handler_checks_bridge
    from app.qt.QtWidgets import QWidget
    from tests.unit.features.form_builder.test_workbench import _open

    sale = Path(__file__).resolve().parents[1] / "fixtures" / "m6" / "forms" / "sale.ui"
    host = QWidget()
    surface = _open(host, sale.read_text(encoding="utf-8"), tmp_path / "sale.ui")
    host.show()
    if not getattr(surface, "_cbcs_handler_checks", False):
        handler_checks_bridge.arm(surface)
    checks = {"n": 0}
    views = {"n": 0}
    real_check = handler_checks_bridge.check_handlers
    canvas = surface.workbench.canvas
    real_view = canvas.viewport_rect

    def _check(*args, **kwargs):  # type: ignore[no-untyped-def]
        checks["n"] += 1
        return real_check(*args, **kwargs)

    def _view(*args, **kwargs):  # type: ignore[no-untyped-def]
        views["n"] += 1
        return real_view(*args, **kwargs)

    handler_checks_bridge.check_handlers = _check  # type: ignore[assignment]
    canvas.viewport_rect = _view  # type: ignore[method-assign]
    try:
        checks["n"] = 0
        views["n"] = 0
        surface.session.log.execute(
            SetEventSteps(
                "clearButton",
                "clicked",
                (slot_step("nameEdit", "clear()"),),
                caption="Clear steps",
            )
        )
        assert checks["n"] == 0
        assert views["n"] == 0
        for _ in range(4):
            qapp.processEvents()
        # Not inside the pumps that follow the commit. The idle turn runs them.
        assert checks["n"] == 0
        pump_until_idle()
    finally:
        handler_checks_bridge.check_handlers = real_check  # type: ignore[assignment]
        canvas.viewport_rect = real_view  # type: ignore[method-assign]
    assert checks["n"] >= 1
