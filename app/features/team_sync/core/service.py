"""TeamSyncService implements TeamSyncApi. One poll() is one mail cycle."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

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
    sha256_hex,
    subject_for,
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
    new_key,
    new_member_id,
    new_project_id,
    read_key,
    replace_member,
    save_me,
    save_team,
    utc_stamp,
    without_member,
    write_key,
    write_key_checksum,
)

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
                items.append(
                    FeedItem(
                        kind=FEED_CHANGE,
                        id=change.id,
                        when=change.when,
                        text=change.note,
                        author_id=change.author_id or None,
                        change=change,
                        delivery=self._delivery_for(change.id),
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
        payload = self._invite(incoming_id)
        root = Path(folder)
        root.mkdir(parents=True, exist_ok=True)
        if (root / ".git").is_dir() and load_team(root) is not None:
            raise TeamSyncError("That folder is already a team project.")
        bundle = (self._invite_dir() / f"{incoming_id}.bundle").read_bytes()
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
        sender = Member(
            id=str(payload.get("from_id", "")),
            name=str(payload.get("sender_name", "")),
            shop=str(payload.get("sender_shop", "")),
            email=str(payload.get("sender_email", "")),
        )
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
        team = TeamFile(
            project_id=str(payload["project_id"]),
            name=str(payload.get("project_name", root.name)),
            members=(sender, me),
            created_at=str(payload.get("created_at") or utc_stamp(when)),
        )
        save_team(root, team)
        key = bytes.fromhex(str(payload["key_hex"]))
        write_key(root, key)
        write_key_checksum(root, key)
        save_me(root, LocalIdentity(me.id, me.name, me.shop, me.email, account.path))
        repo.set_ref(f"refs/peers/{sender.id}/main", tip)
        self._mark_seen_on(root, _seen_key(payload["project_id"], sender.id, incoming_id, "1"))
        self._delete_invite(incoming_id)
        joiner = TeamSyncService(
            str(root),
            machine=self.machine,
            clock=self._clock,
            mail_roots=self._mail_roots,
        )
        joiner._send_join(team, me, sender, tip)
        self._emit(EVENT_INCOMING)
        return str(root)

    def send(self, note: str, paths: Optional[List[str]] = None) -> Change:
        change = self._commit_change(note, paths)
        self._push_change(change)
        self._emit(EVENT_STATUS)
        self._emit(EVENT_FEED)
        self._emit(EVENT_HISTORY)
        return change

    def save_only(self, note: str, paths: Optional[List[str]] = None) -> Change:
        change = self._commit_change(note, paths)
        self._emit(EVENT_STATUS)
        self._emit(EVENT_HISTORY)
        return change

    def post_note(self, text: str) -> None:
        me = self._require_me()
        team = self._require_team()
        self._append_feed(FEED_NOTE, text, me.member_id)
        envelope = self._envelope("note", team, me.member_id, "", bundle_id="n_" + secrets.token_hex(8))
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
        self._repo.replace_worktree(files)
        me = self._require_me()
        extra: List[str] = []
        if meta["kind"] in {"merge", "experiment"} and meta.get("theirs"):
            extra = [str(meta["theirs"])]
        change_id = self._repo.commit(
            str(meta["note"]),
            me.name,
            me.email or "team@localhost",
            me.member_id,
            self.machine.hostname,
            self.now(),
            extra_parents=extra or None,
        )
        incoming_id = str(meta.get("incoming_id") or "")
        if incoming_id:
            try:
                payload = self._incoming_record(incoming_id)
            except TeamSyncError:
                payload = None
            if payload is not None:
                self._repo.delete_ref(f"refs/incoming/{payload['from_id']}/{incoming_id}")
                self._save_incoming(
                    [item for item in self._incoming_records() if item.get("id") != incoming_id]
                )
                self._enqueue_have(str(payload["from_id"]), str(payload["tip"]))
        aside_index = meta.get("aside_index")
        if meta["kind"] == "aside" and isinstance(aside_index, int):
            self._repo.drop_aside(aside_index)
        session.clear()
        self._append_feed(FEED_SYSTEM, str(meta["note"]), me.member_id)
        self._emit(EVENT_COMBINE)
        self._emit(EVENT_HISTORY)
        self._emit(EVENT_STATUS)
        return self._repo.change(change_id)

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
        me = self._require_me()
        head = self._repo.head_sha()
        wanted = self._repo.tree_files(change_id)
        current = self._repo.tree_files(head) if head else {}
        files: Dict[str, Optional[bytes]] = {}
        for path in set(wanted) | set(current):
            files[path] = wanted.get(path)
        self._repo.replace_worktree(files)
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
        me = self._require_me()
        self._repo.set_aside(name, me.name, me.email or "team@localhost")
        self._emit(EVENT_STATUS)

    def bring_back(self, index: int) -> Optional[CombineState]:
        if self._repo.dirty():
            raise TeamSyncError("Set this work aside before bringing another change back.")
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
        me = self._require_me()
        team = self._require_team()
        if member_id == me.member_id:
            raise TeamSyncError("You can't remove yourself.")
        if member_by_id(team, member_id) is None:
            raise TeamSyncError("That person is not on this project.")
        old_key = read_key(Path(self.project_root))
        updated = without_member(team, member_id)
        save_team(Path(self.project_root), updated)
        new = new_key()
        write_key(Path(self.project_root), new)
        write_key_checksum(Path(self.project_root), new)
        self._repo.commit(
            "Removed a team member",
            me.name,
            me.email or "team@localhost",
            me.member_id,
            self.machine.hostname,
            self.now(),
            paths=["cbcs/team.json"],
        )
        for member in updated.members:
            if member.id == me.member_id:
                continue
            envelope = self._envelope(
                "rekey",
                updated,
                me.member_id,
                member.id,
                bundle_id="k_" + secrets.token_hex(8),
                key_hex=new.hex(),
            )
            self._publish(envelope, None, member, change_id="", tip="", sign_key=old_key)
        self._append_feed(FEED_SYSTEM, "A team member was removed and the key changed.", me.member_id)
        self._emit(EVENT_STATUS)

    def export_bundle(self, dest_path: str) -> None:
        if not self._repo.head_sha():
            raise TeamSyncError("Save a change before exporting a bundle.")
        data = self._repo.create_bundle(self._repo.branch_name(), [])
        atomic_write_bytes(Path(dest_path), data)

    def import_bundle(self, src_path: str) -> Optional[Incoming]:
        data = Path(src_path).read_bytes()
        return self._import_bundle_bytes(data, from_id="usb", bundle_id=new_bundle_id(), verified=True)

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

    def _push_change(self, change: Change) -> None:
        team = self._require_team()
        me = self._require_me()
        for member in team.members:
            if member.id == me.member_id:
                continue
            peer = self._repo.get_ref(f"refs/peers/{member.id}/main")
            prereq = ""
            if peer and self._repo.has_object(peer):
                base = self._repo.merge_base(change.id, peer)
                if base:
                    prereq = base
            bundle_id = new_bundle_id()
            bundle = self._repo.create_bundle(
                self._repo.branch_name(),
                [prereq] if prereq else [],
            )
            envelope = self._envelope(
                "push",
                team,
                me.member_id,
                member.id,
                bundle_id=bundle_id,
                tip=change.id,
                needs=prereq,
                changes=str(self._repo.count_since(change.id, [prereq] if prereq else [])),
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
            attachments = {}
            if bundle:
                attachments[attachment_name(envelope.project_name, envelope.bundle_id, index, total)] = part
                part_path = self._part_dir(envelope.bundle_id) / f"out-{index}"
                atomic_write_bytes(part_path, part)
                self._ledger().add_part(envelope.bundle_id, index, total, part_sha, str(part_path))
            folder = publish_out(Path(account.path), self._mail_id(), raw, attachments)
            self._ledger().add_outbox(
                bundle_id=envelope.bundle_id,
                recipient=recipient.id or recipient.email,
                part_idx=index,
                part_total=total,
                verb=envelope.verb,
                change_id=change_id,
                tip=tip,
                created_at=created,
                out_folder=folder,
                state=state,
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
        for mail in self._scan.scan():
            self._handle_mail(mail)

    def _handle_mail(self, mail: InboundMail) -> None:
        envelope = envelope_from_message(mail.subject, mail.body)
        if envelope is None:
            return
        team = self._team()
        if team is not None and envelope.project_id != team.project_id and envelope.verb != "invite":
            return
        if team is None and envelope.verb != "invite":
            return
        key = _seen_key(envelope.project_id, envelope.from_id, envelope.bundle_id or sha256_hex(mail.body.encode())[:16], envelope.part)
        if self._ledger().has_seen(key):
            return
        if not self._trusted(envelope, mail):
            self._ledger().mark_seen(key, iso(self.now()), "unverified")
            self._emit(EVENT_STATUS)
            return
        try:
            self._dispatch(envelope, mail)
        except TeamSyncError:
            self._ledger().mark_seen(key, iso(self.now()), "unverified")
            self._emit(EVENT_STATUS)
            return
        self._ledger().mark_seen(key, iso(self.now()), "ok")

    def _trusted(self, envelope: Envelope, mail: InboundMail) -> bool:
        sender = address_of(mail.from_header)
        if envelope.verb == "invite":
            return bool(envelope.key_hex) and sender == envelope.sender_email.strip().lower()
        team = self._team()
        if team is None:
            return False
        fields = _canonical_fields(envelope)
        if envelope.verb == "join":
            if sender != envelope.member_email.strip().lower():
                return False
            return verify_signature(read_key(Path(self.project_root)), fields, envelope.signature)
        member = member_by_id(team, envelope.from_id)
        if member is None or sender != member.email.strip().lower():
            return False
        return verify_signature(read_key(Path(self.project_root)), fields, envelope.signature)

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
            self._append_feed(FEED_NOTE, _note_text(mail.body), envelope.from_id)
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
        directory = self._invite_dir()
        directory.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(directory / f"{envelope.bundle_id}.bundle", bundle)
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
            "arrived": iso(self.now()),
        }
        atomic_write_bytes(
            directory / f"{envelope.bundle_id}.json",
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
        bundle = self._repo.create_bundle(self._repo.branch_name(), [])
        head = self._repo.head_sha() or ""
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
        if not envelope.key_hex:
            raise TeamSyncError("The rekey message has no key.")
        key = bytes.fromhex(envelope.key_hex)
        write_key(Path(self.project_root), key)
        write_key_checksum(Path(self.project_root), key)
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
        directory = self._hold_dir()
        directory.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(directory / f"{envelope.bundle_id}.bundle", bundle)
        payload = {
            "id": envelope.bundle_id,
            "from_id": envelope.from_id,
            "tip": envelope.tip,
            "needs": needs,
            "sha256": envelope.bundle_sha256,
        }
        atomic_write_bytes(
            directory / f"{envelope.bundle_id}.json",
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
            bundle_path = directory / f"{payload['id']}.bundle"
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
                bundle_id=str(payload.get("id", "")),
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
            self._repo.set_ref(f"refs/peers/{from_id}/main", tip)
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
        if not envelope.bundle_id or envelope.part_total() <= 1 and not mail.attachments:
            if envelope.verb in {"note", "have", "want", "join", "rekey"}:
                return b""
        payload = b""
        if mail.attachments:
            payload = next(iter(mail.attachments.values()))
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
        if CombineSession(self.project_root).load() is not None:
            raise TeamSyncError("Finish or cancel the combine already open.")
        me = self._require_me()
        if self._repo.dirty() and kind != "aside":
            self._repo.set_aside("Before accepting", me.name, me.email or "team@localhost")
        ours = self._repo.head_sha()
        if not ours:
            raise TeamSyncError("Save a change before combining.")
        if kind == "merge" and self._repo.is_ancestor(tip, ours):
            self._finish_fast(incoming_id, theirs_from, tip)
            return None
        base = base_override if base_override is not None else (self._repo.merge_base(ours, tip) or "")
        merge = merge_trees(
            self._repo.tree_files(base) if base else {},
            self._repo.tree_files(ours),
            self._repo.tree_files(tip),
        )
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
            )
            self._emit(EVENT_COMBINE)
            return state
        if not commit_when_clean:
            self._repo.replace_worktree(merge.files)
            return None
        try:
            self._commit_merge(merge, note, me, tip if kind in {"merge", "experiment"} else "")
        except TeamSyncError as exc:
            if str(exc) != "Nothing to save.":
                raise
        if incoming_id:
            self._finish_fast(incoming_id, theirs_from, tip)
        elif kind in {"revert", "cherry"}:
            self._emit(EVENT_HISTORY)
        return None

    def _commit_merge(self, merge: TreeMerge, note: str, me: LocalIdentity, extra_parent: str) -> str:
        self._repo.replace_worktree(merge.files)
        return self._repo.commit(
            note,
            me.name,
            me.email or "team@localhost",
            me.member_id,
            self.machine.hostname,
            self.now(),
            extra_parents=[extra_parent] if extra_parent else None,
        )

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

    def _ledger(self) -> Ledger:
        path = self._ledger_path()
        if self._ledger_obj is None or self._ledger_at != str(path):
            if self._ledger_obj is not None:
                self._ledger_obj.close()
            self._ledger_obj = Ledger(path)
            self._ledger_at = str(path)
        return self._ledger_obj

    def _mark_seen_on(self, root: Path, key: str) -> None:
        path = root / ".git" / "cbcs" / "ledger.sqlite"
        ledger = Ledger(path)
        try:
            ledger.mark_seen(key, iso(self.now()), "ok")
        finally:
            ledger.close()

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
        directory = self._invite_dir()
        for suffix in (".json", ".bundle"):
            try:
                (directory / f"{incoming_id}{suffix}").unlink()
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
        return self.machine.local_state / "team_sync" / "parts" / (bundle_id or "none")

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
