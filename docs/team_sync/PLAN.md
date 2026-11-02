# Team Sync v0.5.0 — delivery plan

Spec: `docs/team_sync/SPEC.md`. Branch: `feat/team-sync` (integration). Lanes branch from it
and merge back after Claude's review. `main` gets one reviewed merge at the end.

## Package layout (frozen)

```
app/features/team_sync/
  __init__.py
  install.py                 # FeatureSpec install: wires UI to the shell
  api.py                     # the frozen service contract below (dataclasses + Protocol)
  core/                      # pure Python, no Qt imports (dune-enforced)
    repo.py                  # TeamRepo: dulwich facade (status, commit, log, diff, blame,
                             #   restore, tags, branches, stash) — the ONLY module importing dulwich
    merge3way.py             # CBCS's own diff3 merge on difflib + tree merge + clash model
    combine.py               # combine session (combine.json), finish/cancel, revert, copy
    bundles.py               # bundle create/import (add_thin_pack), verify_closure, parts
    protocol.py              # CBCS-SYNC/1 envelope format/parse, HMAC sign/verify
    mailbox.py               # FaxMail adapter: find mailbox, out/ writer, zip_in/inbox reader
    ledger.py                # sqlite ledger (outbox, seen, parts), local-state placement
    team.py                  # team.json, members, keys, invites, rekey
    service.py               # TeamSyncService: implements api.TeamSyncApi, owns polling
    fake.py                  # InMemoryTeamSync: deterministic fake for UI work and UI tests
  ui/                        # Qt (via the repo's Qt portability layer)
    team_view.py             # Thread view (activity bar)
    send_sheet.py            # toolbar Send + sheet
    status_segment.py        # status bar segment + popover (+ experiment segment)
    info_bar.py              # editor info bar
    tree_decorations.py      # explorer letters
    review_tab.py            # Review tab (DiffView, side-by-side, word diff, .ui preview)
    combine_tab.py           # Combine tab
    history_tab.py           # History tab (list, lanes when needed, context menu)
    blame.py                 # hover card + current-line summary
    gutter_peek.py           # quick diff peek under a gutter mark
    dialogs.py               # Share, Invite, Members, deleted-clash, USB
    settings_group.py        # Settings › Team
    theme.py                 # stylesheet builder from ShellThemeTokens
vendor: dulwich==0.24.10 (py3-none-any) + typing_extensions==4.12.2, Apache-2.0 / PSF notices
```

## Frozen service contract (`app/features/team_sync/api.py`)

Python 3.9 syntax. All methods are synchronous and may block; the UI calls them through the
background task runner. Events are delivered by the service on the UI thread through a
callback the UI registers (`subscribe`). IDs are strings.

```python
@dataclass(frozen=True)
class Member: id: str; name: str; shop: str; email: str
@dataclass(frozen=True)
class FileChange: path: str; kind: str  # "M" | "A" | "D"
@dataclass(frozen=True)
class Change:  # a commit
    id: str; parents: tuple; author_id: str; author_name: str; when: datetime; note: str
    files: tuple  # FileChange
    milestone: Optional[str]; line: str  # "main" or "exp/<slug>"
@dataclass(frozen=True)
class Delivery: change_id: str; to: str; state: str  # "queued"|"sent"|"delivered"|"accepted"|"waiting_terminal"
@dataclass(frozen=True)
class Incoming: id: str; from_id: str; changes: tuple; arrived: datetime; verified: bool
@dataclass(frozen=True)
class FeedItem: kind: str  # "system"|"note"|"change"|"incoming"
    id: str; author_id: Optional[str]; when: datetime; text: str
    change: Optional[Change]; delivery: Optional[Delivery]; incoming: Optional[Incoming]
@dataclass(frozen=True)
class DiffHunk: old_start: int; old_lines: tuple; new_start: int; new_lines: tuple
@dataclass(frozen=True)
class FileDiff: path: str; kind: str; hunks: tuple; is_form: bool; is_binary: bool
@dataclass(frozen=True)
class Clash: id: str; path: str; kind: str  # "lines"|"form"|"binary"|"deleted"
    ours: tuple; theirs: tuple; base: tuple; context_before: tuple; context_after: tuple
    line: int; resolution: Optional[object]  # None|"ours"|"theirs"|"both"|str(text)
@dataclass(frozen=True)
class CombineState: id: str; theirs_from: str; clashes: tuple; auto_paths: tuple; settled: int
@dataclass(frozen=True)
class TeamStatus:
    shared: bool; project_name: str; me: Optional[Member]; members: tuple
    pending: tuple  # FileChange since last send
    waiting: int  # incoming not yet accepted
    combine: Optional[CombineState]; last_delivery: Optional[Delivery]
    terminal: str  # "ok"|"offline"|"none"
    line: str; experiments: tuple; set_aside: tuple; unverified: int
@dataclass(frozen=True)
class BlameLine: line: int; change_id: str; author_id: str; author_name: str; when: datetime; note: str
@dataclass(frozen=True)
class Mailbox: path: str; email: str; label: str

class TeamSyncApi(Protocol):
    def status(self) -> TeamStatus: ...
    def feed(self, limit: int = 200) -> list: ...
    def mailboxes(self) -> list: ...
    def share(self, name: str, invites: list, message: str, mailbox: Optional[str]) -> None: ...
    def accept_invite(self, incoming_id: str, folder: str) -> str: ...  # returns project path
    def send(self, note: str, paths: Optional[list] = None) -> Change: ...
    def save_only(self, note: str, paths: Optional[list] = None) -> Change: ...
    def post_note(self, text: str) -> None: ...
    def incoming(self) -> list: ...
    def incoming_diff(self, incoming_id: str) -> list: ...  # FileDiff
    def accept(self, incoming_id: str) -> Optional[CombineState]: ...  # None = finished
    def dismiss(self, incoming_id: str) -> None: ...
    def combine_state(self) -> Optional[CombineState]: ...
    def resolve(self, clash_id: str, resolution: object) -> CombineState: ...
    def finish_combine(self) -> Change: ...
    def cancel_combine(self) -> None: ...
    def history(self, path: Optional[str] = None, query: str = "", offset: int = 0, limit: int = 200,
                all_lines: bool = False) -> list: ...
    def change_diff(self, change_id: str, against: Optional[str] = None) -> list: ...
    def working_diff(self, path: str) -> FileDiff: ...  # vs last saved change (gutter peek)
    def blame(self, path: str) -> list: ...
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
    def poll(self) -> None: ...  # one inbound/outbound cycle; the service schedules it every 30 s
    def subscribe(self, callback: Callable[[str], None]) -> Callable[[], None]: ...
    # events: "status", "feed", "incoming", "combine", "history", "toast:<text>"
```

The contract may grow only by adding optional parameters or new methods, recorded here.

### L2 UI additions (not protocol members)

`InMemoryTeamSync.scenario(name)`, `share_summary() -> tuple[int, str]`, and `project_files() -> dict`
exist on the fake so the UI and the screenshot script can jump states. `TeamSyncApi` is unchanged.
The UI reads `share_summary` with `getattr` and falls back when a service does not provide it.

## L1 additions (engine)

`TeamSyncService(project_root, *, machine=None, clock=None, mail_roots=None)`
is the constructor. `machine` is a shop-sharing `Machine`. `clock` returns a
datetime. `mail_roots`, when passed, replaces FaxMail discovery and may be
either a `.Mails` directory or one account directory.

`accept_invite(incoming_id, folder, my_name="", my_shop="")` grows two optional
keyword arguments so the joiner can name themselves. The folder is the new
project root.

`copy_change(change_id) -> Optional[CombineState]` copies one change onto the
current line (cherry-pick through the merge engine).

`invite_detail(incoming_id) -> dict` returns `project_id`, `project_name`,
`sender_name`, `sender_shop`, and `sender_email` for an invite. `Incoming` is
unchanged.

Wire additions beyond the spec's sample body, all signed when the message is
signed: `part-sha256` (this part), and on join `member-id`, `member-name`,
`member-shop`, `member-email`. Invites stay unsigned and carry `key`,
`sender-name`, `sender-shop`, `sender-email`. `have` may include `accepted: 1`.
The outbox stores `recipient`, `part_idx`, `part_total`, `change_id`, and `tip`
next to the columns the spec names, so delivery can be updated per person.

## L1b additions (engine)

`share_experiment(line) -> Change` publishes `exp/<slug>` as its own ref. `send`
always publishes `main` and refuses while the current line is an experiment.

Owner decisions D1 to D6 are recorded in `SPEC.md` under Rules T3a to T3e and the
Merge engine and Security sections. The wire gained optional signed fields
`note`, `removed`, and `line`. `removed` is the member a rekey drops.
`line` is set only when an experiment is shared.

## L3 additions (wiring)

`history()` returns each `Change` with `files=()`. The History list never shows
paths. Selecting a row loads them from `change_diff()`. `feed()` still carries
file counts. Those paths are computed once per commit sha and stored in the
ledger table `commit_files`, because a commit does not change.

No new protocol method. An invite that arrives while no team project is open is
found by `poll()` and `pending_invites()` on a `TeamSyncService` whose root is
`machine.local_state/team_sync/invite_watch`. The UI binds a project service
with `Machine.current()` when a project opens and drops it when the project
changes.

## Lanes

| Lane | Branch | Owner | Depends on | Delivers |
|---|---|---|---|---|
| L0 Foundation | `feat/team-sync` | Claude | — | spec, plan, `api.py`, package skeleton, dune registration, vendored dulwich + typing_extensions, `fake.py` |
| L1 Core engine | `grok/team-sync-core` | Grok | L0 | `core/*` real implementation, tests 1–6, perf budgets |
| L2 UI | `grok/team-sync-ui` | Grok | L0 (`fake.py`) | `ui/*`, `install.py`, UI tests (7), screenshots light/dark against the prototype |
| L3 Integration | `feat/team-sync` | Claude + Grok | L1, L2 | wire the real service, full shards, cbfarm shop day, polish fixes |
| L4 Merge | `main` | Claude | L3 | CHANGELOG, docs (ARCHITECTURE, TASKS, USER_REQUESTS_TODO #23), version bump, PR, merge |

L1 and L2 run in parallel. Each lane's report must include the exact commands it ran and
their results. Claude reviews every diff, reruns the checks, and signs off the UI visually.
