# pyright: reportAttributeAccessIssue=false
"""M6.1a step-list expander and native connections against uic (CONTRACTS 15.6 "Step-list code", UX-LST-004).

* Generated step code is Python 3.9 source and, run under PySide6, runs steps in list order: native steps first,
  off steps never, ``call`` steps get ``args`` values, a call answering False stops the list.
* Connections the engine writes behave like uic's own (oracle; needs ``CBCS_FB_UIC``).
"""

from __future__ import annotations

import ast
import importlib.util
import os
import sys
import types
from pathlib import Path
from typing import Any, List, Tuple

import pytest

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.logic.events_codec import call_step, read_list, slot_step
from app.features.form_builder.engine.logic.intents import m6 as intents
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.reader import read_ui
from tests.form_builder.engine.commands._support import open_log, saved
from tests.form_builder.engine.test_m6_1a_events import ROOT, connection, form

pytestmark = pytest.mark.unit

_HERE = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location("cbcs_uic_compare_m61a", _HERE / "uic_compare.py")
assert _SPEC is not None and _SPEC.loader is not None
_uic = importlib.util.module_from_spec(_SPEC)
sys.modules["cbcs_uic_compare_m61a"] = _uic
_SPEC.loader.exec_module(_uic)

CLEAR = slot_step("nameEdit", "clear()")
FOCUS = slot_step("phoneEdit", "setFocus()")


def generate(text: str, tmp_path: Path) -> str:
    path = tmp_path / "sale.ui"
    path.write_text(text, encoding="utf-8")
    read = read_ui(text, allocator=IdAllocator())
    scope = FormScope(
        kind="project",
        ui_path=str(path),
        project_root=str(tmp_path),
        generated_path=str(tmp_path / "ui_sale.py"),
        window_path=str(tmp_path / "sale_window.py"),
        module_name="ui_sale",
    )
    result = generate_form_module(read.document, scope=scope, source_bytes=text.encode("utf-8"))
    assert result.text is not None, [(d.code, d.message) for d in result.diagnostics]
    assert not [d for d in result.diagnostics if d.code == "FB504"], result.diagnostics
    return result.text


def with_list(*steps_and_flags: Any) -> str:
    """A form whose clearButton has the given steps as one list (some of them off)."""
    log = open_log(form())
    log.execute(SetEventSteps("clearButton", "clicked", tuple(steps_and_flags)))
    return saved(log.document)


def window(source: str, calls: List[Tuple[str, Tuple[Any, ...]]], answers: Any = None) -> Any:
    from PySide6.QtWidgets import QApplication, QDialog

    app = QApplication.instance() or QApplication([])
    del app
    namespace: Any = types.ModuleType("generated_sale")
    exec(compile(source, "ui_sale.py", "exec"), namespace.__dict__)
    answers = answers or {}

    class Window(QDialog):
        def __init__(self) -> None:
            super().__init__()
            self.ui = namespace.Ui_Sale()
            self.ui.setupUi(self)

        def __getattr__(self, name: str) -> Any:
            if name.startswith("m_") or name in ("print_receipt",):
                def method(*args: Any) -> Any:
                    calls.append((name, args))
                    return answers.get(name)

                return method
            raise AttributeError(name)

    return Window()


def test_a_step_list_generates_python_39_with_one_handler_and_one_connect(tmp_path: Path) -> None:
    off = slot_step("phoneEdit", "setFocus()", enabled=False)
    source = generate(with_list(CLEAR, call_step("m_one", 1), off, call_step("m_none", 0)), tmp_path)
    ast.parse(source, feature_version=(3, 9))
    assert source == generate(with_list(CLEAR, call_step("m_one", 1), off, call_step("m_none", 0)), tmp_path)
    assert source.count("self._form = Sale") == 1
    assert source.count("self.clearButton.clicked[bool].connect(self._cbcs_clearButton_clicked)") == 1
    assert "def _cbcs_clearButton_clicked(self, *args):" in source
    assert "# clearButton: When clicked" in source
    assert "#   2. Call m_one()" in source and "#   3. (off) Move focus to phoneEdit" in source
    assert "self.nameEdit.clear()" in source and "self._form.m_one(*args[:1])" in source
    assert "phoneEdit.setFocus" not in source  # an off step is a comment only


def test_a_form_without_lists_generates_exactly_what_it_did(tmp_path: Path) -> None:
    text = form(connection("cancelButton", "clicked()", ROOT, "close()"))
    source = generate(text, tmp_path)
    assert "_cbcs" not in source and "self._form" not in source


def test_steps_run_in_list_order_off_steps_never_and_call_gets_its_values(tmp_path: Path, qapp) -> None:  # type: ignore[no-untyped-def]
    del qapp
    off = slot_step("phoneEdit", "setFocus()", enabled=False)
    text = with_list(call_step("m_none", 0), CLEAR, off, call_step("m_one", 1), slot_step("giftCheck", "toggle()"))
    calls: List[Tuple[str, Tuple[Any, ...]]] = []
    win = window(generate(text, tmp_path), calls)
    win.ui.nameEdit.setText("abc")
    win.ui.giftCheck.setChecked(False)
    win.ui.clearButton.click()
    assert calls == [("m_none", ()), ("m_one", (False,))]
    assert win.ui.nameEdit.text() == "" and win.ui.giftCheck.isChecked() is True
    assert not win.ui.phoneEdit.hasFocus()


def test_a_call_that_answers_false_stops_the_steps_after_it(tmp_path: Path, qapp) -> None:  # type: ignore[no-untyped-def]
    del qapp
    text = with_list(call_step("m_check", 0), CLEAR, slot_step("giftCheck", "toggle()", enabled=False))
    source = generate(text, tmp_path)
    assert "if self._form.m_check() is False:" in source
    for answer, cleared in ((False, False), (None, True), (True, True)):
        calls: List[Tuple[str, Tuple[Any, ...]]] = []
        win = window(source, calls, {"m_check": answer})
        win.ui.nameEdit.setText("keep")
        win.ui.clearButton.click()
        assert calls == [("m_check", ())]
        assert (win.ui.nameEdit.text() == "") is cleared, answer


def test_slot_steps_get_only_the_values_their_parameters_take(tmp_path: Path, qapp) -> None:  # type: ignore[no-untyped-def]
    del qapp
    log = open_log(form())
    off = slot_step("giftCheck", "toggle()", enabled=False)
    log.execute(SetEventSteps("discountCheck", "toggled", (slot_step("giftCheck", "setChecked(bool)"), off)))
    win = window(generate(saved(log.document), tmp_path), [])
    win.ui.discountCheck.setChecked(True)
    assert win.ui.giftCheck.isChecked() is True
    win.ui.discountCheck.setChecked(False)
    assert win.ui.giftCheck.isChecked() is False


def test_native_steps_run_before_the_list_when_an_event_is_in_two_places(tmp_path: Path, qapp) -> None:  # type: ignore[no-untyped-def]
    del qapp
    text = with_list(call_step("m_list", 0), slot_step("giftCheck", "toggle()", enabled=False))
    text = text.replace(
        " <connections/>\n",
        " <connections>\n" + connection("clearButton", "clicked()", ROOT, "m_native()") + " </connections>\n",
    )
    calls: List[Tuple[str, Tuple[Any, ...]]] = []
    win = window(generate(text, tmp_path), calls)
    win.ui.clearButton.click()
    assert [name for name, _ in calls] == ["m_native", "m_list"]


def test_a_list_this_build_cannot_run_generates_nothing(tmp_path: Path) -> None:
    message = read_list('[{"do": "message", "text": "hi"}]').steps[0]
    source = generate(with_list(CLEAR, message), tmp_path)  # one unknown verb: the event does nothing
    assert "_cbcs" not in source
    broken = with_list(CLEAR, slot_step("phoneEdit", "setFocus()", enabled=False)).replace("&quot;do&quot;", "&quot;doo")
    assert "_cbcs" not in generate(broken.replace("[\n", "[\n  not json,\n", 1), tmp_path)


def test_a_step_whose_target_left_the_form_is_a_comment_not_a_crash(tmp_path: Path, qapp) -> None:  # type: ignore[no-untyped-def]
    del qapp
    text = with_list(CLEAR, slot_step("phoneEdit", "setFocus()", enabled=False), call_step("m_none", 0))
    text = text.replace("&quot;target&quot;: &quot;nameEdit&quot;", "&quot;target&quot;: &quot;gone&quot;")
    source = generate(text, tmp_path)
    assert "(missing gone)" in source
    calls: List[Tuple[str, Tuple[Any, ...]]] = []
    window(source, calls).ui.clearButton.click()
    assert calls == [("m_none", ())]


_HOSTILE = (
    '[{"do": "call", "method": "x(); __import__(\'os\').system(\'echo PWN\'); y"}]',
    '[{"do": "slot", "target": "gone\\n__import__(\'os\')\\n#", "slot": "clear()"}]',
    '[{"do": "slot", "target": "nameEdit", "slot": "clear\\n__import__(\'os\')\\nx()"}]',
    '[{"do": "slot", "target": "nameEdit", "slot": "clear(); __import__(\'os\'); x()"}]',
    '[{"do": "slot", "target": "gone\\r__import__(\'os\')", "slot": "clear()"}, '
    '{"do": "slot", "target": "nameEdit", "slot": "clear()", "enabled": false}]',
)


@pytest.mark.parametrize("text", _HOSTILE)
def test_no_text_in_a_step_list_becomes_code(text: str, tmp_path: Path) -> None:
    from xml.sax.saxutils import escape

    prop = '<property name="cbcsOnClicked" stdset="0"><string notr="true">%s</string></property>' % escape(text)
    source = generate(
        form().replace(
            '<widget class="QPushButton" name="clearButton"/>',
            '<widget class="QPushButton" name="clearButton">%s</widget>' % prop,
        ),
        tmp_path,
    )
    tree = ast.parse(source, feature_version=(3, 9))
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == "__import__"]
    assert "\r" not in source


def test_a_native_clicked_bool_connection_passes_checked_like_uic(tmp_path: Path, qapp) -> None:  # type: ignore[no-untyped-def]
    """PySide6 connects bare ``clicked`` as ``clicked()``; uic writes ``clicked["bool"]`` so a slot gets ``checked``."""
    del qapp
    log = open_log(form())
    log.execute(SetEventSteps("clearButton", "clicked", (slot_step("giftCheck", "setChecked(bool)"),)))
    text = saved(log.document)
    assert "<signal>clicked(bool)</signal>" in text and "cbcs" not in text
    source = generate(text.replace('name="clearButton"/>', 'name="clearButton"><property name="checkable"><bool>true</bool></property></widget>'), tmp_path)
    assert 'self.clearButton.clicked["bool"].connect(self.giftCheck.setChecked)' in source
    win = window(source, [])
    win.ui.clearButton.click()
    assert win.ui.giftCheck.isChecked() is True


@pytest.mark.logic("L-runtime-connect")
def test_a_call_reaches_the_window_method_natively_and_from_a_list(tmp_path: Path, qapp) -> None:  # type: ignore[no-untyped-def]
    """LOGIC_DESIGN 3.5: the form object is the receiver, so a method of the window class is there when ``setupUi`` runs."""
    del qapp
    from PySide6.QtWidgets import QDialog

    seen: List[str] = []

    def build(text: str) -> Any:
        namespace: Any = types.ModuleType("generated_sale_3_5")
        exec(compile(generate(text, tmp_path), "ui_sale.py", "exec"), namespace.__dict__)

        class Window(QDialog):
            def __init__(self) -> None:
                super().__init__()
                self.ui = namespace.Ui_Sale()
                self.ui.setupUi(self)

            def save_invoice(self, *args: Any) -> None:
                seen.append("save_invoice%s" % (args,))

        return Window()

    native = open_log(form())
    native.execute(SetEventSteps("clearButton", "clicked", (call_step("save_invoice", 0),)))
    assert "cbcs" not in saved(native.document)
    first = build(saved(native.document))
    first.ui.clearButton.click()
    assert seen == ["save_invoice()"]
    listed = open_log(form())
    listed.execute(SetEventSteps("clearButton", "clicked", (call_step("save_invoice", 1), slot_step("nameEdit", "clear()", enabled=False))))
    assert "cbcsOnClicked" in saved(listed.document)
    second = build(saved(listed.document))
    second.ui.clearButton.click()
    assert seen == ["save_invoice()", "save_invoice(False,)"]



# --- native connections against uic (oracle) ------------------------------------------------


@pytest.fixture
def uic_env(monkeypatch):  # type: ignore[no-untyped-def]
    uic = os.environ.get("CBCS_FB_UIC", "") or "/Applications/FreeCAD.app/Contents/Resources/lib/qt6/uic"
    if not Path(uic).is_file():
        pytest.skip("CBCS_FB_UIC is not set")
    monkeypatch.setenv("CBCS_FB_UIC", uic)


def _oracle(tmp_path: Path, text: str, name: str) -> Tuple[object, ...]:
    path = tmp_path / ("%s.ui" % name)
    path.write_text(text, encoding="utf-8")
    result = _uic.compare(path)
    print("ORACLE %s %s" % (name, result[0]))
    return result


def _engine_made_form() -> str:
    log = open_log(form())
    classes = QtClassTable.shared()
    by_id = {i.intent_id: i for i in intents.INTENTS}
    log.execute(intents.command(log.document, classes, by_id["close-form"], "cancelButton"))
    log.execute(intents.command(log.document, classes, by_id["clear-field"], "clearButton", "nameEdit"))
    log.execute(intents.command(log.document, classes, by_id["move-focus"], "clearButton", "phoneEdit"))
    log.execute(intents.command(log.document, classes, by_id["check-same-way"], "discountCheck", "giftCheck"))
    log.execute(intents.command(log.document, classes, by_id["keep-in-step"], "qtySpin", "qtySlider"))
    log.execute(intents.command(log.document, classes, by_id["show-page"], "customerCombo", "tabs"))
    log.execute(intents.command(log.document, classes, by_id["buttons-accept-reject"], "buttonBox"))
    log.execute(
        SetEventSteps("giftCheck", "clicked", (slot_step("discountCheck", "setChecked(bool)"), slot_step("nameEdit", "selectAll()")))
    )
    return saved(log.document)


def test_connections_the_engine_writes_match_uic(tmp_path: Path, qapp, uic_env) -> None:  # type: ignore[no-untyped-def]
    del qapp, uic_env
    text = _engine_made_form()
    assert text.count("<connection>") == 11 and "cbcs" not in text
    result = _oracle(tmp_path, text, "engine_made")
    assert result[0] == "ok", result


def test_a_form_method_connection_fails_or_works_exactly_as_uic(tmp_path: Path, qapp, uic_env) -> None:  # type: ignore[no-untyped-def]
    del qapp, uic_env
    log = open_log(form())
    log.execute(SetEventSteps("cancelButton", "clicked", (call_step("print_receipt", 0),)))
    log.execute(SetEventSteps("discountCheck", "toggled", (call_step("on_discount", 1), slot_step("giftCheck", "setChecked(bool)"))))
    text = saved(log.document)
    assert text.count("<slot>print_receipt()</slot>") == 2  # one connection, one declaration
    result = _oracle(tmp_path, text, "form_methods")
    # A plain QDialog has no print_receipt: uic and our module hit the same AttributeError.
    assert result[0] in ("ok", "same-error", "env"), result


def test_a_hand_edited_designer_file_keeps_its_hints_and_still_matches_uic(tmp_path: Path, qapp, uic_env) -> None:  # type: ignore[no-untyped-def]
    del qapp, uic_env
    start = form(
        connection("clearButton", "clicked()", "nameEdit", "clear()", hints=True)
        + connection("cancelButton", "clicked()", ROOT, "close()")
    )
    log = open_log(start)
    log.execute(SetEventSteps("clearButton", "clicked", (CLEAR, slot_step("phoneEdit", "clear()"), FOCUS)))
    text = saved(log.document)
    assert text.count("<hints>") == 1
    result = _oracle(tmp_path, text, "designer_hints")
    assert result[0] == "ok", result
