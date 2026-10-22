"""Forms belong to a project: save, adopt, name, create, rename."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from app.features.form_builder.engine.codegen.header import split_generated
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.adoption import (
    adopt_form,
    adopted_forms,
    scope_for,
    unadopt_form,
)
from app.features.form_builder.engine.project.create import create_form
from app.features.form_builder.engine.project.fs import OsFileSystem
from app.features.form_builder.engine.project.names import explain_form_name
from app.features.form_builder.engine.project.rename import apply, plan_rename
from app.features.form_builder.engine.project.save import opening_diagnostics, write_generated
from app.features.form_builder.engine.ui4.reader import read_ui
from app.project.project_manifest import load_project_manifest, save_project_manifest

_BUTTON = (
    '<widget class="QPushButton" name="%(name)s">'
    '<property name="text"><string>%(name)s</string></property>'
    "</widget>"
)


def _ui(class_name: str, body: str = "", tail: str = "") -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ui version="4.0">\n'
        " <class>%s</class>\n"
        ' <widget class="QWidget" name="%s">\n'
        '  <property name="windowTitle"><string>Hello</string></property>\n'
        "  %s\n"
        " </widget>\n"
        " %s\n"
        "</ui>\n"
    ) % (class_name, class_name, body, tail)


def _load(path: Path):
    text = path.read_text(encoding="utf-8")
    document = read_ui(text, allocator=IdAllocator()).document
    return document


def _body8(text: str) -> str:
    parts = split_generated(text)
    payload = parts[1] if parts is not None else text
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]


class _FailOnce(OsFileSystem):
    """Raise on the first write of a chosen path, then behave."""

    def __init__(self, needle: str) -> None:
        self.needle = needle
        self.armed = True

    def write_bytes(self, path: str, data: bytes) -> None:
        if self.armed and path.endswith(self.needle):
            self.armed = False
            raise OSError("simulated write failure")
        super().write_bytes(path, data)


def test_hand_edit_is_copied_aside_before_regeneration(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    fs = OsFileSystem()
    created = create_form(str(root), "invoice", fs)
    generated = next(path for path in created.files if path.endswith("ui_invoice.py"))
    original = Path(generated).read_text(encoding="utf-8")
    edited = original + "\n# shop note\n"
    Path(generated).write_text(edited, encoding="utf-8")
    scope = scope_for(str(root / "forms" / "invoice.ui"), str(root), fs)
    document = _load(root / "forms" / "invoice.ui")
    result = write_generated(scope, document, (root / "forms" / "invoice.ui").read_bytes(), fs)

    assert any(item.code == "FB501" for item in result.diagnostics)
    fix = next(item.fixes[0] for item in result.diagnostics if item.code == "FB501")
    assert fix.title == "Open the saved copy"
    backup = dict(fix.args)["path"]
    assert backup.endswith("ui_invoice.%s.py.txt" % _body8(edited))
    assert Path(backup).read_text(encoding="utf-8") == edited
    assert "shop note" not in Path(generated).read_text(encoding="utf-8")
    assert Path(backup).parent == root / "cbcs" / "form_builder" / "hand_edits"


def test_a_failed_write_leaves_the_generated_file_unchanged(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    fs = OsFileSystem()
    create_form(str(root), "invoice", fs)
    generated = root / "forms" / "ui_invoice.py"
    window = root / "forms" / "invoice_window.py"
    before_generated = generated.read_bytes()
    before_window = window.read_bytes()
    failing = _FailOnce("ui_invoice.py")
    scope = scope_for(str(root / "forms" / "invoice.ui"), str(root), failing)
    document = _load(root / "forms" / "invoice.ui")
    with pytest.raises(OSError):
        write_generated(scope, document, (root / "forms" / "invoice.ui").read_bytes(), failing)
    assert generated.read_bytes() == before_generated
    assert window.read_bytes() == before_window


def test_the_window_file_is_written_once(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    fs = OsFileSystem()
    create_form(str(root), "invoice", fs)
    window = root / "forms" / "invoice_window.py"
    window.write_text(window.read_text(encoding="utf-8") + "\n# mine\n", encoding="utf-8")
    kept = window.read_bytes()
    scope = scope_for(str(root / "forms" / "invoice.ui"), str(root), fs)
    document = _load(root / "forms" / "invoice.ui")
    write_generated(scope, document, (root / "forms" / "invoice.ui").read_bytes(), fs)
    assert window.read_bytes() == kept


def test_codegen_failure_does_not_change_existing_files(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    fs = OsFileSystem()
    create_form(str(root), "invoice", fs)
    ui_path = root / "forms" / "invoice.ui"
    generated = root / "forms" / "ui_invoice.py"
    before_ui = ui_path.read_bytes()
    before_generated = generated.read_bytes()
    ui_path.write_text(_ui("Invoice", body=_BUTTON % {"name": "setupUi"}), encoding="utf-8")
    scope = scope_for(str(ui_path), str(root), fs)
    document = _load(ui_path)
    result = write_generated(scope, document, ui_path.read_bytes(), fs)
    assert result.text_written is False
    assert any(item.code == "FB502" for item in result.diagnostics)
    assert generated.read_bytes() == before_generated
    assert ui_path.read_bytes() != before_ui


def test_an_external_form_is_not_written_beside_itself(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    outside = tmp_path / "loose" / "invoice.ui"
    outside.parent.mkdir()
    outside.write_text(_ui("Invoice"), encoding="utf-8")
    fs = OsFileSystem()
    scope = scope_for(str(outside), str(root), fs)
    document = _load(outside)
    result = write_generated(scope, document, outside.read_bytes(), fs)
    assert scope.generates is False
    assert any(item.code == "FB506" for item in result.diagnostics)
    assert not (outside.parent / "ui_invoice.py").exists()
    assert result.files == ()


def test_opening_a_stale_module_reports_fb505(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    fs = OsFileSystem()
    create_form(str(root), "invoice", fs)
    ui_path = root / "forms" / "invoice.ui"
    scope = scope_for(str(ui_path), str(root), fs)
    assert opening_diagnostics(scope, ui_path.read_bytes(), fs) == ()
    ui_path.write_text(_ui("Invoice", body=_BUTTON % {"name": "okButton"}), encoding="utf-8")
    stale = opening_diagnostics(scope, ui_path.read_bytes(), fs)
    assert [item.code for item in stale] == ["FB505"]


def test_adopt_stores_a_project_relative_path(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    ui_path = root / "dialogs" / "invoice.ui"
    ui_path.parent.mkdir()
    ui_path.write_text(_ui("Invoice"), encoding="utf-8")
    fs = OsFileSystem()
    assert scope_for(str(ui_path), str(root), fs).kind == "external"
    stored = adopt_form(str(root), str(ui_path), fs)
    assert stored == ("dialogs/invoice.ui",)
    assert scope_for(str(ui_path), str(root), fs).kind == "adopted"
    manifest = load_project_manifest(root / "cbcs" / "project.json")
    assert manifest.form_builder["adopted_forms"] == ["dialogs/invoice.ui"]
    save_project_manifest(root / "cbcs" / "project.json", manifest)
    assert adopted_forms(str(root), fs) == ("dialogs/invoice.ui",)


def test_unadopt_removes_the_path(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    ui_path = root / "dialogs" / "invoice.ui"
    ui_path.parent.mkdir()
    ui_path.write_text(_ui("Invoice"), encoding="utf-8")
    fs = OsFileSystem()
    adopt_form(str(root), str(ui_path), fs)
    assert unadopt_form(str(root), str(ui_path), fs) == ()
    assert scope_for(str(ui_path), str(root), fs).kind == "external"


@pytest.mark.parametrize(
    ("stem", "phrase"),
    [
        ("class", "keyword"),
        ("ui_invoice", "ui_"),
        ("cbcs_form", "cbcs_"),
        ("123abc", "Python name"),
        ("", "name"),
    ],
)
def test_a_bad_form_name_explains_why(tmp_path: Path, stem: str, phrase: str) -> None:
    reason = explain_form_name(stem, folder=str(tmp_path), fs=OsFileSystem())
    assert reason is not None
    assert phrase in reason


def test_a_name_that_matches_a_module_is_refused(tmp_path: Path) -> None:
    (tmp_path / "invoice.py").write_text("x = 1\n", encoding="utf-8")
    reason = explain_form_name("invoice", folder=str(tmp_path), fs=OsFileSystem())
    assert reason is not None
    assert "invoice.py" in reason


def test_create_form_reports_every_new_file(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    result = create_form(str(root), "invoice", OsFileSystem(), template="dialog")
    names = sorted(os.path.basename(path) for path in result.files)
    assert names == ["__init__.py", "invoice.ui", "invoice_window.py", "ui_invoice.py"]
    window = (root / "forms" / "invoice_window.py").read_text(encoding="utf-8")
    assert "class InvoiceWindow" in window
    assert "QDialog" in window
    assert "from forms.ui_invoice import Ui_Invoice" in window
    init_text = (root / "forms" / "__init__.py").read_text(encoding="utf-8")
    create_form(str(root), "other", OsFileSystem())
    assert (root / "forms" / "__init__.py").read_text(encoding="utf-8") == init_text


def test_a_changed_qrc_rewrites_only_the_resource_module(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    forms = root / "forms"
    forms.mkdir(parents=True)
    (forms / "dot.bin").write_bytes(b"one")
    qrc = forms / "icons.qrc"
    qrc.write_text(
        '<!DOCTYPE RCC><RCC version="1.0"><qresource prefix="/cbcs"><file>dot.bin</file></qresource></RCC>\n',
        encoding="utf-8",
    )
    ui_path = forms / "invoice.ui"
    ui_path.write_text(
        _ui("Invoice", tail='<resources><include location="icons.qrc"/></resources>'),
        encoding="utf-8",
    )
    fs = OsFileSystem()
    scope = scope_for(str(ui_path), str(root), fs)
    # scope_for on a forms/ file does not need adoption. The project root exists.
    document = _load(ui_path)
    first = write_generated(scope, document, ui_path.read_bytes(), fs)
    rc = forms / "icons_rc.py"
    assert rc.is_file()
    assert any(path.endswith("icons_rc.py") for path in first.files)
    first_bytes = rc.read_bytes()
    second = write_generated(scope, document, ui_path.read_bytes(), fs)
    assert not any(path.endswith("icons_rc.py") for path in second.files)
    assert rc.read_bytes() == first_bytes
    (forms / "dot.bin").write_bytes(b"two")
    third = write_generated(scope, document, ui_path.read_bytes(), fs)
    assert any(path.endswith("icons_rc.py") for path in third.files)
    assert rc.read_bytes() != first_bytes


def test_rename_updates_imports(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    fs = OsFileSystem()
    create_form(str(root), "invoice", fs)
    (root / "app.py").write_text(
        "from forms.ui_invoice import Ui_Invoice\n"
        "import forms.ui_invoice as ui_mod\n"
        "from forms import ui_invoice\n"
        "from forms.invoice_window import InvoiceWindow\n",
        encoding="utf-8",
    )
    (root / "forms" / "extra.py").write_text(
        "from .ui_invoice import Ui_Invoice\n"
        "from . import invoice_window\n",
        encoding="utf-8",
    )
    window = root / "forms" / "invoice_window.py"
    window.write_text(window.read_text(encoding="utf-8") + "\n# mine\n", encoding="utf-8")
    plan = plan_rename(
        str(root),
        str(root / "forms" / "invoice.ui"),
        str(root / "forms" / "billing.ui"),
        fs,
    )
    assert plan.reason is None
    apply(plan, fs)
    assert not (root / "forms" / "invoice.ui").exists()
    assert (root / "forms" / "billing.ui").is_file()
    assert not (root / "forms" / "ui_invoice.py").exists()
    assert (root / "forms" / "ui_billing.py").is_file()
    moved = (root / "forms" / "billing_window.py").read_text(encoding="utf-8")
    assert "# mine" in moved
    assert "from forms.ui_billing import Ui_Invoice" in moved
    assert "class InvoiceWindow" in moved
    app = (root / "app.py").read_text(encoding="utf-8")
    assert "forms.ui_billing" in app
    assert "from forms import ui_billing" in app
    assert "from forms.billing_window import InvoiceWindow" in app
    assert "ui_invoice" not in app
    extra = (root / "forms" / "extra.py").read_text(encoding="utf-8")
    assert "from .ui_billing import Ui_Invoice" in extra
    assert "from . import billing_window" in extra


def test_rename_rolls_back_when_a_write_fails(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    fs = OsFileSystem()
    create_form(str(root), "invoice", fs)
    helper = root / "app.py"
    helper.write_text("from forms.ui_invoice import Ui_Invoice\n", encoding="utf-8")
    before = {
        path: path.read_bytes()
        for path in (
            root / "forms" / "invoice.ui",
            root / "forms" / "ui_invoice.py",
            root / "forms" / "invoice_window.py",
            helper,
        )
    }
    plan = plan_rename(
        str(root),
        str(root / "forms" / "invoice.ui"),
        str(root / "forms" / "billing.ui"),
        fs,
    )
    failing = _FailOnce("ui_billing.py")
    with pytest.raises(OSError):
        apply(plan, failing)
    for path, data in before.items():
        assert path.read_bytes() == data
    assert not (root / "forms" / "billing.ui").exists()
    assert not (root / "forms" / "ui_billing.py").exists()
    assert not (root / "forms" / "billing_window.py").exists()


def test_rename_refuses_a_target_outside_the_project(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    fs = OsFileSystem()
    create_form(str(root), "invoice", fs)
    outside = tmp_path / "elsewhere" / "billing.ui"
    plan = plan_rename(str(root), str(root / "forms" / "invoice.ui"), str(outside), fs)
    assert plan.reason is not None
    assert plan.moves == ()
    apply_error = None
    try:
        apply(plan, fs)
    except Exception as exc:
        apply_error = exc
    assert apply_error is not None
    assert (root / "forms" / "invoice.ui").is_file()
    assert not outside.exists()


def test_rename_refuses_when_the_target_exists(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    fs = OsFileSystem()
    create_form(str(root), "invoice", fs)
    create_form(str(root), "billing", fs)
    plan = plan_rename(
        str(root),
        str(root / "forms" / "invoice.ui"),
        str(root / "forms" / "billing.ui"),
        fs,
    )
    assert plan.reason is not None
    assert "billing.ui" in plan.reason


def test_moving_out_of_forms_adopts_the_new_path(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    fs = OsFileSystem()
    create_form(str(root), "invoice", fs)
    destination = root / "dialogs" / "invoice.ui"
    plan = plan_rename(str(root), str(root / "forms" / "invoice.ui"), str(destination), fs)
    assert plan.reason is None
    apply(plan, fs)
    scope = scope_for(str(destination), str(root), fs)
    assert scope.kind == "adopted"
    assert scope.module_name == "dialogs.ui_invoice"
    assert adopted_forms(str(root), fs) == ("dialogs/invoice.ui",)
    back = plan_rename(str(root), str(destination), str(root / "forms" / "invoice.ui"), fs)
    apply(back, fs)
    assert scope_for(str(root / "forms" / "invoice.ui"), str(root), fs).kind == "project"
    assert adopted_forms(str(root), fs) == ()


def test_apply_refuses_a_plan_that_leaves_the_project(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    fs = OsFileSystem()
    create_form(str(root), "invoice", fs)
    plan = plan_rename(
        str(root),
        str(root / "forms" / "invoice.ui"),
        str(root / "forms" / "billing.ui"),
        fs,
    )
    outside = tmp_path / "escape" / "billing.ui"
    escaped = type(plan)(
        project_root=plan.project_root,
        reason=None,
        moves=(type(plan.moves[0])(source=plan.moves[0].source, destination=str(outside)),),
        edits=(),
        regenerated=(),
        removed=(),
        adopted=None,
    )
    with pytest.raises(Exception):
        apply(escaped, fs)
    assert not outside.exists()
    assert (root / "forms" / "invoice.ui").is_file()
