# pyright: reportAttributeAccessIssue=false
"""Eject dialog, the Data tab after eject, and the window file at load_record.

Skips unless CBCS_FB_SCREENSHOT_DIR is set. The form-builder gate unsets that
variable, so this file does not write during the gate.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.codegen.eject import method_line, plan_eject, splice_window
from app.features.form_builder.engine.codegen.window_template import render_window_class
from app.features.form_builder.engine.data.schema import set_schema_reader
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.qtside.data_panel.chrome import apply_chrome
from app.features.form_builder.qtside.data_panel.eject_dialog import EjectDialog
from app.features.form_builder.qtside.data_panel.panel import DataPanel
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.qtside.preview.what_ran import DataStrip
from app.qt.QtGui import QColor, QFont, QPalette
from app.qt.QtWidgets import QApplication, QLabel, QPlainTextEdit, QVBoxLayout, QWidget
from tests.form_builder.engine.test_m8_3b_lines import _invoice_schema, _prepare
from tests.form_builder.engine.test_m8_5_eject import _scenario_ui
from tests.form_builder.qtside.test_m8_2_shots import _shoot

pytestmark = pytest.mark.unit


def test_eject_shots(tmp_path: Path, qapp: QApplication) -> None:
    raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR", "").strip()
    if not raw:
        pytest.skip("set CBCS_FB_SCREENSHOT_DIR to write eject shots")
    root = Path(raw)
    root.mkdir(parents=True, exist_ok=True)
    from tests.form_builder.engine.test_m8_5_eject import _project

    try:
        project, scope, ui_text = _project(tmp_path, _scenario_ui(), _prepare, "invoice.ui", _invoice_schema())
        session = FormSession.open(ui_text, path=scope.ui_path, scope=scope)
        plan = plan_eject(session.document, scope)
        parent = QWidget()
        parent.resize(640, 280)
        dialog = EjectDialog(parent, plan)
        _shoot(dialog, qapp, root, "eject-dialog", 520, max(dialog.sizeHint().height() + 24, 240))
        with session.log.transaction("Eject to code"):
            for command in plan.commands:
                session.log.execute(command)
        host = QWidget()
        host.session = session
        layout = QVBoxLayout(host)
        panel = DataPanel(host)
        layout.addWidget(panel)

        def apply_theme(tokens: object) -> None:
            host.setObjectName("formBuilder.dataPanel")
            apply_chrome(host, tokens)
            panel.apply_theme(tokens)

        host.apply_theme = apply_theme  # type: ignore[attr-defined]
        _shoot(host, qapp, root, "data-tab-ejected", 420, 180)
        window = render_window_class(session.document, scope=scope)
        text = splice_window(window, plan)
        shell = _editor(text, plan.first_method)
        _shoot(shell, qapp, root, "window-load-record", 720, 480)
        fields = _editor(text, "write_fields")
        _shoot(fields, qapp, root, "window-write-fields", 720, 480)
        from app.features.form_builder.integration.preview_notice import _eject_note

        _shoot(_try_strip(_eject_note(session.document, scope)), qapp, root, "try-ejected-strip", 720, 88)
        assert (root / "eject-dialog-light.png").is_file()
        assert (root / "try-ejected-strip-light.png").is_file()
        assert (root / "eject-dialog-dark.png").is_file()
        assert (root / "data-tab-ejected-light.png").is_file()
        assert (root / "window-load-record-dark.png").is_file()
    finally:
        set_schema_reader(None)


def _try_strip(text: str) -> QWidget:
    shell = QWidget()
    shell.setObjectName("formBuilder.previewShell")
    layout = QVBoxLayout(shell)
    layout.setContentsMargins(12, 8, 12, 8)
    strip = DataStrip(shell)
    strip.set_text(text, False)
    layout.addWidget(strip)

    def apply_theme(tokens: object) -> None:
        chrome = chrome_for(tokens)  # type: ignore[arg-type]
        shell.setAutoFillBackground(True)
        palette = shell.palette()
        palette.setColor(QPalette.Window, QColor(chrome.window))
        palette.setColor(QPalette.WindowText, QColor(chrome.text))
        shell.setPalette(palette)
        shell.setStyleSheet("background: %s; color: %s; border: none;" % (chrome.window, chrome.text))
        strip.apply_chrome(chrome)

    shell.apply_theme = apply_theme  # type: ignore[attr-defined]
    return shell


def _editor(source: str, method: str) -> QWidget:
    shell = QWidget()
    shell.setObjectName("formBuilder.windowFile")
    layout = QVBoxLayout(shell)
    title = QLabel("invoice_window.py", shell)
    title.setObjectName("formBuilder.windowFileTitle")
    editor = QPlainTextEdit(shell)
    editor.setObjectName("formBuilder.windowFileEditor")
    editor.setFont(QFont("Menlo", 12))
    editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    editor.setPlainText(source)
    block = editor.document().findBlockByLineNumber(max(0, method_line(source, method) - 1))
    cursor = editor.textCursor()
    cursor.setPosition(block.position())
    editor.setTextCursor(cursor)
    editor.ensureCursorVisible()
    layout.addWidget(title)
    layout.addWidget(editor)

    def apply_theme(tokens: object) -> None:
        apply_chrome(shell, tokens)
        editor.setStyleSheet(
            "QPlainTextEdit { color: %s; background: %s; }" % (tokens.text_primary, tokens.editor_bg)  # type: ignore[attr-defined]
        )

    shell.apply_theme = apply_theme  # type: ignore[attr-defined]
    return shell
