"""Machine-local invite memory. Survives a restart. Not per project."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict, Set

from app.features.shop_sharing.model import Machine
from app.features.team_sync.core.mailbox import atomic_write_bytes

_LOCK = threading.Lock()


def _path(machine: Machine) -> Path:
    return Path(machine.local_state) / "team_sync" / "machine.json"


def _load(machine: Machine) -> Dict[str, object]:
    path = _path(machine)
    if not path.is_file():
        return {"sent_bundles": [], "member_ids": [], "decisions": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"sent_bundles": [], "member_ids": [], "decisions": {}}
    if not isinstance(payload, dict):
        return {"sent_bundles": [], "member_ids": [], "decisions": {}}
    return payload


def _save(machine: Machine, payload: Dict[str, object]) -> None:
    path = _path(machine)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    atomic_write_bytes(path, raw)


def _strings(payload: Dict[str, object], key: str) -> Set[str]:
    value = payload.get(key)
    if not isinstance(value, list):
        return set()
    return {str(item) for item in value if str(item)}


def remember_member(machine: Machine, member_id: str) -> None:
    if not member_id:
        return
    with _LOCK:
        payload = _load(machine)
        found = _strings(payload, "member_ids")
        found.add(member_id)
        payload["member_ids"] = sorted(found)
        _save(machine, payload)


def remember_sent_bundle(machine: Machine, bundle_id: str) -> None:
    if not bundle_id:
        return
    with _LOCK:
        payload = _load(machine)
        found = _strings(payload, "sent_bundles")
        found.add(bundle_id)
        payload["sent_bundles"] = sorted(found)
        _save(machine, payload)


def remember_decision(machine: Machine, invite_id: str, decision: str) -> None:
    if not invite_id or decision not in ("seen", "declined"):
        return
    with _LOCK:
        payload = _load(machine)
        decisions = payload.get("decisions")
        if not isinstance(decisions, dict):
            decisions = {}
        decisions[str(invite_id)] = decision
        payload["decisions"] = decisions
        _save(machine, payload)


def local_member_ids(machine: Machine) -> Set[str]:
    with _LOCK:
        return _strings(_load(machine), "member_ids")


def suppressed_invite_ids(machine: Machine) -> Set[str]:
    """Sent bundles plus invites this machine already saw or declined."""

    with _LOCK:
        payload = _load(machine)
        hidden = _strings(payload, "sent_bundles")
        decisions = payload.get("decisions")
        if isinstance(decisions, dict):
            hidden.update(str(key) for key, value in decisions.items() if value in ("seen", "declined"))
        return hidden


__all__ = [
    "local_member_ids",
    "remember_decision",
    "remember_member",
    "remember_sent_bundle",
    "suppressed_invite_ids",
]
