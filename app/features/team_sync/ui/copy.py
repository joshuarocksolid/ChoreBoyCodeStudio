"""Plain-language views of Team Sync status. Widgets paint these and nothing else."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.features.team_sync.api import (
    DELIVERY_ACCEPTED,
    DELIVERY_DELIVERED,
    DELIVERY_QUEUED,
    DELIVERY_SENT,
    DELIVERY_WAITING_TERMINAL,
    TERMINAL_OFFLINE,
    Clash,
    TeamStatus,
)


@dataclass(frozen=True)
class StatusView:
    text: str
    level: str
    visible: bool


def first_name(full_name: str) -> str:
    parts = full_name.split()
    return parts[0] if parts else full_name


def deleted_clash_copy(path: str, clash: Clash, theirs_name: str) -> tuple[str, str]:
    """Dialog title and chip. The title is the file. The chip names who deleted and who edited."""
    title = Path(path).name or path
    them = first_name(theirs_name) or "They"
    ours_gone = not any(line.strip() for line in clash.ours)
    theirs_gone = not any(line.strip() for line in clash.theirs)
    if ours_gone and not theirs_gone:
        return title, f"You deleted it · {them} edited it"
    return title, f"{them} deleted it · you edited it"


def delivery_mark(state: str, *, git_names: bool) -> tuple[str, str]:
    """Visible mark and tooltip for one delivery state."""
    tooltips = {
        DELIVERY_QUEUED: "Queued",
        DELIVERY_WAITING_TERMINAL: "Waiting for the terminal",
        DELIVERY_SENT: "Sent",
        DELIVERY_DELIVERED: "Delivered",
        DELIVERY_ACCEPTED: "Accepted",
    }
    tooltip = tooltips.get(state, state)
    if git_names:
        return (tooltip, tooltip)
    if state in (DELIVERY_QUEUED, DELIVERY_WAITING_TERMINAL):
        return ("Queued", tooltip)
    if state == DELIVERY_SENT:
        return ("✓", tooltip)
    if state in (DELIVERY_DELIVERED, DELIVERY_ACCEPTED):
        return ("✓✓", tooltip)
    return ("", tooltip)


def status_view(status: TeamStatus, *, waiting_name: str = "") -> StatusView:
    if not status.shared:
        return StatusView("Team: Not shared", "info", False)
    if status.terminal == TERMINAL_OFFLINE:
        return StatusView("Team: Terminal offline", "warn", True)
    if status.combine is not None and not status.combine.done:
        left = len(status.combine.clashes) - status.combine.settled
        noun = "line" if left == 1 else "lines"
        return StatusView(f"Team: {left} {noun} to choose", "warn", True)
    if status.waiting:
        who = waiting_name or "the team"
        if status.waiting == 1:
            return StatusView(f"Team: 1 from {who}", "info", True)
        return StatusView(f"Team: {status.waiting} waiting", "info", True)
    if status.last_delivery is not None:
        state = status.last_delivery.state
        if state in (DELIVERY_QUEUED, DELIVERY_WAITING_TERMINAL):
            return StatusView("Team: Queued", "info", True)
        if state == DELIVERY_SENT:
            return StatusView("Team: Sent", "info", True)
        if state == DELIVERY_DELIVERED:
            return StatusView("Team: Delivered", "ok", True)
    if status.pending:
        count = len(status.pending)
        noun = "file" if count == 1 else "files"
        return StatusView(f"Team: {count} to send", "info", True)
    return StatusView("Team: Up to date", "ok", True)


def badge_count(status: TeamStatus) -> int:
    unsettled = 0
    if status.combine is not None:
        unsettled = len(status.combine.clashes) - status.combine.settled
    return status.waiting + unsettled


def explorer_letters(
    status: TeamStatus,
    incoming_paths: set[str],
    clash_paths: set[str],
) -> dict[str, tuple[str, str]]:
    """Path to (letter, severity). Clash wins, then incoming, then pending."""
    letters: dict[str, tuple[str, str]] = {}
    for change in status.pending:
        letters[change.path] = (change.kind, "info")
    for path in incoming_paths:
        letters[path] = ("↓", "info")
    for path in clash_paths:
        letters[path] = ("!", "warn")
    return letters


def clock(when: object) -> str:
    text = getattr(when, "strftime", None)
    if text is None:
        return ""
    return when.strftime("%H:%M")  # type: ignore[no-any-return]


def short_date(when: object) -> str:
    text = getattr(when, "strftime", None)
    if text is None:
        return ""
    return f"{when.strftime('%b')} {when.day}"  # type: ignore[union-attr]


__all__ = [
    "StatusView",
    "badge_count",
    "deleted_clash_copy",
    "clock",
    "delivery_mark",
    "explorer_letters",
    "first_name",
    "short_date",
    "status_view",
]
