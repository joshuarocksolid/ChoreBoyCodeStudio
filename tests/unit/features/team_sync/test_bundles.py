"""Bundle round trip, the real-git delta fixture, HMAC, and part checksums."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from app.features.team_sync.api import ShareRequest
from app.features.team_sync.core.bundles import join_parts, split_parts
from app.features.team_sync.core.protocol import (
    Envelope,
    body_for,
    digest_equal,
    sha256_hex,
    verify_signature,
)
from app.features.team_sync.core.repo import TeamRepo
from app.features.team_sync.core.service import TeamSyncService
from app.features.team_sync.core import TeamSyncError
from tests.unit.features.team_sync.conftest import machine, touch_watchdog, write_account

FIXTURE = Path(__file__).parent / "fixtures" / "real_git_delta.bundle"
FIXTURE_TIP = "ddb62daf84c654ec20fdec234f47c6b03bb38314"


def _repo_with_file(root: Path, name: str, text: str) -> TeamRepo:
    root.mkdir()
    (root / name).write_text(text, encoding="utf-8")
    repo = TeamRepo(str(root))
    repo.init_repo()
    repo.commit("start", "Sam", "sam@example.test", "aaaa1111", "shop-pc", _now(), paths=None)
    return repo


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def test_full_and_incremental_round_trip(tmp_path: Path) -> None:
    origin = _repo_with_file(tmp_path / "origin", "note.txt", "one\n")
    full = origin.create_bundle("main", [])
    (tmp_path / "origin" / "note.txt").write_text("two\n", encoding="utf-8")
    second = origin.commit("second", "Sam", "sam@example.test", "aaaa1111", "shop-pc", _now())
    incremental = origin.create_bundle("main", [origin.change(second).parents[0]])

    full_repo = TeamRepo(str(tmp_path / "full"))
    full_repo.init_repo()
    full_refs = full_repo.import_pack(full)
    assert full_repo.head_sha() is None
    full_repo.checkout(full_refs["refs/heads/main"], "main")
    assert (tmp_path / "full" / "note.txt").read_text(encoding="utf-8") == "one\n"

    next_repo = TeamRepo(str(tmp_path / "next"))
    next_repo.init_repo()
    next_repo.import_pack(full)
    next_repo.checkout(full_refs["refs/heads/main"], "main")
    inc_refs = next_repo.import_pack(incremental)
    assert next_repo.get_ref("refs/heads/main") == full_refs["refs/heads/main"]
    next_repo.checkout(inc_refs["refs/heads/main"], "main")
    assert (tmp_path / "next" / "note.txt").read_text(encoding="utf-8") == "two\n"
    assert second in next_repo.new_commit_ids(inc_refs["refs/heads/main"], full_refs["refs/heads/main"])


def test_real_git_delta_bundle_imports_every_commit(tmp_path: Path) -> None:
    repo = TeamRepo(str(tmp_path / "git"))
    repo.init_repo()
    refs = repo.import_pack(FIXTURE.read_bytes())
    assert repo.head_sha() is None
    assert refs["refs/heads/main"] == FIXTURE_TIP
    assert repo.has_object(FIXTURE_TIP)
    blob = repo.file_bytes(FIXTURE_TIP, "big_module.py")
    assert blob is not None and b"# rev 5" in blob
    assert repo.count_since(FIXTURE_TIP, []) == 6


def test_tampered_pack_is_rejected_before_refs_move(tmp_path: Path) -> None:
    raw = bytearray(FIXTURE.read_bytes())
    raw[-20] ^= 0xFF
    repo = TeamRepo(str(tmp_path / "git"))
    repo.init_repo()
    try:
        repo.import_pack(bytes(raw))
    except TeamSyncError:
        pass
    else:
        raise AssertionError("damaged bundle was accepted")
    assert repo.head_sha() is None
    assert repo.get_ref("refs/heads/main") is None


def test_wrong_hmac_is_rejected_before_the_bundle_is_parsed(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "note.txt").write_text("hello\n", encoding="utf-8")
    mails = tmp_path / "Mails"
    account = write_account(mails, "maple", "sam@example.test")
    touch_watchdog(mails, "shop-pc")
    service = TeamSyncService(
        str(project),
        machine=machine(tmp_path / "box", "shop-pc"),
        mail_roots=[str(account)],
    )
    service.share(ShareRequest(project_name="Notes", my_name="Sam", my_shop="Maple"))
    head = service.history(limit=1)[0].id
    key = (project / ".git" / "cbcs" / "key").read_bytes()
    bundle = service._repo.create_bundle("main", [])
    team = service._require_team()
    me = service._require_me()
    envelope = Envelope(
        verb="push",
        project_id=team.project_id,
        project_name="Notes",
        from_id=me.member_id,
        to_id=me.member_id,
        bundle_id="b_0011223344556677",
        tip=head,
        changes="1",
        part="1/1",
        bundle_sha256=sha256_hex(bundle),
        part_sha256=sha256_hex(bundle),
    )
    body = body_for(envelope, sign_key=key).replace(envelope.bundle_sha256, "0" * 64, 1)
    # The replaced digest is inside the signed body, so the signature no longer matches.
    assert "signature: " in body
    signed = body_for(envelope, sign_key=key)
    fields_ok = {
        "verb": envelope.verb,
        "project": envelope.project_id,
        "from": envelope.from_id,
        "to": envelope.to_id,
        "bundle": envelope.bundle_id,
        "tip": envelope.tip,
        "needs": "",
        "changes": "1",
        "part": "1/1",
        "bundle-sha256": envelope.bundle_sha256,
        "part-sha256": envelope.part_sha256,
    }
    signature = signed.split("signature: ", 1)[1].splitlines()[0]
    assert verify_signature(key, fields_ok, signature)
    fields_ok["bundle-sha256"] = "0" * 64
    assert not verify_signature(key, fields_ok, signature)
    assert not digest_equal(signature, "0" * 64)

    forged = _zip(account, body, bundle)
    assert forged.is_file()
    before = service.history(limit=5)
    service.poll()
    assert service.status().unverified == 1
    assert service.incoming() == []
    assert [item.id for item in service.history(limit=5)] == [item.id for item in before]


def test_parts_join_only_when_every_sha_matches() -> None:
    payload = b"abcdefghijklmnopqrstuvwxyz"
    parts = split_parts(payload, limit=10)
    digests = [sha256_hex(part) for part in parts]
    assert join_parts(parts, digests) == payload
    digests[1] = "0" * 64
    try:
        join_parts(parts, digests)
    except TeamSyncError as exc:
        assert "checksum" in str(exc)
    else:
        raise AssertionError("tampered part was joined")


def _zip(account: Path, body: str, bundle: bytes) -> Path:
    folder = "20261102120000000"
    prefix = folder + "!"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(prefix + "/_headers_", "Subject: CBCS-SYNC/1 push Notes\r\nFrom: Sam <sam@example.test>\r\n\r\n")
        archive.writestr(prefix + "/textfile0", body)
        archive.writestr(prefix + "/Notes-b_0011223344556677.cbcsbundle", bundle)
    dest = account / "zip_in" / f"{folder}!.zip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(buffer.getvalue())
    return dest
