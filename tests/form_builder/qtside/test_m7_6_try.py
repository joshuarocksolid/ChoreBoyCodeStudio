# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""M7.6 Try mode: the preview child runs behavior without importing the window file."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List

import pytest

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.ipc.protocol import (
    Appearance,
    LoadForm,
    Log,
    Response,
    TryStart,
    encode_frame,
)
from app.features.form_builder.engine.logic.checks import Preset, write_checks
from app.features.form_builder.engine.logic.events_codec import EventStep, call_step, slot_step, write_list
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.qtside.preview.child.session import ChildSession
from app.features.form_builder.integration.preview_notice import preview_request
from app.qt.QtWidgets import QApplication, QLineEdit, QWidget

pytestmark = pytest.mark.unit

_FORMS = Path(__file__).resolve().parents[1] / "fixtures" / "m7" / "forms"
_INVOICE = _FORMS / "invoice.ui"
_EMAIL = "Enter an email address like name@example.com"
_STOPPED = "Save is clicked: stopped at step 1 (Check all fields)"
_WOULD = "Would call save_invoice()"


class _Writer:
    def __init__(self) -> None:
        self.sent: List[object] = []

    def send(self, message: object) -> None:
        self.sent.append(message)


def _prop(name: str, text: str) -> str:
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
    return '<property name="%s" stdset="0"><string notr="true">%s</string></property>' % (name, escaped)


def _invoice_text() -> str:
    checks = write_checks((Preset("email", None),))
    assert checks is not None
    steps = write_list((EventStep("validate"), call_step("save_invoice")))
    text = _INVOICE.read_text(encoding="utf-8")
    text = text.replace(
        '<widget class="QLineEdit" name="discountEdit"/>',
        '<widget class="QLineEdit" name="discountEdit">%s</widget>' % _prop("cbcsEnabledWhen", "discountCheck"),
    )
    text = text.replace(
        '<widget class="QLabel" name="lineTotalLabel"/>',
        '<widget class="QLabel" name="lineTotalLabel">%s</widget>'
        % (_prop("cbcsValue", "qtySpin * priceSpin") + _prop("cbcsFormat", "money")),
    )
    text = text.replace(
        '<widget class="QLineEdit" name="emailEdit"/>',
        '<widget class="QLineEdit" name="emailEdit">%s</widget>' % _prop("cbcsValidate", checks),
    )
    text = text.replace(
        "</widget>\n   </item>\n  </layout>\n </widget>",
        "%s</widget>\n   </item>\n  </layout>\n </widget>" % _prop("cbcsOnClicked", steps),
    )
    return text


def _window_text(extra: str = "") -> str:
    """A window class ``read_window`` accepts. It is never imported."""
    return (
        "from PySide6.QtWidgets import QDialog\n"
        "from forms.ui_invoice import Ui_Invoice\n"
        "\n"
        "class InvoiceWindow(QDialog):\n"
        "    def __init__(self, parent=None):\n"
        "        super().__init__(parent)\n"
        "        self.ui = Ui_Invoice()\n"
        "        self.ui.setupUi(self)\n"
        "\n"
        "    def save_invoice(self):\n"
        "        pass\n"
        "%s" % extra
    )


def _scope(tmp_path: Path, text: str, name: str = "invoice") -> tuple:
    path = tmp_path / "forms" / ("%s.ui" % name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    window = path.parent / ("%s_window.py" % name)
    if not window.exists():
        window.write_text(_window_text(), encoding="utf-8")
    read = read_ui(text, allocator=IdAllocator())
    scope = FormScope(
        kind="project",
        ui_path=str(path),
        project_root=str(tmp_path),
        generated_path=str(path.parent / ("ui_%s.py" % name)),
        window_path=str(window),
        module_name="ui_%s" % name,
    )
    return read.document, scope, path


class _Session:
    def __init__(self, document: object, scope: object) -> None:
        self.document = document
        self.scope = scope


def _send(child: ChildSession, message: object) -> None:
    child._handle_line(encode_frame(message))  # noqa: SLF001


def _logs(writer: _Writer) -> List[Log]:
    return [item for item in writer.sent if isinstance(item, Log) and item.stream == "try"]


def _try(child: ChildSession, session: _Session, path: Path, *, keep_values: bool = False, values: tuple = ()) -> None:
    message = preview_request(
        session,
        str(path),
        "v1",
        run_behavior=True,
        keep_values=keep_values,
        window_values=values,
        appearance=Appearance(title="Preview · invoice"),
    )
    assert isinstance(message, TryStart)
    assert message.show_form is True
    _send(child, message)


@pytest.fixture
def child(qapp: QApplication):  # type: ignore[no-untyped-def]
    writer = _Writer()
    session = ChildSession(writer, qapp)
    before_path = list(sys.path)
    before_modules = dict(sys.modules)
    yield session, writer
    for view_id in list(session._views):  # noqa: SLF001
        widget = session._views.pop(view_id).widget  # noqa: SLF001
        widget.hide()
        widget.deleteLater()
    qapp.processEvents()
    qapp.removeEventFilter(session._user_close)  # noqa: SLF001
    sys.path[:] = before_path
    for name in list(sys.modules):
        if name not in before_modules:
            sys.modules.pop(name, None)
    for name, module in before_modules.items():
        sys.modules[name] = module


def test_invoice_preview_logs_the_behavior_in_order(child, qapp: QApplication, tmp_path: Path) -> None:
    session_child, writer = child
    text = _invoice_text()
    document, scope, path = _scope(tmp_path, text)
    _try(session_child, _Session(document, scope), path)
    answer = [item for item in writer.sent if isinstance(item, Response)][-1]
    assert answer.ok, answer.detail
    qapp.processEvents()
    shell = session_child._views["v1"].widget  # noqa: SLF001
    assert shell.objectName() == "formBuilder.previewShell"
    discount = shell.findChild(QWidget, "discountEdit")
    check = shell.findChild(QWidget, "discountCheck")
    qty = shell.findChild(QWidget, "qtySpin")
    price = shell.findChild(QWidget, "priceSpin")
    total = shell.findChild(QWidget, "lineTotalLabel")
    email = shell.findChild(QLineEdit, "emailEdit")
    save = shell.findChild(QWidget, "saveButton")
    assert discount is not None and check is not None and email is not None and save is not None
    assert discount.isEnabled() is False
    check.setChecked(True)  # type: ignore[attr-defined]
    qapp.processEvents()
    assert discount.isEnabled() is True
    qty.setValue(2)  # type: ignore[attr-defined]
    price.setValue(3)  # type: ignore[attr-defined]
    qapp.processEvents()
    assert total.text() == "$6.00"  # type: ignore[attr-defined]
    email.setText("not-an-email")
    email.editingFinished.emit()
    qapp.processEvents()
    assert email.toolTip() == _EMAIL
    save.click()  # type: ignore[attr-defined]
    qapp.processEvents()
    email.setText("name@example.com")
    save.click()  # type: ignore[attr-defined]
    qapp.processEvents()
    texts = [item.text for item in _logs(writer)]
    check_at = texts.index("Check emailEdit: %s" % _EMAIL)
    stopped_at = texts.index(_STOPPED)
    would_at = texts.index(_WOULD)
    assert check_at < stopped_at < would_at
    assert any(item.startswith("Rules ran (") for item in texts)
    assert shell.findChild(QWidget, "preview.whatRan") is not None
    assert shell.findChild(QWidget, "preview.whatRan.clear") is not None
    assert shell.findChild(QWidget, "preview.whatRan.copy") is not None


def test_preview_never_imports_the_window_file(child, qapp: QApplication, tmp_path: Path) -> None:
    session_child, writer = child
    marker = tmp_path / "imported.txt"
    text = _INVOICE.read_text(encoding="utf-8").replace(
        '<widget class="QLabel" name="lineTotalLabel"/>',
        '<widget class="QLabel" name="lineTotalLabel">%s</widget>' % _prop("cbcsValue", "window.note()"),
    )
    document, scope, path = _scope(tmp_path, text)
    window = Path(scope.window_path)
    window.write_text(
        "open(%r, 'w').write('imported')\n" % str(marker) + _window_text("\n    def note(self) -> str:\n        return 'secret'\n"),
        encoding="utf-8",
    )
    _try(session_child, _Session(document, scope), path)
    answer = [item for item in writer.sent if isinstance(item, Response)][-1]
    assert answer.ok, answer.detail
    qapp.processEvents()
    assert not marker.exists()
    assert "forms.invoice_window" not in sys.modules
    assert not any(name.endswith("invoice_window") for name in sys.modules)


def test_needs_value_once_then_the_formula_uses_the_strip(child, qapp: QApplication, tmp_path: Path) -> None:
    session_child, writer = child
    text = _INVOICE.read_text(encoding="utf-8").replace(
        '<widget class="QLabel" name="lineTotalLabel"/>',
        '<widget class="QLabel" name="lineTotalLabel">%s</widget>' % _prop("cbcsValue", "window.note()"),
    )
    document, scope, path = _scope(tmp_path, text)
    Path(scope.window_path).write_text(
        _window_text("\n    def note(self) -> str:\n        return 'secret'\n"),
        encoding="utf-8",
    )
    _try(session_child, _Session(document, scope), path)
    qapp.processEvents()
    shell = session_child._views["v1"].widget  # noqa: SLF001
    ui = shell.form_ui
    ui.cbcs_refresh()
    qapp.processEvents()
    ui.cbcs_refresh()
    qapp.processEvents()
    needs = [item for item in _logs(writer) if item.kind == "needs_value"]
    assert [item.text for item in needs] == ["note() needs a window value"]
    box = shell.findChild(QLineEdit, "preview.windowValue.note")
    assert box is not None
    box.setText("9")
    qapp.processEvents()
    total = shell.findChild(QWidget, "lineTotalLabel")
    assert total.text() == "9"  # type: ignore[attr-defined]


def test_a_step_traceback_is_one_log_line_and_the_preview_stays(child, qapp: QApplication, tmp_path: Path) -> None:
    session_child, writer = child
    steps = write_list((slot_step("emailEdit", "missingSlot()"),))
    text = _INVOICE.read_text(encoding="utf-8").replace(
        "</widget>\n   </item>\n  </layout>\n </widget>",
        "%s</widget>\n   </item>\n  </layout>\n </widget>" % _prop("cbcsOnClicked", steps),
    )
    document, scope, path = _scope(tmp_path, text)
    _try(session_child, _Session(document, scope), path)
    qapp.processEvents()
    before = len(writer.sent)
    shell = session_child._views["v1"].widget  # noqa: SLF001
    save = shell.findChild(QWidget, "saveButton")
    save.click()  # type: ignore[attr-defined]
    qapp.processEvents()
    fresh = [item for item in writer.sent[before:] if isinstance(item, Log) and item.kind == "step"]
    assert len(fresh) == 1
    assert "saveButton: When clicked" in fresh[0].text
    assert "AttributeError" in fresh[0].text
    assert "\n" not in fresh[0].text
    assert session_child._views["v1"].widget.isVisible()  # noqa: SLF001
    save.click()  # type: ignore[attr-defined]
    qapp.processEvents()
    assert session_child._views["v1"].widget.isVisible()  # noqa: SLF001


def test_run_behavior_off_matches_the_untraced_module(tmp_path: Path) -> None:
    document, scope, path = _scope(tmp_path, _invoice_text())
    session = _Session(document, scope)
    plain = generate_form_module(document, scope=scope, source_bytes=None)
    chosen = preview_request(session, str(path), "v1", run_behavior=False)
    assert isinstance(chosen, LoadForm)
    assert chosen.module_source == plain.text
    assert plain.text is not None and "_cbcs_trace" not in plain.text
    ast.parse(plain.text, feature_version=(3, 9))
    traced = preview_request(session, str(path), "v1", run_behavior=True)
    assert isinstance(traced, TryStart)
    assert traced.module_source is not None and "_cbcs_trace" in traced.module_source
    assert traced.module_source != plain.text


@pytest.mark.perf
def test_reload_keeps_field_values_within_500ms(child, qapp: QApplication, tmp_path: Path) -> None:
    session_child, writer = child
    document, scope, path = _scope(tmp_path, _invoice_text())
    session = _Session(document, scope)
    _try(session_child, session, path)
    qapp.processEvents()
    shell = session_child._views["v1"].widget  # noqa: SLF001
    email = shell.findChild(QLineEdit, "emailEdit")
    email.setText("kept@example.com")
    changed = _invoice_text().replace("discountCheck", "discountCheck")
    # A real edit: the enabled rule gains a space the generator still accepts.
    changed = changed.replace(
        _prop("cbcsEnabledWhen", "discountCheck"),
        _prop("cbcsEnabledWhen", "discountCheck "),
    )
    load = subprocess.check_output(["uptime"], text=True).strip()
    started = time.perf_counter()
    document2, scope2, path2 = _scope(tmp_path, changed)
    _try(session_child, _Session(document2, scope2), path2, keep_values=True)
    qapp.processEvents()
    elapsed = time.perf_counter() - started
    print("reload %.1f ms | %s" % (elapsed * 1000.0, load))
    assert elapsed < 0.5, "reload %.1f ms | %s" % (elapsed * 1000.0, load)
    again = session_child._views["v1"].widget.findChild(QLineEdit, "emailEdit")  # noqa: SLF001
    assert again is not None
    assert again.text() == "kept@example.com"
    assert writer.sent


def test_a_burst_names_each_rule_once() -> None:
    from app.features.form_builder.qtside.preview.try_log import TryEvent, fold

    refs = ("a:cbcsValue", "b:cbcsValue", "c:cbcsEnabledWhen")
    events = [TryEvent(kind="rule", ref=ref, value=None) for ref in refs * 3]
    lines = fold(events, {}, {})
    assert lines[0].sentence == "Rules ran (3)"
    assert lines[0].details == refs
