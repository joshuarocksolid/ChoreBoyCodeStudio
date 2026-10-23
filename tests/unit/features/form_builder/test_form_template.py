"""The Qt app with a form template matches the generator and follows the binding."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from app.core import constants
from app.features.form_builder.engine.project.create import create_form
from app.features.form_builder.engine.project.fs import OsFileSystem
from app.features.form_builder.integration.adopt_dialog import AdoptDialog, adoption_hint
from app.qt.QtWidgets import QApplication, QDialogButtonBox, QLabel, QPlainTextEdit, QPushButton
from app.shell.theme_tokens import tokens_from_palette
from app.templates.template_service import TemplateService

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[4]
_TEMPLATE_FORMS = _REPO / "templates" / "qt_app_with_form" / "forms"
_FORM_FILES = ("main_window.ui", "ui_main_window.py", "main_window_window.py", "__init__.py")
_MODES = (
    "light",
    "dark",
    constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
)


def test_template_files_match_create_form(tmp_path: Path) -> None:
    created = create_form(str(tmp_path), "main_window", OsFileSystem(), template="app_window")
    assert created.refused is None
    for name in _FORM_FILES:
        assert (_TEMPLATE_FORMS / name).read_bytes() == (tmp_path / "forms" / name).read_bytes()
    ui = (tmp_path / "forms" / "main_window.ui").read_text(encoding="utf-8")
    assert "QFormLayout" in ui and "nameLabel" in ui and "<cstring>nameEdit</cstring>" in ui
    assert "QLineEdit" in ui and "nameEdit" in ui
    assert "QPushButton" in ui and "saveButton" in ui
    assert "QStatusBar" in ui and "Ready" in ui
    assert "<string>Main window</string>" in ui
    assert "<string>MainWindow</string>" not in ui
    window = (tmp_path / "forms" / "main_window_window.py").read_text(encoding="utf-8")
    assert "self.ui.setupUi(self)" in window
    assert "def save_clicked(self):" in window
    assert "showMessage" in window
    assert 'connect(MainWindow.save_clicked)' in (tmp_path / "forms" / "ui_main_window.py").read_text(encoding="utf-8")


def test_template_is_listed_only_on_pyside6(monkeypatch: pytest.MonkeyPatch) -> None:
    service = TemplateService(templates_root=str(_REPO / "templates"))
    monkeypatch.setattr("app.templates.template_service.select_binding", lambda: "PySide2")
    hidden = [item.template_id for item in service.list_templates()]
    assert "qt_app_with_form" not in hidden
    assert "qt_app" in hidden
    monkeypatch.setattr("app.templates.template_service.select_binding", lambda: "PySide6")
    shown = [item.template_id for item in service.list_templates()]
    assert "qt_app_with_form" in shown


def test_hidden_template_can_still_be_materialized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.templates.template_service.select_binding", lambda: "PySide2")
    service = TemplateService(templates_root=str(_REPO / "templates"))
    created = service.materialize_template(
        template_id="qt_app_with_form",
        destination_path=tmp_path / "app",
        project_name="Form App",
    )
    assert (created / "main.py").is_file()
    assert (created / "forms" / "ui_main_window.py").is_file()
    assert (created / "cbcs" / "project.json").is_file()
    ui = (created / "forms" / "main_window.ui").read_text(encoding="utf-8")
    generated = (created / "forms" / "ui_main_window.py").read_text(encoding="utf-8")
    assert "<string>Form App</string>" in ui
    assert "Form App" in generated
    window = (created / "forms" / "main_window_window.py").read_text(encoding="utf-8")
    assert "def save_clicked(self):" in window


def test_template_main_reaches_exec(tmp_path: Path) -> None:
    python = _freecad_11_python()
    if python is None:
        pytest.skip("FreeCAD 1.1 python is not on this machine")
    service = TemplateService(templates_root=str(_REPO / "templates"))
    created = service.materialize_template(
        template_id="qt_app_with_form",
        destination_path=tmp_path / "app",
        project_name="Form App",
    )
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["CBCS_QUIT_AFTER_SHOW"] = "1"
    completed = subprocess.run(
        [str(python), str(created / "main.py")],
        cwd=str(created),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]


def test_adopt_dialog_uses_theme_tokens(qapp) -> None:  # type: ignore[no-untyped-def]
    for mode in _MODES:
        tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
        dialog = AdoptDialog(before="loadUi(path)", after="self.ui.setupUi(self)\n", tokens=tokens)
        dialog.apply_theme(tokens)
        sheet = dialog.styleSheet()
        assert tokens.editor_bg in sheet
        title_rule = sheet.split("adoptTitle", 1)[1]
        assert tokens.text_primary in title_rule
        assert tokens.text_primary != tokens.panel_bg
        titles = dialog.findChildren(QLabel, "formBuilder.adoptTitle")
        assert [label.text() for label in titles] == ["Current call", "Paste this"]
        dialog.deleteLater()


def test_adopt_dialog_names_the_copy_controls_and_focuses_paste(qapp) -> None:  # type: ignore[no-untyped-def]
    tokens = tokens_from_palette(qapp.palette(), force_mode="dark")
    hint = adoption_hint("views/ui_invoice.py", "views/invoice_window.py")
    dialog = AdoptDialog(
        before="loadUi(path)",
        after="self.ui.setupUi(self)\n",
        tokens=tokens,
        hint=hint,
        editor_font=("Courier", 18),
    )
    assert hint in dialog.findChild(QLabel, "formBuilder.adoptHint").text()
    before_copy = dialog.findChild(QPushButton, "formBuilder.adopt.copyBefore")
    paste_copy = dialog.findChild(QPushButton, "formBuilder.adopt.copyAfter")
    assert before_copy is not None and before_copy.accessibleName() == "Copy current call"
    assert paste_copy is not None and paste_copy.accessibleName() == "Copy setupUi lines"
    before_edit = dialog.findChild(QPlainTextEdit, "formBuilder.adoptBefore")
    after_edit = dialog.findChild(QPlainTextEdit, "formBuilder.adoptAfter")
    assert before_edit is not None and before_edit.accessibleName() == "Current call"
    assert after_edit is not None and after_edit.accessibleName() == "Paste this"
    titles = dialog.findChildren(QLabel, "formBuilder.adoptTitle")
    assert titles[0].buddy() is before_edit
    assert titles[1].buddy() is after_edit
    assert before_edit.font().family() == "Courier"
    assert before_edit.font().pointSize() == 18
    box = dialog.findChild(QDialogButtonBox)
    assert box is not None
    close = box.button(QDialogButtonBox.Close)
    assert close is not None and close.isDefault()
    dialog.show()
    qapp.processEvents()
    assert qapp.focusWidget() is paste_copy
    assert close.width() < dialog.width()
    dialog.deleteLater()


def test_adopt_dialog_copy_puts_the_suggestion_on_the_clipboard(qapp) -> None:  # type: ignore[no-untyped-def]
    tokens = tokens_from_palette(qapp.palette(), force_mode="dark")
    after = "self.ui = Ui_Invoice()\nself.ui.setupUi(self)\n"
    dialog = AdoptDialog(before="loadUi(path)", after=after, tokens=tokens)
    button = dialog.findChild(QPushButton, "formBuilder.adopt.copyAfter")
    assert button is not None
    button.click()
    qapp.processEvents()
    clipboard = QApplication.clipboard()
    assert clipboard is not None
    assert clipboard.text() == after


def _freecad_11_python() -> Path | None:
    candidates = [
        os.environ.get("CBCS_FB_PY311", ""),
        "/usr/local/bin/cbcs-fb-python",
        "/opt/freecad-1.1/bin/python",
    ]
    for raw in candidates:
        if not raw:
            continue
        path = Path(raw).expanduser()
        if path.is_file():
            return path
    return None


def test_blank_main_window_is_only_a_central_widget(tmp_path: Path) -> None:
    created = create_form(str(tmp_path), "shell", OsFileSystem(), template="main_window")
    assert created.refused is None
    ui = (tmp_path / "forms" / "shell.ui").read_text(encoding="utf-8")
    assert '<widget class="QWidget" name="central"/>' in ui
    assert "saveButton" not in ui and "<connections>" not in ui
