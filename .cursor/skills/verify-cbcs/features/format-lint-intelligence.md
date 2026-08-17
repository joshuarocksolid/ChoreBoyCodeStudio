# Format, lint, and intelligence

The user formats with Black, organizes imports with isort, sees Problems / overlays, and gets completion, go-to, and rename from Jedi plus runner introspection.

Owns AT-32, AT-36, AT-45–58, AT-73 (editor completion).

## Sub-features

- `format-file` **Tools → Format Current File** rewrites the buffer with Black 24.10.0.
- `organize-imports` **Tools → Organize Imports** is Black-compatible and non-destructive.
- `format-on-save` optional; Save still succeeds if format fails (AT-55).
- `lint-problems` realtime overlays + `#shell.problemsPanel`; provider Default or Pyflakes.
- `lint-safe-fixes` **Apply Safe Fixes** clears stale squiggles without requiring Save.
- `complete-dot` editor `.` completion shows attributes without running project code (AT-73).
- `rename-preview` F2 shows preview / apply / rollback (AT-49).
- `highlight` tree-sitter colors for supported languages (AT-32).

## How to get to it (user POV)

- **Tools → Format Current File / Organize Imports / Lint Current File / Apply Safe Fixes / Rebuild Intelligence Cache / Refresh Runtime Modules / Analyze Imports / Set Language Mode**.
- Problems bottom tab; status `#shell.diagnosticsStatusLabel`.
- Typing `.` or the completion shortcut in a Python buffer.

## Driving it with control-cbcs

Preconditions:

- Project with a messy `fmt_me.py` (`x=1+2` / unsorted imports) and a file with an unused import or syntax issue.
- Doctor passed. Vendor Black/isort/jedi available on the guest copy, or record degraded tooling on `#shell.pythonToolingStatusLabel`.

- **Format.** Open the messy file. `control-cbcs trigger "$SID" shell.action.tools.formatCurrentFile`. Buffer matches Black. Shot `format-after`.
- **Organize.** `control-cbcs trigger "$SID" shell.action.tools.organizeImportsCurrentFile`. Import block is sorted; no other user comments lost.
- **Lint.** `control-cbcs trigger "$SID" shell.action.tools.lintCurrentFile`. `#shell.problemsPanel.tree` has rows or `#shell.diagnosticsStatusLabel` shows counts. Click a row; editor jumps.
- **Safe fix.** Apply safe fixes; squiggles clear without Save. Re-lint is clean for that rule.
- **Completion.** In a Python buffer type `json.` after `import json`. Popup lists attributes; Enter inserts. Down at the last row does not crash.
- **Rename.** On a local function name, `control-cbcs trigger "$SID" shell.action.edit.renameSymbol`. Preview lists edits; apply updates the buffer; rollback restores.
- **Proof.** Shot of formatted buffer + Problems (or empty Problems after fix), and the saved file on disk if you saved.

## Gotchas

- If `#shell.pythonToolingStatusLabel` says tooling is unavailable, format/organize are verified-unreachable — record the chip text.
- Save must succeed when format fails (AT-55). Break Black on purpose (or disable it) and Save; disk still updates.
- Completion must not execute project `__getattr__` / import side effects (AT-73).
- Language mode override changes highlighting without renaming the file.
