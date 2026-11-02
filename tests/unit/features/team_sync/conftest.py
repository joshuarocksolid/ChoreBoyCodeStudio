"""Shared builders for Team Sync engine tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.features.shop_sharing.model import Machine
from app.features.team_sync.core.mailbox import ACCOUNT_CONF


def machine(tmp: Path, hostname: str) -> Machine:
    return Machine(
        home=tmp / "home",
        hostname=hostname,
        local_state=tmp / "state",
        default_home=tmp / "default-home",
    )


def write_account(
    mails: Path,
    folder: str,
    email: str,
    max_size: int = 30000000,
    user_name: str = "",
    company_name: str = "",
) -> Path:
    account = mails / folder
    for name in ("out", "sent", "zip_in", "inbox"):
        (account / name).mkdir(parents=True, exist_ok=True)
    lines = [f"EmailAddress}}{{{email}", f"MaxMsgSize}}{{{max_size}"]
    if user_name:
        lines.append(f"UserName}}{{{user_name}")
    if company_name:
        lines.append(f"CompanyName}}{{{company_name}")
    (account / ACCOUNT_CONF).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return account


def touch_watchdog(mails: Path, hostname: str, when: Optional[datetime] = None) -> None:
    moment = when or datetime.now(timezone.utc)
    (mails / f".{hostname}-watchdog").write_text(
        moment.strftime("%Y-%m-%d %H:%M:%S"),
        encoding="utf-8",
    )
