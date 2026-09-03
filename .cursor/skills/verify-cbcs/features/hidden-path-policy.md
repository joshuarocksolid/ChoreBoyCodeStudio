# Hidden path policy

Hidden (dot-prefixed) path support on ChoreBoy is a per-parent, per-kind fact. `app/bootstrap/hidden_path_policy.py` probes one parent for a hidden file, a hidden directory, and a visible directory, caches the result per process, and leaves no canaries. `resolve_global_state_root` uses that probe to pick the product state default from three candidates, and `packaging/install.py` publishes the Desktop launcher icon as a hidden sibling with a visible sidecar fallback. Evidence table and policy: `docs/DISCOVERY.md` section 4A.

<!-- dune-owners: hidden-path-policy, platform.bootstrap -->

## Sub-features

- `probe-parent` `probe_hidden_path_support(parent)` returns `HiddenPathProbeResult(parent, hidden_file_ok, hidden_dir_ok, visible_dir_ok, errors)`. A missing parent is all-False. Nothing is created above the parent. Canary names are `.cbcs_probe_file.<pid>`, `.cbcs_probe_dir.<pid>`, `cbcs_probe_visible_dir.<pid>` and are removed in `finally`.
- `probe-cache` a second call for the same parent identity (absolute, no final symlink hop) returns the cached result without touching disk. `clear_hidden_path_probe_cache()` forces a re-probe.
- `state-default-probed` with no explicit root, no `CBCS_STATE_ROOT`, no pointer, and no legacy `$HOME/choreboy_code_studio_state`, the default is the first of (a) `/home/default/.local/share/FreeCAD/choreboy_code_studio_state`, (b) `/home/default/.cache/FreeCAD/choreboy_code_studio_state`, (c) `/home/default/FreeCAD/choreboy_code_studio_state` whose parent probed ok. The leaf is always the visible `choreboy_code_studio_state`.
- `state-precedence` explicit argument, `CBCS_STATE_ROOT`, install-parent pointer, shop pointer, and the legacy home directory still win, in that order, and none of them runs the probe.
- `state-symlink` the resolved root keeps the logical path (no final `.resolve()` hop).
- `icon-sidecar` an Apps-slot project install writes the Desktop launcher with `Icon=` pointing at `Desktop/.<stem><suffix>` (hidden sibling). When that hidden file write is denied, `Icon=` points at `Desktop/<stem>.icon<suffix>` (visible sidecar). `Icon=` never points under `~/.local`. App files stay under `~/.local/share/FreeCAD/Macro/Apps/<slug>`.
- `first-launch-real-default` the real chosen default tree (not the disposable `CBCS_STATE_ROOT`) can be created and written on this machine. This closes the 0.4.11 gap where verify only ever exercised the disposable root.

## How to get to it (user POV)

- First launch on a fresh machine creates the resolved state root. The user never sees the probe.
- Installing a shop project package puts a launcher on the Desktop whose icon renders in pcmanfm.
- A shop machine that wants shared state still sets `CBCS_STATE_ROOT` or writes a visible `cbcs_state_root` pointer.

## Driving it with control-cbcs

Preconditions:

- Leased slot. `control-cbcs launch --source`. Doctor passed. HOME is the disposable `/home/default/cbcs-verify-<run-id>` unless a row says otherwise.
- The launch injects `CBCS_STATE_ROOT=$HOME/choreboy_code_studio_state`. Rows that need the product default pop it inside the exec and restore it before returning.
- Never write `/home/default/share/Chore_Boy/CBCS/cbcs_state_root`. Probe the share only when proving that row and confirm the leftover glob below is empty before `stop`.

- **Probe matrix.** For each parent in `$HOME/Desktop`, `$HOME`, `/home/default`, `/home/default/Desktop`, `/home/default/FreeCAD`, `/home/default/.cache/FreeCAD`, `/home/default/.local/share/FreeCAD`, `/home/default/share/Chore_Boy/CBCS`:

```bash
$CONTROL ctl "$SID" exec -- "from pathlib import Path
from app.bootstrap.hidden_path_policy import probe_hidden_path_support
print(probe_hidden_path_support(Path('<parent>')))"
```

  Record `hidden_file_ok`, `hidden_dir_ok`, `visible_dir_ok`, and `errors` per parent into the run notes as the 2026-09-03 table rows (BLOCKED / ALLOWED per kind). A parent that does not exist prints all-False with `parent is not a directory` and must stay absent afterwards. After each probe, the leftover check must print `[]`:

```bash
$CONTROL ctl "$SID" exec -- "import glob
print(glob.glob('<parent>/.cbcs_probe_*') + glob.glob('<parent>/cbcs_probe_visible_dir.*'))"
```

- **Probe cache.** Probe `$HOME/Desktop` twice. The second print is identical and the exec returns without a new canary (watch the Desktop with `ls -la` between calls if you want a second observation). `from app.bootstrap.hidden_path_policy import clear_hidden_path_probe_cache; clear_hidden_path_probe_cache()` then probe again to re-run canaries.
- **Product default (no env, no pointer, no legacy).** Disposable HOME has no `choreboy_code_studio_state` yet, and the rsynced source has no `cbcs_state_root` beside it. Run:

```bash
$CONTROL ctl "$SID" exec -- "import os
from app.bootstrap import paths
saved = os.environ.pop('CBCS_STATE_ROOT')
try:
    root = paths.resolve_global_state_root()
finally:
    os.environ['CBCS_STATE_ROOT'] = saved
print(root)
print(root.parent in (paths.PRODUCT_STATE_XDG_PARENT, paths.PRODUCT_STATE_CACHE_PARENT, paths.PRODUCT_STATE_VISIBLE_PARENT))"
```

  The second line is `True`. Save the first line as the machine's chosen default. Cross-check it against the probe matrix: (a) needs `visible_dir_ok` on `.local/share/FreeCAD`, (b) needs `hidden_dir_ok` and `visible_dir_ok` on `.cache/FreeCAD` (or `.cache`), (c) is the fallback.
- **Legacy wins.** `mkdir -p $HOME/choreboy_code_studio_state` in the disposable HOME, then the same pop-and-resolve exec. The print is that directory. Remove it afterwards so the default row stays reproducible.
- **Env wins.** Without popping, `print(paths.resolve_global_state_root())` prints exactly the launch `CBCS_STATE_ROOT`.
- **Pointer wins.** Write one absolute path (a directory inside the disposable HOME) into `cbcs_state_root` beside the rsynced source parent (the `--source` remote root). The pop-and-resolve exec prints that path. Delete the pointer before `stop`.
- **Symlink logical path.** `ln -s $HOME/real_state $HOME/link_state` (create `real_state` first). `print(paths.resolve_global_state_root('$HOME/link_state'))` prints the `link_state` path, not `real_state`.
- **First launch on the real default.** Using the chosen default from the product-default row:

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
- **Icon sidecar (Apps-slot install).** Export a project package with `askInstallLocation` off and drive its installer by hand per [packaging-installer.md](./packaging-installer.md) AT-105 (not the product `--install` lane). After **Done**, read `$HOME/Desktop/<stem>.desktop`:

```bash
$CONTROL ctl "$SID" exec -- "from pathlib import Path
import os
text = (Path(os.environ['HOME']) / 'Desktop' / '<stem>.desktop').read_text(encoding='utf-8')
icon = next(line.split('=', 1)[1] for line in text.splitlines() if line.startswith('Icon='))
print(icon, Path(icon).is_file(), '/.local/' in icon)"
```

  Expected `Icon=` is `$HOME/Desktop/.<stem>.png` (hidden sibling, preferred) or `$HOME/Desktop/<stem>.icon.png` (visible sidecar, only when the hidden write was denied). `is_file()` is `True`, the `/.local/` check is `False`. Shot the Desktop in pcmanfm showing the launcher icon rendered (`icon-desktop`). Confirm `$HOME/.local/share/FreeCAD/Macro/Apps/<slug>` holds the app files and the Desktop holds only the `.desktop` plus the icon copy.
- **Proof.** The per-parent probe prints and empty leftover globs, the chosen-default print plus its `True`, the first-launch `ok` print, the `Icon=` print, and the `icon-desktop` shot. Record each with the feature id `hidden-path-policy`.

## Gotchas

- The probe result is cached per process. A row that changes the filesystem after a probe must call `clear_hidden_path_probe_cache()` or the old answer comes back.
- `control-cbcs launch` always injects `CBCS_STATE_ROOT`. Only the pop-and-resolve exec above sees the product default. Restore the variable in `finally` or later rows write into the real default.
- Probing `/home/default` and `/home/default/Desktop` briefly writes canaries on the human profile. They are removed in `finally`. Run the leftover glob anyway and record it.
- `.cache/FreeCAD` state (candidate b) may be wiped with the cache. Note it in the run when (b) is the chosen default.
- `.local`, `.cache`, and hidden Desktop siblings are invisible in pcmanfm even when fully writable. Visibility is not ACL. Do not report an invisible-but-writable path as BLOCKED.
- Mac AppRun and offscreen pytest results are not evidence for this table. Only the leased ChoreBoy slot counts.
