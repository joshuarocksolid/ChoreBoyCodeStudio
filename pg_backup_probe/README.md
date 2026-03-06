# PostgreSQL Backup Probe Suite

Probe bundle for determining the best PostgreSQL backup strategy on ChoreBoy under locked-down constraints.

The suite is designed to answer:

1. Can `pg_dump` be found and executed?
2. If not, can we produce reliable backups with pure Python (`pg8000`)?
3. What is the real size and timing envelope for backup operations?
4. Should backups default to per-database or all-database mode?

## Files

| File | Purpose |
|---|---|
| `probe1_pg_discovery.py` | Finds PostgreSQL client binaries (`pg_dump`, `psql`, etc), checks executability, collects server paths (`data_directory`, config files). |
| `probe2_db_inventory.py` | Enumerates databases/tables and computes storage size inventory. Writes `probe2_inventory.json`. |
| `probe3_ddl_extraction.py` | Extracts DDL components from catalogs for a sample table (columns, constraints, indexes, sequences, views/functions samples). |
| `probe4_copy_protocol.py` | Tests `COPY ... TO STDOUT` via `pg8000` and measures export throughput with fallback scan path. |
| `probe5_mini_backup.py` | Builds a restorable `.sql` mini-backup for one table (DDL + data inserts) and performs SQL syntax execution checks on sampled rows. |
| `probe6_full_feasibility.py` | Uses inventory + timed samples to estimate full backup duration and recommends default backup strategy. |
| `probe7_pgdump_hunt.py` | Locates `pg_dump` via `/proc`, pgAdmin3 config, and broad filesystem search; tests execution and backup from AppRun. |
| `results/` | Probe outputs (`probeN_results.txt`, JSON artifacts, and generated sample backup files). |

## Run order

Run probes in this sequence:

1. `probe1_pg_discovery.py`
2. `probe2_db_inventory.py`
3. `probe3_ddl_extraction.py`
4. `probe4_copy_protocol.py`
5. `probe5_mini_backup.py`
6. `probe6_full_feasibility.py`
7. `probe7_pgdump_hunt.py`

## How to run on ChoreBoy

ChoreBoy has no terminal access for users, so run through Code Studio or Python Console.

### Option A: ChoreBoy Code Studio Run

1. Open `pg_backup_probe/` in ChoreBoy Code Studio.
2. Select the probe script in the file tree.
3. Click **Run**.
4. Review output in Run Log.
5. Continue to the next probe.

### Option B: Python Console

```python
import os, runpy
root = "/home/default/pg_backup_probe"
os.chdir(root)
runpy.run_path("probe1_pg_discovery.py", run_name="__main__")
```

Change the filename for each probe.

## Configuration

All probes support environment-variable overrides.

| Variable | Default | Meaning |
|---|---|---|
| `PG_HOST` | `localhost` | PostgreSQL host |
| `PG_PORT` | `5432` | PostgreSQL port |
| `PG_USER` | `postgres` | PostgreSQL user |
| `PG_PASSWORD` | `true` | PostgreSQL password |
| `PG_DATABASE` | `postgres` | Admin connection database for discovery/inventory |
| `PG_TARGET_DATABASE` | `PG_DATABASE` (or `postgres`) | Target database for probes 3-5 |
| `PG_SAMPLE_TABLE` | `public.acct_trans` | Sample table for probes 3-5 (auto-falls back to first non-system table if missing) |
| `PG_BACKUP_ROW_LIMIT` | unset | Optional row limit for probe 5 output size |
| `PG_PROBE6_TABLE_SAMPLE_COUNT` | `8` | Number of representative tables timed by probe 6 |

## Output artifacts

Probe outputs are written to `results/`.

Typical files:

- `probe1_results.txt`
- `probe2_results.txt`
- `probe2_inventory.json`
- `probe3_results.txt`
- `probe3_extracted_ddl.sql`
- `probe3_metadata.json`
- `probe4_results.txt`
- `probe4_metrics.json`
- `probe5_results.txt`
- `probe5_summary.json`
- `probe5_<schema>_<table>_mini_backup.sql`
- `probe6_results.txt`
- `probe6_feasibility.json`
- `probe7_results.txt`
- `probe7_pgdump_status.json`

## Decision interpretation

Use these outcomes to choose backup implementation:

- If `pg_dump` is executable in probe 7, prefer `pg_dump` for production backup/export.
- If `pg_dump` is unavailable or blocked (probe 7), use pure-Python backup path validated by probes 3-5.
- Use probe 6 estimates to decide default UX:
  - fast total duration: allow one-click full backup
  - moderate/slow total duration: default to per-database backup and keep full backup optional

## Expected likely outcome on ChoreBoy

Given known constraints, pure-Python backup via `pg8000` is expected to be the primary viable path. This probe suite verifies that assumption with concrete runtime evidence and timing data on the actual system.
