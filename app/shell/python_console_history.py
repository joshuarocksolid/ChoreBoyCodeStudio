"""Persistence helpers for Python console command history."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from app.bootstrap.paths import PathInput, global_python_console_history_path

if TYPE_CHECKING:
    from app.features.shop_sharing.service import SharedDocuments


def load_python_console_history(state_root: Optional[PathInput], *, max_entries: int) -> list[str]:
    """Load command history list from disk."""
    shop = _shop_documents(state_root)
    if shop is not None:
        return shop.load_console_history(max_entries=max_entries)
    path = Path(global_python_console_history_path(state_root)).expanduser().resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    raw_history = payload.get("history", [])
    if not isinstance(raw_history, list):
        return []
    normalized = [entry for entry in raw_history if isinstance(entry, str) and entry.strip()]
    if len(normalized) > max_entries:
        normalized = normalized[-max_entries:]
    return normalized


def save_python_console_history(
    state_root: Optional[PathInput],
    entries: list[str],
    *,
    appended: int,
    max_entries: int,
) -> None:
    """Persist command history.

    Local mode writes ``entries`` whole. Shop mode appends only the last
    ``appended`` entries, the ones this session added, to the shared list.
    """
    shop = _shop_documents(state_root)
    if shop is not None:
        if appended > 0:
            shop.append_console_history(entries[-appended:], max_entries=max_entries)
        return
    path = Path(global_python_console_history_path(state_root)).expanduser().resolve()
    normalized = [entry for entry in entries if isinstance(entry, str) and entry.strip()]
    if len(normalized) > max_entries:
        normalized = normalized[-max_entries:]
    payload = {"history": normalized}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _shop_documents(state_root: Optional[PathInput]) -> "Optional[SharedDocuments]":
    from app.features.shop_sharing.service import route_documents

    return route_documents(state_root).shop
