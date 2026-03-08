"""Unit tests for shared shell file-dialog helpers."""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QFileDialog

from app.shell import file_dialogs

pytestmark = pytest.mark.unit


def _option_enabled(options: Any, flag: Any) -> bool:
    return bool(options & flag)


def test_choose_existing_directory_applies_non_native_dialog_options(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_get_existing_directory(_parent, _title, _start_directory, options=None):  # type: ignore[no-untyped-def]
        captured["options"] = options
        return "/tmp/project"

    monkeypatch.setattr(file_dialogs.QFileDialog, "getExistingDirectory", fake_get_existing_directory)

    selected = file_dialogs.choose_existing_directory(None, "Open Project", "/tmp")

    assert selected == "/tmp/project"
    options = captured["options"]
    assert _option_enabled(options, QFileDialog.DontUseNativeDialog)
    assert _option_enabled(options, QFileDialog.ShowDirsOnly)
    if hasattr(QFileDialog, "DontUseCustomDirectoryIcons"):
        assert _option_enabled(options, QFileDialog.DontUseCustomDirectoryIcons)


def test_choose_open_files_returns_all_selected_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_get_open_file_names(_parent, _title, _start_directory, _file_filter, options=None):  # type: ignore[no-untyped-def]
        captured["options"] = options
        return (["/tmp/a.py", "/tmp/b.py"], "Python Files (*.py)")

    monkeypatch.setattr(file_dialogs.QFileDialog, "getOpenFileNames", fake_get_open_file_names)

    selected = file_dialogs.choose_open_files(None, "Open File", "/tmp", "Python Files (*.py)")

    assert selected == ["/tmp/a.py", "/tmp/b.py"]
    options = captured["options"]
    assert _option_enabled(options, QFileDialog.DontUseNativeDialog)
    if hasattr(QFileDialog, "DontUseCustomDirectoryIcons"):
        assert _option_enabled(options, QFileDialog.DontUseCustomDirectoryIcons)

