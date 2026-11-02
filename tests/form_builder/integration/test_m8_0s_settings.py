# pyright: reportAttributeAccessIssue=false
"""Project-scope settings pages can be hidden, and a refusal keeps the dialog open."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtWidgets import QDialog, QTabWidget, QWidget

from app.shell.settings_dialog import SettingsDialog
from app.shell.settings_models import EditorSettingsSnapshot
from app.shell.settings_pages import (
    SCOPE_PROJECT,
    SettingsPage,
    SettingsRefusal,
    build_registered_pages,
    project_page_refusal,
    register_settings_page,
    unregister_settings_page,
)

pytestmark = pytest.mark.unit

_KEY = "m8_0s_probe"


def _page() -> SettingsPage:
    def build(parent, payload, project_root):
        del payload
        widget = QWidget(parent)
        widget.setObjectName("m8-probe-%s" % project_root)
        return widget

    def apply(page, payload):
        del page, payload
        return SettingsRefusal("Pick a database file.")

    return SettingsPage(_KEY, "Probe", build, apply, scope=SCOPE_PROJECT)


def test_a_project_page_is_hidden_without_a_project_and_can_refuse(qapp) -> None:
    del qapp
    register_settings_page(_page())
    dialog = None
    try:
        hidden_tabs = QTabWidget()
        hidden = build_registered_pages(hidden_tabs, {}, project_root=None)
        assert all(page.key != _KEY for page, _widget in hidden)
        shown_tabs = QTabWidget()
        shown = build_registered_pages(shown_tabs, {}, project_root="/tmp/shop")
        probe = next(widget for page, widget in shown if page.key == _KEY)
        assert probe.objectName() == "m8-probe-/tmp/shop"
        assert project_page_refusal(shown, {}) == "Pick a database file."
        dialog = SettingsDialog(
            EditorSettingsSnapshot(),
            global_settings_payload={},
            project_root="/tmp/shop",
        )
        dialog.accept()
        assert dialog.result() != int(QDialog.DialogCode.Accepted)
        banner = dialog.findChild(QWidget, "shell.settingsDialog.validationBanner")
        assert banner is not None and banner.text() == "Pick a database file." and banner.isHidden() is False
    finally:
        unregister_settings_page(_KEY)
        if dialog is not None:
            dialog.close()
