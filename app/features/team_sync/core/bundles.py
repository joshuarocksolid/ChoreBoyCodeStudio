"""Git bundle bytes, part splits, and the import path that keeps every commit.

Import goes through TeamRepo.import_pack, which feeds the raw pack to
add_thin_pack and checks the object closure before any ref moves.
"""

from __future__ import annotations

import secrets
from typing import List, Sequence

from app.features.team_sync.core import TeamSyncError
from app.features.team_sync.core.protocol import digest_equal, sha256_hex

PART_LIMIT = 10 * 1024 * 1024
_SIZE_CAP = 36 * 1024 * 1024
_HEADER_BUDGET = 8192


def new_bundle_id() -> str:
    return "b_" + secrets.token_hex(8)


def split_parts(data: bytes, limit: int = PART_LIMIT) -> List[bytes]:
    if limit < 1:
        raise TeamSyncError("A bundle part has to be at least one byte.")
    if not data:
        return [b""]
    return [data[index : index + limit] for index in range(0, len(data), limit)]


def join_parts(parts: Sequence[bytes], digests: Sequence[str]) -> bytes:
    """Join only when every part matches the sha256 that was signed with it."""

    if len(parts) != len(digests):
        raise TeamSyncError("A bundle part is missing.")
    for index, part in enumerate(parts):
        actual = sha256_hex(part)
        if not digest_equal(actual, digests[index]):
            raise TeamSyncError("A bundle part failed its checksum.")
    return b"".join(parts)


def attachment_name(project_name: str, bundle_id: str, part: int, total: int) -> str:
    safe = "".join(ch if ch.isalnum() or ch in " ._-" else "_" for ch in project_name).strip()
    if not safe:
        safe = "project"
    base = f"{safe}-{bundle_id}.cbcsbundle"
    if total <= 1:
        return base
    return f"{base}.part-{part:02d}-of-{total:02d}"


def wrapped_base64_length(raw_bytes: int) -> int:
    """Base64 growth plus a CRLF after every 76 encoded columns."""

    encoded = 4 * ((raw_bytes + 2) // 3)
    breaks = 2 * ((encoded + 75) // 76)
    return encoded + breaks


def part_limit_for(max_message_bytes: int) -> int:
    """Largest raw part whose wrapped base64 plus headers stays under the cap.

    The cap is the account MaxMsgSize and the 36 MB SIZE, whichever is smaller.
    """

    cap = _SIZE_CAP if max_message_bytes <= 0 else min(max_message_bytes, _SIZE_CAP)
    budget = cap - _HEADER_BUDGET
    if budget < 4:
        return 1024
    lo = 1
    hi = min(PART_LIMIT, budget)
    best = 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if wrapped_base64_length(mid) <= budget:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return min(PART_LIMIT, best)
