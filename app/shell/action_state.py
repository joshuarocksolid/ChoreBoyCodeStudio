"""QAction writes that skip a setter when the value is already there.

A setter emits ``changed`` even when the menu is closed, and the menu lays
itself out on that signal. A real change still goes through, so the undo
name is current for the menu and for anything that reads the action.
"""

from __future__ import annotations

from typing import Optional


def assign_action(
    action: object,
    *,
    text: Optional[str] = None,
    enabled: Optional[bool] = None,
    tool_tip: Optional[str] = None,
    status_tip: Optional[str] = None,
    visible: Optional[bool] = None,
) -> bool:
    """Set only the fields that differ. Returns whether any setter ran."""
    wrote = False
    if text is not None and action.text() != text:  # type: ignore[attr-defined]
        action.setText(text)  # type: ignore[attr-defined]
        wrote = True
    if enabled is not None and bool(action.isEnabled()) != bool(enabled):  # type: ignore[attr-defined]
        action.setEnabled(bool(enabled))  # type: ignore[attr-defined]
        wrote = True
    if tool_tip is not None and action.toolTip() != tool_tip:  # type: ignore[attr-defined]
        action.setToolTip(tool_tip)  # type: ignore[attr-defined]
        wrote = True
    if status_tip is not None and action.statusTip() != status_tip:  # type: ignore[attr-defined]
        action.setStatusTip(status_tip)  # type: ignore[attr-defined]
        wrote = True
    if visible is not None and bool(action.isVisible()) != bool(visible):  # type: ignore[attr-defined]
        action.setVisible(bool(visible))  # type: ignore[attr-defined]
        wrote = True
    return wrote


def assign_history_action(action: object, text: str, enabled: bool) -> None:
    """Undo or Redo. The label is written now, and only when it differs."""
    assign_action(action, text=text, enabled=enabled)
