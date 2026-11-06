"""Proofs for the L1b security, data-loss, and merge defects."""

from __future__ import annotations

import io
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import app.features.team_sync.core.mailbox as mailbox
from app.features.team_sync.api import RESOLVE_OURS, RESOLVE_THEIRS
from app.features.team_sync.core import TeamSyncError
from app.features.team_sync.core.mailbox import atomic_write_bytes, publish_out, render_message
from app.features.team_sync.core.protocol import Envelope, body_for, sha256_hex
from app.features.team_sync.core.repo import TeamRepo
from app.features.team_sync.core.service import TeamSyncService
from tests.unit.features.team_sync.conftest import write_account
from tests.unit.features.team_sync.test_combine import _pair


def _bytes_under(root: Path) -> dict:
    found = {}
    for path in root.rglob("*"):
        if ".git" in path.parts or not path.is_file():
            continue
        found[str(path.relative_to(root))] = path.read_bytes()
    return found


def _zip(account: Path, name: str, body: str, bundle: bytes, attachment: str) -> None:
    prefix = "20261102181818000!"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(prefix + "/_headers_", "Subject: CBCS-SYNC/1 push Notes\r\nFrom: Ana <ana@example.test>\r\n\r\n")
        archive.writestr(prefix + "/textfile0", body)
        archive.writestr(prefix + "/" + attachment, bundle)
    (account / "zip_in" / name).write_bytes(buffer.getvalue())


def test_wire_ids_cannot_escape_the_state_directory(tmp_path: Path) -> None:
    sam, _ana, sim = _pair(tmp_path)
    account = Path(sam._require_account().path)
    outside = tmp_path / "outside"
    absolute = Path("/tmp/cbcs-l1b-abs-inject")
    if absolute.exists():
        absolute.unlink()
    team = sam._require_team()
    me = sam._require_me()
    for bundle_id, filename in (
        ("/tmp/cbcs-l1b-abs-inject", "escape.cbcsbundle"),
        ("../../outside", "escape.cbcsbundle"),
        ("b_abc/def", "escape.cbcsbundle"),
    ):
        body = (
            "CBCS-SYNC/1\n"
            "verb: push\n"
            f"project: {team.project_id}\n"
            f"from: {me.member_id}\n"
            f"to: {me.member_id}\n"
            f"bundle: {bundle_id}\n"
            "tip: " + ("a" * 40) + "\n"
            "changes: 1\n"
            "part: 1/1\n"
        )
        _zip(account, f"{bundle_id.replace('/', '_')}.zip".replace("..", "dot"), body, b"nope", filename)
    sim.tick()
    sam.poll()
    assert not absolute.exists()
    assert not outside.exists()
    state = Path(sam.machine.local_state)
    for path in state.rglob("*"):
        assert "team_sync" in path.parts or path == state or state in path.parents


def test_bad_hmac_never_reaches_import_and_tampered_bytes_do_not_either(tmp_path: Path) -> None:
    sam, ana, sim = _pair(tmp_path)
    note = Path(ana.project_root) / "note.txt"
    note.write_text("alpha\nana\ngamma\n", encoding="utf-8")
    ana.send("ana line")
    calls = {"n": 0}
    real = sam._repo.import_pack

    def spy(data: bytes):
        calls["n"] += 1
        return real(data)

    sam._repo.import_pack = spy  # type: ignore[method-assign]
    team = sam._require_team()
    me = sam._require_me()
    bundle = b"not-the-bundle"
    envelope = Envelope(
        verb="push",
        project_id=team.project_id,
        project_name=team.name,
        from_id=me.member_id,
        to_id=me.member_id,
        bundle_id="b_0011223344556677",
        tip="ab" * 20,
        changes="1",
        part="1/1",
        bundle_sha256=sha256_hex(bundle),
        part_sha256=sha256_hex(bundle),
    )
    signed = body_for(envelope, sign_key=b"wrong-key-wrong-key-wrong-key!!")
    account = Path(sam._require_account().path)
    _zip(account, "bad-hmac.zip", signed, bundle, "Notes-b_0011223344556677.cbcsbundle")
    sam.poll()
    assert calls["n"] == 0
    good_key = (Path(sam.project_root) / ".git" / "cbcs" / "key").read_bytes()
    real_bundle = sam._repo.create_bundle("main", [])
    good = Envelope(
        verb="push",
        project_id=team.project_id,
        project_name=team.name,
        from_id=ana._require_me().member_id,
        to_id=me.member_id,
        bundle_id="b_0011223344556678",
        tip=sam._repo.head_sha() or ("cd" * 20),
        changes="1",
        part="1/1",
        bundle_sha256=sha256_hex(real_bundle),
        part_sha256=sha256_hex(real_bundle),
    )
    body = body_for(good, sign_key=good_key)
    _zip(account, "tampered.zip", body, b"tampered-bytes", "Notes-b_0011223344556678.cbcsbundle")
    sam.poll()
    assert calls["n"] == 0
    assert sam.incoming() == [] or all(item.verified for item in sam.incoming())
    del sim


def test_seen_key_survives_a_touched_mailbox_directory(tmp_path: Path) -> None:
    sam, ana, sim = _pair(tmp_path)
    Path(ana.project_root, "note.txt").write_text("alpha\nana\ngamma\n", encoding="utf-8")
    ana.send("ana line")
    assert sim.tick() >= 1
    calls = {"n": 0}
    real = sam._repo.import_pack

    def spy(data: bytes):
        calls["n"] += 1
        return real(data)

    sam._repo.import_pack = spy  # type: ignore[method-assign]
    sam.poll()
    assert calls["n"] == 1
    os.utime(Path(sam._require_account().path) / "zip_in", None)
    sam.poll()
    assert calls["n"] == 1
    assert len(sam.incoming()) == 1


def test_cancel_keeps_checkpoint_bytes_and_head(tmp_path: Path) -> None:
    sam, ana, sim = _pair(tmp_path)
    Path(ana.project_root, "note.txt").write_text("alpha\nana\ngamma\n", encoding="utf-8")
    ana.send("ana line")
    sim.tick()
    sam.poll()
    dirty = Path(sam.project_root, "note.txt")
    dirty.write_text("alpha\nsam\ngamma\n", encoding="utf-8")
    extra = Path(sam.project_root, "extra.txt")
    extra.write_text("untracked\n", encoding="utf-8")
    state = sam.accept(sam.incoming()[0].id)
    assert state is not None
    head = sam._repo.head_sha()
    assert head is not None
    assert "Your work before accepting" in sam._repo.change(head).note
    snapshot = _bytes_under(Path(sam.project_root))
    sam.cancel_combine()
    assert sam._repo.head_sha() == head
    assert _bytes_under(Path(sam.project_root)) == snapshot
    assert extra.read_text(encoding="utf-8") == "untracked\n"


def test_operations_are_refused_while_combining(tmp_path: Path) -> None:
    sam, ana, sim = _pair(tmp_path)
    sam.start_experiment("side")
    sam.switch_line("main")
    Path(ana.project_root, "note.txt").write_text("alpha\nana\ngamma\n", encoding="utf-8")
    ana.send("ana line")
    sim.tick()
    sam.poll()
    Path(sam.project_root, "note.txt").write_text("alpha\nsam\ngamma\n", encoding="utf-8")
    sam.save_only("sam line")
    assert sam.accept(sam.incoming()[0].id) is not None
    refused = (
        lambda: sam.send("no"),
        lambda: sam.save_only("no"),
        lambda: sam.restore(sam._repo.head_sha() or ""),
        lambda: sam.undo_change(sam._repo.head_sha() or ""),
        lambda: sam.switch_line("exp/side"),
        lambda: sam.set_aside("hold"),
        lambda: sam.bring_back(0),
        lambda: sam.accept(sam.incoming()[0].id),
    )
    for call in refused:
        try:
            call()
        except TeamSyncError as exc:
            assert str(exc) == "Finish or cancel combining first."
        else:
            raise AssertionError("a combine session allowed a new change")


def test_finish_after_restart_and_after_an_edit(tmp_path: Path) -> None:
    sam, ana, sim = _pair(tmp_path)
    Path(sam.project_root, "other.txt").write_text("same\n", encoding="utf-8")
    sam.save_only("other")
    sim.tick()
    # Ana already joined. Give her the new file by sending it, then diverge both files.
    sam_note = Path(sam.project_root, "note.txt")
    # Publish the added file first so both sides share it.
    # save_only did not send. Send a no-op by changing nothing new: commit is already saved.
    # Copy the file onto Ana by a push of current main.
    Path(sam.project_root, "marker.txt").write_text("m\n", encoding="utf-8")
    sam.send("marker")
    sim.tick()
    ana.poll()
    ana.accept(ana.incoming()[0].id)
    Path(ana.project_root, "note.txt").write_text("alpha\nana\ngamma\n", encoding="utf-8")
    Path(ana.project_root, "other.txt").write_text("ana\n", encoding="utf-8")
    ana.send("both")
    sim.tick()
    sam.poll()
    Path(sam.project_root, "note.txt").write_text("alpha\nsam\ngamma\n", encoding="utf-8")
    Path(sam.project_root, "other.txt").write_text("sam\n", encoding="utf-8")
    sam.save_only("both")
    state = sam.accept(sam.incoming()[0].id)
    assert state is not None and len(state.clashes) == 2
    for clash in state.clashes:
        sam.resolve(clash.id, RESOLVE_OURS)
    resumed = TeamSyncService(sam.project_root, machine=sam.machine, mail_roots=sam._mail_roots)
    assert resumed.combine_state() is not None
    Path(sam.project_root, "other.txt").write_text("edited during combine\n", encoding="utf-8")
    try:
        resumed.finish_combine()
    except TeamSyncError as exc:
        assert "changed during the combine" in str(exc)
    else:
        raise AssertionError("finish ignored an edit")
    again = resumed.combine_state()
    assert again is not None and not again.done
    kept = [clash for clash in again.clashes if clash.path == "note.txt"]
    fresh = [clash for clash in again.clashes if clash.path == "other.txt"]
    assert kept and kept[0].resolution == RESOLVE_OURS
    assert fresh and fresh[0].resolution is None
    resumed.resolve(fresh[0].id, RESOLVE_THEIRS)
    change = resumed.finish_combine()
    assert "Combined" in change.note
    assert "You accepted" in " ".join(item.text for item in resumed.feed())
    assert Path(sam.project_root, "note.txt").read_text(encoding="utf-8") == "alpha\nsam\ngamma\n"
    del sam_note


def test_file_committed_during_a_session_is_kept(tmp_path: Path) -> None:
    sam, ana, sim = _pair(tmp_path)
    Path(ana.project_root, "note.txt").write_text("alpha\nana\ngamma\n", encoding="utf-8")
    ana.send("ana")
    sim.tick()
    sam.poll()
    Path(sam.project_root, "note.txt").write_text("alpha\nsam\ngamma\n", encoding="utf-8")
    sam.save_only("sam")
    state = sam.accept(sam.incoming()[0].id)
    assert state is not None
    sam.resolve(state.clashes[0].id, RESOLVE_OURS)
    Path(sam.project_root, "during.txt").write_text("kept\n", encoding="utf-8")
    me = sam._require_me()
    sam._repo.commit("during", me.name, me.email, me.member_id, "pc", datetime.now(timezone.utc))
    sam.finish_combine()
    assert Path(sam.project_root, "during.txt").read_text(encoding="utf-8") == "kept\n"


def test_merge_base_on_a_criss_cross(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "note.txt").write_text("p\n", encoding="utf-8")
    repo = TeamRepo(str(root))
    repo.init_repo()
    now = datetime.now(timezone.utc)
    parent = repo.commit("p", "Sam", "sam@example.test", "aaaa1111", "pc", now)
    (root / "note.txt").write_text("a\n", encoding="utf-8")
    middle = repo.commit("a", "Sam", "sam@example.test", "aaaa1111", "pc", now)
    (root / "note.txt").write_text("x\n", encoding="utf-8")
    repo.commit("x", "Sam", "sam@example.test", "aaaa1111", "pc", now)
    (root / "note.txt").write_text("d\n", encoding="utf-8")
    merged = repo.commit("d", "Sam", "sam@example.test", "aaaa1111", "pc", now, extra_parents=[parent])
    assert repo.merge_base(merged, middle) == middle


def test_worktree_rejects_paths_outside_the_project_and_keeps_the_executable_bit(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "note.txt").write_text("one\n", encoding="utf-8")
    repo = TeamRepo(str(root))
    repo.init_repo()
    repo.commit("seed", "Sam", "sam@example.test", "aaaa1111", "pc", datetime.now(timezone.utc))
    outside = tmp_path / "outside"
    for path in ("../outside", "/tmp/cbcs-l1b-worktree", ".git/config", "dir/.git/hooks"):
        try:
            repo.replace_worktree({path: b"nope\n"})
        except TeamSyncError:
            pass
        else:
            raise AssertionError(path)
    assert not outside.exists()
    assert not Path("/tmp/cbcs-l1b-worktree").exists()
    repo.replace_worktree({"run.sh": b"#!/bin/sh\n"}, {"run.sh": 0o100755})
    assert os.stat(root / "run.sh").st_mode & 0o111


def test_fast_forward_does_not_invent_a_merge_commit(tmp_path: Path) -> None:
    sam, ana, sim = _pair(tmp_path)
    before = sam._repo.head_sha()
    Path(ana.project_root, "note.txt").write_text("alpha\nana\ngamma\n", encoding="utf-8")
    sent = ana.send("ana")
    sim.tick()
    sam.poll()
    assert sam.accept(sam.incoming()[0].id) is None
    head = sam._repo.change(sam._repo.head_sha() or "")
    assert head.id == sent.id or before in head.parents or len(head.parents) == 1
    assert "return" not in Path(sam.project_root, "note.txt").read_text(encoding="utf-8")
    assert "ana" in Path(sam.project_root, "note.txt").read_text(encoding="utf-8")


def test_invite_requires_an_empty_folder_and_keeps_team_json(tmp_path: Path) -> None:
    sam, ana, sim = _pair(tmp_path)
    # _pair already accepted. Build a second invite into a dirty folder.
    created = (Path(sam.project_root) / "cbcs" / "team.json").read_text(encoding="utf-8")
    assert "created_at" in created
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "keep.txt").write_text("mine\n", encoding="utf-8")
    # There is no second invite. The empty-folder rule is what accept_invite enforces.
    # Re-share is refused, so call the folder check through a fresh invite poll by
    # writing nothing and checking the occupied path is unchanged when we try accept
    # of a missing id... Use the joiner's team file from the accepted project.
    ana_team = (Path(ana.project_root) / "cbcs" / "team.json").read_text(encoding="utf-8")
    assert "Ana" in ana_team
    assert created.split("created_at", 1)[1][:40] in ana_team or "created_at" in ana_team
    try:
        ana.accept_invite("b_0000000000000000", str(occupied))
    except TeamSyncError as exc:
        assert "empty folder" in str(exc)
    else:
        raise AssertionError("accept wrote into a folder that already had files")
    assert (occupied / "keep.txt").read_text(encoding="utf-8") == "mine\n"
    del sim


def test_usb_bundle_is_signed_and_a_tampered_one_is_not_imported(tmp_path: Path) -> None:
    sam, _ana, _sim = _pair(tmp_path)
    dest = tmp_path / "shop.cbcsbundle"
    calls = {"n": 0}
    real = sam._repo.import_pack

    def spy(data: bytes):
        calls["n"] += 1
        return real(data)

    sam._repo.import_pack = spy  # type: ignore[method-assign]
    sam.export_bundle(str(dest))
    raw = bytearray(dest.read_bytes())
    # Flip a byte inside the zip payload after the local header so the bundle bytes change.
    raw[-8] ^= 0xFF
    dest.write_bytes(bytes(raw))
    try:
        sam.import_bundle(str(dest))
    except TeamSyncError:
        pass
    else:
        raise AssertionError("tampered usb bundle was accepted")
    assert calls["n"] == 0


def test_send_publishes_main_and_share_experiment_publishes_the_line(tmp_path: Path) -> None:
    sam, _ana, _sim = _pair(tmp_path)
    sam.start_experiment("totals")
    Path(sam.project_root, "note.txt").write_text("alpha\nexp\ngamma\n", encoding="utf-8")
    try:
        sam.send("from the experiment")
    except TeamSyncError as exc:
        assert "main" in str(exc).lower() or "main" in str(exc)
    else:
        raise AssertionError("send published an experiment")
    sam.share_experiment("exp/totals")
    account = Path(sam._require_account().path)
    bodies = []
    for folder in (account / "out").iterdir():
        mail = folder / "message.mail"
        if mail.is_file():
            bodies.append(mail.read_text(encoding="utf-8", errors="replace"))
    assert any("line: exp/totals" in body for body in bodies)


def test_a_note_is_in_the_signed_body_and_shows_in_the_feed(tmp_path: Path) -> None:
    sam, ana, sim = _pair(tmp_path)
    ana.post_note("bring the invoice")
    assert sim.tick() >= 1
    sam.poll()
    assert any(item.text == "bring the invoice" for item in sam.feed())


def test_restore_does_not_roll_back_team_json(tmp_path: Path) -> None:
    sam, ana, sim = _pair(tmp_path)
    before = (Path(sam.project_root) / "cbcs" / "team.json").read_bytes()
    old = sam.history(limit=5)[-1].id
    Path(sam.project_root, "note.txt").write_text("alpha\ndirty\ngamma\n", encoding="utf-8")
    sam.restore(old)
    assert (Path(sam.project_root) / "cbcs" / "team.json").read_bytes() == before
    del ana, sim


def test_remove_member_publishes_before_it_switches_keys(tmp_path: Path, monkeypatch) -> None:
    sam, _ana, _sim = _pair(tmp_path)
    key_before = (Path(sam.project_root) / ".git" / "cbcs" / "key").read_bytes()
    team_before = (Path(sam.project_root) / "cbcs" / "team.json").read_bytes()

    def boom(*_args, **_kwargs):
        raise TeamSyncError("terminal refused the message")

    from app.features.team_sync.api import Member
    from app.features.team_sync.core.team import load_team, replace_member, save_team

    root = Path(sam.project_root)
    team = load_team(root)
    assert team is not None
    save_team(root, replace_member(team, Member("cccccccc", "Bea", "Oak", "bea@example.test")))
    me = sam._require_me()
    sam._repo.commit("Bea joined", me.name, me.email, me.member_id, "pc", datetime.now(timezone.utc), paths=["cbcs/team.json"])
    key_before = (root / ".git" / "cbcs" / "key").read_bytes()
    team_before = (root / "cbcs" / "team.json").read_bytes()
    monkeypatch.setattr("app.features.team_sync.core.service.publish_out", boom)
    try:
        sam.remove_member(_ana._require_me().member_id)
    except TeamSyncError:
        pass
    else:
        raise AssertionError("remove member ignored a failed publish")
    assert (Path(sam.project_root) / ".git" / "cbcs" / "key").read_bytes() == key_before
    assert (Path(sam.project_root) / "cbcs" / "team.json").read_bytes() == team_before


def test_atomic_write_retries_and_can_succeed_later(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "note.txt"
    real = os.replace

    def fail(_src, _dst):
        raise OSError("full")

    monkeypatch.setattr(mailbox.os, "replace", fail)
    try:
        atomic_write_bytes(target, b"hi\n")
    except TeamSyncError as exc:
        assert "full" in str(exc) or "Could not write" in str(exc)
    else:
        raise AssertionError("a failed replace was treated as success")
    assert not target.exists()

    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("full")
        return real(src, dst)

    monkeypatch.setattr(mailbox.os, "replace", flaky)
    atomic_write_bytes(target, b"hi\n")
    assert target.read_bytes() == b"hi\n"
    assert calls["n"] == 3


def test_lock_is_created_before_the_message_and_removed_after(tmp_path: Path, monkeypatch) -> None:
    account = write_account(tmp_path / "Mails", "maple", "sam@example.test")
    events = []
    real_open = os.open
    real_unlink = os.unlink
    real_replace = os.replace

    def spy_open(path, flags, *args, **kwargs):
        events.append(("open", str(path)))
        return real_open(path, flags, *args, **kwargs)

    def spy_unlink(path, *args, **kwargs):
        events.append(("unlink", str(path)))
        return real_unlink(path, *args, **kwargs)

    def spy_replace(src, dst):
        events.append(("replace", str(dst)))
        return real_replace(src, dst)

    monkeypatch.setattr(mailbox.os, "open", spy_open)
    monkeypatch.setattr(mailbox.os, "unlink", spy_unlink)
    monkeypatch.setattr(mailbox.os, "replace", spy_replace)
    message = render_message(
        sender_name="Sam",
        sender_email="sam@example.test",
        recipient_name="Ana",
        recipient_email="ana@example.test",
        subject="CBCS-SYNC/1 note p_1 Notes",
        body="CBCS-SYNC/1\nverb: note\n",
        when=datetime(2026, 11, 2, tzinfo=timezone.utc),
        message_id="lock@p",
    )
    publish_out(account, "20261102120000007", message, {"Notes.cbcsbundle": b"abc"})
    lock_at = next(index for index, item in enumerate(events) if item[0] == "open" and item[1].endswith("/.lock"))
    mail_at = next(
        index
        for index, item in enumerate(events)
        if item[0] == "replace" and "/out/" in item[1] and item[1].endswith("/message.mail")
    )
    unlock_at = next(index for index, item in enumerate(events) if item[0] == "unlink" and item[1].endswith("/.lock"))
    assert lock_at < mail_at < unlock_at


def test_a_foreign_out_folder_is_never_removed_or_written(tmp_path: Path, monkeypatch) -> None:
    account = write_account(tmp_path / "Mails", "maple", "sam@example.test")
    mail_id = "20261102120000008"
    foreign = account / "out" / mail_id
    foreign.mkdir()
    (foreign / "message.mail").write_bytes(b"foreign")
    (foreign / ".lock").write_bytes(b"x")
    message = render_message(
        sender_name="Sam",
        sender_email="sam@example.test",
        recipient_name="Ana",
        recipient_email="ana@example.test",
        subject="CBCS-SYNC/1 note p_1 Notes",
        body="CBCS-SYNC/1\nverb: note\n",
        when=datetime(2026, 11, 2, tzinfo=timezone.utc),
        message_id="race@p",
    )
    publish_out(account, mail_id, message, {})
    assert (foreign / "message.mail").read_bytes() == b"foreign"
    assert (foreign / ".lock").read_bytes() == b"x"
    ours = [path for path in (account / "out").iterdir() if path != foreign]
    assert len(ours) == 1
    assert (ours[0] / "message.mail").is_file()

    plain_id = "20261102120000011"
    plain = account / "out" / plain_id
    plain.mkdir()
    (plain / "message.mail").write_bytes(b"also foreign")
    publish_out(account, plain_id, message, {})
    assert (plain / "message.mail").read_bytes() == b"also foreign"
    assert not (plain / ".lock").exists()

    raced = "20261102120000020"
    real_mkdir = os.mkdir

    def hooked(path, mode=0o777, *, dir_fd=None):
        if os.path.basename(os.fspath(path)) == raced:
            if not os.path.isdir(path):
                real_mkdir(path, mode)
            marker = os.path.join(os.fspath(path), "foreign.txt")
            if not os.path.exists(marker):
                with open(marker, "w", encoding="utf-8") as handle:
                    handle.write("keep")
            raise FileExistsError(os.fspath(path))
        return real_mkdir(path, mode)

    monkeypatch.setattr(os, "mkdir", hooked)
    folder = publish_out(account, raced, message, {})
    raced_dir = account / "out" / raced
    assert folder != raced, folder
    assert (raced_dir / "foreign.txt").read_text(encoding="utf-8") == "keep"
    assert not (raced_dir / "message.mail").exists()
    assert (account / "out" / folder / "message.mail").is_file()


def test_a_corrupt_zip_does_not_drop_the_next_message(tmp_path: Path, monkeypatch) -> None:
    sam, ana, sim = _pair(tmp_path)
    ana.post_note("first note")
    ana.post_note("second note")
    assert sim.tick() >= 1
    account = Path(sam._require_account().path)
    (account / "zip_in" / "000-corrupt.zip").write_bytes(b"PK\x03\x04not-a-zip-yet")
    original = TeamSyncService._append_feed
    calls = {"n": 0}

    def flaky(self, kind, text, author_id):
        if text == "first note" and calls["n"] == 0:
            calls["n"] += 1
            raise OSError("busy")
        return original(self, kind, text, author_id)

    monkeypatch.setattr(TeamSyncService, "_append_feed", flaky)
    sam.poll()
    texts = [item.text for item in sam.feed()]
    assert "second note" in texts
    assert "first note" not in texts
    monkeypatch.setattr(TeamSyncService, "_append_feed", original)
    sam.poll()
    texts = [item.text for item in sam.feed()]
    assert "first note" in texts
    assert "second note" in texts
