# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""M6.2b: the window-file gesture, the save-time checks, and preview stand-ins."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import ClassVar, Dict, List, Optional, Sequence

import pytest

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
from app.features.form_builder.engine.commands.catalog_ext.form_fields import SetFormField
from app.features.form_builder.engine.logic.events_codec import call_step
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.integration.code_bridge import CodeBridge
from app.features.form_builder.integration.handler_checks_bridge import arm
from app.features.form_builder.integration.handlers import MethodRequest
from app.features.form_builder.integration.handlers_code import SERVICE, pending_toast
from app.features.form_builder.integration.preview_control import methods_for

pytestmark = [pytest.mark.unit]

FIXTURE = Path(__file__).parent / "fixtures" / "m6" / "forms"
KEPT = "Removed the step. print_receipt() has your code in it, so it stays in sale_window.py."


class _Port:
    def __init__(self, tabs: Dict[str, str], dirty: Sequence[str] = (), sync: bool = False) -> None:
        self.tabs = dict(tabs)
        self.dirty = set(dirty)
        self.sync = sync
        self.shows: List[tuple] = []

    def open_text(self, path: str) -> Optional[str]:
        return self.tabs.get(path)

    def replace_range(self, path: str, start: int, end: int, text: str) -> bool:
        current = self.tabs[path]
        self.tabs[path] = current[:start] + text + current[end:]
        self.dirty.add(path)
        if self.sync:
            Path(path).write_bytes(self.tabs[path].encode("utf-8"))
        return True

    def is_dirty(self, path: str) -> bool:
        return path in self.dirty

    def save(self, path: str) -> bool:
        if self.sync:
            Path(path).write_bytes(self.tabs[path].encode("utf-8"))
        self.dirty.discard(path)
        return True

    def show(self, path: str, line: int, select: object) -> bool:
        self.shows.append((path, line, select))
        return True


class _Surface:
    def __init__(self, session: FormSession, bridge: CodeBridge) -> None:
        self.session = session
        self.code_bridge = bridge
        self.lines: List[str] = []

    def narrate(self, text: str) -> None:
        self.lines.append(text)


def _scope(root: Path, ui: Path, window: Path) -> FormScope:
    return FormScope(
        "project",
        str(ui),
        str(root),
        str(root / "forms" / "ui_sale.py"),
        str(window),
        "forms.ui_sale",
        "forms.sale_window",
    )


def _open(tmp_path: Path, text: str, *, dirty: bool = False, sync: bool = False) -> tuple:
    root = tmp_path / "shop"
    (root / "forms").mkdir(parents=True)
    ui = root / "forms" / "sale.ui"
    ui.write_text((FIXTURE / "sale.ui").read_text(encoding="utf-8"), encoding="utf-8")
    window = root / "forms" / "sale_window.py"
    window.write_bytes(text.encode("utf-8"))
    session = FormSession.open((FIXTURE / "sale.ui").read_text(encoding="utf-8"), path=str(ui), scope=_scope(root, ui, window))
    port = _Port({str(window): text}, dirty=(str(window),) if dirty else (), sync=sync)
    bridge = CodeBridge(str(root), port)
    return _Surface(session, bridge), window, port


def _request(command: object = None) -> MethodRequest:
    commands = () if command is None else (command,)
    label = "Write code for Print receipt clicked"
    if command is None:
        command = SetEventSteps("printButton", "clicked", (call_step("print_receipt"),), caption=label)
        commands = (command,)
    return MethodRequest(label, commands, "print_receipt", "", "printButton", "clicked")


def test_a_stub_for_an_existing_step_undoes_with_that_step(tmp_path: Path) -> None:
    from app.features.form_builder.engine.commands.catalog_ext.methods import PairStub

    text = (FIXTURE / "sale_window.py").read_text(encoding="utf-8")
    surface, window, port = _open(tmp_path, text, dirty=True)
    surface.session.log.execute(
        SetEventSteps("printButton", "clicked", (call_step("print_receipt"),), caption="Call print_receipt()")
    )
    before = port.tabs[str(window)]
    request = MethodRequest("Create method", (PairStub("print_receipt"),), "print_receipt", "", "printButton", "clicked")
    assert SERVICE.make_method(surface, request).ok
    assert "def print_receipt(self):" in port.tabs[str(window)]
    assert "*args" not in port.tabs[str(window)]
    assert len(surface.session.log.entries()) == 2
    assert surface.session.log.undo()
    assert port.tabs[str(window)] == before
    from app.features.form_builder.engine.logic.events import read_event

    state = read_event(surface.session.document, "printButton", "clicked")
    assert any(step.verb == "call" and step.method == "print_receipt" for step in state.steps)


def test_a_slot_whose_types_disagree_is_not_connected_by_name() -> None:
    from app.features.form_builder.qtside.inspector.behavior_ext.events import _slot_agrees

    clicked = ("clicked()", "clicked(bool)")
    assert _slot_agrees(("str",), "clicked", clicked) is False
    assert _slot_agrees(("bool",), "clicked", clicked) is True
    assert _slot_agrees((), "clicked", clicked) is True
    assert _slot_agrees(None, "clicked", clicked) is False


def test_stubs_take_self_and_never_star_args() -> None:
    from app.features.form_builder.engine.codegen.window_template import method_lines

    lines = "\n".join(method_lines("    ", "print_receipt", (), "printButton", "clicked", "\n"))
    assert "def print_receipt(self):" in lines
    assert "*args" not in lines
    with_value = "\n".join(method_lines("    ", "print_receipt", ("checked",), "printButton", "clicked", "\n"))
    assert "def print_receipt(self, checked):" in with_value
    assert "*args" not in with_value


def test_the_plan_uses_the_open_tab_when_it_differs_from_disk(tmp_path: Path) -> None:
    disk = (FIXTURE / "sale_window.py").read_text(encoding="utf-8")
    tab = disk.replace("Notes for the next person", "tab only marker")
    surface, window, port = _open(tmp_path, tab, dirty=True)
    window.write_text(disk, encoding="utf-8")
    outcome = SERVICE.make_method(surface, _request())
    assert outcome.ok and outcome.created_method
    edited = port.tabs[str(window)]
    assert "def print_receipt" in edited and "tab only marker" in edited
    assert "def print_receipt" not in window.read_text(encoding="utf-8")
    assert len(surface.session.log.entries()) == 1


def test_a_rejected_form_command_rolls_the_code_edit_back(tmp_path: Path) -> None:
    text = (FIXTURE / "sale_window.py").read_text(encoding="utf-8")
    surface, window, port = _open(tmp_path, text, dirty=True)
    seen: List[str] = []

    class _Refuse:
        command_type: ClassVar[str] = "probe_refuse"

        @property
        def label(self) -> str:
            return "probe"

        def merge_key(self) -> None:
            return None

        def apply(self, doc: object, ctx: object) -> None:
            del doc, ctx
            seen.append(port.tabs[str(window)])
            raise CommandRejected("The name is not allowed.")

    before = port.tabs[str(window)]
    outcome = SERVICE.make_method(surface, _request(_Refuse()))
    assert not outcome.ok and outcome.reason == "The name is not allowed."
    assert seen and "def print_receipt" in seen[0]
    assert port.tabs[str(window)] == before
    assert surface.session.log.entries() == ()


def test_undo_of_an_unedited_stub_restores_the_file_bytes(tmp_path: Path) -> None:
    text = (
        "class SaleWindow(QDialog):\n"
        "    def __init__(self, parent=None):\n"
        "        super().__init__(parent)\n"
        "        self.ui = Ui_Sale()\n"
        "        self.ui.setupUi(self)"
    )
    surface, window, port = _open(tmp_path, text, sync=True)
    original = window.read_bytes()
    assert not original.endswith(b"\n")
    outcome = SERVICE.make_method(surface, _request())
    assert outcome.ok and len(surface.session.log.entries()) == 1
    assert b"def print_receipt" in window.read_bytes()
    assert surface.session.log.undo()
    assert window.read_bytes() == original
    assert surface.session.log.entries() == ()


def test_undo_after_the_stub_body_changed_keeps_the_method(tmp_path: Path) -> None:
    text = (FIXTURE / "sale_window.py").read_text(encoding="utf-8")
    surface, window, port = _open(tmp_path, text, dirty=True)
    assert SERVICE.make_method(surface, _request()).ok
    source = port.tabs[str(window)]
    at = source.rfind("pass")
    edited = source[:at] + "self.close()" + source[at + 4 :]
    assert "self.close()" in edited
    port.tabs[str(window)] = edited
    assert surface.session.log.undo()
    assert "def print_receipt" in port.tabs[str(window)]
    assert "self.close()" in port.tabs[str(window)]
    assert pending_toast(surface) == KEPT


def test_handler_rows_follow_a_saved_window_file(tmp_path: Path) -> None:
    text = (FIXTURE / "sale_window.py").read_text(encoding="utf-8")
    surface, window, port = _open(tmp_path, text, dirty=True)
    surface.session.log.execute(
        SetEventSteps("printButton", "clicked", (call_step("print_receipt"),), caption="Call print_receipt()")
    )
    arm(surface)
    assert _codes(surface) == ["FB201"] or "FB201" in _codes(surface)
    before = list(_codes(surface))
    port.tabs[str(window)] = text.replace(
        "    def show_total(self):",
        "    def print_receipt(self):\r\n        pass\r\n\r\n    def show_total(self):",
        1,
    )
    assert _codes(surface) == before
    surface.code_bridge.notify_saved(str(window))
    assert "FB201" not in _codes(surface)


def test_preview_methods_do_not_read_the_window_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    text = (FIXTURE / "sale_window.py").read_text(encoding="utf-8")
    surface, _window, _port = _open(tmp_path, text)

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("read_window")

    monkeypatch.setattr("app.features.form_builder.engine.project.window_file.read_window", _boom)
    surface.session.log.execute(
        SetEventSteps("printButton", "clicked", (call_step("print_receipt"),), caption="Call print_receipt()")
    )
    assert ("print_receipt", 0) in methods_for(surface.session.document)


def test_a_stand_in_calls_without_importing_the_window_module(qapp: object) -> None:
    del qapp
    from app.features.form_builder.engine.ipc.protocol import Appearance, LoadForm
    from app.features.form_builder.qtside.preview.child.materialize import FormMaterializer

    source = "class Ui_Sale(object):\n    def setupUi(self, host):\n        host.setWindowTitle('Sale')\n"
    request = LoadForm(
        request_id="1",
        view_id="v",
        form_path="sale.ui",
        module_name="ui_sale_probe",
        module_source=source,
        ui_xml=None,
        project_root=None,
        sys_path=(),
        appearance=Appearance(),
        keep_values=False,
        revision=1,
        form_methods=(("print_receipt", 0),),
    )
    called: List[str] = []
    materializer = FormMaterializer()
    materializer.on_would_call = called.append
    before = set(sys.modules)
    built = materializer.build(request, {}, {})
    assert hasattr(built.widget, "print_receipt")
    built.widget.print_receipt(1, 2)  # type: ignore[attr-defined]
    assert called == ["print_receipt"]
    assert "sale_window" not in sys.modules
    assert not any(name.startswith("forms.") for name in set(sys.modules) - before)


def test_connectslotsbyname_is_on_until_the_form_stores_false(tmp_path: Path) -> None:
    root = tmp_path / "shop"
    (root / "forms").mkdir(parents=True)
    ui = root / "forms" / "sale.ui"
    ui.write_text((FIXTURE / "sale.ui").read_text(encoding="utf-8"), encoding="utf-8")
    session = FormSession.open(ui.read_text(encoding="utf-8"), path=str(ui), scope=_scope(root, ui, root / "forms" / "sale_window.py"))
    assert session.document.ui.field("connectslotsbyname") is None
    assert session.document.ui.field("connectslotsbyname") != "false"
    session.log.execute(SetFormField("connectslotsbyname", "false", "Change form setting: connect methods by name"))
    assert session.document.ui.field("connectslotsbyname") == "false"
    assert 'connectslotsbyname">false' in write_ui(session.document).text or "connectslotsbyname" in write_ui(session.document).text
    written = write_ui(session.document).text
    assert "false" in written and "connectslotsbyname" in written
    session.log.execute(SetFormField("connectslotsbyname", None, "Change form setting: connect methods by name"))
    assert session.document.ui.field("connectslotsbyname") is None
    assert "connectslotsbyname" not in write_ui(session.document).text


def _codes(surface: _Surface) -> List[str]:
    return [item.code for item in surface.session.diagnostics.all() if item.code.startswith("FB2")]
