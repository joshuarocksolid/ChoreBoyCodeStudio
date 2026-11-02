"""CBCS-SYNC/1 envelopes. Signing covers the canonical header lines."""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from app.features.team_sync.core import TeamSyncError

SYNC_PREFIX = "CBCS-SYNC/1"
VERBS = ("invite", "join", "push", "have", "want", "note", "rekey")
_MEMBER_ID = re.compile(r"^[0-9a-f]{8}$")
_PROJECT_ID = re.compile(r"^p_[0-9a-f]{16}$")
_BUNDLE_ID = re.compile(r"^[bhjnkw]_[0-9a-f]{16}$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PART = re.compile(r"^(\d+)/(\d+)$")
_CHANGES = re.compile(r"^\d+$")
_LINE = re.compile(r"^exp/[a-z0-9]+(?:-[a-z0-9]+)*$")
_MAX_PARTS = 4096

# Signature is over these lines, in this order. Invite leaves `key` out of the
# HMAC because the invite is unsigned and the key travels in the body.
_CANONICAL_KEYS = (
    "verb",
    "project",
    "from",
    "to",
    "bundle",
    "tip",
    "needs",
    "changes",
    "part",
    "bundle-sha256",
    "part-sha256",
    "member-id",
    "member-name",
    "member-shop",
    "member-email",
    "sender-name",
    "sender-shop",
    "sender-email",
    "accepted",
    "note",
    "removed",
    "line",
    "key",
)
_ALWAYS = (
    "verb",
    "project",
    "from",
    "to",
    "bundle",
    "tip",
    "needs",
    "changes",
    "part",
    "bundle-sha256",
)


@dataclass(frozen=True)
class Envelope:
    verb: str
    project_id: str
    project_name: str
    from_id: str
    to_id: str = ""
    bundle_id: str = ""
    tip: str = ""
    needs: str = ""
    changes: str = "0"
    part: str = "1/1"
    bundle_sha256: str = ""
    part_sha256: str = ""
    signature: str = ""
    key_hex: str = ""
    member_id: str = ""
    member_name: str = ""
    member_shop: str = ""
    member_email: str = ""
    sender_name: str = ""
    sender_shop: str = ""
    sender_email: str = ""
    accepted: str = ""
    note: str = ""
    removed: str = ""
    line: str = ""

    def part_index(self) -> int:
        return _part_numbers(self.part)[0]

    def part_total(self) -> int:
        return _part_numbers(self.part)[1]


def subject_for(envelope: Envelope) -> str:
    return f"{SYNC_PREFIX} {envelope.verb} {envelope.project_id} {envelope.project_name}"


def body_for(envelope: Envelope, *, sign_key: Optional[bytes] = None) -> str:
    fields = _fields(envelope)
    signature = ""
    if envelope.verb != "invite" and sign_key is not None:
        signature = sign(sign_key, canonical_bytes(fields))
    lines = ["CBCS-SYNC/1"]
    for key in _CANONICAL_KEYS:
        if key == "key" and envelope.verb == "invite":
            continue
        if key not in fields and key not in _ALWAYS:
            continue
        if key not in fields:
            continue
        lines.append(f"{key}: {fields[key]}")
    if envelope.verb == "invite" and envelope.key_hex:
        lines.append(f"key: {envelope.key_hex}")
    if signature:
        lines.append(f"signature: {signature}")
    lines.append("")
    lines.append("Sent by ChoreBoy Code Studio. No action is needed in your mail.")
    return "\n".join(lines) + "\n"


def parse_subject(subject: str) -> Optional[tuple]:
    if not subject.startswith(SYNC_PREFIX + " "):
        return None
    rest = subject[len(SYNC_PREFIX) + 1 :]
    pieces = rest.split(" ", 2)
    if len(pieces) < 2:
        return None
    verb = pieces[0]
    project_id = pieces[1]
    project_name = pieces[2] if len(pieces) > 2 else ""
    if verb not in VERBS:
        return None
    return verb, project_id, project_name


def parse_body(text: str) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line == "CBCS-SYNC/1":
            continue
        if line.startswith("Sent by ChoreBoy Code Studio"):
            break
        if ": " not in line:
            continue
        key, value = line.split(": ", 1)
        fields[key] = value
    return fields


def envelope_from_message(subject: str, body: str) -> Optional[Envelope]:
    parsed = parse_subject(subject)
    if parsed is None:
        return None
    verb, project_id, project_name = parsed
    fields = parse_body(body)
    if fields.get("verb") and fields.get("verb") != verb:
        return None
    return Envelope(
        verb=verb,
        project_id=fields.get("project", project_id),
        project_name=project_name,
        from_id=fields.get("from", ""),
        to_id=fields.get("to", ""),
        bundle_id=fields.get("bundle", ""),
        tip=fields.get("tip", ""),
        needs=fields.get("needs", ""),
        changes=fields.get("changes", "0"),
        part=fields.get("part", "1/1"),
        bundle_sha256=fields.get("bundle-sha256", ""),
        part_sha256=fields.get("part-sha256", ""),
        signature=fields.get("signature", ""),
        key_hex=fields.get("key", ""),
        member_id=fields.get("member-id", ""),
        member_name=fields.get("member-name", ""),
        member_shop=fields.get("member-shop", ""),
        member_email=fields.get("member-email", ""),
        sender_name=fields.get("sender-name", ""),
        sender_shop=fields.get("sender-shop", ""),
        sender_email=fields.get("sender-email", ""),
        accepted=fields.get("accepted", ""),
        note=fields.get("note", ""),
        removed=fields.get("removed", ""),
        line=fields.get("line", ""),
    )


def require_bundle_id(value: str) -> str:
    if not _BUNDLE_ID.match(value or ""):
        raise TeamSyncError("That bundle id is not one Team Sync accepts.")
    return value


def validate_envelope(envelope: Envelope) -> None:
    """Reject a message whose ids could be used as path parts.

    Local files are named only from ids that match these patterns.
    """

    if envelope.verb not in VERBS:
        raise TeamSyncError("That team message is not one Team Sync accepts.")
    if not _PROJECT_ID.match(envelope.project_id):
        raise TeamSyncError("That project id is not one Team Sync accepts.")
    if not _MEMBER_ID.match(envelope.from_id):
        raise TeamSyncError("That member id is not one Team Sync accepts.")
    if envelope.to_id and not _MEMBER_ID.match(envelope.to_id):
        raise TeamSyncError("That member id is not one Team Sync accepts.")
    if not _BUNDLE_ID.match(envelope.bundle_id):
        raise TeamSyncError("That bundle id is not one Team Sync accepts.")
    if envelope.tip and not _SHA.match(envelope.tip):
        raise TeamSyncError("That change id is not one Team Sync accepts.")
    if envelope.needs:
        for item in envelope.needs.split(","):
            if not _SHA.match(item):
                raise TeamSyncError("That change id is not one Team Sync accepts.")
    if not _CHANGES.match(envelope.changes or "0"):
        raise TeamSyncError("That team message is not one Team Sync accepts.")
    match = _PART.match(envelope.part or "")
    if match is None:
        raise TeamSyncError("That part number is not one Team Sync accepts.")
    index = int(match.group(1))
    total = int(match.group(2))
    if total < 1 or total > _MAX_PARTS or index < 1 or index > total:
        raise TeamSyncError("That part number is not one Team Sync accepts.")
    if envelope.bundle_sha256 and not _SHA256.match(envelope.bundle_sha256):
        raise TeamSyncError("That bundle checksum is not one Team Sync accepts.")
    if envelope.part_sha256 and not _SHA256.match(envelope.part_sha256):
        raise TeamSyncError("That bundle checksum is not one Team Sync accepts.")
    if envelope.member_id and not _MEMBER_ID.match(envelope.member_id):
        raise TeamSyncError("That member id is not one Team Sync accepts.")
    if envelope.removed and not _MEMBER_ID.match(envelope.removed):
        raise TeamSyncError("That member id is not one Team Sync accepts.")
    if envelope.line and not _LINE.match(envelope.line):
        raise TeamSyncError("That line name is not one Team Sync accepts.")
    if envelope.key_hex and not _SHA256.match(envelope.key_hex):
        raise TeamSyncError("That project key is not one Team Sync accepts.")
    if envelope.verb == "invite" and not _SHA256.match(envelope.key_hex):
        raise TeamSyncError("That project key is not one Team Sync accepts.")


def canonical_bytes(fields: Dict[str, str]) -> bytes:
    """Header lines the HMAC covers. The signature line itself is not included."""

    lines = ["CBCS-SYNC/1"]
    for key in _CANONICAL_KEYS:
        if key not in fields:
            continue
        if key == "key" and fields.get("verb") == "invite":
            continue
        lines.append(f"{key}: {fields[key]}")
    return ("\n".join(lines)).encode("utf-8")


def sign(key: bytes, payload: bytes) -> str:
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def verify_signature(key: bytes, fields: Dict[str, str], signature: str) -> bool:
    if not signature:
        return False
    expected = sign(key, canonical_bytes(fields))
    return digest_equal(expected, signature)


def digest_equal(left: str, right: str) -> bool:
    if len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fields(envelope: Envelope) -> Dict[str, str]:
    fields = {
        "verb": envelope.verb,
        "project": envelope.project_id,
        "from": envelope.from_id,
        "to": envelope.to_id,
        "bundle": envelope.bundle_id,
        "tip": envelope.tip,
        "needs": envelope.needs,
        "changes": envelope.changes,
        "part": envelope.part,
        "bundle-sha256": envelope.bundle_sha256,
    }
    optional = {
        "part-sha256": envelope.part_sha256,
        "member-id": envelope.member_id,
        "member-name": envelope.member_name,
        "member-shop": envelope.member_shop,
        "member-email": envelope.member_email,
        "sender-name": envelope.sender_name,
        "sender-shop": envelope.sender_shop,
        "sender-email": envelope.sender_email,
        "accepted": envelope.accepted,
        "note": envelope.note,
        "removed": envelope.removed,
        "line": envelope.line,
    }
    for key, value in optional.items():
        if value:
            fields[key] = value
    if envelope.verb == "rekey" and envelope.key_hex:
        fields["key"] = envelope.key_hex
    return fields


def _part_numbers(part: str) -> tuple:
    if "/" not in part:
        return 1, 1
    left, right = part.split("/", 1)
    try:
        return int(left), int(right)
    except ValueError:
        return 1, 1
