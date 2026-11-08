"""Shop-day blockers: names, one history after join, and a single writer per project."""

from __future__ import annotations

import threading
from pathlib import Path

from app.features.team_sync.api import DELIVERY_QUEUED, DELIVERY_WAITING_TERMINAL, Invite, ShareRequest
from app.features.team_sync.core.repo import TeamRepo
from app.features.team_sync.core.service import TeamSyncService
from app.features.team_sync.ui.copy import delivery_mark

from tests.unit.features.team_sync.conftest import machine, touch_watchdog, write_account
from tests.unit.features.team_sync.faxmail_sim import FaxMailSim


def test_share_uses_the_account_person_not_the_mailbox_name(tmp_path: Path) -> None:
    mails = tmp_path / "Mails"
    account = write_account(
        mails,
        "default",
        "rocksolid@upwardmail.com",
        user_name="Sam Brenneman",
        company_name="Maple Ridge",
    )
    touch_watchdog(mails, "sam-pc")
    root = tmp_path / "sam"
    root.mkdir()
    (root / "invoice.py").write_text("def total():\n    return 1\n", encoding="utf-8")
    sam = TeamSyncService(str(root), machine=machine(tmp_path / "box", "sam-pc"), mail_roots=[str(account)])
    box = sam.mailboxes()[0]
    assert box.user_name == "Sam Brenneman"
    assert box.company_name == "Maple Ridge"
    sam.share(ShareRequest(project_name="Invoice", invites=[Invite("Ana Kurtz", "Cedar Hollow", "rocksolid@upwardmail.com")]))
    me = sam.status().me
    assert me is not None
    assert me.name == "Sam Brenneman"
    assert me.shop == "Maple Ridge"


def test_sender_does_not_see_their_invite_after_restart(tmp_path: Path) -> None:
    mails = tmp_path / "Mails"
    account = write_account(mails, "default", "rocksolid@upwardmail.com", user_name="Sam Brenneman", company_name="Maple Ridge")
    touch_watchdog(mails, "sam-pc")
    box = tmp_path / "box"
    root = tmp_path / "sam"
    root.mkdir()
    (root / "invoice.py").write_text("x = 1\n", encoding="utf-8")
    host = machine(box, "sam-pc")
    sam = TeamSyncService(str(root), machine=host, mail_roots=[str(account)])
    sam.share(
        ShareRequest(
            project_name="Invoice",
            my_name="Sam Brenneman",
            my_shop="Maple Ridge",
            invites=[Invite("Ana Kurtz", "Cedar Hollow", "rocksolid@upwardmail.com")],
        )
    )
    assert FaxMailSim(mails).tick() == 1
    restarted = TeamSyncService(str(root), machine=host, mail_roots=[str(account)])
    restarted.poll()
    assert restarted.pending_invites() == []

    ana_box = tmp_path / "ana-box"
    ana_machine = machine(ana_box, "ana-pc")
    ana = TeamSyncService(str(tmp_path / "ana"), machine=ana_machine, mail_roots=[str(account)])
    ana.poll()
    invites = ana.pending_invites()
    assert len(invites) == 1
    detail = ana.invite_detail(invites[0].id)
    assert detail["invitee_name"] == "Ana Kurtz"
    assert detail["invitee_shop"] == "Cedar Hollow"
    joined = ana.accept_invite(invites[0].id, str(tmp_path / "ana-project"), my_name="Ana Kurtz", my_shop="Cedar Hollow")
    project = TeamSyncService(joined, machine=ana_machine, mail_roots=[str(account)])
    members = project.status().members
    assert {member.name for member in members} == {"Sam Brenneman", "Ana Kurtz"}
    assert len({member.id for member in members}) == 2
    assert len({member.email for member in members}) == 1


def test_declined_invite_stays_hidden_across_restart(tmp_path: Path) -> None:
    from app.features.team_sync.core.local_state import remember_decision

    mails = tmp_path / "Mails"
    account = write_account(mails, "default", "rocksolid@upwardmail.com")
    touch_watchdog(mails, "pc")
    host = machine(tmp_path / "box", "pc")
    watcher = TeamSyncService(str(tmp_path / "watch"), machine=host, mail_roots=[str(account)])
    sender = TeamSyncService(str(tmp_path / "sam"), machine=machine(tmp_path / "other", "other"), mail_roots=[str(account)])
    (Path(sender.project_root)).mkdir(parents=True, exist_ok=True)
    (Path(sender.project_root) / "invoice.py").write_text("x = 1\n", encoding="utf-8")
    sender.share(
        ShareRequest(
            project_name="Invoice",
            my_name="Sam Brenneman",
            my_shop="Maple Ridge",
            invites=[Invite("Ana Kurtz", "Cedar Hollow", "rocksolid@upwardmail.com")],
        )
    )
    assert FaxMailSim(mails).tick() == 1
    watcher.poll()
    invites = watcher.pending_invites()
    assert len(invites) == 1
    remember_decision(host, invites[0].id, "declined")
    restarted = TeamSyncService(str(tmp_path / "watch-2"), machine=host, mail_roots=[str(account)])
    restarted.poll()
    assert restarted.pending_invites() == []


def test_waiting_terminal_mark_says_waiting() -> None:
    assert delivery_mark(DELIVERY_WAITING_TERMINAL, git_names=False) == ("Waiting", "Waiting for the terminal")
    assert delivery_mark(DELIVERY_QUEUED, git_names=False)[0] == "Queued"


def test_concurrent_status_send_and_poll_keep_one_history(tmp_path: Path) -> None:
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
        )
    )
    assert sim.tick() == 1
    ana.poll()
    ana.accept_invite(ana.pending_invites()[0].id, str(ana_root), my_name="Ana", my_shop="Cedar")
    assert sim.tick() >= 1
    sam.poll()

    active: dict[str, set[int]] = {"status": set(), "commit": set()}
    overlap = {"hit": False}
    gate = threading.Lock()
    orig_status = TeamRepo.status
    orig_commit = TeamRepo.commit

    def status(self: TeamRepo):  # type: ignore[no-untyped-def]
        me = threading.get_ident()
        with gate:
            active["status"].add(me)
            if any(owner != me for owner in active["commit"]):
                overlap["hit"] = True
        try:
            threading.Event().wait(0.02)
            return orig_status(self)
        finally:
            with gate:
                active["status"].discard(me)

    def commit(self: TeamRepo, *args: object, **kwargs: object) -> str:  # type: ignore[no-untyped-def]
        me = threading.get_ident()
        with gate:
            active["commit"].add(me)
            if any(owner != me for owner in active["status"]):
                overlap["hit"] = True
        try:
            threading.Event().wait(0.02)
            return orig_commit(self, *args, **kwargs)  # type: ignore[arg-type]
        finally:
            with gate:
                active["commit"].discard(me)

    TeamRepo.status = status  # type: ignore[method-assign]
    TeamRepo.commit = commit  # type: ignore[method-assign]
    errors: list[BaseException] = []
    barrier = threading.Barrier(10)

    def run(fn) -> None:  # type: ignore[no-untyped-def]
        try:
            barrier.wait(timeout=5)
            fn()
        except BaseException as exc:  # noqa: BLE001 - the assertion reports the real error
            errors.append(exc)

    threads = []
    for _index in range(4):
        threads.append(threading.Thread(target=run, args=(sam.status,)))
        threads.append(threading.Thread(target=run, args=(sam.poll,)))
    for index in range(2):
        def send_one(index: int = index) -> None:
            path = Path(sam.project_root) / f"note_{index}.py"
            path.write_text(f"x = {index}\n", encoding="utf-8")
            sam.send(f"note {index}", [f"note_{index}.py"])

        threads.append(threading.Thread(target=run, args=(send_one,)))
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        notes = [change.note for change in sam.history(limit=20)]
        sent_notes = sorted(
            item.change.note
            for item in sam.feed()
            if item.delivery is not None and item.change is not None and item.change.note.startswith("note ")
        )
        file_0 = Path(sam.project_root, "note_0.py").read_text(encoding="utf-8")
        file_1 = Path(sam.project_root, "note_1.py").read_text(encoding="utf-8")
        assert not any(thread.is_alive() for thread in threads)
        assert errors == []
        assert overlap["hit"] is False
        assert "note 0" in notes and "note 1" in notes
        assert sent_notes == ["note 0", "note 1"]
        assert file_0 == "x = 0\n" and file_1 == "x = 1\n"
        assert sam.status().shared is True
    finally:
        TeamRepo.status = orig_status  # type: ignore[method-assign]
        TeamRepo.commit = orig_commit  # type: ignore[method-assign]
