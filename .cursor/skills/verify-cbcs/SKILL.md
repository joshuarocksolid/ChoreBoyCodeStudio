---
name: verify-cbcs
description: Drive the live ChoreBoy Code Studio Qt editor on a cbfarm lease. Use when you must prove a user-visible change the way a person would (launch, click, type, screenshot). The Debian lab is only the fallback this skill names.
---

# Verify ChoreBoy Code Studio

ChoreBoy Code Studio is a Qt desktop IDE that runs inside confined FreeCAD AppRun. There is no browser and no DOM. The user touches the Qt window. This skill launches an isolated instance, drives it with `#shell.*` handles, and keeps proof after teardown.

The farm is the default. `control-cbcs` uses the lease in `CBFARM_ENV` on machine `net1`. Pass `--backend lab` or set `CBCS_VERIFY_BACKEND=lab` only for the cases under Lab fallback.

## Reach the farm

Use the cbfarm MCP tools (`mcp__cbfarm__lease`, `mcp__cbfarm__do`, `mcp__cbfarm__push`, `mcp__cbfarm__pull`, `mcp__cbfarm__screenshot`, and the rest of that server) when the session has them.

When it does not, call the harness from the project directory. Define a function. zsh does not word-split a variable.

```bash
C() { /Users/local/Projects/cb_probes-wt/main/harness/cbfarm-mcp-call --host aws-1 --save-dir ./shots "$@"; }
```

`control-cbcs` calls that script itself. `CBFARM_MCP_CALL` overrides the path. The default is `/Users/local/Projects/cb_probes-wt/main/harness/cbfarm-mcp-call`. The host is `CBFARM_HOST` or `aws-1`.

`launch` reuses `CBFARM_ENV` when it is set. It leases a solo env only when that variable is empty, and `stop` releases only a lease this command created. Do not retry a failed lease in a loop. Do not touch an env this run did not lease. Do not drive a window on the Mac.

Read [references/isolation.md](references/isolation.md) before launch and [references/handles.md](references/handles.md) before picking a selector. Read [features/README.md](features/README.md) and the matching feature file before driving a surface.

Do not drive an instance this run did not start. One desktop per lease. Refusing to double-drive keeps a human session intact.

## Launch

Helper: [scripts/control-cbcs](scripts/control-cbcs).

Ready means both of these:

1. Session state is `ready` or `running`
2. `#shell.startupStatusLabel` contains `Runtime ready`

Window title starts with `ChoreBoy Code Studio v`. First launch with a disposable `HOME` shows the welcome pane (`#shell.welcome`) because there is no last project to restore.

### Source checkout (default)

Pushes this repo onto the guest share and starts `run_editor.py` with a disposable guest `HOME`.

```bash
CONTROL=".cursor/skills/verify-cbcs/scripts/control-cbcs"

$CONTROL launch --source --repo "$PWD"
# prints SID=...  RUN_ID=...  ARTIFACTS=...
```

Guest layout:

| Role | Guest path |
|------|------------|
| Checkout | `/mnt/cbprobe/incoming/cbcs-verify-<run-id>/<repo-dir>` |
| Disposable HOME | `/home/default/cbcs-verify-<run-id>` on the guest disk |

`HOME` must not be `/home/default`. That directory is the human's state. A `vendor` symlink is not pushed, so syntax highlighting can be off until you push a real Linux `vendor_py39` tree.

Lab backend still rsyncs to `/mnt/cbprobe/cbcs-verify/<run-id>/src` through `ssh debian`.

### Product installer

Build the zip with `python3 package.py`, then:

```bash
$CONTROL launch --install --zip /path/to/choreboy_code_studio_installer_v<ver>.zip
```

`launch --install` pushes the zip and runs `install-test`, which auto-walks the product installer wizard (`01_welcome` … `05_done`) and exits when that lane finishes. Explicit `#__qt__passive_wizardbutton1` (Next) / `#qt_wizard_commit` (Install) clicks are not reachable in that helper path. Drive those handles only when you launch the installer by hand outside `install-test`. The installer wizard has no `shell.*` names. Do not `invoke` wizard `next`. Password for the product zip is `rsd`. On the farm the zip argument is `@share:incoming/...`. A host path is the lab backend.

### Teardown

```bash
$CONTROL stop "$SID"
```

Stops only that session and deletes the disposable guest tree. Proof under `~/ChoreBoy/artifacts/verify-cbcs/<run-id>/` stays.

## Doctor

Run this first, and again after any failed drive, before touching the UI.

```bash
$CONTROL doctor "$SID"
```

Checks, all required:

- session state `ready` or `running`
- no other `cbcs-verify-*` session is live
- `#shell.startupStatusLabel` contains `Runtime ready`
- process `HOME` equals the disposable dir from `run.json`

On `--backend lab`, doctor also requires `ssh debian true` and `cb-virsh status` of `running`.

Exit non-zero → do not drive. Fix the instance (or relaunch) first.

If the window looks wedged but doctor still passes, relaunch. Do not keep clicking a stuck UI.

## Drive

All actions go through `control-cbcs`. On the farm that is `do verb=ctl`. On the lab it is `cbapp ctl`. Prefer handles in this order:

1. `#shell.*` objectName
2. `text:Visible Label`
3. `class:QPushButton[n]`

Selectors and action ids: [references/handles.md](references/handles.md). Feature recipes: [features/](features/).

```bash
$CONTROL ctl "$SID" click '#shell.welcome.openProjectBtn'
$CONTROL ctl "$SID" type '#shell.findBar.findInput' "def "
$CONTROL ctl "$SID" key Return
$CONTROL trigger "$SID" shell.action.view.theme.dark
$CONTROL arm "$SID" shell.action.help.runtimeOnboarding
$CONTROL read "$SID" shell.startupStatusLabel
$CONTROL wait "$SID" shell.testExplorer.tree --min-rows 1 --timeout 45
$CONTROL ctl "$SID" tree --max-depth 6
$CONTROL ctl "$SID" exec -- "find('#shell.runStatusLabel').text()"
```

`ctl exec` runs Python inside the live app (the Qt bridge). Use it to read widget text or trigger a `shell.action.*` when a click path is missing. Prefer `trigger` / `read` / `click` over raw exec.

Actions that open a modal dialog must use `arm`, not `trigger`. `trigger` runs `QAction.trigger()` inside the bridge call; `QDialog.exec_()` then blocks that call until the dialog closes, so later commands time out. `arm` fires the action on the next event-loop tick.

Use `arm` for anything that `exec_()`s, including: Settings, Recovery Center, Package Project, Open Project, New Project from Template, Load Example Project, Runtime Center / onboarding, format, organize imports, Apply Safe Fixes, and renameSymbol. Lint Current File is fine with `trigger`. Plugin Manager and Dependency Inspector use `show()` — `trigger` is correct for those.

The same block happens if you click `#shell.startupStatusLabel` (Runtime Center) or `trigger` format / organize imports / Safe Fixes / renameSymbol. Those OK / input boxes also use `exec_()`. If the bridge is already blocked, recover with one allow-listed key. On the farm that is `do verb=key` with `Escape` or `Return` (it does not use the guest runner). On the lab, `cb-virsh send-key` uses `KEY_ENTER` or `KEY_ESC`. `KEY_RETURN` is invalid there. `oskey` queues behind the blocked bridge.

Close a dialog you opened with `arm` by `reject()` via `ctl exec`, not by clicking Close while the opener is still in `exec_()`.

Flat-Python paste only hints after a real Qt paste. Use `insertFromMimeData` via `ctl exec`. Bridge `type` will not show `#PasteHintOverlay`.

One structural action, then re-observe (shot or read). Do not queue a script of clicks and only look at the last frame.

Qt-native `click` / `type` first. Use `--mouse` / `oskey` only for desktop chrome the bridge cannot see.

## Evidence

Root: `~/ChoreBoy/artifacts/verify-cbcs/<run-id>/`. Cleanup never deletes this.

Every proof needs the action and the resulting state, not only the final screen.

Required pair for a UI claim:

- `$CONTROL shot "$SID" <feature>-after`
- a `tree` dump or `$CONTROL read` / `ctl exec` of the proving widget

Mutation proofs also read disk from the guest (project `cbcs/`, file contents, `settings.json`, run logs, `run_manifest_*.json`). A status-bar flash alone is not enough.

Four-theme surfaces (Light, Dark, High Contrast Light, High Contrast Dark) need one shot per theme with the app identity visible.

Offscreen automated checks passing is not proof of the live editor.

Record the feature file id and the entry point you used next to the artifacts.

If a path is unreachable, write the command you ran and the unmet precondition. Do not claim a different entry point verified it.

## Cleanup

```bash
$CONTROL stop "$SID"
ls "$ARTIFACTS"    # must still exist
```

- Kill the session id this run created. Never `pkill` by process name.
- Delete only the disposable guest tree for this run (`/mnt/cbprobe/incoming/cbcs-verify-<run-id>/` on the farm, `/mnt/cbprobe/cbcs-verify/<run-id>/` on the lab).
- Leave `~/ChoreBoy/artifacts/verify-cbcs/<run-id>/` intact. Confirm it after stop.
- Failed iterations still get `stop`. Do not leave a live session on the shared desktop.

## Helpers

`scripts/control-cbcs` is executable. From the repo root:

```bash
CONTROL=".cursor/skills/verify-cbcs/scripts/control-cbcs"

$CONTROL launch --source --repo "$PWD"
$CONTROL doctor "$SID"
$CONTROL ctl "$SID" click '#shell.activityBar.btn.explorer'
$CONTROL trigger "$SID" shell.action.view.theme.dark
$CONTROL arm "$SID" shell.action.help.runtimeOnboarding
$CONTROL read "$SID" shell.startupStatusLabel
$CONTROL wait "$SID" shell.testExplorer.tree --min-rows 1 --timeout 45
$CONTROL shot "$SID" after-theme
$CONTROL stop "$SID"
```

`prove-launch` is the launch-runtime recipe in one shot (still leaves artifacts; you must `stop`):

```bash
$CONTROL prove-launch --repo "$PWD"
# then: $CONTROL stop "$SID"
```

Linux-guest pytest (not Mac Darwin AppRun). Refuse a live `cbcs-verify-*` session first. Runs `pytest.main` in-process under guest AppRun — do not treat a Mac `run_test_shard.py` result as product proof:

```bash
$CONTROL shard all --repo "$PWD"
```

Lease, push, `do`, screenshots, reset, and release are the user skill `run-choreboy-app`. This helper adds CBCS isolation, `#shell.*` conveniences, and the artifact contract.

## Lab fallback

Use `--backend lab` or `CBCS_VERIFY_BACKEND=lab` only for the two cases below. Everything else stays on the farm. Never `ChoreBoy5`. Never `cb-slot` with `--cb-slot any`. Never a visible window on the Mac.

**FreeCAD 1.1 / PySide6.** The farm golden image is the PySide2 ChoreBoy. `ChoreBoyExp` is the lab slot for that image. Pin it with the scenario runner's `--want ChoreBoyExp`. Do not pick it for ordinary PySide2 proof.

**Scenario runner.** `scripts/verify-cbcs` stays on the lab. The farm can lease, checkpoint, `install-test`, and the bridge ops `grab`, `state`, `drag`, `dblclick`, and `hover` (`CTL_OPS` in the farm rules). The runner still cannot move, for three host reasons:

1. Every disk probe goes through `cbprobe submit`, which copies a host directory. Farm MCP refuses that verb. `do sh` cannot run while a GUI session holds the one guest runner, and the scenarios interleave probes with a live editor.
2. Disk restore is `cb-slot checkpoint` / `cb-slot revert`. The proof file wants revert text containing `ready=runner` and a post-revert marker read. Farm `checkpoint` plus `reset` restores a disk and reboots the guest. It does not speak that contract, and this runner also releases the slot it leased.
3. `cbapp desktop-shot` is refused through MCP, and cb3 sends Ctrl+Space with `cb-virsh send-key`. Farm `key` is one allow-listed name, not that chord.

## Scenario library (lab only)

One command replays the v0.4.13 FreeCAD 1.0 acceptance on a leased lab slot. The runner is `scripts/verify-cbcs` (Mac Python 3). It leases a free slot, checkpoints the guest disk, installs the zip once, runs each scenario, reverts, and releases. Revert and release also run on failure and on Ctrl-C. `--want ChoreBoy5` is refused. The free-slot list is `ChoreBoy4`, then `ChoreBoy3`.

```bash
scripts/verify-cbcs list
scripts/verify-cbcs run smoke --zip /path/to/choreboy_code_studio_installer_v0.4.13.zip
scripts/verify-cbcs run all --zip /path/to/choreboy_code_studio_installer_v0.4.13.zip
scripts/verify-cbcs run cb3 cb5 --zip ZIP --keep-going
scripts/verify-cbcs run smoke --want ChoreBoyExp --zip ZIP
scripts/verify-cbcs run all --zip ZIP --harness /home/joshua/some/other/probes-checkout
```

`all` is the FreeCAD 1.0 set and keeps going after a failed scenario. A named list stops at the first failure unless `--keep-going` is set. `--want` pins a free slot. The runner refuses a slot it did not lease.

`--harness DIR` is the remote cb_probes checkout. When the flag is omitted, the runner uses the shared probes tree `/home/joshua/Documents/ChoreBoyCodeStudio_Projects/probes`, which carries the bridge ops and `cb-slot checkpoint` / `revert` since cb_probes#5. Every `cb-slot`, `cbapp`, and `cbprobe` call exports `CHOREBOY_REMOTE_PROBES` to that directory and `CHOREBOY_REMOTE_SHARE` to the lease's `CB_SHARE`, so `SHOT:` files are pulled. `summary.json` records `harness`, `remote_share`, and the detected caps.

Before install, the runner calls `cb-slot checkpoint`. On the way out, including after a failed scenario and on Ctrl-C, it calls `cb-slot revert`. Revert destroys only the leased domain, points the disk back at the slot volume, deletes the overlay, and waits until the guest runner heartbeats. A marker file written in the guest home after the checkpoint must be absent after revert. That proof is `restore-proof.json` with `"method": "snapshot"`. The tar of guest home paths is used only when `cb-slot checkpoint --help` says the subcommand is missing. `--no-snapshot` skips both.

| id | what it checks |
| --- | --- |
| smoke | Launch, settled `9/9` chip on FreeCAD 1.0, main-window crop, state dump, Qt binding. Exp smoke waits for `Runtime ready` and records the binding. |
| gates | Fresh install, 9/9 chip, Runtime Center, Python keyword `#0000ff` |
| cb1 | Settings import, history `OSError`, fatal `MainWindow` `RuntimeError` |
| cb2 | Plugin host `PermissionError`, same error on Run |
| cb3 | Manual completion, Ctrl+Space, camelCase, tab, docs, off, console |
| cb3-latency | Median popup `to_paint_ms` under 150 |
| cb4 | Stepped drag, rename, cut/paste, missing file |
| reload | Clean reload, keep buffer, stale save, dirty keep |
| cb5 | Tab drag, split, close group, restore after restart |
| cb6 | Five packaging reports |
| cb7 | Run opens FreeCAD, log noise format, Keep and Stop |
| cb8 | Example install, replace, uninstall, forced failure, idesk launcher |
| cb9 | Shop settings pointer, JSON-only share, missing parent |
| cb10 | Macro/Apps migration |
| ts | Tree-sitter colors. SQL stays plain |

Each scenario writes `~/ChoreBoy/artifacts/verify-cbcs/<run-id>/<scenario>/results.json`:

```json
{
  "scenario": "gates",
  "status": "pass",
  "started": "2026-10-21T00:00:00+00:00",
  "duration_s": 1.0,
  "checks": [{"name": "runtime-ready", "ok": true, "expected": "Runtime ready", "actual": "Startup: Runtime ready (9/9 checks)"}],
  "metrics": {},
  "screenshots": [{"name": "gates-1-window", "path": "/abs/gates-1-window.png", "kind": "window"}],
  "notes": ""
}
```

`status` is `pass`, `fail`, `error`, or `skipped`. The run writes `<run-id>/summary.json` and `SUMMARY.md`.

Bridge ops `grab`, `state`, `drag`, `dblclick`, and `hover` are used when `cbapp ctl` accepts them. Otherwise crops use `find(selector).grab().save` onto the virtiofs share, state is built in `eval`, and drag is stepped XTEST motion. Disk restore uses `cb-slot checkpoint` / `revert` when those subcommands exist. Otherwise the runner tars the guest home paths the v0.4.13 restore used and checks the listing sha256. Capability is detected once per run and stored in `summary.json`. Scenario code calls the adapter, not `cbapp`, for those ops. A check may set `status` to `skipped` when one observation cannot be made. That sub-check does not skip the rest of the scenario.

To add a scenario, add a module `scripts/scenarios/<id>.py` with `run(ctx)`, register it in `scripts/scenarios/registry.py`, and append the id to `SCENARIO_IDS` in `model.py`. `ctx.check` records a row. `ctx.shot` stores a crop, window, or desktop path. `ctx.wait_json` polls widget state. Raise `scenarios.model.Skip` when the spec cannot be driven. Put guest code in Python 3.9.

Time budget. `smoke` should finish in a few minutes after the install. `all` should finish in under 30 minutes of wall clock, including install, the five-sample latency wait, and the home restore. The latency scenario spends five seconds of idle time before each popup measurement because that is the acceptance protocol, not a poll.

## Out of product

These are not features. Do not invent recipes for them:

- Git UI
- Close Project menu
- File → Zip Project / Export to USB (use Package Project)
- Bottom Tasks tab
- Relocatable install
- Internet plugin marketplace
