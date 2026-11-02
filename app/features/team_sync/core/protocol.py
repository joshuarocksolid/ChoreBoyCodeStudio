"""CBCS-SYNC/1 envelopes. Signing covers the canonical header lines."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Dict, List, Optional

SYNC_PREFIX = "CBCS-SYNC/1"
VERBS = ("invite", "join", "push", "have", "want", "note", "rekey")

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
    )


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
