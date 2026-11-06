# Shop sharing: shared Code Studio settings across a shop's ChoreBoys

Status: approved design for v0.4.14. Owner: Joshua. Written 2026-10-26.

## Why

v0.4.13 shares settings through a hand-made pointer file at
`~/share/Chore_Boy/CBCS/cbcs_state_root` or a home-folder link. Tested on a
ChoreBoy (slot ChoreBoy2, v0.4.13 installer) on 2026-10-26:

| # | Setup | Result |
|---|---|---|
| S4 | Client reads the server's pointer through `~/share/net1/` | The absolute path inside is wrong on the client. Falls back to local settings and shows a modal at every launch. |
| S5 | Pointer edited to the client path | The client's first launch emptied the shared recent-projects list (prune + save back). |
| S6 | net1 sets Theme Dark; net2 then changes only Font size | Dark is lost. Save writes the whole in-memory copy. |
| S7 | Share disappears mid-session, then Save | Save silently goes to the local file. No message. |

ChoreBoy facts that shape the design (measured):

- Every ChoreBoy has `/home/default/share`. On the server the shop's files
  live there. On a client the server's share appears under
  `~/share/<server-hostname>/` (for example `~/share/net1/`).
- No terminal. The file manager (pcmanfm) can make a folder or an empty file.
  It cannot make links and there is no plain-text editor besides Code Studio.
- The file manager hides dot names.
- The server can be off. Clients must keep working.
- SQLite and file locks stay off the share.

## Rules

- R1. Shared files hold no absolute paths. Each machine stores its own
  absolute path to the shared folder in its own local state.
- R2. Set up from inside Code Studio. No hand-made files, links or env vars.
- R3. Opt in once per shop, confirm once per machine.
- R4. Several writers, no lost changes: save writes only what changed; lists
  merge; no machine deletes another machine's entries.
- R5. Server down is normal: keep working on the last synced copy, say so in
  the status bar, sync when the share returns. Never switch silently. No modal.
- R6. Where settings are saved is visible in Settings.

## Terms

- **Local state**: `/home/default/FreeCAD/CBCS/state` (`resolve_global_state_root()`).
  Unchanged. Logs, history, caches, SQLite always stay here.
- **Share roots** of this machine, in order: `~/share`, then each visible
  (non-dot) directory directly under `~/share`, sorted by name. When `HOME` is
  not `/home/default`, also `/home/default/share` and its children after the
  `~/share` ones (dedupe by logical path).
- **Shop folder**: `<share root>/Code Studio Settings/`. Visible name. It holds:
  - `shop.json` — marker: `{"schema_version": 1, "created_by_host": "<hostname>", "created_at": "<ISO-8601 UTC>"}`
  - `settings.json` — same schema as today's global settings.
  - `shop_recent_projects.json` — v2 recents (below). A new name so older
    Code Studio versions never read or prune it.
  - `python_console_history.json` — same schema as today.
- **Choice file** (local): `<local state>/shop_sharing.json`
  `{"schema_version": 1, "mode": "shop" | "local", "folder": "<absolute path on this machine>" | null, "declined_folder": "<abs>" | null, "decided_at": "<ISO>", "source": "settings" | "prompt" | "converted"}`.
  Absent means undecided.
- **Mirror** (local): `<local state>/shop_mirror/` holds the last synced copy of
  the three shared files plus `pending.json` (changes made while offline) and
  `sync.json` `{"folder": "<abs>", "last_synced_at": "<ISO>"}`.
- **Shop label**: the share-root child name when the shop folder sits under
  `~/share/<child>/` (for example `net1`), otherwise this machine's hostname
  (`socket.gethostname()`), because the folder is on this machine's own share.

## Resolution at startup (replaces today's settings-root choice)

In this order, first match wins:

1. Explicit `state_root` argument (tests). Unchanged: everything under it, no sharing.
2. `CBCS_STATE_ROOT` env var. Unchanged behaviour (advanced/dev). Keeps today's
   startup problem when it cannot be written.
3. Choice file `mode: "shop"` with a `folder` → shop mode on that folder.
4. Choice file `mode: "local"` → local mode.
5. No choice file → **legacy conversion, one release only** (remove in v0.4.16):
   - v0.4.13 pointer files (same candidates as today: `/home/default/share/Chore_Boy/CBCS/cbcs_state_root`,
     `~/share/Chore_Boy/CBCS/cbcs_state_root`, `~/share/<child>/Chore_Boy/CBCS/cbcs_state_root`).
     A line may now be relative; resolve it against the pointer file's folder.
     Use the first line whose folder exists on this machine (not the first
     absolute line).
   - The legacy `~/choreboy_code_studio_state` link into `~/share` (as today).
   - On a hit, write the choice file `mode: "shop"`, `folder: <that folder>`,
     `source: "converted"`, and use it. Do not move or rename the folder. If
     the folder has no `shop.json`, write one. Shared recents start from that
     folder's old `recent_projects.json` converted to v2 when
     `shop_recent_projects.json` is absent.
6. Otherwise local mode, and undecided (the UI may prompt; see below).

Never resolve the final symlink hop of the shop folder (keep the logical
path; use `os.path.abspath`, not `Path.resolve()`), so Clair's links keep
working.

## Shop mode: reading and writing

Reachable means: the shop folder exists and is a directory and `shop.json`
can be read. Check it at startup, before every shared write, and when the
main window becomes active, at most once every 10 seconds. Never create the
shop folder's parents. Only "turn on sharing" creates the shop folder itself,
and only when its parent exists.

- Read: when reachable, read the shared file and refresh the mirror copy.
  When not reachable, read the mirror copy.
- Write settings (`settings.json`): **three-way merge**. The session keeps the
  payload it last loaded (`base`). On save, compute the leaf-level diff between
  `base` and the new payload (set leaves and removed leaves; nested dicts are
  walked, lists are leaves). Re-read the current shared file, apply the diff,
  write atomically (temp file in the same folder, `os.replace`), then set
  `base` to the written result and update the mirror. A key changed only on
  another machine survives. A key changed on both: last writer wins for that key.
- Offline write: apply the diff to the mirror copy and append it to
  `pending.json`. On the next reachable check, apply pending diffs in order to
  the current shared file, write it, clear `pending.json`, reload.
- Python Console history: the session tracks entries it added. On save, read
  the current shared list, append the session's new entries, trim to the
  existing max. Offline: same into the mirror, pushed on reconnect.
- If the share goes away mid-session the session stays in shop mode. Saves go
  to the mirror + pending. Nothing switches to the local files silently.

## Recent projects v2 (`shop_recent_projects.json`)

```json
{"schema_version": 2, "projects": [
  {"share": "Projects/ShopApp"},
  {"host": "net2", "path": "/home/default/LocalApp"}
]}
```

- `share` entries are paths relative to the share root that holds the shop
  folder (the shop folder's parent). On every machine they resolve against
  that machine's share root, so `/home/default/share/Projects/ShopApp` on net1
  and `/home/default/share/net1/Projects/ShopApp` on net2 are the same entry.
- Any other project is a `host` entry with this machine's hostname and its
  absolute path.
- Remember: re-read the current file, put the entry first, dedupe by identity
  (`share` value, or `host`+`path`), keep the existing cap, write atomically.
- Listing on this machine: `share` entries resolve and are openable when they
  exist; `host` entries for this host are openable when they exist; `host`
  entries for other hosts are returned as unavailable with the host name
  ("on net1") and are never opened.
- Pruning: only remove this host's `host` entries whose path is gone, and
  `share` entries whose path is gone **while the share is reachable**. Never
  remove another host's entries. Never prune while offline.
- Local mode keeps today's v1 `recent_projects.json` unchanged.

## Turning sharing on and off

- **Turn on with a folder** (Settings or prompt):
  - If `<folder>/shop.json` exists → **join**: copy this machine's current
    local `settings.json`, `recent_projects.json`, `python_console_history.json`
    to `<local state>/before_shop/` as a backup, then use the shop folder's
    files. Add this machine's local recents into the shop list as `host`/`share`
    entries (merge, no duplicates).
  - Else → **create**: parent must exist (else refuse with a clear message).
    Create the folder, write `shop.json`, copy this machine's current settings,
    recents (converted to v2) and console history into it.
  - Write the choice file, seed the mirror, reload settings and recents in the
    running window without a restart.
- **Turn off**: copy the current shop settings, recents (this host's and
  share entries resolved to absolute paths) and console history into the local
  files, write `mode: "local"`, reload. The shop folder is not touched.

## UI

### Settings › General › "Shop sharing" group (first group on the tab)

- Checkbox: **Share my settings with the other ChoreBoys in this shop**
- Hint (muted, wraps): "Settings, recent projects and Python Console history are
  saved in a folder on the shop share. History, logs and caches stay on each
  computer. Turn this on at the server first."
- **Saved in**: read-only path field + **Change…** button (folder picker that
  starts in `~/share`). Default when nothing is found: `~/share/Code Studio Settings`.
  If discovery found a shop folder, that one.
- **Status** line: `Shared with <label> · synced <relative time>` /
  `Shop share offline · using the copy from <HH:MM>` / `This computer only`.
- Applied when the dialog's Save is pressed. A refusal (parent missing) shows
  the reason inline and leaves the checkbox off. Global tab only (the group is
  hidden on the Project tab).

### One-time prompt on other machines

When undecided (no choice file, no legacy hit) and discovery finds a shop
folder, show a non-modal bar across the top of the main window (not a dialog):

> **This shop shares Code Studio settings.** Set up on <created_by_host>, <date>. Use them on this computer?
> [Use shop settings] [Keep this computer's]

Below it, muted: "Your current settings are kept as a backup. You can change
this later in Settings › General › Shop sharing."

- Use → join (above). Keep → choice file `mode: "local"`,
  `declined_folder: <folder>`; never ask again for that folder.
- The bar closes after either button. It does not block anything.

### Status bar chip

- Shop mode, reachable: `Settings: shop · <label>` (good style).
- Shop mode, offline: `Settings: shop offline · copy from <HH:MM>` (warning style).
  Tooltip names the folder and the last sync time.
- Local mode: no chip.
- Clicking the chip opens Settings on the General tab scrolled to Shop sharing.

### Startup problems

- Shop mode offline: no startup dialog. The chip says it.
- `CBCS_STATE_ROOT` unwritable: today's dialog stays. Its fix text says
  "Check that this folder exists on this computer" instead of "check that the
  shared folder is connected".

### Welcome screen recent projects

Unavailable entries (another host's project) show greyed with "on <host>" and
are not clickable. Others unchanged.

## Out of scope

- Installer checkbox (the one-time prompt covers "ask once per machine").
- Export/Import settings.
- Per-machine exceptions list (font size, layout).

## Tests (risk-first; only these)

1. Three-way settings merge: two writers change different keys → both survive;
   same key → last writer wins; offline write goes to pending and is pushed on
   reconnect.
2. Recents v2: a share project remembered on a server layout is found on a
   client layout; a client launch never removes server-host entries;
   no pruning while offline.
3. Resolution: choice file beats legacy; relative v0.4.13 pointer works from
   both server and client layouts; legacy link converts to a choice file once.
4. Never create missing parents: an unreachable shop folder is not recreated
   by a save.
5. Turn on (create and join) and turn off move data as described.
6. One UI test: toggling the Settings checkbox on and saving writes the choice
   file and the chip appears.
