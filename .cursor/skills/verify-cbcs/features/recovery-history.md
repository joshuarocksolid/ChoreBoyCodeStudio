# Recovery and local history

Unsaved buffers are protected across a crash. Recovery Center and Local History let the user diff and restore without silent overwrite. Global History finds files that moved or were deleted.

Owns AT-18, AT-65–71.

## Sub-features

- `history-checkpoint` each Save creates a comparable revision (AT-65).
- `history-restore` Local History restore puts older content in the buffer (AT-67).
- `recovery-center` **File → Open Recovery Center...** lists drafts and saved-history timelines. Buttons are **Review Draft**, **Open Timeline**, and **Restore Latest to Buffer**. **Keep for Next Launch** is `#shell.unsavedChangesDialog` on exit, not this dialog.
- `global-history` **File → Open Global History...** across projects (AT-68).
- `history-multi` multi-file transactions are grouped (AT-69).
- `history-retention` Settings → Files retention / size / excludes (AT-70).
- `history-diff-ui` diffs stay readable (AT-71).

## How to get to it (user POV)

- **File → Open Recovery Center...** / **Open Global History...**.
- Tree or tab context **Local History…**.
- Settings → Files (retention).

## Driving it with control-cbcs

Preconditions:

- Project open; disposable HOME.
- Doctor passed.

- **Checkpoint.** Open `main.py`. Change a unique string; Save. Repeat with a second string. Local History lists at least two revisions.
- **Compare.** Open Local History from the tab. Diff view (`#shell.diffView`) shows before/after. Shot `history-diff`.
- **Restore.** Restore the first revision. The **buffer** contains the first unique string. Disk stays at the later save until you Save again.
- **Recovery Center.** `control-cbcs arm "$SID" shell.action.file.recoveryCenter` (modal). The dialog has no `#shell.recoveryCenterDialog` name. Click `text:Open Timeline` or `text:Restore Latest to Buffer`. History files live under `$HOME/choreboy_code_studio_state/history/`, not `.../state`.
- **Proof.** Shot of the diff + the restored buffer, and a copied history blob or index listing in artifacts.

## Gotchas

- Proving crash recovery needs a killed session and a relaunch with the **same** HOME. `control-cbcs stop` deletes that HOME. For this feature, copy the disposable HOME aside, or delay the share `rm` and relaunch with `--env HOME=` pointing at the kept dir (extend the helper only if required).
- Retention excludes can hide the file you just saved. Check Settings → Files before claiming missing history.
- Diff UI must stay readable in Light and Dark.
