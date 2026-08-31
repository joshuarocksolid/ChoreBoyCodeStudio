# Debug

The user sets breakpoints, starts a debug session, steps, inspects frames and watches, and can debug a current or failed test.

Owns AT-30, AT-31, AT-59, AT-60, AT-61, AT-62, AT-63, AT-64.

## Sub-features

- `debug-breakpoint` toggles a breakpoint (F9 / gutter).
- `debug-start` starts Debug Active File or Debug Project.
- `debug-step` Continue / Pause / Step Over / Into / Out from the toolbar.
- `debug-inspect` shows threads, frames, scopes, and watches in `#shell.debug.panel`. Locals are `#shell.debug.variablesTree`.
- `debug-conditional` supports condition and hit-count breakpoints.
- `debug-exceptions` honors exception-stop settings.
- `debug-tests` debugs the current or last failed test (AT-62).
- `debug-dirty-remap` maps dirty-buffer lines to the running session (AT-63).

## How to get to it (user POV)

- **Run → Debug Active File** (Ctrl+F5) / **Debug Project** / step commands / **Toggle Breakpoint** / **Exception Stop Settings...**.
- Toolbar debug and step buttons.
- Bottom **Debug** tab.
- Test Explorer context **Debug**.

## Driving it with control-cbcs

Preconditions:

- Project with a `.py` that hits a known line (e.g. a function you will break on).
- Doctor passed. Runner/debug transport available on the guest.

- **Breakpoint.** Open the file; place the cursor on the target line; `control-cbcs trigger "$SID" shell.action.run.toggleBreakpoint`. Gutter / `#shell.debug.breakpointsTree` shows the break.
- **Start.** `control-cbcs ctl "$SID" click '#shell.toolbar.btn.debug'`. The first stop can be runner bootstrap (`Paused at runner_main.py:…`). Click `#shell.toolbar.btn.continue` to reach the user breakpoint. Start focuses **Run Log** (`auto_open_console_on_run_output`), not Debug. Click `text:Debug` or set `#shell.bottomRegion.tabs` to index 1 before a panel shot. Shot `debug-paused`.
- **Inspect.** `#shell.debug.stackTree` has a frame. `#shell.debug.variablesTree` is populated. Add a watch via `#shell.debug.watchInput` + Return. Watch row shows a value or an explicit error.
- **Step.** `control-cbcs ctl "$SID" click '#shell.toolbar.btn.stepOver'`. Current line advances. Continue with `#shell.toolbar.btn.continue`.
- **Stop.** `#shell.toolbar.btn.stop` ends the session. Editor remains usable.
- **Proof.** Shot of the paused debug panel (stack + breakpoint) and the startup/run chips still healthy.

## Gotchas

- Debug needs the real runner. If the session never pauses, capture stderr / debug transport notes — do not fake a pause via internal setters.
- Conditional breakpoints that never hit look like a failed start. Read the breakpoint tree.
- Theme safety (AT-64): panel must stay readable in Light and Dark at minimum; four themes preferred.
- `removeAllBp` clears breaks. Do not leave them if a later recipe assumes a clean file.
- AT-62 is **Debug Current Test** and **Rerun Last Debug Target**, not the Test Explorer **Debug Failed** button (that is AT-99).
- `toggleBreakpoint` with no current editor file shows **Open a Python file first.** and blocks the bridge if you used `trigger`. Restore `#shell.editorStatusLabel` first.
