"""Combine finish, cancel, and restart."""

from __future__ import annotations

from pathlib import Path

from app.features.team_sync.api import RESOLVE_OURS, ShareRequest
from app.features.team_sync.core.service import TeamSyncService
from tests.unit.features.team_sync.conftest import machine, touch_watchdog, write_account
from tests.unit.features.team_sync.faxmail_sim import FaxMailSim


def _pair(tmp_path: Path):
    mails = tmp_path / "Mails"
    sam_account = write_account(mails, "maple", "sam@example.test")
    ana_account = write_account(mails, "cedar", "ana@example.test")
    touch_watchdog(mails, "sam-pc")
    touch_watchdog(mails, "ana-pc")
    sam_root = tmp_path / "sam"
    ana_root = tmp_path / "ana"
    sam_root.mkdir()
    (sam_root / "note.txt").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    sam = TeamSyncService(str(sam_root), machine=machine(tmp_path / "sam-box", "sam-pc"), mail_roots=[str(sam_account)])
    ana = TeamSyncService(str(ana_root), machine=machine(tmp_path / "ana-box", "ana-pc"), mail_roots=[str(ana_account)])
    from app.features.team_sync.api import Invite

    sam.share(
        ShareRequest(
            project_name="Notes",
            my_name="Sam",
            my_shop="Maple",
            invites=[Invite("Ana", "Cedar", "ana@example.test")],
        )
    )
    sim = FaxMailSim(mails)
    sim.tick()
    ana.poll()
    ana.accept_invite(ana.pending_invites()[0].id, str(ana_root), my_name="Ana", my_shop="Cedar")
    sim.tick()
    sam.poll()
    return sam, ana, sim


def test_finish_writes_the_resolution_and_a_merge_commit(tmp_path: Path) -> None:
    sam, ana, sim = _pair(tmp_path)
    note = Path(ana.project_root) / "note.txt"
    note.write_text("alpha\nana\ngamma\n", encoding="utf-8")
    ana.send("ana line")
    sim.tick()
    sam.poll()
    Path(sam.project_root, "note.txt").write_text("alpha\nsam\ngamma\n", encoding="utf-8")
    sam.save_only("sam line")
    incoming = sam.incoming()[0]
    state = sam.accept(incoming.id)
    assert state is not None
    assert state.settled == 0
    clash_id = state.clashes[0].id
    sam.resolve(clash_id, RESOLVE_OURS)
    change = sam.finish_combine()
    assert len(change.parents) == 2
    text = Path(sam.project_root, "note.txt").read_text(encoding="utf-8")
    assert text == "alpha\nsam\ngamma\n"
    assert "Combined" not in text


def test_cancel_leaves_the_worktree_byte_identical(tmp_path: Path) -> None:
    sam, ana, sim = _pair(tmp_path)
    Path(ana.project_root, "note.txt").write_text("alpha\nana\ngamma\n", encoding="utf-8")
    ana.send("ana line")
    sim.tick()
    sam.poll()
    target = Path(sam.project_root, "note.txt")
    target.write_text("alpha\nsam\ngamma\n", encoding="utf-8")
    sam.save_only("sam line")
    before = target.read_bytes()
    state = sam.accept(sam.incoming()[0].id)
    assert state is not None
    sam.cancel_combine()
    assert target.read_bytes() == before
    assert sam.combine_state() is None


def test_restart_resumes_the_session(tmp_path: Path) -> None:
    sam, ana, sim = _pair(tmp_path)
    Path(ana.project_root, "note.txt").write_text("alpha\nana\ngamma\n", encoding="utf-8")
    ana.send("ana line")
    sim.tick()
    sam.poll()
    Path(sam.project_root, "note.txt").write_text("alpha\nsam\ngamma\n", encoding="utf-8")
    sam.save_only("sam line")
    state = sam.accept(sam.incoming()[0].id)
    assert state is not None
    resumed = TeamSyncService(
        sam.project_root,
        machine=machine(tmp_path / "sam-box", "sam-pc"),
        mail_roots=sam._mail_roots,
    )
    again = resumed.combine_state()
    assert again is not None
    assert again.id == state.id
    assert again.clashes[0].id == state.clashes[0].id
    assert again.settled == 0
