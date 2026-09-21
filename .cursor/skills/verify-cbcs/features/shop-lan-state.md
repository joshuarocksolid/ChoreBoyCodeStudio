# Shop-LAN state

Global settings, logs, history, and plugins live in `/home/default/FreeCAD/CBCS/state`.
Shared shop state is opt-in via `CBCS_STATE_ROOT` or
`/home/default/share/Chore_Boy/CBCS/cbcs_state_root`. Leftover
`choreboy_code_studio_state` trees from earlier releases are copied into dest on first
launch of the update. Occupancy is dest `settings.json`.

<!-- dune-owners: shop-lan-state, platform.bootstrap -->

## Sub-features

- `state-default` is `/home/default/FreeCAD/CBCS/state` when env and shop pointer are absent.
- `state-env` uses `CBCS_STATE_ROOT` when it is non-empty and absolute after expanduser.
- `state-pointer` reads `/home/default/share/Chore_Boy/CBCS/cbcs_state_root` if that file exists.
- `state-symlink` keeps the logical state-root path (no final `.resolve()` hop) so a home→share symlink stays meaningful.
- `state-migrate` copies the first leftover that is not dest (`$HOME/choreboy_code_studio_state`, then XDG, then cache, then `$HOME/FreeCAD/choreboy_code_studio_state`) into dest through `state.migrating` when dest has no `settings.json`. Sources stay.
- `shop-install` keeps the product install default at `/home/default/FreeCAD/CBCS/choreboy_code_studio_vX`. Shop recipe: installer **Ask for install folder** → `/home/default/share/Chore_Boy/CBCS/choreboy_code_studio_vX`. Shared settings stay opt-in.

## How to get to it (user POV)

- First launch creates `/home/default/FreeCAD/CBCS/state` (settings, recents, logs, history), or copies a leftover tree into it.
- Shop machines that want a shared root write a visible `cbcs_state_root` pointer (one absolute path) or set `CBCS_STATE_ROOT`.
- The product installer still offers a folder picker. Choosing the share installs the app there. That does not by itself share settings.

## Driving it with control-cbcs

Preconditions:

- Doctor passed.
- Isolated HOME. `control-cbcs launch` sets `CBCS_STATE_ROOT=$HOME/choreboy_code_studio_state` so a verify session does not write the product dest.

- **Resolved root.** `control-cbcs ctl "$SID" exec -- "from app.bootstrap.paths import resolve_global_state_root; print(resolve_global_state_root())"`. With the launch env, the print is the disposable `$HOME/choreboy_code_studio_state`.
- **Product dest (no env, no pointer).** Disposable HOME may still hold `choreboy_code_studio_state` from launch isolation. That leftover must not change resolve:

```bash
$CONTROL ctl "$SID" exec -- "import os
from app.bootstrap import paths
from app.core import constants
saved = os.environ.pop('CBCS_STATE_ROOT')
try:
    root = paths.resolve_global_state_root()
finally:
    os.environ['CBCS_STATE_ROOT'] = saved
print(root)
print(root == constants.PRODUCT_STATE_ROOT)"
```

  The second line is `True`. The first line is `/home/default/FreeCAD/CBCS/state`.
- **Env wins.** Without popping, `print(paths.resolve_global_state_root())` prints exactly the launch `CBCS_STATE_ROOT`.
- **Pointer wins.** Write one absolute path (a directory inside the disposable HOME) into `/home/default/share/Chore_Boy/CBCS/cbcs_state_root`. The pop-and-resolve exec prints that path. Delete the pointer before `stop`.
- **Symlink logical path.** `ln -s $HOME/real_state $HOME/link_state` (create `real_state` first). `print(paths.resolve_global_state_root('$HOME/link_state'))` prints the `link_state` path, not `real_state`.
- **First launch on the real dest.** Using `/home/default/FreeCAD/CBCS/state`:

```bash
$CONTROL ctl "$SID" exec -- "import os
from app.bootstrap import paths
saved = os.environ.pop('CBCS_STATE_ROOT')
try:
    root = paths.resolve_global_state_root()
finally:
    os.environ['CBCS_STATE_ROOT'] = saved
existed = root.exists()
paths.ensure_directory(root)
marker = root / 'cbcs_first_launch_probe.txt'
marker.write_text('ok', encoding='utf-8')
print(root, existed, marker.read_text(encoding='utf-8'))
marker.unlink()
if not existed:
    root.rmdir()"
```

  The print ends in `ok`. If `existed` was `False` the leaf is removed again so the human machine keeps no empty state tree from verify. If it was `True`, leave it (it is the machine's real state).
- **Opt-in pointer stays off.** Do not create `/home/default/share/Chore_Boy/CBCS/cbcs_state_root` on the human share unless this run is proving the pointer. If you create a pointer, delete it before `stop`.
- **Proof.** Save the printed paths and the first-launch `ok` print. This recipe proves path identity, not a Qt widget. Do not claim live UI verified from it.

## Gotchas

- Shared settings are opt-in. Two writers on one NFS state directory can clobber `settings.json` and sibling files.
- Installing onto the share does not automatically share state.
- State never lives inside `choreboy_code_studio_vX`. The pointer filename is `cbcs_state_root` (visible, not hidden).
- Compare state-root identity without following the final symlink hop. Clair's home→share symlink must remain the logical path.
- Leftover sources are copied, not moved. Occupied dest (`settings.json` already there) skips copy.
