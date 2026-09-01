# Run

The user runs the active file or the project in a separate runner process, sees stdout/stderr in Run Log, can stop a long script, and can pass arguments via ad-hoc or named configurations.

Owns AT-10–16, AT-29, AT-75, AT-RUN-ARGS-AD-HOC, AT-RUN-ARGS-PERSIST, AT-RUN-ARGS-QUOTING, AT-RUN-ARGS-THEME.

<!-- dune-owners: platform.run -->

## Sub-features

- `run-file` starts the focused buffer (F5 / `#shell.toolbar.btn.run`).
- `run-project` starts the project entry (Shift+F5 / `#shell.toolbar.btn.runProject`).
- `run-output` shows stdout, stderr, and traceback in `#shell.bottom.runLog`.
- `run-log-disk` writes `<project>/cbcs/logs/run_*.log` and a run manifest.
- `run-stop` terminates a long-running script (Shift+F2 / `#shell.toolbar.btn.stop`).
- `run-survive` keeps the editor up when user code fails.
- `run-args-adhoc` runs once from **Run With Arguments...** without persisting.
- `run-args-named` round-trips configurations through `cbcs/project.json`.

## How to get to it (user POV)

- **Run → Run Active File / Run Project / Run With Arguments... / Run Configurations... / Stop / Restart**.
- Toolbar run / run-project / stop.
- Status-bar `#shell.statusBar.activeRunConfig` popup.
- Tree context **Run** / **Run With Arguments…** on a `.py`.

## Driving it with control-cbcs

Preconditions:

- Project with a short `main.py` that prints a unique token, plus a failing script and a sleep script if you prove stop.
- Doctor passed. Background runner must be allowed (do not set `CBCS_DISABLE_BACKGROUND_RUNTIME` for this feature).

- **Run file.** Open a short print script, not a Qt CRUD `main.py`. `control-cbcs ctl "$SID" click '#shell.toolbar.btn.run'`. Or `arm` **Run With Arguments** and pick that entry (`#shell.runWithArgumentsDialog.entry`). `#shell.runStatusLabel` becomes `Run: running` then `Run: success (code=0)`. Token text is in `#shell.bottom.runLog.textArea`. Shot `run-success`.
- **Disk log.** Guest `<project>/cbcs/logs/` has a new `run_*.log` containing the same token. Copy it to artifacts.
- **Failure.** Run a script that raises. Run Log shows a traceback. Editor window still accepts clicks. Status `failed`.
- **Stop.** Run a `time.sleep` loop. `control-cbcs ctl "$SID" click '#shell.toolbar.btn.stop'`. Status becomes `terminated`. Process is gone.
- **Ad-hoc args.** `control-cbcs arm "$SID" shell.action.run.runWithArgs` (modal). `#shell.runWithArgumentsDialog` opens. Set argv to `"hello world"` (quoted). Click **Run**. `sys.argv` in the log matches. `cbcs/project.json` does **not** gain that argv unless you saved a configuration.
- **Named config.** **Run → Run Configurations...**. Add a named config; close; reopen project (or re-read `cbcs/project.json`). The name is in the file and on `#shell.statusBar.activeRunConfig`.
- **Proof.** Shot of Run Log + status chip, plus the on-disk run log.

## Gotchas

- Chip text is `Run: running` / `Run: success (code=0)` / `Run: failed (code=N)` / `Run: terminated` / `Run: idle`.
- F5 on a dirty buffer writes a temp file and skips save.
- Named configs drive Shift+F5 (Run Project), not F5. Manifests live in `cbcs/runs/run_manifest_*.json`.
- Dirty buffers may prompt to save before run. External-change stale buffers must prompt, not clobber.
- Missing project entry opens a picker and persists the choice.
- Ad-hoc argv must not persist. If `project.json` changed, the recipe failed.
- Four-theme check for the arguments dialog is AT-RUN-ARGS-THEME — cycle themes after the dialog is open.
- Toolbar stop is disabled when nothing is running.
