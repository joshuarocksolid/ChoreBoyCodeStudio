# Launch and runtime

The editor starts on the real desktop, stays up, and reports whether the FreeCAD AppRun runtime is ready. Clicking the startup chip opens Runtime Center.

Owns AT-01, AT-02, smoke M1.

## Sub-features

- `launch-window` shows a maximized `ChoreBoy Code Studio v*` window.
- `launch-ready` writes `Startup: Runtime ready (N/N checks)` on `#shell.startupStatusLabel`.
- `launch-issues` shows `Runtime issues` plus optional `Syntax highlighting off` when a check fails, without crashing.
- `launch-runtime-center` opens Runtime Center from the startup chip.

## How to get to it (user POV)

- Double-click the desktop launcher, or start via `control-cbcs launch --source` / `--install`.
- Read the left status-bar chip.
- Click that chip, or choose **Tools → Runtime Center...**.

## Driving it with control-cbcs

Preconditions:

- Lab host reachable; VM at desktop.
- No other `cbcs-verify-*` session is live.
- `control-cbcs doctor` is the first command after launch.

- **Start isolated instance.** Run `control-cbcs launch --source --repo <checkout>`. Stdout contains `SID=` and `ARTIFACTS=`. Session state becomes `ready`.
- **Doctor.** Run `control-cbcs doctor "$SID"`. Exit 0. Printed `startup:` contains `Runtime ready`. Printed `home:` is the disposable dir.
- **Identity.** Run `control-cbcs ctl "$SID" exec -- "from PySide2.QtWidgets import QApplication; w=QApplication.activeWindow(); print(w.windowTitle() if w else '')"`. Title contains `ChoreBoy Code Studio`.
- **Chip.** Run `control-cbcs read "$SID" shell.startupStatusLabel`. Text matches `Startup: Runtime ready (`…`)`.
- **Runtime Center from chip.** Run `control-cbcs ctl "$SID" click '#shell.startupStatusLabel'`. `#shell.runtimeCenterDialog` exists. Run `control-cbcs shot "$SID" launch-runtime-center`.
- **Close dialog.** Run `control-cbcs ctl "$SID" click '#shell.runtimeCenterDialog.closeButton'`.
- **Proof.** Run `control-cbcs shot "$SID" launch-runtime` and keep `doctor-startup-label.txt`. Both show the ready chip and the app title.

`control-cbcs prove-launch --repo <checkout>` performs launch, doctor, title, chip, and the launch screenshot. You still `stop` afterward.

## Gotchas

- A disposable HOME has no last project, so the center pane is welcome, not an editor. That is success for launch.
- `Syntax highlighting off` can still sit next to `Runtime ready` if tree-sitter failed. Assert the ready phrase, then note the suffix.
- Session `ready` alone is not enough. The chip must contain `Runtime ready`.
- Do not use the human's `/home/default` profile. Doctor fails if HOME does not match `run.json`.
- `#shell.startupStatusLabel` is a `_ClickableLabel`. Bridge `find('#…')` can miss it. Use `control-cbcs read` (scans `allWidgets` by objectName).
- HOME must be on the guest disk (`/home/default/cbcs-verify-<run-id>`). Virtiofs HOME makes SQLite local-history lock and the editor exits.
- Mac cockpit `vendor` is often a Darwin symlink. `control-cbcs` rsyncs lab Linux `vendor_py39` unless the local tree's SOABI is `cpython-39-x86_64-linux-gnu`. Do not hide the symlink; do not bake a Mac vendor path into the product.
