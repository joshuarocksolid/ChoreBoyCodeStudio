# M8.R speed and VM evidence

Lane B only. No product files changed. No budget row missed, so nothing was profiled and no product fix is proposed.

CPU p95 is Hyndman-Fan type 7 on 19 samples after one warmup. The budget is the raw UX-M8-003 number. Wall p95 is recorded beside it. The idle reference adds the integers from 0 through 115999.

Mac is the gate Python 3.11.14. Load during the SQLite rows was about 1.25, 1.51, 1.75. The later PostgreSQL rows saw about 2.11, 1.69, 1.81. Idle CPU p95 was 1.810 ms.

The VM is cbfarm solo `eoy7`, `/opt/freecad/AppRun`, Python 3.9.2, FreeCAD 1.0.0, PySide2 5.15.2. `os.getloadavg()` raises `OSError: Load averages are unobtainable`, so the VM load column is empty. Idle CPU p95 was 3.534 ms. SQLite work lived in `/tmp/m8r_work` because the share locks SQLite.

Reference counts on both machines. 2,000 customers, 5,000 products, 100,000 invoices, 400,000 lines. Invoices 1 and 2 have 20 lines each. PostgreSQL 9.3 has the same counts plus 26 extra tables, 30 tables in all.

## Budget rows

| Row | Budget Mac / VM | Mac CPU / wall | VM CPU / wall | Result |
| --- | ---: | ---: | ---: | --- |
| Data tab fill, 40 cached columns | 16 / 60 | 7.346 / 7.346 | 9.227 / 9.232 | pass |
| Open a bound form, SQLite, 100,000 keys, both lookups, record 1 with 20 lines | 200 / 800 | 21.858 / 21.884 | 45.195 / 46.076 | pass |
| Show another record with 20 lines | 16 / 60 | 3.206 / 3.214 | 5.909 / 5.910 | pass |
| Dirty check on a keystroke | 1 / 4 | 0.016 / 0.014 | 0.038 / 0.038 | pass |
| Save a record with 20 lines, SQLite | 40 / 160 | 16.169 / 16.269 | 33.556 / 43.076 | pass |
| Load a 2,000-row lookup | 30 / 120 | 5.386 / 5.385 | 9.852 / 9.872 | pass |
| List search, 2,000 customers, limit 500 | 50 / 200 | 2.931 / 2.945 | 4.868 / 4.893 | pass |

Evidence. Data tab counted 40 visible column rows. Open reported keys=100000, lines=20, customers=2001, products=5000. The extra customer is the blank lookup row. List search returned 500 rows. Full samples are in `probe_m8r_vm/results/summary_mac.json` and `summary_vm.json`.

The editor stays responsive during a schema refresh. `tests/form_builder/perf/test_m8_r_budgets.py` pauses the schema read for 0.4 s on a real footer thread and sees the UI thread process a timer while that work is running. The same observation was true on the Mac and on the VM against the reference database, with no artificial pause.

## Recorded only

These rows have no budget.

| Row | Mac CPU / wall | VM CPU / wall |
| --- | ---: | ---: |
| Open a bound form, PostgreSQL | 17.051 / 49.907 | 233.680 / 243.341 |
| Show another record, PostgreSQL | 3.448 / 6.897 | 6.973 / 7.816 |
| Dirty check, PostgreSQL | 0.016 / 0.012 | 0.042 / 0.040 |
| Save 20 lines, PostgreSQL | 12.340 / 40.577 | 206.010 / 210.792 |
| Load the 2,000-row lookup, PostgreSQL | 5.644 / 16.657 | 22.719 / 27.343 |
| List search, PostgreSQL | 2.781 / 8.040 | 6.012 / 9.666 |
| Schema helper, 30 tables | 5.812 / 277.271 | 9.267 / 603.298 |

The helper's CPU is the refresh. The wall time is the cold start, one child per request. On the Mac `command0` is the FreeCAD.app Python and the script is `run_schema_helper.py`. On the VM `command0` is `/opt/freecad/AppRun` and the script is the same. Both refreshes reported tables=30.

Mac PostgreSQL used psycopg 3 against a local `postgres:9.3` container. The VM used pg8000 against net1. The VM open and save are slower. They are not budget rows, and the matching SQLite rows passed, so they were not profiled.

## VM facts (§13.5.11)

### M8.1 drivers and the machine file

Bundled drivers. Failed. A clean `/opt/freecad/AppRun` with the payload off `sys.path` raised `ModuleNotFoundError` for both `psycopg` and `pg8000`. This image does not ship either driver.

pg8000 on the probe path. Passed the connection checks. It loaded from `/mnt/cbprobe/incoming/m8r/payload/pg8000/__init__.py`, connected to `77.77.77.1` database `shop`, `SET client_encoding` then `SHOW client_encoding` returned UTF8 on that same connection, and `INSERT ... RETURNING` returned id 1. The invoice demo and the VM speed rows used this driver.

psycopg on the VM. Failed. `import psycopg` raised `ModuleNotFoundError`. The Mac wheel is a Darwin binary, and this probe did not ship a Linux cp39 build.

md5 auth. Not in effect, and not configurable from this account. A wrong password was accepted. `pg_hba.conf` is `/home/PG_data/pg_hba.conf`. The guest user cannot read it.

Machine file. Passed. `save_machine` wrote `/tmp/m8r_work/machine_file/shop.json` at mode `0o600`. The directory is `0o700`. The file is writable.

### M8.2 bound form on the VM

Passed, on this image's FreeCAD. The UX text names FreeCAD 1.1. The guest is FreeCAD 1.0.0, Python 3.9.2, PySide2 5.15.2. There is no PySide6. Generated forms import PySide6, so the probe installs an alias onto PySide2 before it loads them. The preview child sets `CBCS_QT_API=pyside6` only after that alias, because the child refuses to start otherwise.

Every UX-M8-003 VM budget row passed. The generated invoice form opened record 1 of 100000, showed both lookups, and saved. The customer list is the start screen.

### M8.4 Try rollback

Passed. A second AppRun process ran the preview child on the real display. It loaded the invoice module, changed Notes to `m8r try rollback`, and saved.

Banner. `Try: changes to Shop are rolled back. While a save runs, other people using it may wait up to 2 seconds.`

What ran includes `UPDATE "invoices" SET "notes" = %s` and the line `Saved, then rolled back`.

md5 of the canonical invoice text and the invoice_lines text, before and after.

| Table | Before | After |
| --- | --- | --- |
| invoices | 4b8aa0899216900e49aaa92f3b653b7c | 4b8aa0899216900e49aaa92f3b653b7c |
| invoice_lines | 8a987b801f6ae1c2672644c1d75aa533 | 8a987b801f6ae1c2672644c1d75aa533 |

`do verb=pg --db shop` after the walk returned invoice 1 with an empty notes column. The demo's line 21 was still there. Try did not commit.

Shots. `07_try_banner.png` and `08_what_ran.png`.

### M8.6 helper cold start and AppArmor

Passed. The helper cold start on the VM is the wall p95 above, 603.298 ms, with CPU p95 9.267 ms. `command0` is `/opt/freecad/AppRun`. The refresh saw 30 tables, and PostgreSQL was reachable for this run.

AppArmor. In that same AppRun process, `os.getloadavg()` raises `OSError: Load averages are unobtainable`, and reading `/proc/self/attr/current` raises `PermissionError: [Errno 13]`. The helper is that AppRun, so it runs under the confined runtime.

## Invoice demo

The project was built by Form from a table. Record form with lines, customer list, start screen on the list. The connection is host `77.77.77.1`, port 5432, database `shop`, user `postgres`, no password.

Driver. pg8000. Prepared statements on the open connection. 0. pg8000 is not using the server-side prepares psycopg would count.

Memory. VmRSS 211,432 kB before the demo steps and 231,476 kB after the save.

Steps. The list opened on 2,000 customers (`01_list.png`, "Showing the first 500 of 2,000"). Search for `Customer 1` returned 500 of 1,111 (`02_search.png`). The invoice opened at record 1 of 100000, INV-1, Customer 2, 20 lines (`03_invoice.png`). The lookup grab is the same frame (`04_lookup.png`, same bytes as 03). Add line (`05_add_line.png`) and save (`06_saved.png`). The grid viewport in those two shots still shows the earlier lines. The save itself is in the database.

`do verb=pg --db shop` returned one row. Invoice 1, empty notes, line_no 21, product_id 1, qty 1, price 1, empty description. `demo.json` records the same line and `saved: true`.

## Misses

No UX-M8-003 budget row missed on either machine. No cProfile. No proposed product change.
