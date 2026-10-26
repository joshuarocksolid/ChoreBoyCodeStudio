"""What the shop-sharing UI says and decides. ShopStatus and a clock in, strings and intents out."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional, Union

from app.features.shop_sharing.model import SHOP_FOLDER_NAME, DiscoveredShop, SharingMode, ShopStatus

ChipSeverity = Literal["ok", "warning"]

PINNED_TEXT = "Shop sharing is off because CBCS_STATE_ROOT is set."
LOCAL_TEXT = "This computer only"
GROUP_TITLE = "Shop sharing"
CHECKBOX_TEXT = "Share my settings with the other ChoreBoys in this shop"
HINT_TEXT = (
    "Settings, recent projects and Python Console history are saved in a folder on the shop share. "
    "History, logs and caches stay on each computer. Turn this on at the server first."
)
PROMPT_HEADLINE = "This shop shares Code Studio settings."
PROMPT_NOTE = (
    "Your current settings are kept as a backup. "
    "You can change this later in Settings \u203a General \u203a Shop sharing."
)
USE_TEXT = "Use shop settings"
KEEP_TEXT = "Keep this computer's"
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


@dataclass(frozen=True)
class ChipView:
    """None from chip_view means no chip (local or pinned)."""

    text: str
    tooltip: str
    severity: ChipSeverity


@dataclass(frozen=True)
class PromptCopy:
    headline: str
    question: str
    note: str


@dataclass(frozen=True)
class TurnOn:
    folder: Path


@dataclass(frozen=True)
class TurnOff:
    pass


SharingIntent = Union[TurnOn, TurnOff]


def status_line(status: ShopStatus, *, now: datetime) -> str:
    """Settings status line."""
    if status.mode is SharingMode.PINNED:
        return PINNED_TEXT
    if status.mode is not SharingMode.SHOP:
        return LOCAL_TEXT
    label = status.label or ""
    if status.reachable:
        if status.last_synced_at is None:
            return f"Shared with {label} \u00b7 not synced yet"
        synced = relative_text(status.last_synced_at, now=now)
        return f"Shared with {label} \u00b7 synced {synced}"
    if status.last_synced_at is None:
        return "Shop share offline \u00b7 no synced copy yet"
    return f"Shop share offline \u00b7 using the copy from {clock_text(status.last_synced_at)}"


def chip_view(status: ShopStatus) -> Optional[ChipView]:
    """Shop mode only. Local and pinned return None."""
    if status.mode is not SharingMode.SHOP or status.folder is None:
        return None
    if status.reachable:
        text = f"Settings: shop \u00b7 {status.label or ''}"
        severity: ChipSeverity = "ok"
    elif status.last_synced_at is None:
        text = "Settings: shop offline \u00b7 no copy yet"
        severity = "warning"
    else:
        text = f"Settings: shop offline \u00b7 copy from {clock_text(status.last_synced_at)}"
        severity = "warning"
    synced = "never" if status.last_synced_at is None else _stamp(status.last_synced_at)
    tooltip = f"Settings folder: {status.folder}\nLast synced: {synced}"
    if status.pending_count > 0:
        tooltip = f"{tooltip}\n{status.pending_count} changes waiting for the share"
    return ChipView(text=text, tooltip=tooltip, severity=severity)


def prompt_copy(target: DiscoveredShop) -> PromptCopy:
    """created_by_host empty means another computer. created_at None omits the date."""
    host = target.marker.created_by_host.strip() or "another computer"
    created = target.marker.created_at
    if created is None:
        question = f"Set up on {host}. Use them on this computer?"
    else:
        question = f"Set up on {host}, {_long_date(created)}. Use them on this computer?"
    return PromptCopy(headline=PROMPT_HEADLINE, question=question, note=PROMPT_NOTE)


def sharing_intent(status: ShopStatus, *, checked: bool, folder: Path) -> Optional[SharingIntent]:
    """What Save must do. None means the choice file stays as it is."""
    if status.mode is SharingMode.PINNED:
        return None
    if checked and (status.mode is not SharingMode.SHOP or status.folder != folder):
        return TurnOn(folder)
    if not checked and status.mode is SharingMode.SHOP:
        return TurnOff()
    return None


def shop_folder_for_pick(picked: Path) -> Path:
    """Discovery only finds ``<share root>/Code Studio Settings``."""
    if picked.name == SHOP_FOLDER_NAME:
        return picked
    return picked / SHOP_FOLDER_NAME


def clock_text(when: datetime) -> str:
    """Local wall clock HH:MM of an aware UTC datetime."""
    local = _as_local(when)
    return f"{local.hour:02d}:{local.minute:02d}"


def relative_text(when: datetime, *, now: datetime) -> str:
    """just now, n min ago, n h ago, yesterday, or n days ago."""
    seconds = int((_as_utc(now) - _as_utc(when)).total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"
    hours = seconds // 3600
    if hours < 24:
        return f"{hours} h ago"
    days = seconds // 86400
    if days < 2:
        return "yesterday"
    return f"{days} days ago"


def _as_utc(when: datetime) -> datetime:
    if when.tzinfo is None:
        return when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


def _as_local(when: datetime) -> datetime:
    return _as_utc(when).astimezone()


def _stamp(when: datetime) -> str:
    local = _as_local(when)
    return f"{local.year:04d}-{local.month:02d}-{local.day:02d} {local.hour:02d}:{local.minute:02d}"


def _long_date(when: datetime) -> str:
    local = _as_local(when)
    return f"{_MONTHS[local.month - 1]} {local.day}, {local.year}"
