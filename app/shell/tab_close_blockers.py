"""Extra close confirmation from tab surfaces, ahead of the dirty-buffer prompt."""

from __future__ import annotations

from typing import Sequence

from app.qt.QtWidgets import QMessageBox, QWidget

from app.shell.tab_content_providers import TabContentProviderRegistry


def confirm_tab_close_blockers(
    parent: QWidget,
    registry: TabContentProviderRegistry,
    file_paths: Sequence[str],
) -> bool:
    """Return True when close may continue.

    An empty blocker list does not prompt. Markdown surfaces return none, so
    today's close prompts stay the same.
    """
    reasons: list[str] = []
    for file_path in file_paths:
        surface = registry.surface_for_path(file_path)
        if surface is None:
            continue
        reasons.extend(surface.close_blockers())
    if not reasons:
        return True
    answer = QMessageBox.question(
        parent,
        "Close",
        "Close anyway?\n\n" + "\n".join(reasons),
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    return answer == QMessageBox.Yes
