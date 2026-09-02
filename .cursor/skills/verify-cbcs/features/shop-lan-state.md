# Shop-LAN state

Global settings, logs, history, and plugins live in one visible state root. The product
default is `/home/default/FreeCAD/choreboy_code_studio_state`. Shared shop state is
opt-in via `CBCS_STATE_ROOT` or a `cbcs_state_root` pointer file. An existing
`$HOME/choreboy_code_studio_state` directory keeps that machine on the legacy root.

<!-- dune-owners: shop-lan-state, platform.bootstrap -->

## Sub-features

- `state-default` resolves to `/home/default/FreeCAD/choreboy_code_studio_state` when env, pointer, and legacy home dir are absent.
- `state-legacy` uses `$HOME/choreboy_code_studio_state` when that path already exists as a directory (or a symlink to a directory).
- `state-env` uses `CBCS_STATE_ROOT` when it is non-empty and absolute after expanduser.
- `state-pointer` reads `cbcs_state_root` beside the install parent, then `/home/default/share/Chore_Boy/CBCS/cbcs_state_root` if that file exists.
- `state-symlink` keeps the logical state-root path (no final `.resolve()` hop) so a home→share symlink stays meaningful.
- `shop-install` keeps the product install default at `/home/default/choreboy_code_studio_vX`. Shop recipe: installer **Ask for install folder** → `/home/default/share/Chore_Boy/CBCS/choreboy_code_studio_vX`. Shared settings stay opt-in.

## How to get to it (user POV)

- First launch creates the resolved state root (settings, recents, logs, history).
- Shop machines that want a shared root write a visible `cbcs_state_root` pointer (one absolute path) or set `CBCS_STATE_ROOT`.
- The product installer still offers a folder picker. Choosing the share installs the app there. That does not by itself share settings.

## Driving it with control-cbcs

Preconditions:

- Doctor passed.
- Isolated HOME. `control-cbcs launch` sets `CBCS_STATE_ROOT=$HOME/choreboy_code_studio_state` so a verify session does not write the product default.

- **Resolved root.** `control-cbcs ctl "$SID" exec -- "from app.bootstrap.paths import resolve_global_state_root; print(resolve_global_state_root())"`. With the launch env, the print is the disposable `$HOME/choreboy_code_studio_state`.
- **Opt-in pointer stays off.** Do not create `/home/default/share/Chore_Boy/CBCS/cbcs_state_root` on the human share unless this run is proving the pointer. If you create a pointer, delete it before `stop`.
- **Proof.** Save the printed path. This recipe proves path identity, not a Qt widget. Do not claim live UI verified from it.

## Gotchas

- Shared settings are opt-in. Two writers on one NFS state directory can clobber `settings.json` and sibling files.
- Installing onto the share does not automatically share state.
- State never lives inside `choreboy_code_studio_vX`. The pointer filename is `cbcs_state_root` (visible, not hidden).
- Compare state-root identity without following the final symlink hop. Clair's home→share symlink must remain the logical path.
