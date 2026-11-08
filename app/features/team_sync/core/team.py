"""team.json, the local key, and who this station is. No absolute paths, no secrets in git."""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from app.features.team_sync.api import Member
from app.features.team_sync.core import TeamSyncError
from app.features.team_sync.core.mailbox import atomic_write_bytes

TEAM_FILENAME = "cbcs/team.json"
KEY_NAME = "key"
ME_NAME = "me.json"
SCHEMA_VERSION = 1

DEFAULT_GITIGNORE_LINES = (
    "vendor/",
    "__pycache__/",
    "*.pyc",
    "*.pyo",
    "cbcs/runs/",
    ".cbcs_*",
)


@dataclass(frozen=True)
class TeamFile:
    project_id: str
    name: str
    members: tuple
    created_at: str


@dataclass(frozen=True)
class LocalIdentity:
    member_id: str
    name: str
    shop: str
    email: str
    mailbox: str


def new_member_id() -> str:
    return secrets.token_hex(4)


def new_project_id() -> str:
    return "p_" + secrets.token_hex(8)


def new_key() -> bytes:
    return secrets.token_bytes(32)


def team_path(project_root: Path) -> Path:
    return Path(project_root) / TEAM_FILENAME


def load_team(project_root: Path) -> Optional[TeamFile]:
    path = team_path(project_root)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TeamSyncError(f"Could not read the team file: {exc}") from exc
    if not isinstance(payload, dict):
        raise TeamSyncError("The team file is not a team record.")
    members = []
    for raw in payload.get("members") or []:
        if not isinstance(raw, dict):
            continue
        members.append(
            Member(
                id=str(raw.get("id", "")),
                name=str(raw.get("name", "")),
                shop=str(raw.get("shop", "")),
                email=str(raw.get("email", "")),
            )
        )
    return TeamFile(
        project_id=str(payload.get("project_id", "")),
        name=str(payload.get("name", "")),
        members=tuple(members),
        created_at=str(payload.get("created_at", "")),
    )


def save_team(project_root: Path, team: TeamFile) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "project_id": team.project_id,
        "name": team.name,
        "members": [
            {"id": member.id, "name": member.name, "shop": member.shop, "email": member.email}
            for member in sorted(team.members, key=lambda item: item.id)
        ],
        "created_at": team.created_at,
    }
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    atomic_write_bytes(team_path(project_root), text.encode("utf-8"))


def ensure_gitignore(project_root: Path) -> None:
    path = Path(project_root) / ".gitignore"
    existing = ""
    if path.is_file():
        existing = path.read_text(encoding="utf-8", errors="replace")
    present = set(existing.splitlines())
    missing = [line for line in DEFAULT_GITIGNORE_LINES if line not in present]
    if not missing:
        return
    block = "\n".join(missing) + "\n"
    if not existing:
        text = "# ChoreBoy Code Studio\n" + block
    else:
        if not existing.endswith("\n"):
            existing += "\n"
        text = existing + "\n# ChoreBoy Code Studio\n" + block
    atomic_write_bytes(path, text.encode("utf-8"))


def state_dir(project_root: Path) -> Path:
    path = Path(project_root) / ".git" / "cbcs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_key(project_root: Path, key: bytes) -> None:
    if len(key) != 32:
        raise TeamSyncError("The project key has to be 32 bytes.")
    path = state_dir(project_root) / KEY_NAME
    atomic_write_bytes(path, key, mode=0o600)
    os.chmod(str(path), 0o600)


def read_key(project_root: Path) -> bytes:
    path = state_dir(project_root) / KEY_NAME
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise TeamSyncError(f"Could not read the project key: {exc}") from exc
    if len(data) != 32:
        raise TeamSyncError("The project key is damaged.")
    digest_path = path.with_name(KEY_NAME + ".sha256")
    if digest_path.is_file():
        expected = digest_path.read_text(encoding="utf-8").strip()
        import hashlib

        actual = hashlib.sha256(data).hexdigest()
        if actual != expected:
            raise TeamSyncError("The project key no longer matches its checksum.")
    return data


def write_key_checksum(project_root: Path, key: bytes) -> None:
    import hashlib

    path = state_dir(project_root) / (KEY_NAME + ".sha256")
    atomic_write_bytes(path, (hashlib.sha256(key).hexdigest() + "\n").encode("utf-8"), mode=0o600)


def save_me(project_root: Path, identity: LocalIdentity) -> None:
    payload = {
        "member_id": identity.member_id,
        "name": identity.name,
        "shop": identity.shop,
        "email": identity.email,
        "mailbox": identity.mailbox,
    }
    path = state_dir(project_root) / ME_NAME
    atomic_write_bytes(path, (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def load_me(project_root: Path) -> Optional[LocalIdentity]:
    path = Path(project_root) / ".git" / "cbcs" / ME_NAME
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return LocalIdentity(
        member_id=str(payload.get("member_id", "")),
        name=str(payload.get("name", "")),
        shop=str(payload.get("shop", "")),
        email=str(payload.get("email", "")),
        mailbox=str(payload.get("mailbox", "")),
    )


def utc_stamp(when: datetime) -> str:
    moment = when if when.tzinfo is not None else when.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def member_by_id(team: TeamFile, member_id: str) -> Optional[Member]:
    for member in team.members:
        if member.id == member_id:
            return member
    return None


def member_by_email(team: TeamFile, email: str) -> Optional[Member]:
    wanted = email.strip().lower()
    for member in team.members:
        if member.email.strip().lower() == wanted:
            return member
    return None


def replace_member(team: TeamFile, member: Member) -> TeamFile:
    others: List[Member] = [item for item in team.members if item.id != member.id]
    others.append(member)
    return TeamFile(team.project_id, team.name, tuple(others), team.created_at)


def without_member(team: TeamFile, member_id: str) -> TeamFile:
    kept = tuple(item for item in team.members if item.id != member_id)
    return TeamFile(team.project_id, team.name, kept, team.created_at)


def merge_team_bytes(
    base: Optional[bytes],
    ours: Optional[bytes],
    theirs: Optional[bytes],
    *,
    ours_newer: bool,
) -> Optional[bytes]:
    """Union members by id. A missing member is a removal. Newer field values win."""

    if ours is None and theirs is None:
        return None
    base_payload = _team_payload(base)
    ours_payload = _team_payload(ours)
    theirs_payload = _team_payload(theirs)
    if ours_payload is None and theirs_payload is None:
        return ours if ours is not None else theirs
    base_members = _member_map(base_payload)
    ours_members = _member_map(ours_payload)
    theirs_members = _member_map(theirs_payload)
    removed = set()
    if ours is not None:
        removed |= set(base_members) - set(ours_members)
    if theirs is not None:
        removed |= set(base_members) - set(theirs_members)
    merged = []
    for member_id in sorted((set(base_members) | set(ours_members) | set(theirs_members)) - removed):
        left = ours_members.get(member_id)
        right = theirs_members.get(member_id)
        if left is None:
            merged.append(right)
            continue
        if right is None:
            merged.append(left)
            continue
        merged.append(
            _merge_member(base_members.get(member_id, {}), left, right, ours_newer=ours_newer)
        )
    source = base_payload or ours_payload or theirs_payload or {}
    created = str(source.get("created_at", ""))
    if base_payload is not None and base_payload.get("created_at"):
        created = str(base_payload["created_at"])
    payload = {
        "schema_version": SCHEMA_VERSION,
        "project_id": _merge_field(base_payload, ours_payload, theirs_payload, "project_id", ours_newer),
        "name": _merge_field(base_payload, ours_payload, theirs_payload, "name", ours_newer),
        "members": merged,
        "created_at": created,
    }
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def remember_previous_key(project_root: Path, key: bytes, until: str) -> None:
    """Keep a retired key until ``until`` so mail already in flight still verifies."""

    path = state_dir(project_root) / "previous_keys.json"
    rows: List[dict] = []
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            loaded = []
        if isinstance(loaded, list):
            rows = [item for item in loaded if isinstance(item, dict)]
    rows.append({"key_hex": key.hex(), "until": until})
    atomic_write_bytes(path, (json.dumps(rows, indent=2, sort_keys=True) + "\n").encode("utf-8"), mode=0o600)


def verification_keys(project_root: Path, now_stamp: str) -> List[bytes]:
    """Current key, then previous keys whose grace window is still open."""

    found = [read_key(project_root)]
    path = state_dir(project_root) / "previous_keys.json"
    if not path.is_file():
        return found
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return found
    if not isinstance(loaded, list):
        return found
    for item in loaded:
        if not isinstance(item, dict):
            continue
        until = str(item.get("until", ""))
        if until and until < now_stamp:
            continue
        try:
            key = bytes.fromhex(str(item.get("key_hex", "")))
        except ValueError:
            continue
        if len(key) == 32 and key not in found:
            found.append(key)
    return found


def _team_payload(data: Optional[bytes]) -> Optional[dict]:
    if not data:
        return None
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _member_map(payload: Optional[dict]) -> Dict[str, dict]:
    found: Dict[str, dict] = {}
    if payload is None:
        return found
    for raw in payload.get("members") or []:
        if not isinstance(raw, dict) or not raw.get("id"):
            continue
        member_id = str(raw.get("id"))
        found[member_id] = {
            "id": member_id,
            "name": str(raw.get("name", "")),
            "shop": str(raw.get("shop", "")),
            "email": str(raw.get("email", "")),
        }
    return found


def _merge_member(base: dict, ours: dict, theirs: dict, *, ours_newer: bool) -> dict:
    merged = {"id": str(ours.get("id") or theirs.get("id"))}
    for key in ("name", "shop", "email"):
        merged[key] = _pick_field(str(base.get(key, "")), str(ours.get(key, "")), str(theirs.get(key, "")), ours_newer)
    return merged


def _merge_field(
    base: Optional[dict],
    ours: Optional[dict],
    theirs: Optional[dict],
    key: str,
    ours_newer: bool,
) -> str:
    base_value = str((base or {}).get(key, ""))
    ours_value = str((ours or {}).get(key, base_value))
    theirs_value = str((theirs or {}).get(key, base_value))
    return _pick_field(base_value, ours_value, theirs_value, ours_newer)


def _pick_field(base: str, ours: str, theirs: str, ours_newer: bool) -> str:
    if ours != base and theirs != base and ours != theirs:
        return ours if ours_newer else theirs
    if theirs != base and ours == base:
        return theirs
    return ours
