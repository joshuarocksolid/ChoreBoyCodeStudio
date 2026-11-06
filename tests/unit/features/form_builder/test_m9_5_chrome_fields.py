# pyright: reportAttributeAccessIssue=false
"""Chrome fields follow the host theme. The canvas editor colour stays off these controls."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtWidgets import QCheckBox, QLabel, QLineEdit, QVBoxLayout, QWidget

from app.core import constants
from app.features.form_builder.engine.project.fs import OsFileSystem
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.integration.settings_ext.connections_page import ConnectionsPage
from app.features.form_builder.qtside.data_panel.sheets import ConnectSheet
from app.features.form_builder.qtside.inspector.pane import _stylesheet
from app.features.form_builder.qtside.start.panel import NewFormPanel
from app.shell.style_sheet import build_shell_style_sheet
from app.shell.theme_tokens import tokens_from_palette

pytestmark = pytest.mark.unit


class _Host:
    def __init__(self, tokens: object) -> None:
        self.tokens = tokens

    def resolve_theme_tokens(self) -> object:
        return self.tokens


class _Session:
    document = object()


def _tokens(qapp: object, mode: str) -> object:
    return tokens_from_palette(qapp.palette(), force_mode=mode)  # type: ignore[attr-defined]


def _fill(widget: QWidget) -> tuple:
    image = widget.grab().toImage()
    color = image.pixelColor(min(4, image.width() - 1), image.height() // 2)
    return (color.red(), color.green(), color.blue())


def _hex(color: str) -> tuple:
    text = color.lstrip("#")
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def test_connections_page_repaints_when_the_host_theme_changes(qapp, tmp_path) -> None:  # type: ignore[no-untyped-def]
    light = _tokens(qapp, "light")
    dark = _tokens(qapp, "dark")
    host = _Host(light)
    window = QWidget()
    window._shell_theme_workflow = host
    window.resize(800, 500)
    window.show()
    page = ConnectionsPage(window, str(tmp_path))
    page.resize(640, 360)
    page.show()
    qapp.processEvents()
    assert light.panel_bg in page.styleSheet()  # type: ignore[attr-defined]
    host.tokens = dark
    window.setStyleSheet(build_shell_style_sheet(dark))  # type: ignore[arg-type]
    qapp.processEvents()
    sheet = page.styleSheet()
    assert dark.input_bg in sheet  # type: ignore[attr-defined]
    assert dark.text_primary in sheet  # type: ignore[attr-defined]
    assert light.text_primary not in sheet  # type: ignore[attr-defined]


def test_connect_sheet_fields_follow_a_later_host_theme(qapp) -> None:  # type: ignore[no-untyped-def]
    light = _tokens(qapp, "light")
    dark = _tokens(qapp, constants.UI_THEME_MODE_HIGH_CONTRAST_DARK)
    host = _Host(light)
    window = QWidget()
    window._shell_theme_workflow = host
    sheet = ConnectSheet(window, _Session(), light)
    sheet.resize(480, 420)
    sheet.show()
    qapp.processEvents()
    host.tokens = dark
    window.setStyleSheet(build_shell_style_sheet(dark))  # type: ignore[arg-type]
    qapp.processEvents()
    labels = [item for item in sheet.findChildren(QLabel) if item.text() == "Connection"]
    edit = sheet.findChild(QLineEdit, "formBuilder.data.recordWord")
    box = sheet.findChild(QCheckBox, "formBuilder.data.allowOverwrite")
    tables = sheet.findChild(QWidget, "formBuilder.data.tables")
    assert labels and edit is not None and box is not None and tables is not None
    assert _fill(edit) == _hex(dark.input_bg)  # type: ignore[attr-defined]
    assert _fill(tables) == _hex(dark.input_bg)  # type: ignore[attr-defined]
    assert dark.text_primary in sheet.styleSheet()  # type: ignore[attr-defined]
    assert _bright(_text_pixel(labels[0], 0))
    assert _bright(_text_pixel(box, 22))


def test_start_name_field_uses_chrome_input(qapp, tmp_path) -> None:  # type: ignore[no-untyped-def]
    dark = _tokens(qapp, "dark")
    panel = NewFormPanel(
        project_root=str(tmp_path),
        directory=str(tmp_path),
        fs=OsFileSystem(),
        chrome=chrome_for(dark),  # type: ignore[arg-type]
    )
    panel.resize(900, 640)
    panel.show()
    qapp.processEvents()
    name = panel.findChild(QLineEdit, "formBuilder.newForm.name")
    assert name is not None
    assert _fill(name) == _hex(dark.input_bg)  # type: ignore[attr-defined]


def test_inspector_line_edit_uses_chrome_input(qapp) -> None:  # type: ignore[no-untyped-def]
    dark = chrome_for(_tokens(qapp, "dark"))  # type: ignore[arg-type]
    inspector = QWidget()
    inspector.setObjectName("formBuilder.inspector")
    content = QWidget(inspector)
    content.setObjectName("formBuilder.inspectorContent")
    content.setStyleSheet(
        "QWidget#formBuilder\\.inspectorContent { background: %s; color: %s; }"
        "QLabel { color: %s; background: transparent; }"
        % (dark.panel, dark.text, dark.text)
    )
    edit = QLineEdit("Invoice", content)
    name = QLineEdit("invoice", inspector)
    name.setObjectName("formBuilder.inspectorName")
    name.setStyleSheet(
        "QLineEdit#formBuilder\\.inspectorName { background: transparent; color: %s;"
        " border: 1px solid transparent; }"
        % dark.text
    )
    layout = QVBoxLayout(inspector)
    inner = QVBoxLayout(content)
    inner.addWidget(edit)
    layout.addWidget(content)
    layout.addWidget(name)
    inspector.setStyleSheet(_stylesheet(dark))
    inspector.resize(280, 120)
    inspector.show()
    qapp.processEvents()
    assert _fill(edit) == _hex(dark.input)
    assert _fill(name) != _hex(dark.input)


def _bright(pixel: tuple) -> bool:
    return pixel[0] > 200 and pixel[1] > 200 and pixel[2] > 200


def _text_pixel(widget: QWidget, start_x: int) -> tuple:
    image = widget.grab().toImage()
    found = (0, 0, 0)
    for y in range(image.height()):
        for x in range(start_x, image.width()):
            color = image.pixelColor(x, y)
            if color.red() > 200 and color.green() > 200 and color.blue() > 200:
                return (color.red(), color.green(), color.blue())
            found = (color.red(), color.green(), color.blue())
    return found
