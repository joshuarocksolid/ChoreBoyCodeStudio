# pyright: reportAttributeAccessIssue=false
"""A form tab reloaded from disk, or destroyed without release, leaves the session."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.features.form_builder.integration.provider import FormTabProvider
from app.features.form_builder.integration.qrc_provider import refresh_picture_checks
from app.features.form_builder.integration.surface import FormSurface
from app.features.form_builder.qtside.data_panel.eject_cmd import _reload
from app.qt.QtWidgets import QApplication, QPlainTextEdit, QWidget
from app.shell.tab_content_providers import TabSurfaceRequest
from app.shell.theme_tokens import tokens_from_palette

pytestmark = pytest.mark.unit

_UI = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QPushButton" name="okButton">
     <property name="text">
      <string>OK</string>
     </property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


class _Registry:
    def __init__(self, path: str, surface: FormSurface) -> None:
        self._path = os.path.abspath(path)
        self._surface = surface

    def surface_for_path(self, asked: str) -> FormSurface | None:
        if os.path.abspath(asked) == self._path:
            return self._surface
        return None


def _open(qapp: QApplication, root: Path) -> tuple[QWidget, FormSurface, str]:
    forms = root / "forms"
    forms.mkdir(parents=True)
    path = forms / "invoice.ui"
    path.write_text(_UI, encoding="utf-8")
    parent = QWidget()

    def create_source_editor() -> QPlainTextEdit:
        editor = QPlainTextEdit(parent)
        editor.setObjectName("shell.editorTabs.textEditor")
        return editor

    surface = FormTabProvider().create_surface(
        TabSurfaceRequest(
            file_path=str(path),
            initial_text=_UI,
            parent=parent,
            theme=tokens_from_palette(qapp.palette(), force_mode="light"),
            create_source_editor=create_source_editor,
            open_linked_file=lambda _linked: None,
            project_root=str(root),
        )
    )
    parent.show()
    surface.show()
    qapp.processEvents()
    return parent, surface, str(path)


def test_reloading_a_form_tab_from_disk_drops_the_old_diagnostics_listener(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[FormSurface] = []

    def wrapped(self: FormSurface, _diagnostics: object) -> None:
        calls.append(self)

    monkeypatch.setattr(FormSurface, "_schedule_problems", wrapped)
    _parent, surface, path = _open(qapp, tmp_path)
    session = surface.session
    shell = QWidget()
    shell._tab_content_registry = _Registry(path, surface)  # type: ignore[attr-defined]
    calls.clear()
    _reload(shell, path, surface.current_text())
    session.diagnostics.publish("reader", ())
    refresh_picture_checks()
    assert surface not in calls


def test_a_destroyed_form_tab_is_not_told_about_later_diagnostics(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[FormSurface] = []

    def wrapped(self: FormSurface, _diagnostics: object) -> None:
        calls.append(self)

    monkeypatch.setattr(FormSurface, "_schedule_problems", wrapped)
    parent, surface, _path = _open(qapp, tmp_path)
    session = surface.session
    calls.clear()
    parent.deleteLater()
    qapp.processEvents()
    session.diagnostics.publish("reader", ())
    refresh_picture_checks()
    assert surface not in calls
