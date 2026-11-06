"""Small Team Sync widgets shared by the thread, history, and dialogs."""

from __future__ import annotations

from app.qt.QtCore import Qt
from app.qt.QtWidgets import QLabel

# Saturated fills with white initials. Teal is Sam, orange is Ana, matching the prototype.
_PINNED = {
    "e5f6a7b8": "#0F766E",
    "a1b2c3d4": "#C2410C",
}
_PALETTE = (
    "#0F766E",
    "#C2410C",
    "#1D4ED8",
    "#7E22CE",
    "#0E7490",
    "#B45309",
    "#BE123C",
    "#047857",
)


def initials(name: str) -> str:
    parts = [part for part in name.replace(".", " ").split() if part]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def avatar_color(member_id: str) -> str:
    pinned = _PINNED.get(member_id)
    if pinned is not None:
        return pinned
    total = 0
    for character in member_id:
        total = (total * 33 + ord(character)) % 997
    return _PALETTE[total % len(_PALETTE)]


class Avatar(QLabel):
    def __init__(self, member_id: str, name: str, parent=None, size: int = 22) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self.set_person(member_id, name, size)

    def set_person(self, member_id: str, name: str, size: int = 22) -> None:
        self.setText(initials(name))
        color = avatar_color(member_id or name)
        radius = size // 2
        self.setStyleSheet(
            f"background: {color}; color: #FFFFFF; border-radius: {radius}px;"
            f" font-size: {max(9, size // 2 - 1)}px; font-weight: 600;"
        )


class KindLabel(QLabel):
    def __init__(self, kind: str, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(kind, parent)
        self.setFixedWidth(18)
        self.setAlignment(Qt.AlignCenter)


__all__ = ["Avatar", "KindLabel", "avatar_color", "initials"]
