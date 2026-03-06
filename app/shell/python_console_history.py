"""Persistence helpers for Python console command history."""

from __future__ import annotations

import json
from pathlib import Path


def load_python_console_history(history_path: str | Path, *, max_entries: int) -> list[str]:
    """Load command history list from disk."""
    path = Path(history_path).expanduser().resolve()
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


def save_python_console_history(history_path: str | Path, entries: list[str], *, max_entries: int) -> None:
    """Persist command history list to disk."""
    path = Path(history_path).expanduser().resolve()
    normalized = [entry for entry in entries if isinstance(entry, str) and entry.strip()]
    if len(normalized) > max_entries:
        normalized = normalized[-max_entries:]
    payload = {"history": normalized}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
