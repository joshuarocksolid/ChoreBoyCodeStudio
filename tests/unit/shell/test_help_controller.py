"""Unit tests for shell help controller."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication, QWidget  # noqa: E402

import app.shell.help_controller as help_controller_module  # noqa: E402
from app.shell.help_controller import ShellHelpController  # noqa: E402
from app.shell.shortcut_preferences import SHORTCUT_COMMANDS  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


def _build_controller(
    *,
    reveal_calls: list[str] | None = None,
    shortcuts: dict[str, str] | None = None,
) -> ShellHelpController:
    calls = reveal_calls if reveal_calls is not None else []
    return ShellHelpController(
        state_root=None,
        resolve_theme_tokens=lambda: object(),
        reveal_path_in_file_manager=lambda path: calls.append(path),
        get_effective_shortcuts=lambda: dict(shortcuts or {}),
    )


def test_build_shortcuts_help_markdown_renders_assigned_shortcuts() -> None:
    first_command = SHORTCUT_COMMANDS[0]
    controller = _build_controller(shortcuts={first_command.action_id: "Ctrl+Alt+H"})

    markdown = controller.build_shortcuts_help_markdown()

    assert "# Keyboard Shortcuts" in markdown
    assert first_command.category in markdown
    assert f"**Ctrl+Alt+H**: {first_command.label}" in markdown


def test_build_shortcuts_help_markdown_handles_empty_assignments() -> None:
    controller = _build_controller(shortcuts={})

    markdown = controller.build_shortcuts_help_markdown()

    assert "No shortcuts are currently assigned." in markdown


def test_open_app_log_shows_message_when_log_file_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    controller = _build_controller()
    messages: list[tuple[str, str]] = []
    missing_log = tmp_path / "missing.log"
    parent = QWidget()

    monkeypatch.setattr(help_controller_module, "global_app_log_path", lambda _state_root: missing_log)
    monkeypatch.setattr(
        help_controller_module.QMessageBox,
        "information",
        lambda _parent, title, body: messages.append((title, body)),
    )

    controller.open_app_log(parent=parent)

    assert messages
    assert messages[0][0] == "Application Log"
    assert str(missing_log) in messages[0][1]


def test_open_log_folder_reveals_existing_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    reveal_calls: list[str] = []
    controller = _build_controller(reveal_calls=reveal_calls)
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True)
    parent = QWidget()

    monkeypatch.setattr(help_controller_module, "global_logs_dir", lambda _state_root: log_dir)

    controller.open_log_folder(parent=parent)

    assert reveal_calls == [str(log_dir)]


def test_show_shortcuts_uses_help_markdown_dialog(monkeypatch: pytest.MonkeyPatch) -> None:
    first_command = SHORTCUT_COMMANDS[0]
    controller = _build_controller(shortcuts={first_command.action_id: "Ctrl+Shift+Y"})
    shown: list[tuple[str, str]] = []
    parent = QWidget()

    monkeypatch.setattr(
        help_controller_module,
        "show_help_markdown",
        lambda title, markdown, _tokens, parent=None: shown.append((title, markdown)),
    )

    controller.show_shortcuts(parent=parent)

    assert shown
    assert shown[0][0] == "Keyboard Shortcuts"
    assert "Ctrl+Shift+Y" in shown[0][1]


def test_show_packaging_backup_uses_help_file_dialog(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = _build_controller()
    shown: list[tuple[str, str]] = []
    parent = QWidget()

    monkeypatch.setattr(
        help_controller_module,
        "show_help_file",
        lambda title, file_name, _tokens, parent=None: shown.append((title, file_name)),
    )

    controller.show_packaging_backup(parent=parent)

    assert shown == [("Packaging, Sharing, and Backup", "packaging_backup.md")]
