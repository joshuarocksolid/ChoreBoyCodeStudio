# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""M6.0s seams, Qt-free halves: discovery by module, the code bridge, the handler service, Method.params, Problems code rows."""

from __future__ import annotations

import ast
import os
import stat
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pytest

from app.features.form_builder.engine import contributors
from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.codegen.logic_hooks import Contribution, Method
from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.diagnostics import DiagnosticLocation, FormDiagnostic, Severity
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.logic import intents
from app.features.form_builder.engine.project import written_files
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.integration import code_bridge, handlers, problems_bridge
from app.features.form_builder.integration.code_bridge import BridgeEdit, CodeBridge
from tests.form_builder.m5_0s_support import forget_package, make_package

pytestmark = [pytest.mark.unit]

FIXTURE = Path(__file__).parent / "fixtures" / "m6"


# --------------------------------------------------------------------- intents


_INTENTS = {
    "m7_rules": """
        from app.features.form_builder.engine.logic.intents import Intent

        def register(registry):
            registry.add(Intent("probe.rule", "Enable only when...", lambda sender, target: (), event="toggled"))
    """,
    "m6_basic": """
        from app.features.form_builder.engine.logic.intents import Intent

        def steps(sender, target):
            return ({"do": "slot", "target": "form", "slot": "close()"},)

        def register(registry):
            registry.add(Intent("probe.close", "Close this form", steps, sender_classes=("QAbstractButton",), event="clicked"))
            registry.add(Intent("probe.any", "Do anything", steps))
    """,
    "broken": "def register(registry):\n    raise RuntimeError('lane bug')\n",
    "_helper": "raise SystemExit\n",
}


def test_intents_register_from_new_files_in_module_order_and_filter_by_sender(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = make_package(tmp_path, monkeypatch, "m6_intent_probe", _INTENTS)
    try:
        registry = intents.load_intents(package)
        # Sorted module names (broken, m6_basic, m7_rules), registration order inside a module.
        assert [intent.intent_id for intent in registry.all()] == ["probe.close", "probe.any", "probe.rule"]
        assert [i.intent_id for i in registry.for_classes(("QPushButton", "QAbstractButton", "QWidget"))] == [
            "probe.close",
            "probe.any",
            "probe.rule",
        ]
        assert [i.intent_id for i in registry.for_classes(("QLineEdit",))] == ["probe.any", "probe.rule"]
        # "+ Then..." keeps the current event's intents and the ones that follow any event.
        assert [i.intent_id for i in registry.for_classes(("QAbstractButton",), event="clicked")] == [
            "probe.close",
            "probe.any",
        ]
        assert contributors.FAILURES.pop("m6_intent_probe.broken").startswith("step intent: RuntimeError")
        with pytest.raises(ValueError):
            registry.add(registry.get("probe.any"))
    finally:
        forget_package("m6_intent_probe")


def test_every_m6_seam_loads_its_product_modules_without_a_failure(qapp) -> None:  # type: ignore[no-untyped-def]
    del qapp
    from app.features.form_builder.integration import activate_ext, overlay_ext
    from app.features.form_builder.qtside.inspector import behavior_ext

    intents.load_intents(intents)
    activate_ext.load_activators(activate_ext)
    overlay_ext.load_overlay_kinds(overlay_ext)
    behavior_ext.load_sections(behavior_ext)
    assert {name: why for name, why in contributors.FAILURES.items() if name.startswith("app.")} == {}


# ----------------------------------------------------------------- code bridge


class _Port:
    """A window with one open tab: a text buffer, a dirty flag, and a record of what the bridge asked."""

    def __init__(self, tabs: Dict[str, str], dirty: Sequence[str] = ()) -> None:
        self.tabs = dict(tabs)
        self.dirty = set(dirty)
        self.calls: List[tuple] = []

    def open_text(self, path: str) -> Optional[str]:
        return self.tabs.get(path)

    def replace_range(self, path: str, start: int, end: int, text: str) -> bool:
        self.calls.append(("replace", path, start, end, text))
        current = self.tabs[path]
        self.tabs[path] = current[:start] + text + current[end:]
        self.dirty.add(path)
        return True

    def is_dirty(self, path: str) -> bool:
        return path in self.dirty

    def save(self, path: str) -> bool:
        self.calls.append(("save", path))
        self.dirty.discard(path)
        return True

    def show(self, path: str, line: int, select) -> bool:  # type: ignore[no-untyped-def]
        self.calls.append(("show", path, line, select))
        return True


def _project(tmp_path: Path) -> Tuple[Path, Path]:
    root = tmp_path / "shop"
    (root / "forms").mkdir(parents=True)
    window = root / "forms" / "sale_window.py"
    window.write_bytes((FIXTURE / "forms" / "sale_window.py").read_bytes())
    return root, window


def _end_of_class_edit(text: str, method: str = "    def print_receipt(self):\r\n        pass\r\n") -> BridgeEdit:
    marker = "    # Notes for the next person"
    at = text.index(marker)
    return BridgeEdit(at, at, method + "\r\n")


def test_closed_file_is_written_atomically_keeping_mode_line_endings_and_everything_else(tmp_path: Path) -> None:
    root, window = _project(tmp_path)
    os.chmod(window, 0o640)
    before = window.read_bytes()
    text = before.decode("utf-8")
    seen: List[Sequence[str]] = []
    previous = written_files.set_written_file_listener(seen.append)
    saved: List[str] = []
    try:
        bridge = CodeBridge(str(root), _Port({}))
        bridge.on_saved(saved.append)
        edit = _end_of_class_edit(text)
        result = bridge.apply(str(window), edit, base_text=text)
    finally:
        written_files.set_written_file_listener(previous)
    assert result.ok and result.mode == "disk" and result.saved and not result.created
    after = window.read_bytes()
    assert after == before[: edit.start] + edit.text.encode() + before[edit.start :]
    assert b"\n" not in after.replace(b"\r\n", b"")  # still CRLF all through
    assert stat.S_IMODE(os.stat(window).st_mode) == 0o640
    assert [p.name for p in window.parent.iterdir() if p.name.endswith(".tmp")] == []
    assert seen == [(str(window),)] and saved == [str(window)]
    # The inverse puts the original bytes back exactly.
    inverse = result.inverse
    assert inverse is not None
    restored = bridge.apply(str(window), inverse)
    assert restored.ok and window.read_bytes() == before


def test_a_missing_window_file_is_created_and_a_stale_plan_or_outside_path_is_refused(tmp_path: Path) -> None:
    root, window = _project(tmp_path)
    bridge = CodeBridge(str(root), _Port({}))
    fresh = root / "forms" / "new_window.py"
    created = bridge.apply(str(fresh), BridgeEdit(0, 0, "class NewWindow:\n    pass\n"))
    assert created.ok and created.created and fresh.read_text() == "class NewWindow:\n    pass\n"
    stale = bridge.apply(str(window), BridgeEdit(0, 0, "# x\r\n"), base_text="not what is on disk")
    assert not stale.ok and stale.reason == code_bridge.CHANGED
    outside = tmp_path / "elsewhere.py"
    outside.write_text("x = 1\n")
    assert not bridge.apply(str(outside), BridgeEdit(0, 0, "# x\n")).ok
    assert outside.read_text() == "x = 1\n"
    link = root / "forms" / "link.py"
    link.symlink_to(outside)
    escaped = bridge.apply(str(link), BridgeEdit(0, 0, "# x\n"))
    assert not escaped.ok and escaped.reason == code_bridge.OUTSIDE
    assert outside.read_text() == "x = 1\n"
    assert bridge.text_of(str(link)) is None
    assert not bridge.open_at(str(outside), 3)


def test_an_open_tab_gets_one_edit_and_is_saved_only_when_it_was_clean(tmp_path: Path) -> None:
    root, window = _project(tmp_path)
    text = window.read_bytes().decode("utf-8").replace("\r\n", "\n")
    path = str(window)
    edit = BridgeEdit(len(text), len(text), "\n    def extra(self):\n        pass\n")

    clean = _Port({path: text})
    bridge = CodeBridge(str(root), clean)
    heard: List[str] = []
    bridge.on_saved(heard.append)
    assert bridge.text_of(path) == text
    result = bridge.apply(path, edit, base_text=text)
    assert result.ok and result.mode == "tab" and result.saved
    assert [call[0] for call in clean.calls] == ["replace", "save"]
    assert heard == [path]
    assert window.read_bytes().decode("utf-8").replace("\r\n", "\n") == text  # the bridge never wrote the file itself

    unsaved = _Port({path: text}, dirty=[path])
    result = CodeBridge(str(root), unsaved).apply(path, edit)
    assert result.ok and not result.saved
    assert [call[0] for call in unsaved.calls] == ["replace"]  # the person's own unsaved work stays unsaved
    assert path in unsaved.dirty

    stale = _Port({path: text + "# typed since the plan\n"})
    assert CodeBridge(str(root), stale).apply(path, edit, base_text=text).reason == code_bridge.CHANGED
    assert stale.calls == []


def test_the_shell_port_edits_the_tabs_document_as_one_undo_step_in_utf16_positions(qapp) -> None:  # type: ignore[no-untyped-def]
    del qapp
    from types import SimpleNamespace

    from app.qt.QtWidgets import QPlainTextEdit

    editor = QPlainTextEdit()
    original = "# 😀 fish\nclass A:\n    pass\n"
    editor.setPlainText(original)
    editor.document().setModified(False)
    window = SimpleNamespace(_workspace_controller=SimpleNamespace(widget_for_path=lambda path: editor))
    port = code_bridge.ShellPort(window)
    at = original.index("class")
    assert port.open_text("a.py") == original
    assert port.replace_range("a.py", at, at, "# new\n")
    assert editor.toPlainText() == "# 😀 fish\n# new\nclass A:\n    pass\n"
    editor.undo()
    assert editor.toPlainText() == original


# ------------------------------------------------------------- handler service


class _Log:
    def __init__(self, reject: bool = False) -> None:
        self.reject = reject
        self.opened: List[str] = []
        self.ran: List[object] = []

    def transaction(self, label: str):  # type: ignore[no-untyped-def]
        from contextlib import contextmanager

        @contextmanager
        def scope():  # type: ignore[no-untyped-def]
            self.opened.append(label)
            yield

        return scope()

    def execute(self, command: object) -> None:
        if self.reject:
            raise CommandRejected("No.")
        self.ran.append(command)


def test_default_handler_service_commits_steps_in_one_transaction_and_writes_no_code() -> None:
    from types import SimpleNamespace

    handlers.set_service(None)
    default = handlers.service()
    assert isinstance(default, handlers.DefaultHandlerService)
    log = _Log()
    surface = SimpleNamespace(session=SimpleNamespace(log=log, scope=FormScope(kind="external", ui_path="/x/a.ui")))
    done = default.make_method(surface, handlers.MethodRequest("Write code for Save clicked", ("a", "b"), method="save"))
    assert done.ok and not done.created_method
    assert log.opened == ["Write code for Save clicked"] and log.ran == ["a", "b"]
    refused = default.make_method(
        SimpleNamespace(session=SimpleNamespace(log=_Log(reject=True))), handlers.MethodRequest("x", ("a",))
    )
    assert not refused.ok and refused.reason == "No."
    assert default.methods(surface) == () and default.go_to(surface, "save") is False


def test_handler_service_is_found_in_handlers_code_without_editing_this_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = make_package(
        tmp_path, monkeypatch, "m6_handlers_probe", {"handlers_code": "class S:\n    pass\n\nSERVICE = S()\n"}
    )
    try:
        monkeypatch.setattr(handlers, "CODE_MODULE", "m6_handlers_probe.handlers_code")
        monkeypatch.setattr(handlers, "_CODE_LOOKED", False)
        monkeypatch.setattr(handlers, "_CODE", None)
        found = handlers.service()
        assert type(found).__name__ == "S" and found is package.handlers_code.SERVICE
        handlers.set_service(handlers.DefaultHandlerService())
        assert isinstance(handlers.service(), handlers.DefaultHandlerService)
    finally:
        handlers.set_service(None)
        forget_package("m6_handlers_probe")


# ----------------------------------------------------------- Method.params


def test_a_generated_method_can_take_parameters_and_the_default_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Steps:
        expander_id = "probe_steps"
        level = 1
        order = 100

        def contribute(self, doc, ctx):  # type: ignore[no-untyped-def]
            del doc, ctx
            return Contribution(
                setup_lines=("self._cbcs_a(1)",),
                methods=(
                    Method("_cbcs_saveButton_clicked", "pass", "saveButton: When clicked", params="*args"),
                    Method("_cbcs_plain", "pass", "x"),
                ),
            )

    monkeypatch.setattr("app.features.form_builder.engine.codegen.emit.load_expanders", lambda: (Steps(),))
    ui = tmp_path / "forms"
    ui.mkdir()
    path = ui / "sale.ui"
    path.write_bytes((FIXTURE / "forms" / "sale.ui").read_bytes())
    scope = FormScope(
        kind="project",
        ui_path=str(path),
        project_root=str(tmp_path),
        generated_path=str(ui / "ui_sale.py"),
        window_path=str(ui / "sale_window.py"),
        module_name="forms.ui_sale",
        window_module_name="forms.sale_window",
    )
    document = read_ui(path.read_text(encoding="utf-8"), allocator=IdAllocator()).document
    result = generate_form_module(document, scope=scope, source_bytes=path.read_bytes())
    assert result.text is not None
    assert "    def _cbcs_saveButton_clicked(self, *args):" in result.text
    assert "    def _cbcs_plain(self):" in result.text
    ast.parse(result.text, feature_version=(3, 9))


# ------------------------------------------------------------ Problems rows


def test_a_problem_in_code_carries_its_file_and_line_to_the_row() -> None:
    in_code = FormDiagnostic(
        "FB209",
        Severity.WARNING,
        "sale_window.py can't be read.",
        DiagnosticLocation(code_path="forms/sale_window.py", code_line=7),
        "handlers",
    )
    in_form = FormDiagnostic("FB209", Severity.WARNING, "x", DiagnosticLocation(object_name="saveButton", line=12), "handlers")
    rows = {
        row.message: row for row in problems_bridge.code_diagnostics_for_form("/p/forms/sale.ui", (in_code, in_form))
    }
    code_row = dict(rows["sale_window.py can't be read."].detail or {})
    assert code_row["fb_code_path"] == "forms/sale_window.py" and code_row["fb_code_line"] == "7"
    assert code_row["location_label"] == "sale_window.py:7"
    plain = dict(rows["saveButton: x"].detail or {})
    assert "fb_code_path" not in plain and plain["location_label"] == "saveButton"


def test_double_click_on_a_code_row_opens_the_code_only_when_no_widget_is_named(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from app.features.form_builder.integration.surface import FormSurface

    port = _Port({})
    stub = SimpleNamespace(
        _request=SimpleNamespace(project_root=str(tmp_path)),
        code_bridge=CodeBridge(str(tmp_path), port),
    )
    detail = {"fb_code_path": "forms/sale_window.py", "fb_code_line": "9"}
    assert FormSurface._reveal_code(stub, detail) is True
    assert port.calls == [("show", str(tmp_path / "forms" / "sale_window.py"), 9, None)]
    assert FormSurface._reveal_code(stub, {"fb_object": "saveButton"}) is False
    assert FormSurface._reveal_code(stub, {"fb_code_path": "../outside.py"}) is False


# ------------------------------------------------------------------ fixtures


def test_the_m6_fixture_project_reads_clean_and_keeps_its_bytes() -> None:
    for name in ("sale.ui", "designer_made.ui"):
        text = (FIXTURE / "forms" / name).read_text(encoding="utf-8")
        scope = FormScope(kind="external", ui_path=str(FIXTURE / "forms" / name))
        session = FormSession.open(text, path=scope.ui_path, scope=scope)
        try:
            assert [d.code for d in session.diagnostics.all() if d.severity is Severity.ERROR] == []
            assert session.text() == text
        finally:
            session.dispose()
    window = (FIXTURE / "forms" / "sale_window.py").read_bytes()
    assert window.count(b"\r\n") == window.count(b"\n") > 10
    ast.parse(window.decode("utf-8"))
