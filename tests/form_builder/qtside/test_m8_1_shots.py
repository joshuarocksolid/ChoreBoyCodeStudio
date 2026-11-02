# pyright: reportAttributeAccessIssue=false
"""M8.1 Connections screenshots. Skips unless CBCS_FB_SCREENSHOT_DIR is set."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.core import constants
from app.qt.QtWidgets import QApplication, QWidget
from app.shell.theme_tokens import tokens_from_palette

from app.features.form_builder.engine.data.connections import Connection, ConnectionSet
from app.features.form_builder.engine.data.connections_module import save_project_connections
from app.features.form_builder.integration.connection_paths import project_slug
from app.features.form_builder.engine.data.source import RecordSource, write_data
from app.features.form_builder.integration.settings_ext.connections_page import (
    ConnectionsPage,
    build_rename_question,
    rename_sentence,
)
from tests.form_builder.fixtures.m8.make_shop import build

pytestmark = pytest.mark.unit

_MODES = (
    constants.UI_THEME_MODE_LIGHT,
    constants.UI_THEME_MODE_DARK,
    constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
)


def _pump(qapp: QApplication, times: int = 6) -> None:
    for _ in range(times):
        qapp.processEvents()


def _grab(widget: QWidget, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    widget.grab().save(str(path))


def _theme(widget: QWidget, mode: str, qapp: QApplication) -> None:
    widget.apply_theme(tokens_from_palette(widget.palette(), force_mode=mode))
    widget.resize(960, 640)
    widget.show()
    _pump(qapp)


def _until(qapp: QApplication, predicate, seconds: float = 5.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.02)


def _form(connection: str) -> str:
    payload = write_data(RecordSource(connection, "invoices", "id"))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<ui version=\"4.0\">\n"
        " <class>Form</class>\n"
        " <widget class=\"QWidget\" name=\"Form\">\n"
        "  <property name=\"cbcsData\" stdset=\"0\">"
        "<string notr=\"true\">%s</string></property>\n"
        " </widget>\n"
        " <resources/>\n"
        " <connections/>\n"
        "</ui>\n"
    ) % payload


def test_connection_screenshots(qapp, tmp_path) -> None:
    raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR") or ""
    if not raw:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is not set")
    folder = Path(raw)
    project = tmp_path / "shop"
    project.mkdir()
    build(str(project / "data" / "shop.db"))
    forms = project / "forms"
    forms.mkdir()
    (forms / "invoice.ui").write_text(_form("shop"), encoding="utf-8")
    save_project_connections(
        str(project),
        ConnectionSet(
            (
                Connection("shop", "Shop database", "sqlite", file="data/shop.db"),
                Connection(
                    "office",
                    "Office",
                    "postgres",
                    host="192.168.1.20",
                    database="shop",
                    user="clerk",
                    password="ask",
                ),
            )
        ),
        slug=project_slug(str(project)),
    )
    for mode in _MODES:
        empty = ConnectionsPage(None, str(tmp_path / ("empty-" + mode)))
        (tmp_path / ("empty-" + mode)).mkdir()
        _theme(empty, mode, qapp)
        _grab(empty, folder / ("connections-empty-%s.png" % mode))
        empty.close()

        editor = ConnectionsPage(None, str(project))
        _theme(editor, mode, qapp)
        _grab(editor, folder / ("connections-editor-%s.png" % mode))
        editor._list.setCurrentRow(1)
        _pump(qapp)
        _grab(editor, folder / ("connections-editor-postgres-%s.png" % mode))
        editor._list.setCurrentRow(0)
        editor._test_button.click()
        _until(qapp, lambda editor=editor: editor._result.text().startswith("Connected"))
        _pump(qapp)
        _grab(editor, folder / ("connections-sqlite-pass-%s.png" % mode))

        editor._file.setText("data/missing.db")
        editor._test_button.click()
        _until(
            qapp,
            lambda editor=editor: editor._test_button.isEnabled() and not editor._result.text().startswith("Testing"),
        )
        _pump(qapp)
        _grab(editor, folder / ("connections-sqlite-fail-%s.png" % mode))
        editor.close()

        used = ConnectionsPage(None, str(project))
        _theme(used, mode, qapp)
        used._remove.click()
        _pump(qapp)
        _grab(used, folder / ("connections-remove-%s.png" % mode))
        used.close()

        dialog = build_rename_question(None, rename_sentence(3, "shop"))
        dialog.apply_theme = lambda tokens: dialog.setStyleSheet(
            "QDialog { background: %s; color: %s; } QLabel { color: %s; } QPushButton { color: %s; background: %s; border: %dpx solid %s; padding: 4px 10px; }"
            % (
                tokens.panel_bg,
                tokens.text_primary,
                tokens.text_primary,
                tokens.text_primary,
                tokens.input_bg,
                int(tokens.focus_border_width or 1),
                tokens.accent,
            )
        )
        _theme(dialog, mode, qapp)
        _grab(dialog, folder / ("connections-rename-%s.png" % mode))
        dialog.close()
