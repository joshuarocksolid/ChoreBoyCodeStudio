"""Shared helpers for constructing shell menu actions."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from app.shell.shortcut_preferences import normalize_shortcut


def register_menu_action(
    *,
    qt_widgets: Any,
    menu: Any,
    action_lookup: dict[str, Any],
    action_id: str,
    label: str,
    shortcut: str | None = None,
    enabled: bool = False,
    callback: Callable[[], object] | None = None,
    shortcut_overrides: Mapping[str, str] | None = None,
) -> Any:
    action = qt_widgets.QAction(label, menu)
    action.setObjectName(action_id)

    effective_shortcut = shortcut
    if shortcut_overrides is not None and action_id in shortcut_overrides:
        override = normalize_shortcut(shortcut_overrides[action_id])
        effective_shortcut = override if override else None
    if effective_shortcut:
        action.setShortcut(effective_shortcut)

    action.setEnabled(enabled)
    if callback is not None:
        action.triggered.connect(callback)
    menu.addAction(action)
    action_lookup[action_id] = action
    return action
