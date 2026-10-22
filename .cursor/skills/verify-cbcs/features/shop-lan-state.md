# Shop-LAN state

Local logs, history, plugins, cache, trash, and SQLite stay in `/home/default/FreeCAD/CBCS/state`.
Shared settings are opt-in and hold only `settings.json`, `recent_projects.json`, and
`python_console_history.json`. `CBCS_STATE_ROOT` and a `cbcs_state_root` pointer select
that JSON directory. They never move SQLite or logs. A pointer is read from
`/home/default/share/Chore_Boy/CBCS/cbcs_state_root` and from the same relative path
under one `~/share/<child>/` (for example `~/share/net1/Chore_Boy/CBCS/cbcs_state_root`).
Leftover settings JSON is copied once into the active settings root when that root has
no `settings.json`. History and SQLite are not copied.

<!-- dune-owners: shop-lan-state, platform.bootstrap -->

## Sub-features

- `state-default` local root is `/home/default/FreeCAD/CBCS/state` even when env or a shop pointer is set.
- `state-env` uses `CBCS_STATE_ROOT` as the shared settings directory when it is non-empty and absolute after expanduser.
- `state-pointer` reads the server pointer and `~/share/<child>/Chore_Boy/CBCS/cbcs_state_root`.
- `state-symlink` keeps the logical path (no final `.resolve()` hop). A legacy `~/choreboy_code_studio_state` symlink into `~/share` is the shared settings root, not the local root.
- `state-migrate` copies the three JSON files from the first leftover that has `settings.json`. Sources stay. No `state.migrating` tree.
- `shop-install` keeps the product install default at `/home/default/FreeCAD/CBCS/choreboy_code_studio_vX`. Shop recipe: installer **Ask for install folder** → `/home/default/share/Chore_Boy/CBCS/choreboy_code_studio_vX`. Shared settings stay opt-in.

## How to get to it (user POV)

- First launch creates `/home/default/FreeCAD/CBCS/state` for logs and SQLite. Settings JSON live there until a shared root is configured.
- Shop machines that want shared settings write a visible `cbcs_state_root` pointer (one absolute path) or set `CBCS_STATE_ROOT`.
- If that folder cannot be written, CBCS keeps using local settings for the session and says "Shared settings are not available".
- The product installer still offers a folder picker. Choosing the share installs the app there. That does not by itself share settings.

## Driving it with control-cbcs

Preconditions:

- Doctor passed.
- Isolated HOME. `control-cbcs launch` sets `CBCS_STATE_ROOT=$HOME/choreboy_code_studio_state`. That env now selects shared settings only. `resolve_global_state_root()` stays `/home/default/FreeCAD/CBCS/state`, so logs and SQLite from a verify session still land in the product dest. Do not treat the env as a full state sandbox.

- **Local root.** `control-cbcs ctl "$SID" exec -- "from app.bootstrap.paths import resolve_global_state_root; print(resolve_global_state_root())"`. The print is `/home/default/FreeCAD/CBCS/state` even when `CBCS_STATE_ROOT` is set.
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
- **Env selects settings only.** Without popping, `print(paths.resolve_global_state_root())` is still the product dest. `print(paths.global_settings_path())` is `$CBCS_STATE_ROOT/settings.json`. `print(paths.global_state_db_path())` stays under the product dest.
- **Pointer selects settings only.** Write one absolute path (a directory inside the disposable HOME) into `/home/default/share/Chore_Boy/CBCS/cbcs_state_root`, or under `$HOME/share/net1/Chore_Boy/CBCS/cbcs_state_root` when proving the client path. Pop `CBCS_STATE_ROOT` first. `print(paths.global_settings_path().parent)` is that path. `print(paths.resolve_global_state_root())` stays the product dest. Delete the pointer before `stop`.
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

- Shared settings are opt-in JSON. Two writers on one shared folder can clobber `settings.json`. SQLite stays on the local dest because `~/share` is a network share in real shops.
- Installing onto the share does not automatically share settings.
- State never lives inside `choreboy_code_studio_vX`. The pointer filename is `cbcs_state_root` (visible, not hidden).
- Compare path identity without following the final symlink hop. Clair's home→share symlink must remain the logical path.
- Leftover settings JSON is copied, not moved. Occupied dest (`settings.json` already there) skips the copy. History and SQLite in the leftover are left untouched.
- `CBCS_STATE_ROOT` does not keep verify logs and SQLite off the product dest. That is a gap until a local-root override exists.
