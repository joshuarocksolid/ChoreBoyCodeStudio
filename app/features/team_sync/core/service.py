"""TeamSyncService implements TeamSyncApi. One poll() is one mail cycle."""

from __future__ import annotations

import json
import secrets
import zipfile
import zlib
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from app.features.shop_sharing.model import Machine
from app.features.shop_sharing.storage import logical_path, share_roots
from app.features.team_sync.api import (
    DELIVERY_DELIVERED,
    DELIVERY_QUEUED,
    DELIVERY_SENT,
    DELIVERY_WAITING_TERMINAL,
    EVENT_COMBINE,
    EVENT_FEED,
    EVENT_HISTORY,
    EVENT_INCOMING,
    EVENT_STATUS,
    EVENT_TOAST_PREFIX,
    FEED_CHANGE,
    FEED_INCOMING,
    FEED_NOTE,
    FEED_SYSTEM,
    TERMINAL_NONE,
    TERMINAL_OK,
    Change,
    CombineState,
    Delivery,
    FeedItem,
    FileChange,
    FileDiff,
    Incoming,
    Mailbox,
    Member,
    Resolution,
    ShareRequest,
    TeamStatus,
    Unsubscribe,
)
from app.features.team_sync.core import TeamSyncError
from app.features.team_sync.core.bundles import (
    attachment_name,
    join_parts,
    new_bundle_id,
    part_limit_for,
    split_parts,
)
from app.features.team_sync.core.combine import CombineSession
from app.features.team_sync.core.ledger import Ledger, OutboxRow, iso
from app.features.team_sync.core.mailbox import (
    InboundMail,
    MailNotReady,
    MailScan,
    address_of,
    atomic_write_bytes,
    discover_mailboxes,
    publish_out,
    is_sent,
    read_account_settings,
    render_message,
    terminal_state,
)
from app.features.team_sync.core.merge3way import TreeMerge, merge_trees
from app.features.team_sync.core.protocol import (
    Envelope,
    body_for,
    digest_equal,
    envelope_from_message,
    parse_body,
    require_bundle_id,
    sha256_hex,
    subject_for,
    validate_envelope,
    verify_signature,
)
from app.features.team_sync.core.repo import TeamRepo
from app.features.team_sync.core.team import (
    LocalIdentity,
    TeamFile,
    ensure_gitignore,
    load_me,
    load_team,
    member_by_email,
    member_by_id,
    merge_team_bytes,
    new_key,
    new_member_id,
    new_project_id,
    read_key,
    remember_previous_key,
    replace_member,
    save_me,
    save_team,
    utc_stamp,
    verification_keys,
    without_member,
    write_key,
    write_key_checksum,
)

_BUSY = "Finish or cancel combining first."
_TEAM_PATH = "cbcs/team.json"
_RETRY_LIMIT = 5

_RANK = {
    DELIVERY_WAITING_TERMINAL: 0,
    DELIVERY_QUEUED: 1,
    DELIVERY_SENT: 2,
    DELIVERY_DELIVERED: 3,
    "accepted": 4,
}


class TeamSyncService:
    def __init__(
        self,
        project_root: str,
        *,
        machine: Optional[Machine] = None,
        clock: Optional[Callable[[], datetime]] = None,
        mail_roots: Optional[Sequence[str]] = None,
    ) -> None:
        self.project_root = str(project_root)
        self.machine = machine if machine is not None else Machine.current()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._mail_roots = None if mail_roots is None else [str(root) for root in mail_roots]
        self._repo = TeamRepo(self.project_root)
        self._subscribers: List[Callable[[str], None]] = []
        self._mail_seq = 0
        self._scan: Optional[MailScan] = None
        self._ledger_obj: Optional[Ledger] = None
        self._ledger_at: str = ""

    def status(self) -> TeamStatus:
        team = self._team()
        me = self._me()
        combine = CombineSession(self.project_root).load() if self._repo.exists() else None
        pending = tuple(self._repo.status()) if self._repo.exists() else ()
        incoming = self.incoming()
        return TeamStatus(
            shared=team is not None,
            project_name=team.name if team is not None else Path(self.project_root).name,
            me=_member(me) if me is not None else None,
            members=team.members if team is not None else (),
            pending=pending,
            waiting=len(incoming),
            combine=combine,
            last_delivery=self._last_delivery(),
            terminal=self._terminal(),
            line=self._repo.branch_name() if self._repo.exists() else "main",
            experiments=tuple(self._repo.experiment_names()) if self._repo.exists() else (),
            set_aside=tuple(self._repo.aside_entries()) if self._repo.exists() else (),
            unverified=self._ledger().unverified_count(),
        )

    def feed(self, limit: int = 200) -> List[FeedItem]:
        items: List[FeedItem] = []
        items.extend(self._read_feed())
        if self._repo.exists() and self._repo.head_sha():
            for change in self._repo.history(limit=limit):
                counted = replace(change, files=self._cached_files(change.id))
                items.append(
                    FeedItem(
                        kind=FEED_CHANGE,
                        id=counted.id,
                        when=counted.when,
                        text=counted.note,
                        author_id=counted.author_id or None,
                        change=counted,
                        delivery=self._delivery_for(counted.id),
                    )
                )
        for item in self.incoming():
            items.append(
                FeedItem(
                    kind=FEED_INCOMING,
                    id=item.id,
                    when=item.arrived,
                    text=item.changes[0].note if item.changes else "Incoming change",
                    author_id=item.from_id,
                    incoming=item,
                )
            )
        items.sort(key=lambda entry: entry.when, reverse=True)
        return items[:limit]

    def mailboxes(self) -> List[Mailbox]:
        return discover_mailboxes(self.machine, self._mail_roots)

    def share(self, request: ShareRequest) -> None:
        if self._team() is not None:
            raise TeamSyncError("This project is already shared.")
        account = self._pick_mailbox(request.mailbox, required=bool(request.invites))
        self._repo.init_repo()
        ensure_gitignore(Path(self.project_root))
        when = self.now()
        member = Member(
            id=new_member_id(),
            name=request.my_name or _name_from_email(account.email if account else ""),
            shop=request.my_shop or (account.label if account else self.machine.hostname),
            email=account.email if account else "",
        )
        team = TeamFile(
            project_id=new_project_id(),
            name=request.project_name,
            members=(member,),
            created_at=utc_stamp(when),
        )
        save_team(Path(self.project_root), team)
        key = new_key()
        write_key(Path(self.project_root), key)
        write_key_checksum(Path(self.project_root), key)
        if account is not None:
            save_me(
                Path(self.project_root),
                LocalIdentity(member.id, member.name, member.shop, member.email, account.path),
            )
        note = request.message.strip() or f"Shared {request.project_name}"
        self._repo.commit(
            note,
            member.name,
            member.email or "team@localhost",
            member.id,
            self.machine.hostname,
            when,
        )
        self._append_feed(FEED_SYSTEM, f"{member.name} shared {request.project_name}", member.id)
        for invite in request.invites:
            self._send_invite(team, member, invite.name, invite.shop, invite.email, request.message)
        self._emit(EVENT_STATUS)
        self._emit(EVENT_FEED)
        self._emit(EVENT_HISTORY)

    def pending_invites(self) -> List[Incoming]:
        invites = []
        team = self._team()
        for payload in self._invite_records():
            if team is not None and payload.get("project_id") != team.project_id:
                continue
            invites.append(_incoming_from_invite(payload))
        return invites

    def invite_detail(self, incoming_id: str) -> Dict[str, str]:
        payload = self._invite(incoming_id)
        return {
            "project_id": str(payload.get("project_id", "")),
            "project_name": str(payload.get("project_name", "")),
            "sender_name": str(payload.get("sender_name", "")),
            "sender_shop": str(payload.get("sender_shop", "")),
            "sender_email": str(payload.get("sender_email", "")),
        }

    def accept_invite(self, incoming_id: str, folder: str, my_name: str = "", my_shop: str = "") -> str:
        _require_empty_folder(Path(folder))
        payload = self._invite(incoming_id)
        root = _empty_project_folder(Path(folder))
        bundle_name = require_bundle_id(str(payload.get("id", incoming_id)))
        bundle = (self._invite_dir() / f"{bundle_name}.bundle").read_bytes()
        claimed = str(payload.get("bundle_sha256", ""))
        if claimed and not digest_equal(sha256_hex(bundle), claimed):
            raise TeamSyncError("The invite bundle no longer matches its checksum.")
        repo = TeamRepo(str(root))
        repo.init_repo()
        refs = repo.import_pack(bundle)
        tip = _tip_from_refs(refs) or str(payload.get("tip", ""))
        branch = "main"
        for name in refs:
            if name.startswith("refs/heads/"):
                branch = name[len("refs/heads/") :]
                break
        repo.checkout(tip, branch)
        imported = load_team(root)
        if imported is None:
            raise TeamSyncError("The invite did not include a team.")
        sender = member_by_id(imported, str(payload.get("from_id", "")))
        if sender is None and imported.members:
            sender = imported.members[0]
        if sender is None:
            raise TeamSyncError("The invite did not include a team.")
        account = self._pick_mailbox(None, required=True)
        if account is None:
            raise TeamSyncError("No FaxMail mailbox found.")
        me = Member(
            id=new_member_id(),
            name=my_name or _name_from_email(account.email),
            shop=my_shop or account.label,
            email=account.email,
        )
        when = self.now()
        team = replace_member(imported, me)
        save_team(root, team)
        key = bytes.fromhex(str(payload["key_hex"]))
        write_key(root, key)
        write_key_checksum(root, key)
        save_me(root, LocalIdentity(me.id, me.name, me.shop, me.email, account.path))
        repo.commit(
            f"{me.name} joined",
            me.name,
            me.email or "team@localhost",
            me.id,
            self.machine.hostname,
            when,
            paths=[_TEAM_PATH],
        )
        repo.set_ref(f"refs/peers/{sender.id}/main", tip)
        self._delete_invite(bundle_name)
        joiner = TeamSyncService(
            str(root),
            machine=self.machine,
            clock=self._clock,
            mail_roots=self._mail_roots,
        )
        part = str(payload.get("part") or "1/1")
        joiner._ledger().mark_seen(
            _seen_key(imported.project_id, sender.id, bundle_name, part),
            iso(self.now()),
            "ok",
        )
        joiner._send_join(team, me, sender, tip)
        self._emit(EVENT_INCOMING)
        return str(root)

    def send(self, note: str, paths: Optional[List[str]] = None) -> Change:
        self._require_idle()
        if self._repo.branch_name() != "main":
            raise TeamSyncError(
                "Sending shares main. Share this line with the team if it should leave the shop."
            )
        change = self._commit_change(note, paths)
        self._push_change(change, ref="main")
        self._emit(EVENT_STATUS)
        self._emit(EVENT_FEED)
        self._emit(EVENT_HISTORY)
        return change

    def share_experiment(self, line: str) -> Change:
        self._require_idle()
        if not line.startswith("exp/"):
            raise TeamSyncError("That line is not an experiment.")
        if self._repo.branch_name() != line:
            raise TeamSyncError("Switch to that line before sharing it.")
        if self._repo.dirty():
            change = self._commit_change(f"Shared {line}", None)
        else:
            head = self._repo.head_sha()
            if not head:
                raise TeamSyncError("Save a change before sharing this line.")
            change = self._repo.change(head)
        self._push_change(change, ref=line)
        self._emit(EVENT_STATUS)
        self._emit(EVENT_FEED)
        self._emit(EVENT_HISTORY)
        return change

    def save_only(self, note: str, paths: Optional[List[str]] = None) -> Change:
        self._require_idle()
        change = self._commit_change(note, paths)
        self._emit(EVENT_STATUS)
        self._emit(EVENT_HISTORY)
        return change

    def post_note(self, text: str) -> None:
        me = self._require_me()
        team = self._require_team()
        self._append_feed(FEED_NOTE, text, me.member_id)
        envelope = self._envelope(
            "note",
            team,
            me.member_id,
            "",
            bundle_id="n_" + secrets.token_hex(8),
            note=text,
        )
        for member in team.members:
            if member.id == me.member_id:
                continue
            self._publish(envelope, None, member, change_id="", tip="")
        self._emit(EVENT_FEED)

    def incoming(self) -> List[Incoming]:
        records = []
        for payload in self._incoming_records():
            changes = tuple(self._repo.change(sha) for sha in payload.get("change_ids") or [])
            records.append(
                Incoming(
                    id=str(payload["id"]),
                    from_id=str(payload["from_id"]),
                    changes=changes,
                    arrived=_parse_time(str(payload.get("arrived", ""))),
                    verified=bool(payload.get("verified", True)),
                )
            )
        return records

    def incoming_diff(self, incoming_id: str) -> List[FileDiff]:
        payload = self._incoming_record(incoming_id)
        tip = str(payload["tip"])
        head = self._repo.head_sha()
        base = self._repo.merge_base(head, tip) if head else None
        return self._repo.diff_commits(tip, base)

    def accept(self, incoming_id: str) -> Optional[CombineState]:
        payload = self._incoming_record(incoming_id)
        return self._merge_tip(
            tip=str(payload["tip"]),
            theirs_from=str(payload["from_id"]),
            note=self._accept_note(str(payload["from_id"])),
            kind="merge",
            incoming_id=incoming_id,
        )

    def dismiss(self, incoming_id: str) -> None:
        payload = self._incoming_record(incoming_id)
        self._repo.delete_ref(f"refs/incoming/{payload['from_id']}/{incoming_id}")
        self._save_incoming(
            [item for item in self._incoming_records() if item.get("id") != incoming_id]
        )
        self._emit(EVENT_INCOMING)
        self._emit(EVENT_STATUS)

    def combine_state(self) -> Optional[CombineState]:
        if not self._repo.exists():
            return None
        return CombineSession(self.project_root).load()

    def resolve(self, clash_id: str, resolution: Resolution) -> CombineState:
        state = CombineSession(self.project_root).resolve(clash_id, resolution)
        self._emit(EVENT_COMBINE)
        return state

    def finish_combine(self) -> Change:
        session = CombineSession(self.project_root)
        meta = session.meta()
        files = session.finish_files()
        if not self._finish_still_matches(meta, files):
            self._checkpoint("finishing a combine")
            head = self._repo.head_sha() or str(meta["ours"])
            base = str(meta.get("base") or "")
            if meta["kind"] in {"merge", "experiment"}:
                base = self._repo.merge_base(head, str(meta["theirs"])) or base
            merge = self._merged(base, head, str(meta["theirs"]), keep_team=meta["kind"] == "revert")
            state = session.remerge(
                ours=head,
                base=base,
                merge=merge,
                modes=self._modes_for(merge, head, str(meta["theirs"])),
            )
            if not state.done:
                raise TeamSyncError("A file changed during the combine. The new clashes are waiting.")
            meta = session.meta()
            files = session.finish_files()
        modes = session.file_modes()
        ours_files = self._repo.tree_files(str(meta["ours"]))
        changed = {
            path: data for path, data in files.items() if ours_files.get(path) != data
        }
        self._repo.replace_worktree(changed, modes, only_listed=True)
        me = self._require_me()
        aside_index = meta.get("aside_index")
        if meta["kind"] == "aside":
            if isinstance(aside_index, int):
                self._repo.drop_aside(aside_index)
            session.clear()
            self._emit(EVENT_COMBINE)
            self._emit(EVENT_STATUS)
            head = self._repo.head_sha() or ""
            return self._repo.change(head)
        extra: List[str] = []
        if meta["kind"] in {"merge", "experiment"} and meta.get("theirs"):
            extra = [str(meta["theirs"])]
        if not self._repo.dirty() and not extra:
            change_id = self._repo.head_sha() or ""
        else:
            change_id = self._repo.commit(
                str(meta.get("commit_note") or meta["note"]),
                me.name,
                me.email or "team@localhost",
                me.member_id,
                self.machine.hostname,
                self.now(),
                paths=list(changed),
                extra_parents=extra or None,
            )
        self._close_incoming(str(meta.get("incoming_id") or ""))
        session.clear()
        self._append_feed(FEED_SYSTEM, str(meta.get("feed") or meta["note"]), me.member_id)
        change = self._repo.change(change_id)
        if meta["kind"] == "merge":
            self._push_change(change, ref="main")
        self._emit(EVENT_COMBINE)
        self._emit(EVENT_HISTORY)
        self._emit(EVENT_STATUS)
        return change

    def cancel_combine(self) -> None:
        CombineSession(self.project_root).clear()
        self._emit(EVENT_COMBINE)
        self._emit(EVENT_STATUS)

    def history(
        self,
        path: Optional[str] = None,
        query: str = "",
        offset: int = 0,
        limit: int = 200,
        all_lines: bool = False,
    ) -> List[Change]:
        if not self._repo.exists():
            return []
        return self._repo.history(path, query, offset, limit, all_lines)

    def change_diff(self, change_id: str, against: Optional[str] = None) -> List[FileDiff]:
        return self._repo.diff_commits(change_id, against)

    def working_diff(self, path: str) -> FileDiff:
        return self._repo.working_diff(path)

    def blame(self, path: str) -> list:
        return self._repo.blame(path)

    def restore(self, change_id: str) -> Change:
        self._require_idle()
        self._checkpoint("restoring a change")
        me = self._require_me()
        head = self._repo.head_sha()
        wanted = self._repo.tree_files(change_id)
        current = self._repo.tree_files(head) if head else {}
        files: Dict[str, Optional[bytes]] = {}
        for path in set(wanted) | set(current):
            if path == _TEAM_PATH:
                files[path] = current.get(path)
                continue
            files[path] = wanted.get(path)
        self._repo.replace_worktree(files, self._repo.tree_modes(change_id))
        note = self._repo.change(change_id).note
        change_id_new = self._repo.commit(
            f"Restored {note}" if note else "Restored an earlier change",
            me.name,
            me.email or "team@localhost",
            me.member_id,
            self.machine.hostname,
            self.now(),
        )
        self._emit(EVENT_HISTORY)
        return self._repo.change(change_id_new)

    def undo_change(self, change_id: str) -> Optional[CombineState]:
        change = self._repo.change(change_id)
        if not change.parents:
            raise TeamSyncError("The first change has nothing before it.")
        return self._merge_tip(
            tip=change.parents[0],
            theirs_from=change.author_id,
            note=f"Undid {change.note}" if change.note else "Undid a change",
            kind="revert",
            incoming_id="",
            base_override=change_id,
        )

    def copy_change(self, change_id: str) -> Optional[CombineState]:
        change = self._repo.change(change_id)
        if not change.parents:
            base = ""
        else:
            base = change.parents[0]
        return self._merge_tip(
            tip=change_id,
            theirs_from=change.author_id,
            note=f"Copied {change.note}" if change.note else "Copied a change",
            kind="cherry",
            incoming_id="",
            base_override=base,
        )

    def set_aside(self, name: str) -> None:
        self._require_idle()
        me = self._require_me()
        self._repo.set_aside(name, me.name, me.email or "team@localhost")
        self._emit(EVENT_STATUS)

    def bring_back(self, index: int) -> Optional[CombineState]:
        self._require_idle()
        stash_sha, base_sha, stash_name = self._repo.aside_trees(index)
        state = self._merge_tip(
            tip=stash_sha,
            theirs_from=stash_name,
            note=f"Brought back {stash_name}",
            kind="aside",
            incoming_id="",
            base_override=base_sha,
            aside_index=index,
            commit_when_clean=False,
        )
        if state is None:
            self._repo.drop_aside(index)
            self._emit(EVENT_STATUS)
        return state

    def mark_milestone(self, change_id: str, version: str, note: str = "") -> None:
        me = self._require_me()
        self._repo.tag(change_id, version, note, me.name, me.email or "team@localhost", self.now())
        self._emit(EVENT_HISTORY)

    def start_experiment(self, name: str, from_change: Optional[str] = None) -> None:
        if self._repo.dirty():
            raise TeamSyncError("Set this work aside before switching lines.")
        line = "exp/" + _slug(name)
        sha = from_change or self._repo.head_sha()
        if not sha:
            raise TeamSyncError("Save a change before starting a line of work.")
        self._repo.create_branch(line, sha)
        self._repo.switch(line)
        self._emit(EVENT_STATUS)

    def switch_line(self, line: str) -> None:
        self._require_idle()
        self._repo.switch(line)
        self._emit(EVENT_STATUS)

    def bring_experiment_in(self, line: str) -> Optional[CombineState]:
        tip = self._repo.get_ref(f"refs/heads/{line}")
        if not tip:
            raise TeamSyncError(f"There is no line named {line}.")
        return self._merge_tip(
            tip=tip,
            theirs_from=line,
            note=f"Brought in {line}",
            kind="experiment",
            incoming_id="",
        )

    def delete_experiment(self, line: str) -> None:
        self._repo.delete_branch(line)
        self._emit(EVENT_STATUS)

    def remove_member(self, member_id: str) -> None:
        self._require_idle()
        me = self._require_me()
        team = self._require_team()
        if member_id == me.member_id:
            raise TeamSyncError("You can't remove yourself.")
        if member_by_id(team, member_id) is None:
            raise TeamSyncError("That person is not on this project.")
        old_key = read_key(Path(self.project_root))
        updated = without_member(team, member_id)
        new = new_key()
        for member in updated.members:
            if member.id == me.member_id:
                continue
            envelope = self._envelope(
                "rekey",
                team,
                me.member_id,
                member.id,
                bundle_id="k_" + secrets.token_hex(8),
                key_hex=new.hex(),
                removed=member_id,
            )
            self._publish(envelope, None, member, change_id="", tip="", sign_key=old_key)
        save_team(Path(self.project_root), updated)
        until = utc_stamp(self.now() + timedelta(days=7))
        remember_previous_key(Path(self.project_root), old_key, until)
        write_key(Path(self.project_root), new)
        write_key_checksum(Path(self.project_root), new)
        self._repo.commit(
            "Removed a team member",
            me.name,
            me.email or "team@localhost",
            me.member_id,
            self.machine.hostname,
            self.now(),
            paths=[_TEAM_PATH],
        )
        self._append_feed(FEED_SYSTEM, "A team member was removed and the key changed.", me.member_id)
        self._emit(EVENT_STATUS)

    def export_bundle(self, dest_path: str) -> None:
        if not self._repo.get_ref("refs/heads/main"):
            raise TeamSyncError("Save a change before exporting a bundle.")
        team = self._require_team()
        me = self._require_me()
        data = self._repo.create_bundle("main", [])
        bundle_id = new_bundle_id()
        tip = self._repo.get_ref("refs/heads/main") or ""
        envelope = self._envelope(
            "push",
            team,
            me.member_id,
            me.member_id,
            bundle_id=bundle_id,
            tip=tip,
            changes="1",
        )
        signed = Envelope(
            verb=envelope.verb,
            project_id=envelope.project_id,
            project_name=envelope.project_name,
            from_id=envelope.from_id,
            to_id=envelope.to_id,
            bundle_id=envelope.bundle_id,
            tip=envelope.tip,
            changes=envelope.changes,
            part="1/1",
            bundle_sha256=sha256_hex(data),
            part_sha256=sha256_hex(data),
        )
        body = body_for(signed, sign_key=read_key(Path(self.project_root)))
        payload = _usb_zip(body, data)
        atomic_write_bytes(Path(dest_path), payload)

    def import_bundle(self, src_path: str) -> Optional[Incoming]:
        raw = Path(src_path).read_bytes()
        body, bundle = _read_usb(raw)
        fields = parse_body(body)
        envelope = Envelope(
            verb=fields.get("verb", ""),
            project_id=fields.get("project", ""),
            project_name=self._require_team().name,
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
            line=fields.get("line", ""),
        )
        validate_envelope(envelope)
        team = self._require_team()
        if envelope.project_id != team.project_id:
            raise TeamSyncError("That bundle is for a different project.")
        if not digest_equal(sha256_hex(bundle), envelope.bundle_sha256):
            raise TeamSyncError("The bundle checksum does not match.")
        canonical = _canonical_fields(envelope)
        keys = verification_keys(Path(self.project_root), iso(self.now()))
        if not any(verify_signature(key, canonical, envelope.signature) for key in keys):
            raise TeamSyncError("That USB bundle could not be verified.")
        return self._import_bundle_bytes(
            bundle,
            from_id=envelope.from_id,
            bundle_id=envelope.bundle_id,
            verified=True,
            line=envelope.line,
        )

    def poll(self) -> None:
        self._refresh_outbound()
        self._scan_mail()
        self._release_holding()
        self._emit(EVENT_STATUS)

    def subscribe(self, callback: Callable[[str], None]) -> Unsubscribe:
        self._subscribers.append(callback)

        def unsubscribe() -> None:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

        return unsubscribe

    def close(self) -> None:
        if self._ledger_obj is not None:
            self._ledger_obj.close()
            self._ledger_obj = None
        self._subscribers.clear()

    def now(self) -> datetime:
        when = self._clock()
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return when.astimezone(timezone.utc)

    def _commit_change(self, note: str, paths: Optional[Sequence[str]]) -> Change:
        me = self._require_me()
        change_id = self._repo.commit(
            note,
            me.name,
            me.email or "team@localhost",
            me.member_id,
            self.machine.hostname,
            self.now(),
            paths=paths,
        )
        return self._repo.change(change_id)

    def _push_change(self, change: Change, ref: str = "main") -> None:
        team = self._require_team()
        me = self._require_me()
        line = ref if ref.startswith("exp/") else ""
        peer_ref = f"refs/peers/{{member}}/{ref}" if line else "refs/peers/{member}/main"
        for member in team.members:
            if member.id == me.member_id:
                continue
            peer = self._repo.get_ref(peer_ref.format(member=member.id))
            prereq = ""
            if peer and self._repo.has_object(peer):
                base = self._repo.merge_base(change.id, peer)
                if base:
                    prereq = base
            bundle_id = new_bundle_id()
            bundle = self._repo.create_bundle(ref, [prereq] if prereq else [])
            envelope = self._envelope(
                "push",
                team,
                me.member_id,
                member.id,
                bundle_id=bundle_id,
                tip=change.id,
                needs=prereq,
                changes=str(self._repo.count_since(change.id, [prereq] if prereq else [])),
                line=line,
            )
            self._publish(envelope, bundle, member, change_id=change.id, tip=change.id)

    def _send_invite(
        self,
        team: TeamFile,
        me: Member,
        name: str,
        shop: str,
        email: str,
        message: str,
    ) -> None:
        head = self._repo.head_sha() or ""
        bundle_id = new_bundle_id()
        bundle = self._repo.create_bundle(self._repo.branch_name(), [])
        envelope = Envelope(
            verb="invite",
            project_id=team.project_id,
            project_name=team.name,
            from_id=me.id,
            to_id="",
            bundle_id=bundle_id,
            tip=head,
            changes=str(self._repo.count_since(head, [])),
            key_hex=read_key(Path(self.project_root)).hex(),
            sender_name=me.name,
            sender_shop=me.shop,
            sender_email=me.email,
        )
        recipient = Member(id="", name=name, shop=shop, email=email)
        self._publish(envelope, bundle, recipient, change_id=head, tip=head, sign_key=None)

    def _send_join(self, team: TeamFile, me: Member, sender: Member, tip: str) -> None:
        envelope = self._envelope(
            "join",
            team,
            me.id,
            sender.id,
            bundle_id="j_" + secrets.token_hex(8),
            tip=tip,
            member_id=me.id,
            member_name=me.name,
            member_shop=me.shop,
            member_email=me.email,
        )
        self._publish(envelope, None, sender, change_id="", tip=tip)

    def _publish(
        self,
        envelope: Envelope,
        bundle: Optional[bytes],
        recipient: Member,
        *,
        change_id: str,
        tip: str,
        sign_key: Optional[bytes] = b"",
    ) -> None:
        account = self._require_account()
        _email, max_size = read_account_settings(Path(account.path) / "account_settings_v2.conf")
        limit = part_limit_for(max_size or 0)
        parts = split_parts(bundle, limit) if bundle else [b""]
        whole = sha256_hex(bundle) if bundle else ""
        total = len(parts) if bundle else 1
        key: Optional[bytes]
        if sign_key == b"":
            key = None if envelope.verb == "invite" else read_key(Path(self.project_root))
        else:
            key = sign_key
        me = self._require_me()
        terminal = self._terminal()
        state = DELIVERY_QUEUED if terminal == TERMINAL_OK else DELIVERY_WAITING_TERMINAL
        created = iso(self.now())
        for index, part in enumerate(parts, start=1):
            part_sha = sha256_hex(part) if bundle else ""
            piece = Envelope(
                verb=envelope.verb,
                project_id=envelope.project_id,
                project_name=envelope.project_name,
                from_id=envelope.from_id,
                to_id=recipient.id,
                bundle_id=envelope.bundle_id,
                tip=envelope.tip,
                needs=envelope.needs,
                changes=envelope.changes,
                part=f"{index}/{total}",
                bundle_sha256=whole,
                part_sha256=part_sha,
                key_hex=envelope.key_hex,
                member_id=envelope.member_id,
                member_name=envelope.member_name,
                member_shop=envelope.member_shop,
                member_email=envelope.member_email,
                sender_name=envelope.sender_name,
                sender_shop=envelope.sender_shop,
                sender_email=envelope.sender_email,
                accepted=envelope.accepted,
                note=envelope.note,
                removed=envelope.removed,
                line=envelope.line,
            )
            body = body_for(piece, sign_key=key)
            raw = render_message(
                sender_name=me.name,
                sender_email=me.email,
                recipient_name=recipient.name,
                recipient_email=recipient.email,
                subject=subject_for(piece),
                body=body,
                when=self.now(),
                message_id=f"{envelope.bundle_id}.{index}@{envelope.project_id}",
            )
            recipient_key = recipient.id or recipient.email
            existing = self._ledger().outbox_part(envelope.bundle_id, recipient_key, index)
            if existing and self._out_live(account.path, existing.out_folder):
                continue
            held = self._part_dir(envelope.bundle_id)
            atomic_write_bytes(held / f"out-{index}.mail", raw)
            attachments = {}
            if bundle:
                filename = attachment_name(envelope.project_name, envelope.bundle_id, index, total)
                attachments[filename] = part
                part_path = held / f"out-{index}"
                atomic_write_bytes(part_path, part)
                atomic_write_bytes(held / f"out-{index}.name", filename.encode("utf-8"))
                self._ledger().add_part(envelope.bundle_id, index, total, part_sha, str(part_path))

            def _claimed(folder_id: str, _index: int = index, _key: str = recipient_key) -> None:
                self._ledger().add_outbox(
                    bundle_id=envelope.bundle_id,
                    recipient=_key,
                    part_idx=_index,
                    part_total=total,
                    verb=envelope.verb,
                    change_id=change_id,
                    tip=tip,
                    created_at=created,
                    out_folder=folder_id,
                    state=state,
                )

            publish_out(
                Path(account.path),
                self._mail_id(),
                raw,
                attachments,
                on_claimed=_claimed,
            )

    def _envelope(self, verb: str, team: TeamFile, from_id: str, to_id: str, **fields: str) -> Envelope:
        return Envelope(
            verb=verb,
            project_id=team.project_id,
            project_name=team.name,
            from_id=from_id,
            to_id=to_id,
            bundle_id=str(fields.get("bundle_id", "")),
            tip=str(fields.get("tip", "")),
            needs=str(fields.get("needs", "")),
            changes=str(fields.get("changes", "0")),
            key_hex=str(fields.get("key_hex", "")),
            member_id=str(fields.get("member_id", "")),
            member_name=str(fields.get("member_name", "")),
            member_shop=str(fields.get("member_shop", "")),
            member_email=str(fields.get("member_email", "")),
            note=str(fields.get("note", "")),
            removed=str(fields.get("removed", "")),
            line=str(fields.get("line", "")),
        )

    def _refresh_outbound(self) -> None:
        account = self._account()
        if account is None:
            return
        terminal = self._terminal()
        for row in self._ledger().rows([DELIVERY_QUEUED, DELIVERY_WAITING_TERMINAL]):
            if row.out_folder and is_sent(Path(account.path), row.out_folder):
                self._ledger().set_state(
                    row.bundle_id,
                    row.recipient,
                    row.part_idx,
                    DELIVERY_SENT,
                    sent_at=iso(self.now()),
                )
            elif row.state == DELIVERY_WAITING_TERMINAL and terminal == TERMINAL_OK:
                self._ledger().set_state(row.bundle_id, row.recipient, row.part_idx, DELIVERY_QUEUED)

    def _scan_mail(self) -> None:
        accounts = self._scan_accounts()
        if not accounts:
            return
        if self._scan is None or self._scan.roots != tuple(accounts):
            self._scan = MailScan(roots=tuple(accounts))
        self._resume_unpublished()
        try:
            mails = self._scan.scan()
        except OSError:
            self._scan.invalidate()
            return
        for mail in mails:
            try:
                self._handle_mail(mail)
            except MailNotReady:
                self._scan.invalidate()
            except (OSError, ValueError, zipfile.BadZipFile, zlib.error):
                self._scan.invalidate()

    def _handle_mail(self, mail: InboundMail) -> None:
        envelope = envelope_from_message(mail.subject, mail.body)
        if envelope is None:
            if self._scan is not None:
                self._scan.remember(mail.key, "skip")
            return
        try:
            validate_envelope(envelope)
        except TeamSyncError:
            self._reject_unverified(mail, envelope)
            return
        team = self._team()
        if team is not None and envelope.project_id != team.project_id and envelope.verb != "invite":
            if self._scan is not None:
                self._scan.remember(mail.key, "skip")
            return
        if team is None and envelope.verb != "invite":
            if self._scan is not None:
                self._scan.remember(mail.key, "skip")
            return
        key = _seen_key(envelope.project_id, envelope.from_id, envelope.bundle_id, envelope.part)
        if self._ledger().has_seen(key):
            if self._scan is not None:
                self._scan.remember(mail.key, "done")
            return
        if not self._trusted(envelope, mail):
            self._reject_unverified(mail, envelope)
            return
        if self._combine_open() and envelope.verb in {"join", "rekey"}:
            self._retry_later(key)
            if self._scan is not None:
                self._scan.forget(mail.key)
            return
        try:
            if envelope.verb in {"push", "invite"} or envelope.part_total() > 1:
                if self._scan is not None:
                    mail = self._scan.load_attachments(mail)
            self._dispatch(envelope, mail)
        except MailNotReady:
            self._retry_later(key)
            if self._scan is not None:
                self._scan.forget(mail.key)
            return
        except TeamSyncError as exc:
            if _permanent_failure(str(exc)):
                self._reject_unverified(mail, envelope)
            else:
                self._retry_later(key)
                if self._scan is not None:
                    self._scan.forget(mail.key)
            return
        except (OSError, ValueError, zipfile.BadZipFile, zlib.error):
            self._retry_later(key)
            if self._scan is not None:
                self._scan.forget(mail.key)
            return
        self._ledger().mark_seen(key, iso(self.now()), "ok")
        if self._scan is not None:
            self._scan.remember(mail.key, "done")

    def _reject_unverified(self, mail: InboundMail, envelope: Envelope) -> None:
        key = _seen_key(envelope.project_id, envelope.from_id, envelope.bundle_id, envelope.part or "1/1")
        self._ledger().mark_seen(key, iso(self.now()), "unverified")
        if self._scan is not None:
            self._scan.remember(mail.key, "done")
        self._emit(EVENT_STATUS)

    def _retry_later(self, key: str) -> None:
        if self._ledger().bump_retry(key) >= _RETRY_LIMIT:
            self._ledger().mark_seen(key, iso(self.now()), "unverified")
            self._emit(EVENT_STATUS)

    def _trusted(self, envelope: Envelope, mail: InboundMail) -> bool:
        sender = address_of(mail.from_header)
        if envelope.verb == "invite":
            return bool(envelope.key_hex) and sender == envelope.sender_email.strip().lower()
        team = self._team()
        if team is None:
            return False
        fields = _canonical_fields(envelope)
        keys = verification_keys(Path(self.project_root), iso(self.now()))
        if envelope.verb == "join":
            if sender != envelope.member_email.strip().lower():
                return False
            return any(verify_signature(key, fields, envelope.signature) for key in keys)
        member = member_by_id(team, envelope.from_id)
        if member is None or sender != member.email.strip().lower():
            return False
        return any(verify_signature(key, fields, envelope.signature) for key in keys)

    def _dispatch(self, envelope: Envelope, mail: InboundMail) -> None:
        if envelope.verb == "invite":
            self._store_invite(envelope, mail)
        elif envelope.verb == "join":
            self._apply_join(envelope)
        elif envelope.verb == "push":
            self._apply_push(envelope, mail)
        elif envelope.verb == "have":
            self._apply_have(envelope)
        elif envelope.verb == "want":
            self._apply_want(envelope)
        elif envelope.verb == "note":
            text = envelope.note or _note_text(mail.body)
            self._append_feed(FEED_NOTE, text, envelope.from_id)
            self._emit(EVENT_FEED)
        elif envelope.verb == "rekey":
            self._apply_rekey(envelope)
        else:
            raise TeamSyncError("Unknown team message.")

    def _store_invite(self, envelope: Envelope, mail: InboundMail) -> None:
        bundle = self._assemble(envelope, mail)
        if bundle is None:
            return
        if envelope.bundle_sha256 and not digest_equal(sha256_hex(bundle), envelope.bundle_sha256):
            raise TeamSyncError("The invite bundle checksum does not match.")
        bundle_id = require_bundle_id(envelope.bundle_id)
        directory = self._invite_dir()
        directory.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(directory / f"{bundle_id}.bundle", bundle)
        payload = {
            "id": envelope.bundle_id,
            "project_id": envelope.project_id,
            "project_name": envelope.project_name,
            "from_id": envelope.from_id,
            "sender_name": envelope.sender_name,
            "sender_shop": envelope.sender_shop,
            "sender_email": envelope.sender_email,
            "key_hex": envelope.key_hex,
            "tip": envelope.tip,
            "bundle_sha256": envelope.bundle_sha256,
            "part": envelope.part or "1/1",
            "arrived": iso(self.now()),
        }
        atomic_write_bytes(
            directory / f"{bundle_id}.json",
            (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
        self._toast(f"{envelope.sender_name} invited you to {envelope.project_name}")
        self._emit(EVENT_INCOMING)

    def _apply_join(self, envelope: Envelope) -> None:
        team = self._require_team()
        me = self._require_me()
        member = Member(
            id=envelope.member_id or envelope.from_id,
            name=envelope.member_name,
            shop=envelope.member_shop,
            email=envelope.member_email,
        )
        if self._combine_open():
            raise MailNotReady("Finish or cancel combining first.")
        if member_by_id(team, member.id) is None:
            save_team(Path(self.project_root), replace_member(team, member))
            self._repo.commit(
                f"{member.name} joined",
                me.name,
                me.email or "team@localhost",
                me.member_id,
                self.machine.hostname,
                self.now(),
                paths=["cbcs/team.json"],
            )
        if envelope.tip and self._repo.has_object(envelope.tip):
            self._repo.set_ref(f"refs/peers/{member.id}/main", envelope.tip)
        self._append_feed(FEED_SYSTEM, f"{member.name} joined {team.name}", member.id)
        self._emit(EVENT_FEED)
        self._emit(EVENT_STATUS)

    def _apply_push(self, envelope: Envelope, mail: InboundMail) -> None:
        bundle = self._assemble(envelope, mail)
        if bundle is None:
            return
        if envelope.bundle_sha256 and not digest_equal(sha256_hex(bundle), envelope.bundle_sha256):
            raise TeamSyncError("The bundle checksum does not match.")
        needs = [item for item in envelope.needs.split(",") if item]
        if any(not self._repo.has_object(sha) for sha in needs):
            self._hold(envelope, bundle, needs)
            self._want_once(envelope)
            return
        self._import_bundle_bytes(
            bundle,
            from_id=envelope.from_id,
            bundle_id=envelope.bundle_id,
            verified=True,
            line=envelope.line,
        )

    def _apply_have(self, envelope: Envelope) -> None:
        tip = envelope.tip
        if not tip:
            return
        when = iso(self.now())
        for row in self._ledger().for_tip(envelope.from_id, tip):
            self._ledger().set_state(
                row.bundle_id,
                row.recipient,
                row.part_idx,
                DELIVERY_DELIVERED,
                delivered_at=when,
            )
        if self._repo.has_object(tip):
            self._repo.set_ref(f"refs/peers/{envelope.from_id}/main", tip)
        self._emit(EVENT_FEED)

    def _apply_want(self, envelope: Envelope) -> None:
        team = self._require_team()
        me = self._require_me()
        member = member_by_id(team, envelope.from_id)
        if member is None or not self._repo.head_sha():
            return
        bundle_id = new_bundle_id()
        bundle = self._repo.create_bundle("main", [])
        head = self._repo.get_ref("refs/heads/main") or ""
        reply = self._envelope(
            "push",
            team,
            me.member_id,
            member.id,
            bundle_id=bundle_id,
            tip=head,
            changes=str(self._repo.count_since(head, [])),
        )
        self._publish(reply, bundle, member, change_id=head, tip=head)

    def _apply_rekey(self, envelope: Envelope) -> None:
        if self._combine_open():
            raise MailNotReady("Finish or cancel combining first.")
        if not envelope.key_hex:
            raise TeamSyncError("The rekey message has no key.")
        try:
            key = bytes.fromhex(envelope.key_hex)
        except ValueError as exc:
            raise TeamSyncError("The rekey message has no key.") from exc
        if len(key) != 32:
            raise TeamSyncError("The rekey message has no key.")
        root = Path(self.project_root)
        team = self._require_team()
        me = self._require_me()
        if envelope.removed and member_by_id(team, envelope.removed) is not None:
            team = without_member(team, envelope.removed)
            save_team(root, team)
            self._repo.commit(
                "Removed a team member",
                me.name,
                me.email or "team@localhost",
                me.member_id,
                self.machine.hostname,
                self.now(),
                paths=[_TEAM_PATH],
            )
        old = read_key(root)
        if old != key:
            remember_previous_key(root, old, utc_stamp(self.now() + timedelta(days=7)))
            write_key(root, key)
            write_key_checksum(root, key)
        self._append_feed(FEED_SYSTEM, "The project key changed.", envelope.from_id)
        self._emit(EVENT_FEED)

    def _want_once(self, envelope: Envelope) -> None:
        flag = self._hold_dir() / f"{envelope.bundle_id}.wanted"
        if flag.is_file():
            return
        team = self._require_team()
        me = self._require_me()
        member = member_by_id(team, envelope.from_id)
        if member is None:
            return
        reply = self._envelope(
            "want",
            team,
            me.member_id,
            member.id,
            bundle_id="w_" + secrets.token_hex(8),
            needs=envelope.needs,
            tip=self._repo.head_sha() or "",
        )
        self._publish(reply, None, member, change_id="", tip=envelope.tip)
        atomic_write_bytes(flag, b"wanted\n")

    def _hold(self, envelope: Envelope, bundle: bytes, needs: List[str]) -> None:
        bundle_id = require_bundle_id(envelope.bundle_id)
        directory = self._hold_dir()
        directory.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(directory / f"{bundle_id}.bundle", bundle)
        payload = {
            "id": envelope.bundle_id,
            "from_id": envelope.from_id,
            "tip": envelope.tip,
            "needs": needs,
            "sha256": envelope.bundle_sha256,
        }
        atomic_write_bytes(
            directory / f"{bundle_id}.json",
            (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )

    def _release_holding(self) -> None:
        directory = self._hold_dir()
        if not directory.is_dir():
            return
        for path in sorted(directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            needs = [item for item in payload.get("needs") or [] if item]
            if any(not self._repo.has_object(sha) for sha in needs):
                continue
            try:
                held_id = require_bundle_id(str(payload.get("id", "")))
            except TeamSyncError:
                continue
            bundle_path = directory / f"{held_id}.bundle"
            try:
                data = bundle_path.read_bytes()
            except OSError:
                continue
            claimed = str(payload.get("sha256", ""))
            if claimed and not digest_equal(sha256_hex(data), claimed):
                continue
            self._import_bundle_bytes(
                data,
                from_id=str(payload.get("from_id", "")),
                bundle_id=held_id,
                verified=True,
            )
            path.unlink(missing_ok=True)
            bundle_path.unlink(missing_ok=True)

    def _import_bundle_bytes(
        self,
        bundle: bytes,
        *,
        from_id: str,
        bundle_id: str,
        verified: bool,
        line: str = "",
    ) -> Optional[Incoming]:
        if not self._repo.exists():
            self._repo.init_repo()
        refs = self._repo.import_pack(bundle)
        tip = _tip_from_refs(refs)
        if not tip:
            return None
        head = self._repo.head_sha()
        change_ids = self._repo.new_commit_ids(tip, head)
        if not change_ids:
            return None
        self._repo.set_ref(f"refs/incoming/{from_id}/{bundle_id}", tip)
        if from_id and from_id != "usb":
            peer = f"refs/peers/{from_id}/{line}" if line.startswith("exp/") else f"refs/peers/{from_id}/main"
            self._repo.set_ref(peer, tip)
        arrived = iso(self.now())
        records = [item for item in self._incoming_records() if item.get("id") != bundle_id]
        records.append(
            {
                "id": bundle_id,
                "from_id": from_id,
                "tip": tip,
                "arrived": arrived,
                "verified": verified,
                "change_ids": change_ids,
            }
        )
        self._save_incoming(records)
        author = self._repo.change(change_ids[-1]).author_name or from_id
        self._toast(f"{author} sent a change")
        self._emit(EVENT_INCOMING)
        self._emit(EVENT_FEED)
        changes = tuple(self._repo.change(sha) for sha in change_ids)
        return Incoming(
            id=bundle_id,
            from_id=from_id,
            changes=changes,
            arrived=_parse_time(arrived),
            verified=verified,
        )

    def _assemble(self, envelope: Envelope, mail: InboundMail) -> Optional[bytes]:
        if envelope.verb in {"note", "have", "want", "join", "rekey"} and not mail.attachments:
            return b""
        payload = _bundle_attachment(envelope, mail)
        if envelope.part_sha256 and payload and not digest_equal(sha256_hex(payload), envelope.part_sha256):
            raise TeamSyncError("A bundle part failed its checksum.")
        directory = self._part_dir(envelope.bundle_id)
        directory.mkdir(parents=True, exist_ok=True)
        index = envelope.part_index()
        atomic_write_bytes(directory / str(index), payload)
        atomic_write_bytes(
            directory / f"{index}.sha",
            (envelope.part_sha256 or sha256_hex(payload)).encode("ascii"),
        )
        parts = []
        digests = []
        for number in range(1, envelope.part_total() + 1):
            part_path = directory / str(number)
            if not part_path.is_file():
                return None
            parts.append(part_path.read_bytes())
            digests.append((directory / f"{number}.sha").read_text(encoding="ascii").strip())
        return join_parts(parts, digests)

    def _merge_tip(
        self,
        *,
        tip: str,
        theirs_from: str,
        note: str,
        kind: str,
        incoming_id: str,
        base_override: Optional[str] = None,
        aside_index: Optional[int] = None,
        commit_when_clean: bool = True,
    ) -> Optional[CombineState]:
        self._require_idle()
        self._checkpoint(_checkpoint_phrase(kind, self._person(theirs_from)))
        me = self._require_me()
        ours = self._repo.head_sha()
        if not ours:
            raise TeamSyncError("Save a change before combining.")
        if kind == "merge" and self._repo.is_ancestor(ours, tip):
            self._repo.checkout(tip, self._repo.branch_name())
            self._finish_fast(incoming_id, theirs_from, tip)
            return None
        if kind == "merge" and self._repo.is_ancestor(tip, ours):
            self._finish_fast(incoming_id, theirs_from, tip)
            return None
        base = base_override if base_override is not None else (self._repo.merge_base(ours, tip) or "")
        merge = self._merged(base, ours, tip, keep_team=kind == "revert")
        commit_note = self._combined_note(theirs_from) if kind == "merge" else note
        feed = self._accept_note(theirs_from) if kind == "merge" else note
        modes = self._modes_for(merge, ours, tip)
        if merge.clashes:
            state = CombineSession(self.project_root).start(
                session_id="k_" + secrets.token_hex(4),
                kind=kind,
                theirs_from=theirs_from,
                note=note,
                ours=ours,
                theirs=tip,
                base=base,
                incoming_id=incoming_id,
                merge=merge,
                aside_index=aside_index,
                modes=modes,
                feed=feed,
                commit_note=commit_note,
            )
            self._emit(EVENT_COMBINE)
            return state
        if not commit_when_clean:
            self._write_merge(merge, ours, modes)
            return None
        try:
            self._commit_merge(
                merge,
                commit_note,
                me,
                tip if kind in {"merge", "experiment"} else "",
                modes,
            )
        except TeamSyncError as exc:
            if str(exc) != "Nothing to save.":
                raise
        if incoming_id:
            self._finish_fast(incoming_id, theirs_from, tip)
        elif kind in {"revert", "cherry", "experiment"}:
            self._append_feed(FEED_SYSTEM, feed, me.member_id)
            self._emit(EVENT_HISTORY)
        return None

    def _commit_merge(
        self,
        merge: TreeMerge,
        note: str,
        me: LocalIdentity,
        extra_parent: str,
        modes: Optional[Dict[str, int]] = None,
    ) -> str:
        head = self._repo.head_sha() or ""
        self._write_merge(merge, head, modes or {})
        if not self._repo.dirty():
            return head
        return self._repo.commit(
            note,
            me.name,
            me.email or "team@localhost",
            me.member_id,
            self.machine.hostname,
            self.now(),
            extra_parents=[extra_parent] if extra_parent else None,
        )

    def _write_merge(self, merge: TreeMerge, ours_sha: str, modes: Dict[str, int]) -> None:
        ours_files = self._repo.tree_files(ours_sha)
        changed = {
            path: data for path, data in merge.files.items() if ours_files.get(path) != data
        }
        self._repo.replace_worktree(changed, modes, only_listed=True)

    def _merged(
        self,
        base_sha: str,
        ours_sha: str,
        theirs_sha: str,
        *,
        keep_team: bool,
    ) -> TreeMerge:
        base = self._repo.tree_files(base_sha) if base_sha else {}
        ours = self._repo.tree_files(ours_sha)
        theirs = self._repo.tree_files(theirs_sha)
        result = merge_trees(base, ours, theirs)
        if _TEAM_PATH in base or _TEAM_PATH in ours or _TEAM_PATH in theirs:
            merged = merge_team_bytes(
                base.get(_TEAM_PATH),
                ours.get(_TEAM_PATH),
                theirs.get(_TEAM_PATH),
                ours_newer=self._repo.commit_time(ours_sha) >= self._repo.commit_time(theirs_sha),
            )
            files = dict(result.files)
            files[_TEAM_PATH] = merged
            clashes = tuple(clash for clash in result.clashes if clash.path != _TEAM_PATH)
            result = TreeMerge(files=files, clashes=clashes)
        if keep_team:
            files = dict(result.files)
            files[_TEAM_PATH] = ours.get(_TEAM_PATH)
            clashes = tuple(clash for clash in result.clashes if clash.path != _TEAM_PATH)
            result = TreeMerge(files=files, clashes=clashes)
        return result

    def _modes_for(self, merge: TreeMerge, ours_sha: str, theirs_sha: str) -> Dict[str, int]:
        ours_modes = self._repo.tree_modes(ours_sha)
        theirs_modes = self._repo.tree_modes(theirs_sha)
        ours_files = self._repo.tree_files(ours_sha)
        theirs_files = self._repo.tree_files(theirs_sha)
        modes: Dict[str, int] = {}
        for path, data in merge.files.items():
            if data is None:
                continue
            if data == theirs_files.get(path) and path in theirs_modes:
                modes[path] = theirs_modes[path]
            elif path in ours_modes:
                modes[path] = ours_modes[path]
            else:
                modes[path] = theirs_modes.get(path, 0o100644)
        return modes

    def _finish_still_matches(self, meta: Dict[str, object], files: Dict[str, Optional[bytes]]) -> bool:
        ours = str(meta.get("ours") or "")
        if self._repo.head_sha() != ours or self._repo.dirty():
            return False
        ours_files = self._repo.tree_files(ours)
        for path in files:
            if self._repo.work_bytes(path) != ours_files.get(path):
                return False
        return True

    def _close_incoming(self, incoming_id: str) -> None:
        if not incoming_id:
            return
        try:
            payload = self._incoming_record(incoming_id)
        except TeamSyncError:
            return
        self._repo.delete_ref(f"refs/incoming/{payload['from_id']}/{incoming_id}")
        self._save_incoming(
            [item for item in self._incoming_records() if item.get("id") != incoming_id]
        )
        self._enqueue_have(str(payload["from_id"]), str(payload["tip"]))

    def _checkpoint(self, action: str) -> None:
        if self._repo.exists() and self._repo.dirty():
            self._commit_change(f"Your work before {action}", None)

    def _require_idle(self) -> None:
        if self._combine_open():
            raise TeamSyncError(_BUSY)

    def _combine_open(self) -> bool:
        return bool(self._repo.exists() and CombineSession(self.project_root).load() is not None)

    def _person(self, from_id: str) -> str:
        team = self._team()
        member = member_by_id(team, from_id) if team is not None else None
        return member.name if member is not None else from_id

    def _combined_note(self, from_id: str) -> str:
        return f"Combined {self._person(from_id)}'s change"

    def _out_live(self, account: str, folder_id: str) -> bool:
        if not folder_id:
            return False
        if is_sent(Path(account), folder_id):
            return True
        folder = Path(account) / "out" / folder_id
        return (folder / "message.mail").is_file() and not (folder / ".lock").exists()

    def _resume_unpublished(self) -> None:
        account = self._account()
        if account is None:
            return
        for row in self._ledger().rows([DELIVERY_QUEUED, DELIVERY_WAITING_TERMINAL]):
            if self._out_live(account.path, row.out_folder):
                continue
            part = next(
                (item for item in self._ledger().parts_for(row.bundle_id) if item.idx == row.part_idx),
                None,
            )
            if part is None:
                continue
            mail_path = Path(part.path).with_name(f"out-{row.part_idx}.mail")
            name_path = Path(part.path).with_name(f"out-{row.part_idx}.name")
            if not mail_path.is_file() or not Path(part.path).is_file() or not name_path.is_file():
                continue
            filename = name_path.read_text(encoding="utf-8")
            message = mail_path.read_bytes()
            payload = Path(part.path).read_bytes()

            def _claimed(folder_id: str, _row: OutboxRow = row) -> None:
                self._ledger().set_folder(_row.bundle_id, _row.recipient, _row.part_idx, folder_id)

            try:
                publish_out(
                    Path(account.path),
                    self._mail_id(),
                    message,
                    {filename: payload},
                    on_claimed=_claimed,
                )
            except (OSError, TeamSyncError):
                continue

    def _finish_fast(self, incoming_id: str, from_id: str, tip: str) -> None:
        if incoming_id:
            self._repo.delete_ref(f"refs/incoming/{from_id}/{incoming_id}")
            self._save_incoming(
                [item for item in self._incoming_records() if item.get("id") != incoming_id]
            )
            self._enqueue_have(from_id, tip)
        me = self._me()
        self._append_feed(FEED_SYSTEM, self._accept_note(from_id), me.member_id if me else None)
        self._emit(EVENT_INCOMING)
        self._emit(EVENT_HISTORY)
        self._emit(EVENT_STATUS)

    def _enqueue_have(self, member_id: str, tip: str) -> None:
        team = self._team()
        me = self._me()
        if team is None or me is None:
            return
        member = member_by_id(team, member_id)
        if member is None:
            return
        envelope = self._envelope(
            "have",
            team,
            me.member_id,
            member.id,
            bundle_id="h_" + secrets.token_hex(8),
            tip=tip,
            accepted="1",
        )
        self._publish(envelope, None, member, change_id=tip, tip=tip)

    def _accept_note(self, from_id: str) -> str:
        team = self._team()
        member = member_by_id(team, from_id) if team else None
        name = member.name if member is not None else from_id
        return f"You accepted {name}'s change"

    def _last_delivery(self) -> Optional[Delivery]:
        if not self._repo.exists() and not self._ledger_path().exists():
            return None
        row = self._ledger().latest()
        if row is None:
            return None
        return self._delivery_for(row.change_id) or Delivery(row.change_id, row.recipient, row.state)

    def _delivery_for(self, change_id: str) -> Optional[Delivery]:
        rows = [row for row in self._ledger().for_change(change_id) if row.verb == "push"]
        if not rows:
            return None
        chosen = min(rows, key=lambda row: _RANK.get(row.state, 0))
        return Delivery(change_id, chosen.recipient, chosen.state)

    def _terminal(self) -> str:
        accounts = self._scan_accounts()
        if not accounts:
            return TERMINAL_NONE
        return terminal_state(accounts, self.now(), self.machine.hostname)

    def _scan_accounts(self) -> List[str]:
        me = self._me()
        if me is not None and me.mailbox:
            return [me.mailbox]
        boxes = self.mailboxes()
        if self._mail_roots is not None:
            return [box.path for box in boxes]
        if len(boxes) == 1:
            return [boxes[0].path]
        return []

    def _account(self) -> Optional[Mailbox]:
        wanted = self._scan_accounts()
        boxes = self.mailboxes()
        for box in boxes:
            if box.path in wanted:
                return box
        if len(boxes) == 1:
            return boxes[0]
        return None

    def _require_account(self) -> Mailbox:
        account = self._account()
        if account is None:
            raise TeamSyncError("No FaxMail mailbox found.")
        return account

    def _pick_mailbox(self, requested: Optional[str], required: bool) -> Optional[Mailbox]:
        boxes = self.mailboxes()
        if requested:
            for box in boxes:
                if box.path == requested or box.email.lower() == requested.lower() or box.label == requested:
                    return box
            raise TeamSyncError("That FaxMail mailbox is not on this machine.")
        if len(boxes) == 1:
            return boxes[0]
        if len(boxes) > 1:
            if required:
                raise TeamSyncError("Choose a FaxMail mailbox.")
            return None
        if required:
            raise TeamSyncError("No FaxMail mailbox found.")
        return None

    def _team(self) -> Optional[TeamFile]:
        if not (Path(self.project_root) / "cbcs" / "team.json").is_file():
            return None
        return load_team(Path(self.project_root))

    def _require_team(self) -> TeamFile:
        team = self._team()
        if team is None:
            raise TeamSyncError("Share the project first.")
        return team

    def _me(self) -> Optional[LocalIdentity]:
        if not self._repo.exists():
            return None
        return load_me(Path(self.project_root))

    def _require_me(self) -> LocalIdentity:
        me = self._me()
        if me is None:
            raise TeamSyncError("Share the project first.")
        return me

    def _project_id(self) -> str:
        team = self._team()
        return team.project_id if team is not None else ""

    def _on_share(self) -> bool:
        try:
            project = logical_path(self.project_root)
        except ValueError:
            return False
        try:
            roots = share_roots(self.machine)
        except OSError:
            return False
        for root in roots:
            try:
                project.relative_to(logical_path(root))
            except ValueError:
                continue
            else:
                return True
        return False

    def _ledger_path(self) -> Path:
        if self._on_share():
            project_id = self._project_id() or "pending"
            return self.machine.local_state / "team_sync" / project_id / "ledger.sqlite"
        if self._repo.exists():
            return Path(self.project_root) / ".git" / "cbcs" / "ledger.sqlite"
        return self.machine.local_state / "team_sync" / "pending" / "ledger.sqlite"

    def _cached_files(self, sha: str) -> Tuple[FileChange, ...]:
        cached = self._ledger().commit_files(sha)
        if cached is not None:
            return tuple(FileChange(path, kind) for path, kind in cached)
        files = tuple(self._repo.changed_files(sha))
        self._ledger().remember_commit_files(sha, [(item.path, item.kind) for item in files])
        return files

    def _ledger(self) -> Ledger:
        path = self._ledger_path()
        if self._ledger_obj is None or self._ledger_at != str(path):
            if self._ledger_obj is not None:
                self._ledger_obj.close()
            self._ledger_obj = Ledger(path)
            self._ledger_at = str(path)
        return self._ledger_obj

    def _invite_dir(self) -> Path:
        return self.machine.local_state / "team_sync" / "invites"

    def _invite_records(self) -> List[dict]:
        directory = self._invite_dir()
        if not directory.is_dir():
            return []
        records = []
        for path in sorted(directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(payload, dict):
                records.append(payload)
        return records

    def _invite(self, incoming_id: str) -> dict:
        for payload in self._invite_records():
            if payload.get("id") == incoming_id:
                return payload
        raise TeamSyncError("That invite is no longer waiting.")

    def _delete_invite(self, incoming_id: str) -> None:
        bundle_id = require_bundle_id(incoming_id)
        directory = self._invite_dir()
        for suffix in (".json", ".bundle"):
            try:
                (directory / f"{bundle_id}{suffix}").unlink()
            except FileNotFoundError:
                continue

    def _incoming_path(self) -> Path:
        return Path(self.project_root) / ".git" / "cbcs" / "incoming.json"

    def _incoming_records(self) -> List[dict]:
        path = self._incoming_path()
        if not path.is_file():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        items = payload.get("items") if isinstance(payload, dict) else None
        return [item for item in items or [] if isinstance(item, dict)]

    def _save_incoming(self, items: List[dict]) -> None:
        path = self._incoming_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(
            path,
            (json.dumps({"items": items}, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )

    def _incoming_record(self, incoming_id: str) -> dict:
        for item in self._incoming_records():
            if item.get("id") == incoming_id:
                return item
        raise TeamSyncError("That incoming change is no longer waiting.")

    def _part_dir(self, bundle_id: str) -> Path:
        return self.machine.local_state / "team_sync" / "parts" / require_bundle_id(bundle_id)

    def _hold_dir(self) -> Path:
        if self._repo.exists():
            return Path(self.project_root) / ".git" / "cbcs" / "holding"
        return self.machine.local_state / "team_sync" / "holding"

    def _feed_path(self) -> Path:
        if self._repo.exists():
            return Path(self.project_root) / ".git" / "cbcs" / "feed.jsonl"
        return self.machine.local_state / "team_sync" / "pending-feed.jsonl"

    def _append_feed(self, kind: str, text: str, author_id: Optional[str]) -> None:
        path = self._feed_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "id": "f_" + secrets.token_hex(6),
            "kind": kind,
            "when": iso(self.now()),
            "text": text,
            "author_id": author_id or "",
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def _read_feed(self) -> List[FeedItem]:
        path = self._feed_path()
        if not path.is_file():
            return []
        items = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            kind = str(payload.get("kind", FEED_SYSTEM))
            items.append(
                FeedItem(
                    kind=kind if kind in {FEED_SYSTEM, FEED_NOTE} else FEED_SYSTEM,
                    id=str(payload.get("id", "")),
                    when=_parse_time(str(payload.get("when", ""))),
                    text=str(payload.get("text", "")),
                    author_id=str(payload.get("author_id") or "") or None,
                )
            )
        return items

    def _mail_id(self) -> str:
        when = self.now()
        base = when.strftime("%Y%m%d%H%M%S") + f"{when.microsecond // 1000:03d}"
        self._mail_seq += 1
        value = int(base) + self._mail_seq - 1
        return f"{value:017d}"

    def _toast(self, text: str) -> None:
        self._emit(EVENT_TOAST_PREFIX + text)

    def _emit(self, event: str) -> None:
        for callback in list(self._subscribers):
            callback(event)


def _require_empty_folder(root: Path) -> None:
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise TeamSyncError("Choose a new or empty folder. That one already has files.")


def _empty_project_folder(root: Path) -> Path:
    _require_empty_folder(root)
    if not root.exists():
        root.mkdir(parents=True)
    return root


def _checkpoint_phrase(kind: str, name: str) -> str:
    phrases = {
        "merge": f"accepting {name}'s change",
        "revert": "undoing a change",
        "cherry": "copying a change",
        "experiment": "bringing an experiment in",
        "aside": "bringing a change back",
    }
    return phrases.get(kind, "combining")


def _permanent_failure(message: str) -> bool:
    text = message.lower()
    return "checksum" in text or "damaged" in text or "not one team sync" in text


def _bundle_attachment(envelope: Envelope, mail: InboundMail) -> bytes:
    index = envelope.part_index()
    total = envelope.part_total()
    marker = f".part-{index:02d}-of-{total:02d}"
    chosen: Optional[bytes] = None
    for name, payload in mail.attachments.items():
        lower = name.lower()
        if ".cbcsbundle" not in lower:
            continue
        if total > 1 and marker not in lower:
            continue
        chosen = payload
        break
    if chosen is None:
        raise TeamSyncError("The bundle attachment is missing.")
    return chosen


def _usb_zip(body: str, bundle: bytes) -> bytes:
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("envelope.txt", body)
        archive.writestr("bundle", bundle)
    return buffer.getvalue()


def _read_usb(raw: bytes) -> Tuple[str, bytes]:
    import io

    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except (zipfile.BadZipFile, ValueError) as exc:
        raise TeamSyncError("That USB bundle is not a signed ChoreBoy bundle.") from exc
    with archive:
        names = set(archive.namelist())
        if "envelope.txt" not in names or "bundle" not in names:
            raise TeamSyncError("That USB bundle is not a signed ChoreBoy bundle.")
        body = archive.read("envelope.txt").decode("utf-8")
        bundle = archive.read("bundle")
    return body, bundle


def _member(identity: LocalIdentity) -> Member:
    return Member(identity.member_id, identity.name, identity.shop, identity.email)


def _seen_key(project_id: str, from_id: str, bundle_id: str, part: str) -> str:
    return f"{project_id}|{from_id}|{bundle_id}|{part}"


def _canonical_fields(envelope: Envelope) -> Dict[str, str]:
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
        "key": envelope.key_hex if envelope.verb == "rekey" else "",
    }
    for key, value in optional.items():
        if value:
            fields[key] = value
    return fields


def _tip_from_refs(refs: Dict[str, str]) -> str:
    for name in ("refs/heads/main",):
        if name in refs:
            return refs[name]
    for name, sha in refs.items():
        if name.startswith("refs/heads/"):
            return sha
    if refs:
        return next(iter(refs.values()))
    return ""


def _incoming_from_invite(payload: dict) -> Incoming:
    return Incoming(
        id=str(payload.get("id", "")),
        from_id=str(payload.get("from_id", "")),
        changes=(),
        arrived=_parse_time(str(payload.get("arrived", ""))),
        verified=True,
    )


def _parse_time(text: str) -> datetime:
    if not text:
        return datetime.now(timezone.utc)
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def _name_from_email(email: str) -> str:
    local = email.split("@", 1)[0]
    return local or "Shop"


def _slug(name: str) -> str:
    cleaned = []
    for char in name.strip().lower():
        if char.isalnum():
            cleaned.append(char)
        elif char in " -_":
            cleaned.append("-")
    slug = "".join(cleaned).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    if not slug:
        raise TeamSyncError("Name a line of work before starting it.")
    return slug


def _note_text(body: str) -> str:
    lines = []
    for line in body.splitlines():
        if not line.strip() or line.startswith("Sent by ChoreBoy"):
            continue
        if ": " in line and line.split(": ", 1)[0] in {
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
            "signature",
        }:
            continue
        lines.append(line)
    return "\n".join(lines).strip()
