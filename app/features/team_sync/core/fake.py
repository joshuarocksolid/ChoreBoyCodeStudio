"""Deterministic in-memory Team Sync engine for the UI and its tests.

No Qt. ``scenario(name)`` jumps the whole story so screenshots and tests can
land on one state without walking the mail path.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

from app.features.team_sync.core import TeamSyncError

from app.features.team_sync.api import (
    CLASH_DELETED,
    CLASH_FORM,
    CLASH_LINES,
    DELIVERY_ACCEPTED,
    DELIVERY_DELIVERED,
    DELIVERY_QUEUED,
    DELIVERY_SENT,
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
    FILE_ADDED,
    FILE_DELETED,
    FILE_MODIFIED,
    MAIN_LINE,
    TERMINAL_NONE,
    TERMINAL_OFFLINE,
    TERMINAL_OK,
    BlameLine,
    Change,
    Clash,
    CombineState,
    Delivery,
    DiffHunk,
    FeedItem,
    FileChange,
    FileDiff,
    Incoming,
    Mailbox,
    Member,
    SetAside,
    ShareRequest,
    TeamStatus,
    Unsubscribe,
)


SAM = Member("e5f6a7b8", "Sam Brenneman", "Maple Ridge", "mapleridge@example.test")
ANA = Member("a1b2c3d4", "Ana Kurtz", "Cedar Hollow", "cedarhollow@example.test")

_T0 = datetime(2026, 11, 2, 9, 1, tzinfo=timezone.utc)
_NOTE = "Round totals to cents, add statement report"

_INVOICE_OLD = "\n".join(
    [
        "def invoice_total(lines):",
        "    total = 0",
        "    for line in lines:",
        "        total += line.amount",
        "    return total",
        "",
    ]
)
_INVOICE_NEW = "\n".join(
    [
        "def invoice_total(lines):",
        "    total = 0",
        "    for line in lines:",
        "        total += line.amount",
        "    return round(total, 2)",
        "",
    ]
)
_STATEMENT = "\n".join(
    [
        "def statement_report(customer):",
        "    return customer.invoices",
        "",
    ]
)
_FORM_OLD = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>InvoiceForm</class>
 <widget class="QWidget" name="InvoiceForm">
  <property name="windowTitle"><string>Invoice</string></property>
  <layout class="QVBoxLayout">
   <item>
    <widget class="QLabel" name="titleLabel">
     <property name="text"><string>Invoice</string></property>
    </widget>
   </item>
   <item>
    <widget class="QLineEdit" name="totalEdit">
     <property name="text"><string>0</string></property>
    </widget>
   </item>
  </layout>
 </widget>
</ui>
"""
_FORM_NEW = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>InvoiceForm</class>
 <widget class="QWidget" name="InvoiceForm">
  <property name="windowTitle"><string>Invoice</string></property>
  <layout class="QVBoxLayout">
   <item>
    <widget class="QLabel" name="titleLabel">
     <property name="text"><string>Statement</string></property>
    </widget>
   </item>
   <item>
    <widget class="QLineEdit" name="totalEdit">
     <property name="text"><string>0.00</string></property>
    </widget>
   </item>
  </layout>
 </widget>
</ui>
"""


def _change(
    change_id: str,
    author: Member,
    when: datetime,
    note: str,
    files: tuple[FileChange, ...],
    *,
    milestone: Optional[str] = None,
    line: str = MAIN_LINE,
    parents: tuple[str, ...] = (),
) -> Change:
    return Change(
        id=change_id,
        parents=parents,
        author_id=author.id,
        author_name=author.name,
        when=when,
        note=note,
        files=files,
        milestone=milestone,
        line=line,
    )


def _hunk(old: str, new: str) -> tuple[DiffHunk, ...]:
    old_lines = tuple(old.splitlines())
    new_lines = tuple(new.splitlines())
    return (
        DiffHunk(
            old_start=1,
            old_lines=old_lines,
            new_start=1,
            new_lines=new_lines,
        ),
    )


def _file_diff(path: str, kind: str, old: str, new: str, *, is_form: bool = False) -> FileDiff:
    return FileDiff(
        path=path,
        kind=kind,
        hunks=_hunk(old, new) if old or new else (),
        is_form=is_form,
        old_text=old,
        new_text=new,
    )


def _line_clash(clash_id: str, path: str, line: int) -> Clash:
    return Clash(
        id=clash_id,
        path=path,
        kind=CLASH_LINES,
        line=line,
        ours=("    return total",),
        theirs=("    return round(total, 2)",),
        base=("    return total",),
        context_before=("    for line in lines:", "        total += line.amount"),
        context_after=("    tax = total * rate",),
    )


def _form_clash() -> Clash:
    return Clash(
        id="k_form",
        path="invoice_form.ui",
        kind=CLASH_FORM,
        line=0,
        ours=(_FORM_OLD,),
        theirs=(_FORM_NEW,),
        base=(_FORM_OLD,),
    )


def _deleted_clash() -> Clash:
    return Clash(
        id="k_deleted",
        path="legacy_tax.py",
        kind=CLASH_DELETED,
        line=0,
        ours=("def tax(total):\n    return total * 0.05\n",),
        theirs=(),
        base=("def tax(total):\n    return total * 0.05\n",),
    )


def _large_text(prefix: str) -> str:
    rows = []
    for index in range(2000):
        if index % 40 == 0:
            rows.append(f"{prefix} line {index} total = round(amount, 2)")
        else:
            rows.append(f"{prefix} line {index} total = amount")
    return "\n".join(rows) + "\n"


class InMemoryTeamSync:
    """Seeded with the Invoice App story. Methods mutate that story in place."""

    def __init__(self) -> None:
        self._listeners: List[Callable[[str], None]] = []
        self._counter = 10
        self._texts: Dict[str, tuple[str, str]] = {}
        self._blame: Dict[str, List[BlameLine]] = {}
        self._feed: List[FeedItem] = []
        self._changes: List[Change] = []
        self._deliveries: Dict[str, Delivery] = {}
        self._incoming: List[Incoming] = []
        self._invites: List[Incoming] = []
        self._combine: Optional[CombineState] = None
        self._pending: List[FileChange] = []
        self._set_aside: List[SetAside] = []
        self._experiments: List[str] = []
        self._line = MAIN_LINE
        self._terminal = TERMINAL_NONE
        self._unverified = 0
        self._shared = False
        self._project_name = ""
        self._me: Optional[Member] = None
        self._members: List[Member] = []
        self._mailboxes = [
            Mailbox("/home/share/PDF/.Mails/cedar", "cedarhollow@example.test", "cedar"),
        ]
        self._accept_clashes: Optional[tuple[Clash, ...]] = None
        self._share_files = 12
        self._share_size = "48 KB"
        self._toast = ""
        self.scenario("idle")

    def scenario(self, name: str) -> None:
        """Replace the story with a named state."""
        builder = _SCENARIOS.get(name)
        if builder is None:
            known = ", ".join(sorted(_SCENARIOS))
            raise ValueError(f"Unknown Team Sync scenario {name!r}. Known: {known}")
        builder(self)
        self._emit(EVENT_STATUS)
        self._emit(EVENT_FEED)
        self._emit(EVENT_INCOMING)
        self._emit(EVENT_COMBINE)
        self._emit(EVENT_HISTORY)
        if self._toast:
            self._emit(EVENT_TOAST_PREFIX + self._toast)

    def share_summary(self) -> tuple[int, str]:
        return (self._share_files, self._share_size)

    def project_files(self) -> Dict[str, str]:
        """Relative path to text, so a screenshot project can show the letters."""
        files = {
            "invoice.py": _INVOICE_NEW,
            "statement.py": _STATEMENT,
            "invoice_form.ui": _FORM_NEW,
            "legacy_tax.py": "def tax(total):\n    return total * 0.05\n",
        }
        return files

    def status(self) -> TeamStatus:
        last = None
        if self._me is not None:
            for change in self._changes:
                if change.author_id == self._me.id and change.id in self._deliveries:
                    last = self._deliveries[change.id]
                    break
        return TeamStatus(
            shared=self._shared,
            project_name=self._project_name,
            me=self._me,
            members=tuple(self._members),
            pending=tuple(self._pending),
            waiting=len(self._incoming),
            combine=self._combine,
            last_delivery=last,
            terminal=self._terminal,
            line=self._line,
            experiments=tuple(self._experiments),
            set_aside=tuple(self._set_aside),
            unverified=self._unverified,
        )

    def feed(self, limit: int = 200) -> List[FeedItem]:
        return list(self._feed[:limit])

    def mailboxes(self) -> List[Mailbox]:
        return list(self._mailboxes)

    def share(self, request: ShareRequest) -> None:
        self._shared = True
        self._project_name = request.project_name or "Invoice App"
        self._me = Member("a1b2c3d4", request.my_name or ANA.name, request.my_shop or ANA.shop, ANA.email)
        self._members = [self._me]
        for invite in request.invites:
            self._members.append(Member(f"m{len(self._members)}", invite.name or invite.email, invite.shop, invite.email))
        self._terminal = TERMINAL_OK
        self._push_feed(
            FeedItem(
                kind=FEED_SYSTEM,
                id=self._next_id("f"),
                when=_now(),
                text=f"{self._me.name.split()[0]} shared {self._project_name}",
                author_id=self._me.id,
            )
        )
        self._emit(EVENT_STATUS)
        self._emit(EVENT_FEED)

    def pending_invites(self) -> List[Incoming]:
        return list(self._invites)

    def invite_detail(self, incoming_id: str) -> Dict[str, str]:
        item = next((row for row in self._invites if row.id == incoming_id), None)
        author = item.changes[0].author_name if item is not None and item.changes else ""
        return {
            "project_id": "",
            "project_name": self._project_name or "Invoice App",
            "sender_name": author,
            "sender_shop": "",
            "sender_email": "",
            "invitee_name": "",
            "invitee_shop": "",
        }

    def accept_invite(self, incoming_id: str, folder: str, my_name: str = "", my_shop: str = "") -> str:
        self._invites = [item for item in self._invites if item.id != incoming_id]
        self._shared = True
        self._project_name = "Invoice App"
        self._me = Member(ANA.id, my_name or ANA.name, my_shop or ANA.shop, ANA.email)
        self._members = [ANA, SAM]
        self._terminal = TERMINAL_OK
        self._emit(EVENT_STATUS)
        return folder

    def send(self, note: str, paths: Optional[List[str]] = None) -> Change:
        return self._commit(note, paths, deliver=True)

    def share_experiment(self, line: str) -> Change:
        if not str(line).startswith("exp/"):
            raise TeamSyncError("That line is not an experiment.")
        if self._line != line:
            raise TeamSyncError("Switch to that line before sharing it.")
        if not self._changes and not self._pending:
            raise TeamSyncError("Save a change before sharing this line.")
        change = self._commit(f"Shared {line}", None, deliver=True)
        shared = replace(change, line=line)
        self._changes = [shared if item.id == change.id else item for item in self._changes]
        return shared

    def save_only(self, note: str, paths: Optional[List[str]] = None) -> Change:
        return self._commit(note, paths, deliver=False)

    def post_note(self, text: str) -> None:
        author = self._me or ANA
        self._push_feed(
            FeedItem(
                kind=FEED_NOTE,
                id=self._next_id("n"),
                when=_now(),
                text=text,
                author_id=author.id,
            )
        )
        self._emit(EVENT_FEED)

    def incoming(self) -> List[Incoming]:
        return list(self._incoming)

    def incoming_diff(self, incoming_id: str) -> List[FileDiff]:
        item = self._find_incoming(incoming_id)
        if item is None or not item.changes:
            return []
        return self.change_diff(item.changes[0].id)

    def accept(self, incoming_id: str) -> Optional[CombineState]:
        item = self._find_incoming(incoming_id)
        self._incoming = [row for row in self._incoming if row.id != incoming_id]
        self._feed = [row for row in self._feed if row.incoming is None or row.incoming.id != incoming_id]
        if self._accept_clashes:
            state = CombineState(
                id="combine-1",
                theirs_from=item.from_id if item is not None else SAM.id,
                note=item.changes[0].note if item and item.changes else _NOTE,
                clashes=self._accept_clashes,
            )
            self._combine = state
            self._accept_clashes = None
            self._emit(EVENT_COMBINE)
            self._emit(EVENT_STATUS)
            self._emit(EVENT_INCOMING)
            return state
        author = self._member(item.from_id if item is not None else SAM.id)
        self._remember(
            _change(
                self._next_id("c"),
                self._me or ANA,
                _now(),
                f"You accepted {author.name.split()[0]}'s change",
                item.changes[0].files if item and item.changes else (),
                parents=(self._changes[0].id,) if self._changes else (),
            ),
            deliver=False,
        )
        self._emit(EVENT_STATUS)
        self._emit(EVENT_FEED)
        self._emit(EVENT_INCOMING)
        self._emit(EVENT_HISTORY)
        return None

    def dismiss(self, incoming_id: str) -> None:
        self._incoming = [row for row in self._incoming if row.id != incoming_id]
        self._feed = [row for row in self._feed if row.incoming is None or row.incoming.id != incoming_id]
        self._emit(EVENT_INCOMING)
        self._emit(EVENT_FEED)
        self._emit(EVENT_STATUS)

    def combine_state(self) -> Optional[CombineState]:
        return self._combine

    def resolve(self, clash_id: str, resolution: object) -> CombineState:
        if self._combine is None:
            raise ValueError("No combine in progress")
        clashes = []
        for clash in self._combine.clashes:
            if clash.id == clash_id:
                clashes.append(_replace_resolution(clash, resolution))
            else:
                clashes.append(clash)
        self._combine = CombineState(
            id=self._combine.id,
            theirs_from=self._combine.theirs_from,
            note=self._combine.note,
            clashes=tuple(clashes),
            auto_paths=self._combine.auto_paths,
        )
        self._emit(EVENT_COMBINE)
        self._emit(EVENT_STATUS)
        return self._combine

    def finish_combine(self) -> Change:
        state = self._combine
        if state is None or not state.done:
            raise ValueError("Finish stays disabled until every clash is settled")
        author = self._member(state.theirs_from)
        change = self._remember(
            _change(
                self._next_id("c"),
                self._me or ANA,
                _now(),
                f"Combined {author.name.split()[0]}'s change",
                tuple(FileChange(clash.path, FILE_MODIFIED) for clash in state.clashes),
                parents=(self._changes[0].id,) if self._changes else (),
            ),
            deliver=False,
        )
        self._combine = None
        self._emit(EVENT_COMBINE)
        self._emit(EVENT_STATUS)
        self._emit(EVENT_HISTORY)
        return change

    def cancel_combine(self) -> None:
        self._combine = None
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
        rows = self._changes
        if not all_lines:
            rows = [row for row in rows if row.line == self._line or row.line == MAIN_LINE]
        if path:
            rows = [row for row in rows if any(change.path == path for change in row.files)]
        if query:
            needle = query.lower()
            rows = [row for row in rows if needle in row.note.lower() or needle in row.id.lower()]
        page = rows[offset : offset + limit]
        return [replace(row, files=()) for row in page]

    def change_diff(self, change_id: str, against: Optional[str] = None) -> List[FileDiff]:
        del against
        change = next((row for row in self._changes if row.id == change_id), None)
        if change is None:
            return [self._invoice_diff()]
        diffs = []
        for file_change in change.files:
            old, new = self._texts.get(file_change.path, ("", ""))
            diffs.append(
                _file_diff(
                    file_change.path,
                    file_change.kind,
                    old,
                    new,
                    is_form=file_change.path.endswith(".ui"),
                )
            )
        return diffs or [self._invoice_diff()]

    def working_diff(self, path: str) -> FileDiff:
        old, new = self._texts.get(path, (_INVOICE_OLD, _INVOICE_NEW))
        if path.endswith(".ui"):
            old, new = _FORM_OLD, _FORM_NEW
        return _file_diff(path, FILE_MODIFIED, old, new, is_form=path.endswith(".ui"))

    def blame(self, path: str) -> List[BlameLine]:
        cached = self._blame.get(path)
        if cached:
            return list(cached)
        change = self._changes[0] if self._changes else None
        if change is None:
            return []
        return [
            BlameLine(
                line=index,
                change_id=change.id,
                author_id=change.author_id,
                author_name=change.author_name,
                when=change.when,
                note=change.note,
            )
            for index in range(1, 6)
        ]

    def restore(self, change_id: str) -> Change:
        target = next(row for row in self._changes if row.id == change_id)
        return self._remember(
            _change(
                self._next_id("c"),
                self._me or ANA,
                _now(),
                f"Restore {target.note}",
                target.files,
                parents=(self._changes[0].id,) if self._changes else (),
            ),
            deliver=False,
        )

    def undo_change(self, change_id: str) -> Optional[CombineState]:
        del change_id
        if self._accept_clashes:
            return self.accept(self._incoming[0].id) if self._incoming else None
        self._remember(
            _change(
                self._next_id("c"),
                self._me or ANA,
                _now(),
                "Undo this change",
                (FileChange("invoice.py", FILE_MODIFIED),),
            ),
            deliver=False,
        )
        return None

    def set_aside(self, name: str) -> None:
        self._set_aside.append(
            SetAside(index=len(self._set_aside), name=name or "Set aside", when=_now(), files=len(self._pending) or 1)
        )
        self._pending = []
        self._emit(EVENT_STATUS)

    def bring_back(self, index: int) -> Optional[CombineState]:
        self._set_aside = [row for row in self._set_aside if row.index != index]
        self._pending = [FileChange("invoice.py", FILE_MODIFIED)]
        self._emit(EVENT_STATUS)
        return None

    def mark_milestone(self, change_id: str, version: str, note: str = "") -> None:
        del note
        updated = []
        for change in self._changes:
            if change.id == change_id:
                updated.append(
                    Change(
                        id=change.id,
                        parents=change.parents,
                        author_id=change.author_id,
                        author_name=change.author_name,
                        when=change.when,
                        note=change.note,
                        files=change.files,
                        milestone=version,
                        line=change.line,
                    )
                )
            else:
                updated.append(change)
        self._changes = updated
        self._emit(EVENT_HISTORY)

    def start_experiment(self, name: str, from_change: Optional[str] = None) -> None:
        del from_change
        line = name if name.startswith("exp/") else f"exp/{name.strip().lower().replace(' ', '-')}"
        if line not in self._experiments:
            self._experiments.append(line)
        self._line = line
        self._emit(EVENT_STATUS)
        self._emit(EVENT_HISTORY)

    def switch_line(self, line: str) -> None:
        self._line = line
        self._emit(EVENT_STATUS)

    def bring_experiment_in(self, line: str) -> Optional[CombineState]:
        clash = _line_clash("k_exp", "invoice.py", 5)
        self._combine = CombineState(id="combine-exp", theirs_from=line, note=line, clashes=(clash,))
        self._experiments = [item for item in self._experiments if item != line]
        self._line = MAIN_LINE
        self._emit(EVENT_COMBINE)
        self._emit(EVENT_STATUS)
        return self._combine

    def delete_experiment(self, line: str) -> None:
        self._experiments = [item for item in self._experiments if item != line]
        if self._line == line:
            self._line = MAIN_LINE
        self._emit(EVENT_STATUS)

    def remove_member(self, member_id: str) -> None:
        self._members = [member for member in self._members if member.id != member_id]
        self._emit(EVENT_STATUS)

    def export_bundle(self, dest_path: str) -> None:
        from pathlib import Path

        target = Path(dest_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("CBCS-SYNC/1\n", encoding="utf-8")

    def import_bundle(self, src_path: str) -> Optional[Incoming]:
        del src_path
        incoming = _sam_incoming()
        self._incoming.append(incoming)
        self._emit(EVENT_INCOMING)
        self._emit(EVENT_TOAST_PREFIX + "Opened a bundle from USB")
        return incoming

    def poll(self) -> None:
        changed = False
        for change_id, delivery in list(self._deliveries.items()):
            nxt = _advance_delivery(delivery)
            if nxt.state != delivery.state:
                self._deliveries[change_id] = nxt
                changed = True
        if changed:
            self._emit(EVENT_STATUS)
            self._emit(EVENT_FEED)

    def subscribe(self, callback: Callable[[str], None]) -> Unsubscribe:
        self._listeners.append(callback)

        def unsubscribe() -> None:
            if callback in self._listeners:
                self._listeners.remove(callback)

        return unsubscribe

    def _commit(self, note: str, paths: Optional[List[str]], *, deliver: bool) -> Change:
        chosen = self._pending
        if paths is not None:
            chosen = [row for row in self._pending if row.path in paths]
            self._pending = [row for row in self._pending if row.path not in paths]
        else:
            self._pending = []
        change = self._remember(
            _change(
                self._next_id("c"),
                self._me or ANA,
                _now(),
                note or "Update",
                tuple(chosen) or (FileChange("invoice.py", FILE_MODIFIED),),
            ),
            deliver=deliver,
        )
        self._emit(EVENT_STATUS)
        self._emit(EVENT_FEED)
        self._emit(EVENT_HISTORY)
        return change

    def _remember(self, change: Change, *, deliver: bool) -> Change:
        self._changes.insert(0, change)
        if deliver and self._me is not None:
            other = next((member for member in self._members if member.id != self._me.id), SAM)
            self._deliveries[change.id] = Delivery(change.id, other.id, DELIVERY_QUEUED)
        self._push_feed(
            FeedItem(
                kind=FEED_CHANGE,
                id=self._next_id("f"),
                when=change.when,
                text=change.note,
                author_id=change.author_id,
                change=change,
                delivery=self._deliveries.get(change.id),
            )
        )
        return change

    def _push_feed(self, item: FeedItem) -> None:
        self._feed.append(item)

    def _emit(self, event: str) -> None:
        for callback in list(self._listeners):
            callback(event)

    def _next_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}{self._counter}"

    def _find_incoming(self, incoming_id: str) -> Optional[Incoming]:
        return next((row for row in self._incoming if row.id == incoming_id), None)

    def _member(self, member_id: str) -> Member:
        for member in self._members:
            if member.id == member_id:
                return member
        if member_id == SAM.id:
            return SAM
        return ANA

    def _invoice_diff(self) -> FileDiff:
        return _file_diff("invoice.py", FILE_MODIFIED, _INVOICE_OLD, _INVOICE_NEW)


def _replace_resolution(clash: Clash, resolution: object) -> Clash:
    text = resolution if isinstance(resolution, str) else None
    return Clash(
        id=clash.id,
        path=clash.path,
        kind=clash.kind,
        line=clash.line,
        ours=clash.ours,
        theirs=clash.theirs,
        base=clash.base,
        context_before=clash.context_before,
        context_after=clash.context_after,
        resolution=text,
    )


def _advance_delivery(delivery: Delivery) -> Delivery:
    order = {
        DELIVERY_QUEUED: DELIVERY_SENT,
        DELIVERY_SENT: DELIVERY_DELIVERED,
        DELIVERY_DELIVERED: DELIVERY_ACCEPTED,
    }
    nxt = order.get(delivery.state)
    if nxt is None:
        return delivery
    return Delivery(delivery.change_id, delivery.to, nxt)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sam_incoming() -> Incoming:
    change = _change(
        "c_round",
        SAM,
        _T0 + timedelta(hours=2),
        _NOTE,
        (
            FileChange("invoice.py", FILE_MODIFIED),
            FileChange("statement.py", FILE_ADDED),
            FileChange("invoice_form.ui", FILE_MODIFIED),
        ),
        parents=("c_share",),
    )
    return Incoming(id="in_sam_1", from_id=SAM.id, changes=(change,), arrived=_T0 + timedelta(hours=3))


def _base_story(engine: InMemoryTeamSync, *, shared: bool = True) -> None:
    engine._shared = shared
    engine._project_name = "Invoice App" if shared else ""
    engine._me = ANA if shared else None
    engine._members = [ANA, SAM] if shared else []
    engine._terminal = TERMINAL_OK if shared else TERMINAL_NONE
    engine._line = MAIN_LINE
    engine._experiments = []
    engine._pending = []
    engine._set_aside = []
    engine._incoming = []
    engine._invites = []
    engine._combine = None
    engine._unverified = 0
    engine._accept_clashes = None
    engine._toast = ""
    engine._texts = {
        "invoice.py": (_INVOICE_OLD, _INVOICE_NEW),
        "statement.py": ("", _STATEMENT),
        "invoice_form.ui": (_FORM_OLD, _FORM_NEW),
        "legacy_tax.py": ("def tax(total):\n    return total * 0.05\n", ""),
    }
    share = _change(
        "c_share",
        SAM,
        _T0,
        "Shared Invoice App",
        (FileChange("invoice.py", FILE_ADDED),),
        milestone="v0.4",
    )
    sent = _change(
        "c_cents",
        ANA,
        _T0 + timedelta(hours=1),
        "Save totals before tax",
        (FileChange("invoice.py", FILE_MODIFIED),),
        parents=("c_share",),
    )
    engine._changes = [sent, share]
    engine._deliveries = {"c_cents": Delivery("c_cents", SAM.id, DELIVERY_ACCEPTED)}
    engine._blame = {
        "invoice.py": [
            BlameLine(1, "c_share", SAM.id, SAM.name, _T0, "Shared Invoice App"),
            BlameLine(5, "c_round", SAM.id, SAM.name, _T0 + timedelta(hours=2), _NOTE),
        ]
    }
    engine._feed = [
        FeedItem(FEED_SYSTEM, "f_share", _T0, "Sam shared Invoice App", author_id=SAM.id),
        FeedItem(
            FEED_CHANGE,
            "f_cents",
            sent.when,
            sent.note,
            author_id=ANA.id,
            change=sent,
            delivery=engine._deliveries["c_cents"],
        ),
    ]


def _scenario_not_shared(engine: InMemoryTeamSync) -> None:
    _base_story(engine, shared=False)
    engine._changes = []
    engine._deliveries = {}
    engine._feed = []
    engine._terminal = TERMINAL_NONE


def _scenario_idle(engine: InMemoryTeamSync) -> None:
    _base_story(engine)


def _scenario_pending(engine: InMemoryTeamSync) -> None:
    _base_story(engine)
    engine._pending = [
        FileChange("invoice.py", FILE_MODIFIED),
        FileChange("statement.py", FILE_ADDED),
        FileChange("legacy_tax.py", FILE_DELETED),
    ]
    engine._set_aside = [SetAside(0, "Tax experiment notes", _T0 + timedelta(minutes=30), 2)]


def _scenario_queued(engine: InMemoryTeamSync) -> None:
    _base_story(engine)
    engine._deliveries["c_cents"] = Delivery("c_cents", SAM.id, DELIVERY_QUEUED)
    engine._feed[-1] = FeedItem(
        FEED_CHANGE,
        "f_cents",
        engine._changes[0].when,
        engine._changes[0].note,
        author_id=ANA.id,
        change=engine._changes[0],
        delivery=engine._deliveries["c_cents"],
    )


def _scenario_sent(engine: InMemoryTeamSync) -> None:
    _scenario_queued(engine)
    engine._deliveries["c_cents"] = Delivery("c_cents", SAM.id, DELIVERY_SENT)
    engine._feed[-1] = FeedItem(
        FEED_CHANGE,
        "f_cents",
        engine._changes[0].when,
        engine._changes[0].note,
        author_id=ANA.id,
        change=engine._changes[0],
        delivery=engine._deliveries["c_cents"],
    )


def _scenario_delivered(engine: InMemoryTeamSync) -> None:
    _scenario_queued(engine)
    engine._deliveries["c_cents"] = Delivery("c_cents", SAM.id, DELIVERY_DELIVERED)
    engine._feed[-1] = FeedItem(
        FEED_CHANGE,
        "f_cents",
        engine._changes[0].when,
        engine._changes[0].note,
        author_id=ANA.id,
        change=engine._changes[0],
        delivery=engine._deliveries["c_cents"],
    )


def _attach_incoming(engine: InMemoryTeamSync, *, clashes: Optional[tuple[Clash, ...]]) -> None:
    _base_story(engine)
    incoming = _sam_incoming()
    engine._incoming = [incoming]
    engine._accept_clashes = clashes
    engine._changes.insert(0, incoming.changes[0])
    engine._feed.append(
        FeedItem(
            FEED_INCOMING,
            "f_in",
            incoming.arrived,
            incoming.changes[0].note,
            author_id=SAM.id,
            change=incoming.changes[0],
            incoming=incoming,
        )
    )
    engine._toast = "Sam sent a change"


def _scenario_incoming(engine: InMemoryTeamSync) -> None:
    _attach_incoming(engine, clashes=None)


def _scenario_incoming_clash(engine: InMemoryTeamSync) -> None:
    _attach_incoming(engine, clashes=(_line_clash("k1", "invoice.py", 5), _line_clash("k2", "statement.py", 2)))


def _scenario_combine(engine: InMemoryTeamSync, clashes: tuple[Clash, ...]) -> None:
    _base_story(engine)
    engine._combine = CombineState(id="combine-1", theirs_from=SAM.id, note=_NOTE, clashes=clashes)


def _scenario_combine_one(engine: InMemoryTeamSync) -> None:
    _scenario_combine(engine, (_line_clash("k1", "invoice.py", 5),))


def _scenario_combine_several(engine: InMemoryTeamSync) -> None:
    _scenario_combine(
        engine,
        (
            _line_clash("k1", "invoice.py", 5),
            _line_clash("k2", "invoice.py", 8),
            _line_clash("k3", "statement.py", 2),
        ),
    )


def _scenario_combine_form(engine: InMemoryTeamSync) -> None:
    _scenario_combine(engine, (_form_clash(),))


def _scenario_combine_deleted(engine: InMemoryTeamSync) -> None:
    _scenario_combine(engine, (_deleted_clash(),))


def _scenario_experiments(engine: InMemoryTeamSync) -> None:
    _base_story(engine)
    engine._experiments = ["exp/rounding"]
    engine._line = "exp/rounding"
    experiment = _change(
        "c_exp",
        ANA,
        _T0 + timedelta(hours=4),
        "Try rounding on a side line",
        (FileChange("invoice.py", FILE_MODIFIED),),
        line="exp/rounding",
        parents=("c_cents",),
    )
    engine._changes.insert(0, experiment)
    engine._feed.append(
        FeedItem(FEED_CHANGE, "f_exp", experiment.when, experiment.note, author_id=ANA.id, change=experiment)
    )


def _scenario_terminal_offline(engine: InMemoryTeamSync) -> None:
    _base_story(engine)
    engine._terminal = TERMINAL_OFFLINE
    engine._deliveries["c_cents"] = Delivery("c_cents", SAM.id, DELIVERY_QUEUED)


def _scenario_unverified(engine: InMemoryTeamSync) -> None:
    _base_story(engine)
    engine._unverified = 1


def _scenario_invite(engine: InMemoryTeamSync) -> None:
    _scenario_not_shared(engine)
    change = _change("c_invite", SAM, _T0, "Join Invoice App", ())
    engine._invites = [Incoming("invite_1", SAM.id, (change,), _T0, verified=True)]
    engine._toast = "Sam invited you to Invoice App"


def _scenario_milestones(engine: InMemoryTeamSync) -> None:
    _base_story(engine)


def _scenario_large(engine: InMemoryTeamSync) -> None:
    _base_story(engine)
    old = _large_text("old")
    new = _large_text("new")
    engine._texts["big.py"] = (old, new)
    changes = []
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    for index in range(1000):
        author = SAM if index % 3 == 0 else ANA
        line = "exp/rounding" if index % 17 == 0 else MAIN_LINE
        changes.append(
            _change(
                f"c{index:04d}",
                author,
                start + timedelta(hours=index),
                f"Change {index}: round line {index}",
                (FileChange("big.py", FILE_MODIFIED), FileChange("invoice.py", FILE_MODIFIED)),
                milestone="v1.0" if index == 995 else None,
                line=line,
                parents=(f"c{index-1:04d}",) if index else (),
            )
        )
    changes.reverse()
    engine._changes = changes
    engine._feed = engine._feed[:1]


_SCENARIOS = {
    "not_shared": _scenario_not_shared,
    "idle": _scenario_idle,
    "pending": _scenario_pending,
    "queued": _scenario_queued,
    "sent": _scenario_sent,
    "delivered": _scenario_delivered,
    "incoming": _scenario_incoming,
    "incoming_clash": _scenario_incoming_clash,
    "combine_one": _scenario_combine_one,
    "combine_several": _scenario_combine_several,
    "combine_form": _scenario_combine_form,
    "combine_deleted": _scenario_combine_deleted,
    "experiments": _scenario_experiments,
    "terminal_offline": _scenario_terminal_offline,
    "unverified": _scenario_unverified,
    "invite": _scenario_invite,
    "milestones": _scenario_milestones,
    "large": _scenario_large,
}


__all__ = ["ANA", "InMemoryTeamSync", "SAM"]
