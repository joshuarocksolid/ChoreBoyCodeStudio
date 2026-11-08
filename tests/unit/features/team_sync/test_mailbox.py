"""FaxMail adapter: lock order, sent, zip read, duplicates, and one want."""

from __future__ import annotations

from pathlib import Path

from app.features.team_sync.api import Invite, ShareRequest
from app.features.team_sync.core.mailbox import MailScan, publish_out, render_message
from app.features.team_sync.core.service import TeamSyncService
from tests.unit.features.team_sync.conftest import machine, touch_watchdog, write_account
from tests.unit.features.team_sync.faxmail_sim import FaxMailSim
from datetime import datetime, timezone


def test_send_locks_first_and_unlocks_last(tmp_path: Path) -> None:
    account = write_account(tmp_path / "Mails", "maple", "sam@example.test")
    trace: list = []
    message = render_message(
        sender_name="Sam",
        sender_email="sam@example.test",
        recipient_name="Ana",
        recipient_email="ana@example.test",
        subject="CBCS-SYNC/1 note p_1 Notes",
        body="CBCS-SYNC/1\nverb: note\n",
        when=datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc),
        message_id="note@p_1",
    )
    folder = publish_out(account, "20261102120000000", message, {"note.txt": b"hi"}, trace)
    assert trace[0] == "lock"
    assert trace[-1] == "unlock"
    assert "copy" in trace
    published = account / "out" / folder
    assert (published / "message.mail").is_file()
    assert (published / "att" / "note.txt").read_bytes() == b"hi"
    assert not (published / ".lock").exists()


def test_out_moves_to_sent_and_cbcs_zip_is_not_moved(tmp_path: Path) -> None:
    mails = tmp_path / "Mails"
    sam = write_account(mails, "maple", "sam@example.test")
    ana = write_account(mails, "cedar", "ana@example.test")
    touch_watchdog(mails, "shop-pc")
    message = render_message(
        sender_name="Sam",
        sender_email="sam@example.test",
        recipient_name="Ana",
        recipient_email="ana@example.test",
        subject="CBCS-SYNC/1 note p_1 Notes",
        body="CBCS-SYNC/1\nverb: note\nproject: p_1\n",
        when=datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc),
        message_id="note@p_1",
    )
    folder = publish_out(sam, "20261102120000001", message, {})
    other = ana / "zip_in" / "19990101010101010!.zip"
    other.write_bytes(b"not a zip we should touch")
    moved = FaxMailSim(mails).tick()
    assert moved == 1
    assert not (sam / "out" / folder).exists()
    assert (sam / "sent" / folder / "message.mail").is_file()
    delivered = ana / "zip_in" / f"{folder}!.zip"
    assert delivered.is_file()
    assert other.read_bytes() == b"not a zip we should touch"
    scan = MailScan(roots=(str(ana),))
    found = scan.scan()
    assert len(found) == 1
    assert found[0].source == str(delivered)
    assert scan.scan() == []
    assert delivered.is_file()


def test_duplicate_mail_is_ignored_and_missing_needs_sends_one_want(tmp_path: Path) -> None:
    mails = tmp_path / "Mails"
    sam = write_account(mails, "maple", "sam@example.test")
    ana = write_account(mails, "cedar", "ana@example.test")
    touch_watchdog(mails, "sam-pc")
    touch_watchdog(mails, "ana-pc")
    _seed_ana_and_want(tmp_path, mails, sam, ana, FaxMailSim(mails))


def _seed_ana_and_want(tmp_path: Path, mails: Path, sam: Path, ana: Path, sim: FaxMailSim) -> None:
    project = tmp_path / "sam-project"
    project.mkdir()
    (project / "note.txt").write_text("v1\n", encoding="utf-8")
    service = TeamSyncService(
        str(project),
        machine=machine(tmp_path / "sam-box-2", "sam-pc"),
        mail_roots=[str(sam)],
    )
    service.share(
        ShareRequest(
            project_name="Notes",
            my_name="Sam",
            my_shop="Maple",
            invites=[Invite(name="Ana", shop="Cedar", email="ana@example.test")],
        )
    )
    assert sim.tick() == 1
    ana_service = TeamSyncService(
        str(tmp_path / "ana-project"),
        machine=machine(tmp_path / "ana-box-2", "ana-pc"),
        mail_roots=[str(ana)],
    )
    ana_service.poll()
    invite = ana_service.pending_invites()[0]
    ana_service.accept_invite(invite.id, str(tmp_path / "ana-project"), my_name="Ana", my_shop="Cedar")
    assert sim.tick() >= 1
    service.poll()
    (tmp_path / "ana-project" / "note.txt").write_text("v2\n", encoding="utf-8")
    ana_service.send("second")
    assert sim.tick() == 1
    # Rewrite the delivered push so its needs sha is one Sam does not have,
    # and re-sign it. Easier path: poll once (imports), then we craft a second
    # message. The want test below builds that message from the live key.
    service.poll()
    assert service.incoming()
    _inject_push_with_missing_need(service, ana, sam)
    service.poll()
    wants = list((sam / "out").glob("*"))
    assert len(wants) == 1
    body = (wants[0] / "message.mail").read_text(encoding="utf-8")
    assert "verb: want" in body
    service.poll()
    assert len(list((sam / "out").glob("*"))) == 1


def _inject_push_with_missing_need(service: TeamSyncService, ana: Path, sam: Path) -> None:
    from app.features.team_sync.core.protocol import body_for, sha256_hex
    from app.features.team_sync.core.mailbox import render_message
    from datetime import datetime, timezone

    team = service._require_team()
    me = service._require_me()
    ana_member = [member for member in team.members if member.email == "ana@example.test"][0]
    missing = "0123456789abcdef0123456789abcdef01234567"
    bundle = service._repo.create_bundle("main", [])
    envelope = __import__(
        "app.features.team_sync.core.protocol", fromlist=["Envelope"]
    ).Envelope(
        verb="push",
        project_id=team.project_id,
        project_name=team.name,
        from_id=ana_member.id,
        to_id=me.member_id,
        bundle_id="b_aabbccddeeff0011",
        tip=service._repo.head_sha() or "",
        needs=missing,
        changes="1",
        part="1/1",
        bundle_sha256=sha256_hex(bundle),
        part_sha256=sha256_hex(bundle),
    )
    key = (Path(service.project_root) / ".git" / "cbcs" / "key").read_bytes()
    body = body_for(envelope, sign_key=key)
    raw = render_message(
        sender_name=ana_member.name,
        sender_email=ana_member.email,
        recipient_name=me.name,
        recipient_email=me.email,
        subject=f"CBCS-SYNC/1 push {team.project_id} {team.name}",
        body=body,
        when=datetime.now(timezone.utc),
        message_id="want-case@notes",
    )
    import io
    import zipfile

    folder = "20261102130000000"
    prefix = folder + "!"
    raw_text = raw.decode("utf-8")
    headers, message_body = raw_text.split("\r\n\r\n", 1)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(prefix + "/_headers_", headers + "\r\n")
        archive.writestr(prefix + "/textfile0", message_body)
        archive.writestr(prefix + f"/{team.name}-b_aabbccddeeff0011.cbcsbundle", bundle)
    dest = sam / "zip_in" / f"{folder}!.zip"
    dest.write_bytes(buffer.getvalue())
