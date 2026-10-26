"""Spec item 6: toggling sharing on in Settings writes the choice file and shows the chip."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtWidgets import (  # noqa: E402
    QAction,
    QApplication,
    QCheckBox,
    QDialog,
    QLabel,
    QPushButton,
)

from app.bootstrap.paths import resolve_global_state_root  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402
from testing.main_window_test_helpers import prepare_main_window_for_test  # noqa: E402
from tests.unit.features.shop_sharing.shop_layout import ShopLayout, read_json  # noqa: E402

pytestmark = pytest.mark.unit


def test_turning_on_sharing_in_settings_writes_choice_and_shows_chip(
    shop: ShopLayout,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del shop
    window = MainWindow(state_root=None)
    prepare_main_window_for_test(window, app=qapp)
    try:
        def save_with_sharing_on(dialog: QDialog) -> int:
            checkbox = dialog.findChild(QCheckBox, "shell.settings.shopSharing.enabled")
            assert checkbox is not None
            checkbox.setChecked(True)
            ok = dialog.findChild(QPushButton, "shell.settingsDialog.okBtn")
            assert ok is not None
            ok.click()
            return dialog.result()

        monkeypatch.setattr(
            "app.shell.file_project_commands_workflow.exec_qt",
            save_with_sharing_on,
        )
        action = window.findChild(QAction, "shell.action.file.settings")
        assert action is not None
        action.trigger()

        choice = read_json(resolve_global_state_root(None) / "shop_sharing.json")
        chip = window.findChild(QLabel, "shell.status.shopSharing")
        assert choice["mode"] == "shop"
        assert chip is not None and not chip.isHidden()
        assert chip.text().startswith("Settings: shop \u00b7 ")
    finally:
        shutdown_main_window_for_test(window, qapp)
