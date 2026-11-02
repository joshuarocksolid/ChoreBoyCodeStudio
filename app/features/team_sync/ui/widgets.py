"""Small Team Sync widgets shared by the thread, history, and dialogs."""

from __future__ import annotations

from app.qt.QtCore import Qt
from app.qt.QtWidgets import QLabel

_PALETTE = (
    "#1F4E3D",
    "#1E3A5F",
    "#6B3A2A",
    "#4A3560",
    "#0F4C5C",
    "#6B4E16",
    "#6B2D2D",
    "#243E2F",
)


def initials(name: str) -> str:
    parts = [part for part in name.replace(".", " ").split() if part]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def avatar_color(member_id: str) -> str:
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
