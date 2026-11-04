# M8.R speed and VM evidence

Lane B only. No product files changed. No budget row missed, so nothing was profiled and no product fix is proposed.

CPU p95 is Hyndman-Fan type 7 on 19 samples after one warmup. The budget is the raw UX-M8-003 number. Wall p95 sits beside it. The idle reference adds the integers from 0 through 115999. On both VMs `os.getloadavg()` raises `OSError: Load averages are unobtainable`, so the load column is empty. SQLite work lived in `/tmp/m8r_work` because the share locks SQLite.

Reference counts. 2,000 customers, 5,000 products, 100,000 invoices, 400,000 lines. Invoices 1 and 2 have 20 lines each.

## FreeCAD 1.1 VM budget rows

This is the target runtime. cbprobe slot `ChoreBoyExp`, `/opt/freecad/AppRun`, FreeCAD 1.1.1 (git `0108fd4b4`, 2026-04-14), Python 3.11.14, PySide6 6.8.3, Qt 6.8.3. `qt_alias.install()` returned `native`. There is no PySide2. Idle CPU p95 was 3.658 ms. Judged-sample ranges are under each row. Samples are in `probe_m8r_vm/results/summary_fc11.json`.

| Row | Budget | CPU / wall p95 | Judged range (CPU) | Result |
| --- | ---: | ---: | ---: | --- |
| Data tab fill, 40 cached columns | 60 | 26.185 / 26.200 | 20.073 to 26.954 | pass |
| Open a bound form, SQLite, 100,000 keys, both lookups, record 1 with 20 lines | 800 | 55.783 / 55.800 | 49.602 to 64.061 | pass |
| Show another record with 20 lines | 60 | 7.332 / 7.331 | 6.181 to 7.517 | pass |
| Dirty check on a keystroke | 4 | 0.059 / 0.055 | 0.045 to 0.071 | pass |
| Save a record with 20 lines, SQLite | 160 | 40.206 / 51.345 | 36.002 to 46.332 | pass |
| Load a 2,000-row lookup | 120 | 13.955 / 13.960 | 11.627 to 14.258 | pass |
| List search, 2,000 customers, limit 500 | 200 | 7.312 / 7.361 | 5.861 to 7.895 | pass |

Open evidence was keys=100000, lines=20, customers=2001, products=5000. CPU and wall match on the open, so that time is inside the process. The idle reference is 3.658 ms. No row was profiled, because none missed its budget.

The UI thread keeps processing events during a schema refresh. The unit test pauses the read for 0.4 s. The same observation was true on this VM with no pause (`responsive_reference` in the summary).

Schema helper, SQLite, 4 tables. Recorded, not budgeted. CPU p95 7.119 ms, wall p95 10.704 ms, evidence `tables=4`, `command0` `/opt/freecad/AppRun`, script `run_schema_helper.py`. This is a successful refresh. An earlier sample in the same session raised because the harness still required 30 tables. That sample is not this number.

## FreeCAD 1.0 VM budget rows

cbfarm solo, `/opt/freecad/AppRun`, Python 3.9.2, FreeCAD 1.0.0, PySide2 5.15.2. Generated forms were loaded through a PySide6 alias. These rows are not the target runtime. Idle CPU p95 was 3.534 ms. Samples are in `summary_vm.json`.

| Row | Budget | CPU / wall p95 | Result |
| --- | ---: | ---: | --- |
| Data tab fill | 60 | 9.227 / 9.232 | pass |
| Open a bound form, SQLite | 800 | 45.195 / 46.076 | pass |
| Show another record | 60 | 5.909 / 5.910 | pass |
| Dirty check | 4 | 0.038 / 0.038 | pass |
| Save 20 lines, SQLite | 160 | 33.556 / 43.076 | pass |
| Load a 2,000-row lookup | 120 | 9.852 / 9.872 | pass |
| List search | 200 | 4.868 / 4.893 | pass |

## Mac budget rows

Gate Python 3.11.14. Load during the SQLite rows was about 1.25, 1.51, 1.75. Idle CPU p95 was 1.810 ms. Samples are in `summary_mac.json`.

| Row | Budget | CPU / wall p95 | Result |
| --- | ---: | ---: | --- |
| Data tab fill | 16 | 7.346 / 7.346 | pass |
| Open a bound form, SQLite | 200 | 21.858 / 21.884 | pass |
| Show another record | 16 | 3.206 / 3.214 | pass |
| Dirty check | 1 | 0.016 / 0.014 | pass |
| Save 20 lines, SQLite | 40 | 16.169 / 16.269 | pass |
| Load a 2,000-row lookup | 30 | 5.386 / 5.385 | pass |
| List search | 50 | 2.931 / 2.945 | pass |

## Recorded PostgreSQL rows

These have no budget. The FreeCAD 1.1 VM could not open a TCP connection to PostgreSQL, so there is no 1.1 PostgreSQL timing. The numbers below are FreeCAD 1.0 on cbfarm, driver pg8000, against net1 PostgreSQL 9.3. The Mac used psycopg 3 against a local `postgres:9.3` container. Load on those Mac rows was about 2.11, 1.69, 1.81.

| Row | Mac CPU / wall | FreeCAD 1.0 VM CPU / wall |
| --- | ---: | ---: |
| Open a bound form | 17.051 / 49.907 | 233.680 / 243.341 |
| Show another record | 3.448 / 6.897 | 6.973 / 7.816 |
| Dirty check | 0.016 / 0.012 | 0.042 / 0.040 |
| Save 20 lines | 12.340 / 40.577 | 206.010 / 210.792 |
| Load the 2,000-row lookup | 5.644 / 16.657 | 22.719 / 27.343 |
| List search | 2.781 / 8.040 | 6.012 / 9.666 |
| Schema helper, 30 tables | 5.812 / 277.271 | 9.267 / 603.298 |

The 30-table helper wall time is the cold start, one child per request. On the Mac `command0` is the FreeCAD.app Python. On the FreeCAD 1.0 VM it is `/opt/freecad/AppRun`.

## The frame prefix is not a product bug

`FrameDecoder.feed` in `app/features/form_builder/engine/ipc/protocol.py` splits frames on `\n` only (line 679). The `\x1e` character is the start of `FRAME_PREFIX` (`\x1eCBFP1 `), and `str.splitlines` treats `\x1e` as a line break. That split was in the probe script that read a frame file. It is not how the preview IPC decoder works.

## VM facts

### M8.1 drivers

FreeCAD 1.1. Passed for the bundled imports. A clean AppRun import, with the payload off `sys.path`, loaded psycopg 3.3.4 from `/opt/freecad/usr/lib/python3.11/site-packages/psycopg/__init__.py` and pg8000 1.31.5 from the matching `pg8000` path. Versions are in `facts_fc11.json`.

The same VM could not complete a TCP connection to PostgreSQL 9.3, so `SET client_encoding`, `RETURNING`, and md5 auth were not run from this guest. From the Debian host, `postgres:9.3` published on `77.77.77.1:54329` and `192.168.122.1:54329` used `host all all all md5`. A wrong password was rejected. The right password connected. From the guest, `192.168.122.1:54329` raised `OSError: [Errno 101] Network is unreachable`, and `77.77.77.1:54329` raised `ConnectionRefusedError: [Errno 111] Connection refused`. The domain has NICs on `virbr0` and `virbr77`. Neither bridge had an ARP entry for this domain's MAC. The container was removed with `docker rm -fv m8r-vm-pg`.

FreeCAD 1.0, labeled as that runtime. Bundled imports failed. Neither driver is in that AppRun. pg8000 on the probe path connected to `77.77.77.1` database `shop`. `SET client_encoding` then `SHOW client_encoding` returned UTF8, and `INSERT ... RETURNING` returned id 1. psycopg did not load. md5 auth was not in effect. A wrong password was accepted, and the guest cannot read `pg_hba.conf`.

Machine file. Passed on both images. `save_machine` wrote `/tmp/m8r_work/machine_file/shop.json` at mode `0o600`. The directory is `0o700`.

### M8.2 bound form

FreeCAD 1.1. Passed on real PySide6. Every budget row above passed. The generated invoice form opened record 1 of 100000, showed the customer combo, added a line, and saved. Shots `fc11_05_add_line.png` and `fc11_06_saved.png` show line 21. `fc11_03_invoice.png` and `fc11_04_lookup.png` are different files. The lookup grab is the invoice before the new line, not an open combo popup. SQLite shows the saved line as product 1, qty 1, price 1. The description cell was empty after save. `demo_fc11.json` has `saved: true` and 21 lines.

FreeCAD 1.0. Passed only through the alias. Shots `01_list.png` through `06_saved.png`. Shots 03 and 04 are the same bytes. Shots 05 and 06 do not show line 21 in the viewport. The row was in PostgreSQL.

### M8.4 Try

FreeCAD 1.1, SQLite scratch mode, real PySide6, preview `ChildSession` under AppRun on the display. Source `shop.db` sha256 before and after was `7f898ba06850d2864d5674a1afaec6ce1b595768de7c7d7bb46967b1d8fc2522`. Notes were set to `m8r try rollback`. What ran includes `UPDATE "invoices" SET "notes" = ?`. The window strip says `Data scratch copy` and offers Reset data. Shot `fc11_07_try_banner.png`. The `preview.banner` label was empty. Scratch mode does not use the PostgreSQL rollback sentence.

FreeCAD 1.0, PostgreSQL rollback. Passed. Banner `Try: changes to Shop are rolled back. While a save runs, other people using it may wait up to 2 seconds.` What ran includes `UPDATE "invoices" SET "notes" = %s` and `Saved, then rolled back`. Invoice md5 `4b8aa0899216900e49aaa92f3b653b7c` and line md5 `8a987b801f6ae1c2672644c1d75aa533` were unchanged. That result is `facts_try.json`. `facts.json` keeps the earlier attempt, which did not save, under `try_first_attempt`.

### M8.6 helper and AppArmor

FreeCAD 1.1. Passed for a SQLite file. Wall p95 10.704 ms, CPU p95 7.119 ms, 4 tables, `command0` `/opt/freecad/AppRun`. The same process gets the load-average `OSError` and `PermissionError` on `/proc/self/attr/current`.

FreeCAD 1.0. The 30-table PostgreSQL helper cold start is the 603.298 ms wall p95 above, also under AppRun, with the same AppArmor errors.

## Misses

No UX-M8-003 budget row missed on the Mac, on FreeCAD 1.1, or on FreeCAD 1.0. No cProfile. No proposed product change.

FreeCAD 1.1 did not reach PostgreSQL. The FreeCAD 1.0 PostgreSQL demo and Try remain the server evidence, and they are labeled with that runtime.
