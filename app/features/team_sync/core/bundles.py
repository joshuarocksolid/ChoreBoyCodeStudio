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


def part_limit_for(max_message_bytes: int) -> int:
    """Fit a part under the terminal cap after base64 growth and headers."""

    if max_message_bytes <= 0:
        return PART_LIMIT
    raw_budget = max(1024, ((max_message_bytes - 4096) * 3) // 4)
    return min(PART_LIMIT, raw_budget)
