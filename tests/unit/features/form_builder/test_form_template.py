"""The Qt app with a form template matches the generator and follows the binding."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from app.core import constants
from app.features.form_builder.engine.project.create import create_form
from app.features.form_builder.engine.project.fs import OsFileSystem
from app.features.form_builder.integration.adopt_dialog import AdoptDialog
from app.qt.QtWidgets import QApplication, QPushButton
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
    created = create_form(str(tmp_path), "main_window", OsFileSystem(), template="main_window")
    assert created.refused is None
    for name in _FORM_FILES:
        assert (_TEMPLATE_FORMS / name).read_bytes() == (tmp_path / "forms" / name).read_bytes()
    window = (_TEMPLATE_FORMS / "main_window_window.py").read_text(encoding="utf-8")
    assert "self.ui.setupUi(self)" in window


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
        assert tokens.editor_bg in dialog.styleSheet()
        assert tokens.text_primary in dialog.styleSheet()
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
