"""Unit tests for plugin uninstall move-to-trash UX copy."""

from __future__ import annotations

from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QMessageBox  # noqa: E402

from app.shell.plugins_panel import PluginManagerDialog  # noqa: E402

pytestmark = pytest.mark.unit


def test_uninstall_confirmation_mentions_move_to_trash(monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = PluginManagerDialog.__new__(PluginManagerDialog)
    dialog_any = cast(Any, dialog)
    dialog_any._state_root = None
    dialog_any._selected_plugin_key = lambda: ("acme.demo", "1.0.0")
    refresh_calls: list[bool] = []
    dialog_any.refresh_plugins = lambda: refresh_calls.append(True)
    changed_calls: list[bool] = []
    dialog_any._on_plugins_changed = lambda: changed_calls.append(True)

    prompts: list[tuple[str, str]] = []
    uninstall_calls: list[tuple[str, str]] = []
    infos: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.shell.plugins_panel.QMessageBox.question",
        lambda _parent, title, text, *_args: prompts.append((title, text)) or QMessageBox.Yes,
    )
    monkeypatch.setattr(
        "app.shell.plugins_panel.uninstall_plugin",
        lambda plugin_id, version, state_root=None: uninstall_calls.append((plugin_id, version or "")),
    )
    monkeypatch.setattr(
        "app.shell.plugins_panel.QMessageBox.information",
        lambda _parent, title, text: infos.append((title, text)),
    )

    PluginManagerDialog._handle_uninstall(dialog)

    assert prompts == [
        (
            "Move Plugin to Trash",
            "Move acme.demo@1.0.0 to trash and uninstall?\nYou can restore it from trash if needed.",
        )
    ]
    assert uninstall_calls == [("acme.demo", "1.0.0")]
    assert refresh_calls == [True]
    assert changed_calls == [True]
    assert infos == [("Plugin Uninstalled", "acme.demo@1.0.0 was moved to trash and uninstalled.")]


def test_uninstall_cancellation_skips_uninstall_call(monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = PluginManagerDialog.__new__(PluginManagerDialog)
    dialog_any = cast(Any, dialog)
    dialog_any._state_root = None
    dialog_any._selected_plugin_key = lambda: ("acme.demo", "1.0.0")
    dialog_any.refresh_plugins = lambda: None
    dialog_any._on_plugins_changed = None

    uninstall_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.shell.plugins_panel.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.No,
    )
    monkeypatch.setattr(
        "app.shell.plugins_panel.uninstall_plugin",
        lambda plugin_id, version, state_root=None: uninstall_calls.append((plugin_id, version or "")),
    )

    PluginManagerDialog._handle_uninstall(dialog)

    assert uninstall_calls == []
