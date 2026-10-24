"""The form timings meter stays hidden unless a developer asks for it."""

from __future__ import annotations

import pytest

from app.qt.QtWidgets import QApplication, QLabel, QMainWindow
from app.shell.status_bar import create_shell_status_bar, form_timings_enabled

pytestmark = pytest.mark.usefixtures("qapp")


class _Settings:
    def __init__(self, value: object) -> None:
        self.value_for = value

    def value(self, key: str, default: object = None) -> object:
        if key == "form_builder/dev/show_timings":
            return self.value_for
        return default


def test_timings_stay_hidden_until_the_developer_switch_is_on(
    monkeypatch: pytest.MonkeyPatch, qapp: QApplication
) -> None:
    monkeypatch.delenv("CBCS_FB_TIMINGS", raising=False)
    window = QMainWindow()
    window.resize(900, 80)
    controller = create_shell_status_bar(window)
    label = window.findChild(QLabel, "shell.formTimingsLabel")
    editor = window.findChild(QLabel, "shell.editorStatusLabel")
    assert label is not None and editor is not None
    window.show()
    qapp.processEvents()
    assert not label.isVisible()
    controller.set_form_timings("edit 12 ms")
    qapp.processEvents()
    assert not label.isVisible()
    assert label.text() == ""

    monkeypatch.setenv("CBCS_FB_TIMINGS", "1")
    controller.set_form_timings("edit 12 ms")
    qapp.processEvents()
    assert label.isVisible()
    assert label.text() == "edit 12 ms"
    assert label.geometry().right() >= editor.geometry().right()

    controller.set_form_timings("")
    assert not label.isVisible()
    window.deleteLater()
    qapp.processEvents()


def test_qsettings_flag_shows_the_same_meter(monkeypatch: pytest.MonkeyPatch, qapp: QApplication) -> None:
    monkeypatch.delenv("CBCS_FB_TIMINGS", raising=False)
    assert form_timings_enabled(_Settings(False)) is False
    assert form_timings_enabled(_Settings(True)) is True
    window = QMainWindow()
    controller = create_shell_status_bar(window)
    label = window.findChild(QLabel, "shell.formTimingsLabel")
    assert label is not None
    window.show()
    controller.set_form_timings("open 4 ms", _Settings(True))
    qapp.processEvents()
    assert label.isVisible()
    assert label.text() == "open 4 ms"
    window.deleteLater()
