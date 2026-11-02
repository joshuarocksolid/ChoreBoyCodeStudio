"""Frozen service contract between Team Sync's core engine and its UI.

The UI only talks to :class:`TeamSyncApi`. ``core.service.TeamSyncService`` implements it
for real; ``core.fake.InMemoryTeamSync`` implements it for UI work and UI tests. The
contract may grow only by adding optional parameters or new methods (record them in
``docs/team_sync/PLAN.md``). All methods may block; the UI calls them on the background
task runner. Events reach the UI through :meth:`TeamSyncApi.subscribe`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List, Optional, Tuple, Union

try:  # Python 3.8+ has Protocol in typing; keep the import explicit for pyright.
    from typing import Protocol
except ImportError:  # pragma: no cover
    from typing_extensions import Protocol  # type: ignore[assignment]


FILE_MODIFIED = "M"
FILE_ADDED = "A"
FILE_DELETED = "D"

DELIVERY_QUEUED = "queued"
DELIVERY_WAITING_TERMINAL = "waiting_terminal"
DELIVERY_SENT = "sent"
DELIVERY_DELIVERED = "delivered"
DELIVERY_ACCEPTED = "accepted"

FEED_SYSTEM = "system"
FEED_NOTE = "note"
FEED_CHANGE = "change"
FEED_INCOMING = "incoming"

CLASH_LINES = "lines"
CLASH_FORM = "form"
CLASH_BINARY = "binary"
CLASH_DELETED = "deleted"

RESOLVE_OURS = "ours"
RESOLVE_THEIRS = "theirs"
RESOLVE_BOTH = "both"
RESOLVE_DELETE = "delete"

TERMINAL_OK = "ok"
TERMINAL_OFFLINE = "offline"
TERMINAL_NONE = "none"

MAIN_LINE = "main"

EVENT_STATUS = "status"
EVENT_FEED = "feed"
EVENT_INCOMING = "incoming"
EVENT_COMBINE = "combine"
EVENT_HISTORY = "history"
EVENT_TOAST_PREFIX = "toast:"

Resolution = Union[None, str]
"""``None`` (unsettled), one of the ``RESOLVE_*`` values, or ``"text:" + edited text``."""

RESOLVE_TEXT_PREFIX = "text:"


@dataclass(frozen=True)
class Member:
    id: str
    name: str
    shop: str
    email: str


@dataclass(frozen=True)
class FileChange:
    path: str
    kind: str  # FILE_MODIFIED | FILE_ADDED | FILE_DELETED


@dataclass(frozen=True)
class Change:
    """One saved change (a git commit)."""

    id: str
    parents: Tuple[str, ...]
    author_id: str
    author_name: str
    when: datetime
    note: str
    files: Tuple[FileChange, ...] = ()
    milestone: Optional[str] = None
    line: str = MAIN_LINE


@dataclass(frozen=True)
class Delivery:
    change_id: str
    to: str  # member id
    state: str  # DELIVERY_*


@dataclass(frozen=True)
class Incoming:
    id: str
    from_id: str
    changes: Tuple[Change, ...]
    arrived: datetime
    verified: bool = True


@dataclass(frozen=True)
class FeedItem:
    kind: str  # FEED_*
    id: str
    when: datetime
    text: str
    author_id: Optional[str] = None
    change: Optional[Change] = None
    delivery: Optional[Delivery] = None
    incoming: Optional[Incoming] = None


@dataclass(frozen=True)
class DiffHunk:
    old_start: int
    old_lines: Tuple[str, ...]
    new_start: int
    new_lines: Tuple[str, ...]
    context_before: Tuple[str, ...] = ()
    context_after: Tuple[str, ...] = ()


@dataclass(frozen=True)
class FileDiff:
    path: str
    kind: str  # FILE_*
    hunks: Tuple[DiffHunk, ...] = ()
    is_form: bool = False
    is_binary: bool = False
    old_text: Optional[str] = None  # whole files, filled for forms and on request
    new_text: Optional[str] = None


@dataclass(frozen=True)
class Clash:
    id: str
    path: str
    kind: str  # CLASH_*
    line: int  # 1-based line in "ours" where the clash starts (0 for whole-file kinds)
    ours: Tuple[str, ...] = ()
    theirs: Tuple[str, ...] = ()
    base: Tuple[str, ...] = ()
    context_before: Tuple[str, ...] = ()
    context_after: Tuple[str, ...] = ()
    resolution: Resolution = None


@dataclass(frozen=True)
class CombineState:
    id: str
    theirs_from: str  # member id, or "exp/<slug>" when bringing an experiment in
    note: str
    clashes: Tuple[Clash, ...] = ()
    auto_paths: Tuple[str, ...] = ()

    @property
    def settled(self) -> int:
        return sum(1 for clash in self.clashes if clash.resolution is not None)

    @property
    def done(self) -> bool:
        return self.settled == len(self.clashes)


@dataclass(frozen=True)
class SetAside:
    index: int
    name: str
    when: datetime
    files: int


@dataclass(frozen=True)
class TeamStatus:
    shared: bool
    project_name: str
    me: Optional[Member] = None
    members: Tuple[Member, ...] = ()
    pending: Tuple[FileChange, ...] = ()
    waiting: int = 0
    combine: Optional[CombineState] = None
    last_delivery: Optional[Delivery] = None
    terminal: str = TERMINAL_NONE
    line: str = MAIN_LINE
    experiments: Tuple[str, ...] = ()
    set_aside: Tuple[SetAside, ...] = ()
    unverified: int = 0


@dataclass(frozen=True)
class BlameLine:
    line: int  # 1-based
    change_id: str
    author_id: str
    author_name: str
    when: datetime
    note: str


@dataclass(frozen=True)
class Mailbox:
    path: str  # absolute path of .Mails/<account>
    email: str
    label: str  # account folder name


@dataclass(frozen=True)
class Invite:
    name: str
    shop: str
    email: str


@dataclass
class ShareRequest:
    project_name: str
    invites: List[Invite] = field(default_factory=list)
    message: str = ""
    mailbox: Optional[str] = None
    my_name: str = ""
    my_shop: str = ""


Unsubscribe = Callable[[], None]


class TeamSyncApi(Protocol):
    """Everything the Team Sync UI may ask of the engine."""

    def status(self) -> TeamStatus: ...

    def feed(self, limit: int = 200) -> List[FeedItem]: ...

    def mailboxes(self) -> List[Mailbox]: ...

    def share(self, request: ShareRequest) -> None: ...

    def pending_invites(self) -> List[Incoming]: ...

    def accept_invite(self, incoming_id: str, folder: str) -> str: ...

    def send(self, note: str, paths: Optional[List[str]] = None) -> Change: ...

    def share_experiment(self, line: str) -> Change: ...

    def save_only(self, note: str, paths: Optional[List[str]] = None) -> Change: ...

    def post_note(self, text: str) -> None: ...

    def incoming(self) -> List[Incoming]: ...

    def incoming_diff(self, incoming_id: str) -> List[FileDiff]: ...

    def accept(self, incoming_id: str) -> Optional[CombineState]: ...

    def dismiss(self, incoming_id: str) -> None: ...

    def combine_state(self) -> Optional[CombineState]: ...

    def resolve(self, clash_id: str, resolution: Resolution) -> CombineState: ...

    def finish_combine(self) -> Change: ...

    def cancel_combine(self) -> None: ...

    def history(
        self,
        path: Optional[str] = None,
        query: str = "",
        offset: int = 0,
        limit: int = 200,
        all_lines: bool = False,
    ) -> List[Change]: ...

    def change_diff(self, change_id: str, against: Optional[str] = None) -> List[FileDiff]: ...

    def working_diff(self, path: str) -> FileDiff: ...

    def blame(self, path: str) -> List[BlameLine]: ...

    def restore(self, change_id: str) -> Change: ...

    def undo_change(self, change_id: str) -> Optional[CombineState]: ...

    def set_aside(self, name: str) -> None: ...

    def bring_back(self, index: int) -> Optional[CombineState]: ...

    def mark_milestone(self, change_id: str, version: str, note: str = "") -> None: ...

    def start_experiment(self, name: str, from_change: Optional[str] = None) -> None: ...

    def switch_line(self, line: str) -> None: ...

    def bring_experiment_in(self, line: str) -> Optional[CombineState]: ...

    def delete_experiment(self, line: str) -> None: ...

    def remove_member(self, member_id: str) -> None: ...

    def export_bundle(self, dest_path: str) -> None: ...

    def import_bundle(self, src_path: str) -> Optional[Incoming]: ...

    def poll(self) -> None: ...

    def subscribe(self, callback: Callable[[str], None]) -> Unsubscribe: ...


__all__ = [
    "BlameLine",
    "CLASH_BINARY",
    "CLASH_DELETED",
    "CLASH_FORM",
    "CLASH_LINES",
    "Change",
    "Clash",
    "CombineState",
    "DELIVERY_ACCEPTED",
    "DELIVERY_DELIVERED",
    "DELIVERY_QUEUED",
    "DELIVERY_SENT",
    "DELIVERY_WAITING_TERMINAL",
    "Delivery",
    "DiffHunk",
    "EVENT_COMBINE",
    "EVENT_FEED",
    "EVENT_HISTORY",
    "EVENT_INCOMING",
    "EVENT_STATUS",
    "EVENT_TOAST_PREFIX",
    "FEED_CHANGE",
    "FEED_INCOMING",
    "FEED_NOTE",
    "FEED_SYSTEM",
    "FILE_ADDED",
    "FILE_DELETED",
    "FILE_MODIFIED",
    "FeedItem",
    "FileChange",
    "FileDiff",
    "Incoming",
    "Invite",
    "MAIN_LINE",
    "Mailbox",
    "Member",
    "RESOLVE_BOTH",
    "RESOLVE_DELETE",
    "RESOLVE_OURS",
    "RESOLVE_TEXT_PREFIX",
    "RESOLVE_THEIRS",
    "Resolution",
    "SetAside",
    "ShareRequest",
    "TERMINAL_NONE",
    "TERMINAL_OFFLINE",
    "TERMINAL_OK",
    "TeamStatus",
    "TeamSyncApi",
    "Unsubscribe",
]
