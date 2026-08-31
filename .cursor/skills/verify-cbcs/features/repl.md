# Python console

The bottom Python Console is a live REPL in a child process. History survives restart. Dropping a `.py` onto the console executes it. Dot completion reads the live namespace.

Owns AT-26 and console completion (AT-74 console).

## Sub-features

- `repl-exec` executes a typed expression and prints the result.
- `repl-history` recalls prior lines with Up/Down after restart (Ctrl+\`).
- `repl-drop-exec` runs a dropped local `.py` in the console namespace.
- `repl-complete` offers dot completion from the live runner.
- `repl-clear` **Run → Clear Console** clears console + run log + debug output (display-only clear is the pane button).

## How to get to it (user POV)

- Bottom tab **Python Console** (`#shell.bottom.pythonConsole`).
- **Run → Restart Python Console (REPL)** (Ctrl+\`).
- **Run → Clear Console**.
- Drop a `.py` onto the console widget.

## Driving it with control-cbcs

Preconditions:

- Doctor passed.
- Runner/REPL child allowed to start (do not disable background runtime).

- **Focus console.** Set `#shell.bottomRegion.tabs` current index to 0 (**Python Console**). `text:Python Console` can miss. Then click `#shell.bottom.pythonConsole`.
- **Expression.** Click `#shell.bottom.pythonConsole`. `control-cbcs keypress "$SID" shell.bottom.pythonConsole 'print("cbcs-repl-token")' --return`. Bridge `type` inserts text and skips `keyPressEvent`, so Return then submits empty. The token must appear on its own output line. Shot `repl-print`.
- **Restart.** `control-cbcs trigger "$SID" shell.action.run.pythonConsole`. Console reconnects. Up recalls the previous line (history file under disposable HOME).
- **Drop execute.** Drop `example.py` onto `#shell.bottom.pythonConsole` (or document verified-unreachable if the bridge cannot synthesize a drop). Console shows the script's prints.
- **Completion.** Type `sys.` after `import sys`. A completion popup appears with attribute detail. Do not execute project code to populate it.
- **Proof.** Shot of the printed token. History JSON is written only on window close (`$HOME/choreboy_code_studio_state/python_console_history.json`). Copy it after close, not after the first print.

## Gotchas

- Drop on the **main window** opens a tab; drop on the **console** executes. Do not mix the proofs.
- The small clear button on the console is display-only. **Run → Clear Console** also clears Run Log.
- Ctrl+R opens a Console History picker. That is a product feature.
- First keystroke after launch may wait for the REPL child. If nothing prints, doctor the session and read guest REPL logs under `$HOME/choreboy_code_studio_state/repl/`.
