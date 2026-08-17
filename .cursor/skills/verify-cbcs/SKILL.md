---
name: verify-cbcs
description: Drive the live ChoreBoy Code Studio Qt desktop editor on the ChoreBoy VM via cbapp. Use when you must prove a user-visible change the way a person would — launch, click, type, screenshot — not when offscreen automated checks are enough.
---

# Verify ChoreBoy Code Studio

ChoreBoy Code Studio is a PySide2 desktop IDE that runs inside confined FreeCAD AppRun. There is no browser, no CDP port, and no DOM. The user touches the Qt window. This skill is the recipe for launching an isolated instance on the ChoreBoy VM, driving it with `#shell.*` handles, and keeping proof artifacts after teardown.

You are on the Mac cockpit. Execution is on the lab VM. Read [references/isolation.md](references/isolation.md) before launch and [references/handles.md](references/handles.md) before picking a selector. Read [features/README.md](features/README.md) and the matching feature file before driving a surface.

Do not drive an instance this run did not start. One VM desktop: refusing to double-drive beats corrupting a human session.

## Launch

Helper: [scripts/control-cbcs](scripts/control-cbcs) (executable; invocation below).

Ready means both of these:

1. `cbapp` session state is `ready` or `running`
2. `#shell.startupStatusLabel` contains `Runtime ready`

Window title starts with `ChoreBoy Code Studio v`. First launch with a disposable `HOME` shows the welcome pane (`#shell.welcome`) because there is no last project to restore.

### Source checkout (default)

Rsyncs this repo onto the virtiofs share and starts `run_editor.py` with a disposable guest `HOME`.

```bash
CONTROL=".cursor/skills/verify-cbcs/scripts/control-cbcs"

$CONTROL launch --source --repo /Users/local/Projects/ChoreBoyCodeStudio
# prints SID=...  RUN_ID=...  ARTIFACTS=...
```

Guest layout (created by the helper):

| Role | Guest path |
|------|------------|
| Checkout | `/mnt/cbprobe/cbcs-verify/<run-id>/src` |
| Disposable HOME | `/home/default/cbcs-verify-<run-id>` (guest disk; not virtiofs) |

`HOME` is never `/home/default`. That is the human's state.

### Product installer

Build the zip with `python3 package.py`, then:

```bash
$CONTROL launch --install --zip /path/to/choreboy_code_studio_installer_v<ver>.zip
```

The installer wizard has no `shell.*` names. Click visible Next / Install:

- `#__qt__passive_wizardbutton1` (Next)
- `#qt_wizard_commit` (Install / finish)

Do not `invoke` wizard `next`. Password for the product zip is `rsd`.

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

- `ssh debian true`
- `cb-virsh status` contains `running`
- session state `ready` or `running`
- no other `cbcs-verify-*` session is live
- `#shell.startupStatusLabel` contains `Runtime ready`
- process `HOME` equals the disposable dir from `run.json`

Exit non-zero → do not drive. Fix the instance (or relaunch) first.

If the window looks wedged but doctor still passes, relaunch. Do not keep clicking a stuck UI.

## Drive

All actions go through `control-cbcs` → `cbapp ctl`. Prefer handles in this order:

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
- Delete only the disposable guest tree under `/mnt/cbprobe/cbcs-verify/<run-id>/`.
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

Topology, VM start, and generic `cbapp` ops live in the user skill `run-choreboy-app`. This helper only adds CBCS isolation, `#shell.*` conveniences, and the artifact contract.

## Out of product

These are not features. Do not invent recipes for them:

- Git UI
- Close Project menu
- File → Zip Project / Export to USB (use Package Project)
- Bottom Tasks tab
- Relocatable install
- Internet plugin marketplace
