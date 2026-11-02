"""Two shops: share, join, send, accept, clash, finish, have, and a forged message."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from app.features.team_sync.api import DELIVERY_DELIVERED, Invite, RESOLVE_THEIRS, ShareRequest
from app.features.team_sync.core.protocol import body_for, sha256_hex
from app.features.team_sync.core.mailbox import render_message
from app.features.team_sync.core.service import TeamSyncService
from datetime import datetime, timezone

from tests.unit.features.team_sync.conftest import machine, touch_watchdog, write_account
from tests.unit.features.team_sync.faxmail_sim import FaxMailSim


def test_two_shops_share_join_send_clash_and_deliver(tmp_path: Path) -> None:
    mails = tmp_path / "Mails"
    sam_account = write_account(mails, "maple", "sam@example.test")
    ana_account = write_account(mails, "cedar", "ana@example.test")
    touch_watchdog(mails, "sam-pc")
    touch_watchdog(mails, "ana-pc")
    sam_root = tmp_path / "sam"
    ana_root = tmp_path / "ana"
    sam_root.mkdir()
    (sam_root / "invoice.py").write_text("def total(x):\n    return x\n", encoding="utf-8")
    sam = TeamSyncService(str(sam_root), machine=machine(tmp_path / "sam-box", "sam-pc"), mail_roots=[str(sam_account)])
    ana = TeamSyncService(str(ana_root), machine=machine(tmp_path / "ana-box", "ana-pc"), mail_roots=[str(ana_account)])
    sim = FaxMailSim(mails)
    sam.share(
        ShareRequest(
            project_name="Invoice",
            my_name="Sam",
            my_shop="Maple",
            invites=[Invite("Ana", "Cedar", "ana@example.test")],
            message="Invoice for the shop",
        )
    )
    assert sim.tick() == 1
    ana.poll()
    invite = ana.pending_invites()[0]
    assert ana.invite_detail(invite.id)["project_name"] == "Invoice"
    ana.accept_invite(invite.id, str(ana_root), my_name="Ana", my_shop="Cedar")
    assert sim.tick() >= 1
    sam.poll()
    assert any(member.email == "ana@example.test" for member in sam.status().members)

    path = Path(ana.project_root) / "invoice.py"
    path.write_text("def total(x):\n    return x + 1\n", encoding="utf-8")
    sent = ana.send("round the total")
    assert sim.tick() >= 1
    sam.poll()
    incoming = sam.incoming()
    assert len(incoming) == 1
    assert sam.accept(incoming[0].id) is None
    assert "return x + 1" in Path(sam.project_root, "invoice.py").read_text(encoding="utf-8")
    sim.tick()
    ana.poll()

    Path(sam.project_root, "invoice.py").write_text("def total(x):\n    return x + 2\n", encoding="utf-8")
    sam.save_only("sam's total")
    path.write_text("def total(x):\n    return x * 2\n", encoding="utf-8")
    ana.send("ana's total")
    assert sim.tick() >= 1
    sam.poll()
    state = sam.accept(sam.incoming()[0].id)
    assert state is not None and not state.done
    sam.resolve(state.clashes[0].id, RESOLVE_THEIRS)
    merged = sam.finish_combine()
    assert len(merged.parents) == 2
    assert "return x * 2" in Path(sam.project_root, "invoice.py").read_text(encoding="utf-8")

    assert sim.tick() >= 1
    ana.poll()
    delivery = ana._delivery_for(sent.id)
    assert delivery is not None
    assert delivery.state == DELIVERY_DELIVERED
    incoming = ana.incoming()
    assert incoming, "finishing a combine left the other station with nothing to receive"
    assert ana.accept(incoming[0].id) is None
    assert "return x * 2" in Path(ana.project_root, "invoice.py").read_text(encoding="utf-8")

    _forge(sam, ana_account)
    sam.poll()
    assert sam.status().unverified >= 1
    assert all(item.verified for item in sam.incoming())


def _forge(sam: TeamSyncService, ana_account: Path) -> None:
    team = sam._require_team()
    bundle = b"not a real bundle"
    body = body_for(
        __import__("app.features.team_sync.core.protocol", fromlist=["Envelope"]).Envelope(
            verb="push",
            project_id=team.project_id,
            project_name=team.name,
            from_id="deadbeef",
            to_id=sam._require_me().member_id,
            bundle_id="b_ffffffffffffffff",
            tip="0" * 40,
            changes="1",
            part="1/1",
            bundle_sha256=sha256_hex(bundle),
            part_sha256=sha256_hex(bundle),
        ),
        sign_key=b"not-the-key-not-the-key-not-key",
    )
    raw = render_message(
        sender_name="Stranger",
        sender_email="ana@example.test",
        recipient_name="Sam",
        recipient_email="sam@example.test",
        subject=f"CBCS-SYNC/1 push {team.project_id} {team.name}",
        body=body,
        when=datetime.now(timezone.utc),
        message_id="forged@invoice",
    )
    headers, message_body = raw.decode("utf-8").split("\r\n\r\n", 1)
    folder = "20261102151515000"
    prefix = folder + "!"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(prefix + "/_headers_", headers + "\r\n")
        archive.writestr(prefix + "/textfile0", message_body)
        archive.writestr(prefix + "/Invoice-b_ffffffffffffffff.cbcsbundle", bundle)
    # The forged note is addressed to Sam, so it lands in Sam's zip_in.
    dest_account = Path(sam._require_account().path)
    (dest_account / "zip_in" / f"{folder}!.zip").write_bytes(buffer.getvalue())
    del ana_account
