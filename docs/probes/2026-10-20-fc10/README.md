# FreeCAD 1.0 platform probe, 2026-10-20

These sentences answer the Phase 0.1 questions. Tables and file citations are in `docs/DISCOVERY.md` sections 4, 4A, and 4G. Screenshots are in `/Users/local/Projects/ChoreBoyCodeStudio_wt/v0413-evidence/phase0-probe/`.

1. On FreeCAD 1.0.0, confined AppRun can execute `/opt/freecad/AppRun -c`, `/bin/sh`, and `/bin/ls`. `/usr/bin/pdftoppm`, `/usr/bin/python3`, `/bin/bash`, `pcmanfm` (`/usr/local/bin/pcmanfm`), `xdg-open`, `okular`, and `/usr/bin/env` raise errno 13. `soffice` and `libreoffice` are absent. `/bin/sh -c 'pdftoppm -v'` exits 126.

2. On slot ChoreBoy2, `/home/default`, `/home/default/FreeCAD`, `/home/default/FreeCAD/CBCS`, `/home/default/.cache/FreeCAD`, `/tmp`, and `/home/default/share` accept a visible directory, a file, `fcntl` `LOCK_EX|LOCK_NB`, and SQLite in WAL and DELETE modes. A hidden directory under `/home/default` is errno 13. `/home/default/.local/share/FreeCAD` and `Macro/Apps` accept the directories and the file, then deny the lock, and both journal modes raise `database is locked`.

3. pcmanfm, started from the idesk Home icon on ChoreBoy2, opened `/home/default`, `FreeCAD`, `FreeCAD/CBCS`, `.cache/FreeCAD`, `/tmp`, and `~/share`. It showed "Permission denied" for `.local/share/FreeCAD`, `Macro/Apps`, and `.idesktop`. `~/Desktop` and `~/share/Chore_Boy` were absent on that slot, and the dialog said the directory is not valid.

4. The ChoreBoy2 desktop is idesk on fluxbox. The wallpaper icons are Home, Draw, Spreadsheet, Writer, Mount, Unmount, and Backup. `/usr/bin/idesk` exists. `~/.ideskrc` and `~/.idesktop` exist, are mode `0755` and owned by uid 1000, and AppRun cannot read them. pcmanfm cannot open `~/.idesktop`. AppRun cannot write a `.lnk` there. `/home/default/IntellaQuote.desktop` is a normal desktop entry and is not on the wallpaper. Writing `~/Desktop/cbcs_phase0_20261020.desktop` did not add an icon. idesk was not restarted. The `.lnk` text was not captured. ChoreBoy, ChoreBoy2, ChoreBoy3, and ChoreBoy4 have no `~/Desktop`. ChoreBoy5 has an empty one.

5. `~/share` has the same `st_dev` as `/home/default` (`65030`). `/tmp` is `64768` and `/mnt/cbprobe` is `36`. `/proc/mounts` is errno 13, so the mount table text was not read. fcntl and both SQLite modes work on `~/share` on ChoreBoy2. No measured slot has a `net*` child of `~/share`. `~/share/Chore_Boy` exists on ChoreBoy and ChoreBoy5, holds an empty `CBCS` directory, and accepts the lock and both journal modes. `/home/default/.nfs_log.txt` exists and AppRun cannot read it.

6. ChoreBoy, ChoreBoy2, ChoreBoy3, ChoreBoy4, and ChoreBoy5 report FreeCAD `1.0.0` revision `39109 (Git)`, commit `2fcc5317fe`, dated `2024/11/18`, and Python `3.9.2`. Hostnames were `net1`, `net2`, `net1`, `net4`, and `net1`. ChoreBoy6 stayed leased to another holder through the end of this run. An earlier probe the same day recorded that same FreeCAD string for ChoreBoy6 in `v0413-evidence/repro-A/fc-versions/ChoreBoy6.txt`. This run did not repeat it. ChoreBoyExp and ChoreBoyFactory were shut off. Their disks were not readable without root, and they were not booted, so their FreeCAD version is unknown.

## Scripts

`platform/run_probe.py` is the exec and path matrix. `version/run_probe.py` is the per-slot version and share listing. `share_extra/run_probe.py` lock-tests `~/share/Chore_Boy` when that directory exists. `read_more/run_probe.py` asks `/bin/sh` to read mounts and idesk files. `platform/idle_desktop.py` keeps a Qt loop so the desktop session can send keystrokes.

Each probe deletes only names containing `cbcs_phase0_20261020`. The ChoreBoy2 sweep and the later `share_extra` sweeps reported no leftover names.
