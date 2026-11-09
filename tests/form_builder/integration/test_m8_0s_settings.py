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
    apply_built_pages,
    apply_project_pages,
    build_registered_pages,
    register_settings_page,
    unregister_settings_page,
)

pytestmark = pytest.mark.unit

_KEY = "m8_0s_probe"


def _page(calls: list, *, key: str = _KEY, refuse: bool = True) -> SettingsPage:
    def build(parent, payload, project_root):
        del payload
        widget = QWidget(parent)
        widget.setObjectName("m8-probe-%s" % project_root)
        return widget

    def apply(widget, project_root):
        calls.append((key, project_root))
        del widget
        if refuse:
            return SettingsRefusal("Pick a database file.")
        return None

    return SettingsPage(key, "Probe", build, apply, scope=SCOPE_PROJECT)


def test_a_project_page_applies_once_and_a_refusal_keeps_the_dialog_open(qapp) -> None:
    del qapp
    calls: list = []
    later: list = []
    register_settings_page(_page(calls))
    register_settings_page(_page(later, key="m8.0s.later", refuse=False))
    dialog = None
    try:
        hidden_tabs = QTabWidget()
        hidden = build_registered_pages(hidden_tabs, {}, project_root=None)
        assert all(page.key != _KEY for page, _widget in hidden)
        shown_tabs = QTabWidget()
        shown = build_registered_pages(shown_tabs, {}, project_root="/tmp/shop")
        probe = next(widget for page, widget in shown if page.key == _KEY)
        assert probe.objectName() == "m8-probe-/tmp/shop"
        assert apply_project_pages(shown, "/tmp/shop") == "Pick a database file."
        assert calls == [(_KEY, "/tmp/shop")] and later == []
        calls.clear()
        dialog = SettingsDialog(
            EditorSettingsSnapshot(),
            global_settings_payload={},
            project_root="/tmp/shop",
        )
        dialog.accept()
        assert dialog.result() != int(QDialog.DialogCode.Accepted)
        banner = dialog.findChild(QWidget, "shell.settingsDialog.validationBanner")
        assert banner is not None and banner.text() == "Pick a database file." and banner.isHidden() is False
        assert calls == [(_KEY, "/tmp/shop")] and later == []
        apply_built_pages(dialog._feature_pages, {})
        assert calls == [(_KEY, "/tmp/shop")] and later == []
    finally:
        unregister_settings_page("m8.0s.later")
        unregister_settings_page(_KEY)
        if dialog is not None:
            dialog.close()


def test_ok_applies_a_project_page_once(qapp) -> None:
    del qapp
    calls: list = []
    register_settings_page(_page(calls, refuse=False))
    dialog = None
    try:
        dialog = SettingsDialog(
            EditorSettingsSnapshot(),
            global_settings_payload={},
            project_root="/tmp/shop",
        )
        dialog.accept()
        assert dialog.result() == int(QDialog.DialogCode.Accepted)
        dialog.apply_feature_pages({})
        assert calls == [(_KEY, "/tmp/shop")]
    finally:
        unregister_settings_page(_KEY)
        if dialog is not None:
            dialog.close()
