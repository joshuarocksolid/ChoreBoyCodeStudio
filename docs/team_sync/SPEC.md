# Team Sync: code collaboration between ChoreBoy shops

Status: approved design for v0.5.0. Owner: Joshua (program run by Claude, heavy lifting by Grok). Written 2026-11-02.

Design record (decisions and prototypes):

- Architecture and research: artifact "CBCS Team Sync" (https://claude.ai/artifact/UqxrdJui2nd42bt36LtjSp)
- UX round one (where Team Sync lives): artifact "Team Sync Prototype" (https://claude.ai/artifact/NAMuctwQXSNeQc5eA6Afsn)
- UX round two (diffs, combining, power tools): artifact "Team Sync Power Tools" (https://claude.ai/artifact/QyJgD7eqsmJF6wyScG6D93)
- Prototype sources and verdicts: branch `prototype/team-sync` (throwaway, never merged).

This supersedes `docs/USER_REQUESTS_TODO.md` #23 ("Git idea via faxmail terminal", WON'T DO).

## Why

ChoreBoy users cannot use GitHub. ChoreBoys have no internet route and cannot run
`git`, `ssh` or any program besides `/bin/sh`. Shops still need to work on the same
projects. Every shop has a FaxMail terminal that sends and receives email, and every
shop's ChoreBoys share net1's `/home/share`. Team Sync gives two or more shops a shared
project with real history, using only those.

## Facts this design rests on (all measured, see the architecture artifact)

- Confined CBCS (FreeCAD AppRun, Python 3.9.2) can: write and atomically `os.replace`
  on net1's NFS share; use `O_EXCL` and `mkdir` as locks; send SMTP to `77.77.77.15:25`;
  import `sqlite3`, `zlib`, `zipfile`, `hashlib`, `hmac`, `difflib`.
- Carts mount the share `soft,timeo=5,retrans=2`: a stalled server makes a write fail
  mid-way. Hardlinks are denied. Running `/usr/bin/git` is denied.
- FaxMail outbound: a folder `.Mails/<account>/out/<id>/` holding `message.mail` (mutt
  `-H` draft: headers, blank line, body) and `att/`. `compile_mail.sh` skips folders
  holding `.lock`, sends within 15 s, then moves the folder to `sent/<id>/`.
- FaxMail inbound: getmail every 3 min (04:00–22:57), every 15 min overnight. Each message
  lands on the share as `.Mails/<account>/zip_in/<ts>!.zip` containing `<ts>!/_headers_`,
  `<ts>!/textfile0` (body) and attachments byte-for-byte. The ChoreBoy FaxMail client may
  later unpack zips into `.Mails/<account>/inbox/<ts>!/` (same three kinds of files).
- The terminal accepts messages up to 36 MB (`SIZE 36000000`); base64 grows 5 MiB to 7.2 MB.
- dulwich 0.24.10 (pure Python, last release for Python 3.9) runs in confined AppRun:
  commit 202 files on the share in ~0.6 s, make full and incremental bundles, import a
  delta-compressed bundle made by real git via `object_store.add_thin_pack`, and real git
  reads its bundles (`git fsck --strict` clean). `Bundle.store_objects` and
  `add_pack_data(iter_unpacked())` lose commits on offset deltas: never use them.
- dulwich's `merge`, `cherry_pick` and `revert` need `merge3`, which is GPL-2.0-or-later.
  CBCS is MIT. dulwich is used under its Apache-2.0 option. **CBCS writes its own
  three-way merge on `difflib`.**

## Decisions (from the prototype rounds)

| Area | Decision |
|---|---|
| Direction | Thread as the one Team view, plus toolbar Send, an editor info bar for incoming changes, and a clickable Team status-bar segment. |
| Saving | Send saves a change (a git commit) and sends it. "Save Only" makes a checkpoint without sending. |
| Incoming | Nothing touches the user's files until they press Accept. |
| Alerts | Team badge, status segment, editor bar on affected open files, and a toast when something arrives. |
| Reviewing | A Review editor tab (inline or side by side, word-level highlights) with "Show in file". |
| Clashes | A Combine editor tab. Files stay untouched until Finish. Cancel restores everything. |
| History | Plain list, newest first. Lanes appear only when experiments exist or advanced tools are on. |
| Git power | Three layers: everyday, on demand (menus, hovers), Advanced setting (off by default). |
| Words | Change, Send, Accept, Combine, Restore, Undo, Set aside, Milestone, Experiment. Git names only in tooltips, or everywhere when "Show git names" is on. |

## Rules

- T1. Plain, quiet, fast. No UI for a project until it is shared, except one way in.
- T2. Never block typing. Every disk, git, merge, bundle and mail operation runs on the
  background task runner. The UI thread only paints results.
- T3. Nothing lost. Incoming work goes to a holding area. Accept, Restore and Undo always
  create a new change. Combine never edits files before Finish. Every Accept leaves a
  restore point (the pre-accept commit, reachable from History).
- T4. Nothing from outside runs. Bundles are verified (HMAC + sender) before dulwich parses
  them. Imports never execute hooks or code.
- T5. The FaxMail terminal is not modified. CBCS writes only `out/<id>/` folders it created
  and reads `zip_in/`, `inbox/` and `sent/` read-only. It never deletes or moves user mail.
- T6. Shared files hold no absolute paths (same rule as shop sharing, `docs/shop_sharing/SPEC.md` R1).
- T7. Torn writes are expected on the share: write temp + fsync + `os.replace`, verify hashes
  on read, retry on `OSError`.
- T8. Order comes from the commit graph, never from clocks.

## Terms

- **Team project**: a project folder whose `.git` holds Team Sync history and whose
  `cbcs/team.json` lists the team. A project is solo until it is shared.
- **Shop**: one FaxMail mailbox (one email address). In v0.5.0 one station per shop works
  on a team project; same-shop stations (shop hub) are P2.
- **Member**: `{"id": "<shop id>", "name": "Ana Kurtz", "shop": "Cedar Hollow", "email": "cedarhollow@…"}`.
  `id` is a random 8-hex string fixed at join.
- **Project key**: 32 random bytes per team project, created at share, sent in the invite,
  stored only in `.git/cbcs/key` (mode 600), never committed. Rotated when a member is removed.
- **Change**: a git commit. Author `Name <email>`. Message = the note. Trailers:
  `CBCS-Shop: <shop id>`, `CBCS-Station: <hostname>`.
- **Peer tip**: `refs/peers/<shop id>/main`, the last commit we know that shop has.
- **Incoming**: `refs/incoming/<shop id>/<bundle id>` until accepted or dismissed.
- **Milestone**: a tag `v<version>` (annotated, message = package note).
- **Experiment**: a branch `exp/<slug>`. Local unless shared. `main` is the shared line.
- **Set aside**: dulwich stash.

## Storage layout

In the project (committed): `cbcs/team.json`

```json
{"schema_version": 1, "project_id": "p_2c91…", "name": "Invoice App",
 "members": [{"id": "a1b2c3d4", "name": "Sam Brenneman", "shop": "Maple Ridge", "email": "mapleridge@…"}],
 "created_at": "2026-11-02T14:01:00Z"}
```

In `.git/cbcs/` (local, never committed, never sent):

- `key` — project key (raw 32 bytes, mode 600).
- `me.json` — `{"member_id", "mailbox": "<abs path to .Mails/<account>>", "email"}`.
- `ledger.sqlite` — local only (`.git` lives in the project; if the project is on the share,
  the ledger moves to `<local state>/team_sync/<project_id>/ledger.sqlite`; SQLite never on the
  share). Tables: `outbox(bundle_id, verb, created_at, out_folder, state, sent_at, delivered_at, accepted_at)`,
  `seen(message_key, seen_at, result)`, `parts(bundle_id, idx, total, sha256, path)`.
- `combine.json` — an in-progress combine session (see Merge).
- `holding/` — verified bundles waiting to be accepted.

The default `.gitignore` written at share time ignores `vendor/`, `__pycache__/`, `*.pyc`,
`cbcs/runs/`, `.cbcs_*`, plus whatever `app/packaging/payload_policy.py` already prunes.

## Wire format: CBCS-SYNC/1

One email per message. Subject: `CBCS-SYNC/1 <verb> <project_id> <project name>`.
Body (plain text, first lines, `key: value`):

```
CBCS-SYNC/1
verb: push
project: p_2c91…
from: a1b2c3d4
to: e5f6a7b8
bundle: b_<16 hex>
tip: <commit sha>
needs: <commit sha>[,<sha>…]
changes: 2
part: 1/1
bundle-sha256: <hex of the whole bundle>
signature: <hex HMAC-SHA256(key, canonical header lines + bundle-sha256)>

Sent by ChoreBoy Code Studio. No action is needed in your mail.
```

Verbs: `invite` (carries the key, unsigned, see Security), `join`, `push`, `have`
(tips I now hold; confirms delivery), `want` (resend from these tips), `note`
(a thread message with no bundle), `rekey` (new project key after a member is removed,
signed with the old key, sent only to remaining members). Attachment: `<project name>-<bundle id>.cbcsbundle`
(a git v2 bundle), or parts `…​.cbcsbundle.part-02-of-03` when over 10 MiB raw.

Idempotent: `seen` keys on `(from, bundle, part)`. A duplicate is ignored. A bundle whose
`needs` we lack triggers one `want` reply and stays in holding.

## FaxMail adapter

- **Find the mailbox**: candidates `<share root>/PDF/.Mails/*/` for each root from
  `shop_sharing.storage.share_roots(machine)`, plus `/home/default/PDF/.Mails/*/`. An account
  folder qualifies when it holds `account_settings_v2.conf`. Read `EmailAddress}{<…>` for our
  address and `MaxMsgSize}{…` for the size cap. One account → use it. Several → the user picks
  once (Share dialog), saved in `me.json`. None → Team Sync shows "No FaxMail mailbox found"
  and offers Save to USB.
- **Send**: build in a temp folder on local disk, then create `out/<id>/` with `.lock`
  first, copy `message.mail` and `att/`, fsync, remove `.lock`. `<id>` = 17-digit UTC
  timestamp like FaxMail's own (`YYYYMMDDHHMMSSmmm`), unique per folder. State `queued`.
- **Sent**: `out/<id>` gone and `sent/<id>/message.mail` present → `sent`.
- **Delivered**: a verified `have` from that member naming the tip → `delivered`.
- **Receive**: every 30 s (stat only; full scan when a directory mtime changed) list
  `zip_in/*.zip` and `inbox/*/`. Read `_headers_` from the zip without extracting; a Subject
  starting `CBCS-SYNC/1 ` for one of our projects is ours. Copy the attachment out (never
  move the zip), verify, file into holding. Others' mail is never touched.
- **Never**: delete, rename or rewrite anything under `.Mails` except our own `out/<id>/`
  while it still holds `.lock`.

## Merge engine (CBCS's own)

- Text files: line-level diff3 on `difflib.SequenceMatcher` over (base, ours, theirs).
  Non-overlapping hunks merge. Identical changes on both sides merge. Overlapping different
  hunks produce a **clash** `{path, base_lines, ours_lines, theirs_lines, ours_range, context}`.
- Whole-file kinds: `.ui` forms, binary files (NUL byte in the first 8 KB) and files over
  1 MiB clash as whole files when both sides changed them.
- Tree cases: added on one side → take it; both added same path, same content → take it,
  different → whole-file clash; deleted vs unchanged → delete; deleted vs edited → **deleted
  clash** (Keep yours / Delete it); renamed files are handled as delete + add.
- A **combine session** (`combine.json`): `{ours, theirs, base, auto_paths, clashes:[{id, path,
  kind, resolution: null|"ours"|"theirs"|"both"|{"text": …}}]}`. Nothing is written to the
  working tree until Finish: Finish writes all merged files atomically, then commits a merge
  commit with both parents and the note "Combined <name>'s change". Cancel deletes
  the session. The session survives a restart.
- "Both" for a single-line clash: ours then theirs, unless one side's line is a prefix
  expression of the other (keep it simple; the user can Edit).
- Undo this change (revert) and Copy a change (cherry-pick) use the same engine with
  (base = change's parent, ours = HEAD, theirs = inverse/change).

## UI (precise; matches the round-two prototype)

All UI lives in `app/features/team_sync/ui/` and is installed through `FeatureSpec`. It
uses CBCS widgets, `ShellThemeTokens`, `dialog_chrome`, `DiffView`, the diff gutter and
the existing background task runner. No new visual language. Inside the UI: one label per
thing, no hint lines, detail behind hover or click.

1. **Activity bar**: Team icon (two heads, CBCS icon style) after Tests. Badge = incoming
   changes + clashes waiting.
2. **Team view (Thread)**: header `TEAM` + member avatars (initials, stable colour per member).
   Not shared → centered "Not shared" + **Share Project…**. Shared → feed of system lines
   ("Sam shared Invoice App · 9:01"), notes and changes (avatar, name or "You", time, note,
   "3 files" link, delivery mark: `Queued` / ✓ / ✓✓, tooltip names the state). An incoming
   change is highlighted with **Review**. Composer at the bottom: "N files" chip (expands to a
   checklist of changed files with M/A/D), message field, send button; its menu: Send, Save
   Only, Set Aside. A set-aside row above the composer: name + **Bring Back**.
3. **Toolbar**: **Send** button (Package Project style, left of Package Project) with a count of
   changed files; opens a sheet: file checklist, note, **Send to <shop>**. Shown only in team
   projects.
4. **Status bar**: `Team: Up to date` / `3 to send` / `Queued` / `Sent` / `Delivered` /
   `1 from Sam` / `1 line to choose` / `Terminal offline` with a dot (ok, info, warn). Click
   opens a popover: members, last sent change with marks, waiting items, terminal health
   (from `.faxmail15-watchdog`-style `.<host>-watchdog` files under `.Mails`; stale > 5 min =
   offline), and History. When an experiment exists, a second segment shows the current line
   of work and opens the experiment menu.
5. **Explorer**: letters at row end: M changed since last send, A new, D deleted, ↓ incoming,
   ! needs a choice. Cached; never a disk walk on paint.
6. **Editor info bar**: on an open file touched by an incoming change: avatar, "Sam changed
   this file", **Review**. On a file with a clash: "1 line in invoice.py needs your choice",
   **Cancel Combine**, **Resolve**.
7. **Toast** when something arrives (one per bundle, not per part), with **Review**.
8. **Review tab** (editor tab "Review · Sam"): header (avatar, note, time, Inline/Side by side,
   Show in File, Not Now, Accept). Left: file list with M/A/D. Right: `DiffView` with
   word-level highlights. `.ui` files show a visual before/after (render both forms
   read-only with the Designer loader if available, else a property-change table) with changed
   widgets outlined and a property table. Accept → combine; if no clashes, finish immediately
   and post "You accepted Sam's change" to the thread.
9. **Combine tab** ("Combine"): header (warning icon, "N of M settled", previous/next, Cancel,
   Finish disabled until all settled). Left: clashes grouped by file (✓ settled, current,
   waiting). Right: Yours and Theirs side by side with 2 lines of context and **Use This**;
   below, **Result** with **Both** and **Edit**. Form clashes: two form previews with **Keep
   this form** and a difference table. Deleted clashes: a small dialog, Keep your version /
   Delete it.
10. **History tab**: search field, "Main" filter, list (avatar, note with milestone flag chip,
    date), selection shows the change's files and diff. Lanes appear when an experiment exists
    or advanced tools are on. Right-click: Compare with Current, Compare with…, Restore This
    Version, Undo This Change, Start Experiment Here, Mark as Milestone…, Copy Change ID.
11. **Who changed this**: hover on a line shows a card (avatar, name, shop, date, note, small
    diff, Open Change, File History). The current line shows a faint end-of-line summary
    (`Sam · Nov 2 · Round totals to cents`), toggled in Settings › Team.
12. **Gutter quick diff**: clicking a change mark opens a peek under the line with the old and
    new lines and **Undo Edit**.
13. **Share dialog**: title "Share <project>", chip "<n> files · <size>", Invite (member
    tokens; type an email + shop name), Message (optional). Mailbox choice only when several.
    Footer: Cancel, **Send Invite**.
14. **Invite**: arrives as a toast + dialog: "<name> invited you to <project>", "✓ Verified"
    (sender address matches the invite's `from` email), Location field. **Open Project**.
15. **Package Project**: adds "Mark this version in history" (on by default) → milestone tag.
16. **Settings › Team** (global): Show who-changed summary on the current line; Show git names;
    Show change IDs; Advanced: Copy a change into an experiment, Find when something broke,
    Tidy changes before sending. All off except the line summary.
17. **Members** (from the popover ⋯): list, Remove (rotates the key and sends the new key to
    remaining members in a signed `rekey` note), Save to USB / Open from USB (same bundle).

## Performance budgets (enforced by `tests/integration/performance/`)

Measured on the Mac dev AppRun and spot-checked on a ChoreBoy; project of 500 files / 5 MB.

| Operation | Budget |
|---|---|
| Changed-file status refresh (background) | ≤ 150 ms; UI thread work ≤ 5 ms |
| Explorer decorations repaint | no disk access; ≤ 1 ms per visible row |
| Send (commit + bundle + out folder) for a 3-file change | ≤ 1.0 s |
| Inbound scan with nothing new | ≤ 20 ms (stat only) |
| Import + verify a 50-commit bundle | ≤ 2.0 s |
| Three-way merge of a 2,000-line file | ≤ 150 ms |
| Review tab first paint | ≤ 150 ms; large diffs render lazily |
| History tab first paint (1,000 changes) | ≤ 200 ms (load in pages of 200) |
| Blame for a 2,000-line file | ≤ 400 ms, cached per (path, HEAD) |

## Security

- The invite carries the project key in clear: email is the only channel. Threat model:
  stops forged changes from strangers who email the shop; does not stop someone who can
  read the shop's mailbox. Documented in the Share dialog's tooltip, not in the UI copy.
- Every non-invite message: HMAC over canonical header lines + bundle sha256; sender address
  must match the member's email; `from` must be a member. Failures are dropped and listed in
  the popover as "1 message couldn't be verified".
- dulwich never sees an unverified bundle. Imports run `verify_closure` before any ref moves.

## Out of scope for v0.5.0

- Same-shop stations through net1's share (shop hub) — P2.
- LAN live link — P3. RockSolid relay mailbox and GitHub mirror — P4.
- Rewriting history after a change is sent. Submodules, worktrees, LFS, hooks.

## Tests (risk-first; only these)

1. Merge engine matrix: non-overlapping hunks, identical edits, overlapping clash, add/add,
   delete/edit, `.ui` whole-file, binary, CRLF preserved, trailing newline preserved.
2. Combine session: Finish writes exactly the resolved content and a two-parent commit;
   Cancel leaves the tree byte-identical; a restart resumes the session.
3. Bundles: full and incremental round trip; a real-git delta bundle imports completely
   (fixture made with git); a tampered bundle or wrong HMAC is rejected before parsing; parts
   join only when every part's sha matches.
4. Mail adapter on a fixture `.Mails` tree: send writes `.lock` first and removes it last;
   `out→sent` moves to Sent; a CBCS zip in `zip_in` is read without moving it; non-CBCS mail
   untouched; duplicates ignored; a missing prerequisite sends one `want`.
5. End-to-end two-repo flow with an in-memory mailbox: share → join → send → accept →
   clash → finish → have → ✓✓.
6. Performance budgets above (performance shard).
7. One UI test per surface that can regress silently: Send button count follows status;
   Review tab Accept moves to Combine when clashes exist; Combine Finish disabled until all
   settled.

## Verification before merge

- `python3 testing/run_test_shard.py fast`, `integration`, `performance`, `npx pyright`,
  `npx pyright -p pyrightconfig.tests.json`, dune checks — all clean.
- cbfarm `shop` lease: Sam on net1 and Ana on net2, both on the shop's own FaxMail account,
  run the full day (share, join, send, deliver, receive, combine, history) through the twin's
  mail path, with screenshots of every surface in light and dark, and the terminal-offline
  case via the twin's fault controls.
- Visual sign-off by Claude against the round-two prototype.
