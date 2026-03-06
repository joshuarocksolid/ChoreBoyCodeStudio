# PostgreSQL Backup Probe: Findings Summary

## Executive summary

Six probes ran on ChoreBoy to determine the best PostgreSQL backup strategy under the system's locked-down constraints. The headline results:

- **PostgreSQL 9.3.6** is running on `localhost:5432` with a non-standard data directory at `/home/PG_data`.
- **`pg_dump` was not found** by the probe searching the AppRun Python environment's PATH and standard binary locations.
- **pgAdmin3 can run `pg_dump` successfully** (confirmed by screenshots showing `exit code 0`), which means the binary exists somewhere on the system but is not visible from the AppRun context.
- **Pure-Python backup via `pg8000` is fully validated**: DDL extraction, `COPY TO STDOUT` data export, and mini-backup generation all work.
- **Full all-database backup is fast**: estimated at ~1.4 seconds for ~36 MB across 286 tables.

## Environment facts

| Property                  | Value                                          |
| ------------------------- | ---------------------------------------------- |
| Python runtime            | 3.9.2 via `/opt/freecad/usr/bin/FreeCAD`       |
| PostgreSQL server version | 9.3.6                                          |
| Data directory            | `/home/PG_data`                                |
| Config file               | `/home/PG_data/postgresql.conf`                |
| HBA file                  | `/home/PG_data/pg_hba.conf`                    |
| Connection                | `postgres@localhost:5432` (password: `true`)    |
| pg8000 version            | 1.31.5 (vendored, pure-Python)                 |
| Total databases           | 11 (9 connectable, 2 templates)                |
| Total user tables         | 286                                            |
| Total user table data     | ~36.4 MB (`38,215,680` bytes)                  |

### Database inventory

| Database             | Size (bytes) | Top table                              | Est. backup |
| -------------------- | ------------ | -------------------------------------- | ----------- |
| default_db           | 28,721,668   | `public.core_postal_code_record` (15 MB) | 0.7 s       |
| classicaccounting    | 24,684,728   | `public.core_postal_code_record` (7 MB)  | 0.5 s       |
| fertilizer           | 7,760,056    | `public.job_batch_products` (104 KB)     | < 0.1 s     |
| fertilizer1          | 7,784,632    | `public.job_fields` (80 KB)              | < 0.1 s     |
| fertilizer_cmd_ctr   | 7,760,056    | `public.job_fields` (80 KB)              | < 0.1 s     |
| postgres             | 7,776,440    | `job_manager.user_roles` (72 KB)         | < 0.1 s     |
| puppy                | 7,194,808    | `public.schema_migrations` (48 KB)       | < 0.1 s     |
| classcheduler        | 6,752,440    | `class_scheduler.schema_migrations` (48 KB) | < 0.1 s  |
| django_probe         | 6,449,336    | (no user tables)                         | 0 s         |

## Probe-by-probe results

| Probe | Purpose | Result | Key detail |
| ----- | ------- | ------ | ---------- |
| 1 | Find `pg_dump` and PG client binaries | **Not found** | Searched `which`, `/usr/bin/`, `/usr/lib/postgresql/*/bin/`, `/usr/local/bin/`, `/opt/freecad/usr/bin/`. Zero candidates. |
| 2 | Database and table inventory | **Pass** | 11 databases, 286 user tables, 38 MB total data. |
| 3 | DDL extraction from catalogs | **Pass** | Columns, PK/UK/FK constraints, indexes, sequences all extracted for `job_manager.user_roles`. Generated 8 SQL statements. |
| 4 | `COPY TO STDOUT` protocol | **Pass** | Works via `pg8000` stream parameter. Smoke test: 149 bytes in 2.3 ms. |
| 5 | Mini backup (DDL + INSERT data) | **Pass** | Produced 1,191-byte `.sql` file for `job_manager.user_roles`. Syntax-validated against server. |
| 6 | Full feasibility estimate | **Pass** | ~1.4 s for all databases. Throughput: ~26 MB/s (COPY), ~447k rows/s. Recommendation: full all-database backup is feasible as a single user action. |

## The pg_dump discovery gap

### What probe 1 searched

The probe looked for `pg_dump` in these locations:

- `shutil.which("pg_dump")` — follows the AppRun process PATH
- `/usr/bin/pg_dump`
- `/usr/lib/postgresql/*/bin/pg_dump`
- `/usr/local/bin/pg_dump`
- `/opt/freecad/usr/bin/pg_dump`

All returned zero results.

### What pgAdmin3 shows

User-provided screenshots from pgAdmin3 on ChoreBoy show:

- pgAdmin3 connected to `PostgreSQL 9.3 [localhost:5432]`
- Backup dialog running `pg_dump` with output lines like:
  - `pg_dump: reading foreign key constraints for table "teacher"`
  - `pg_dump: dumping contents of table employee`
  - `Process returned exit code 0.`
- Output file written to `/home/default/classschedulerbackup`

### Root cause analysis

The PostgreSQL installation on ChoreBoy is non-standard. The data directory is `/home/PG_data`, not the Debian default `/var/lib/postgresql/9.3/main`. This means the server binaries — and `pg_dump` alongside them — are installed in a custom location that was not in probe 1's search list.

pgAdmin3 knows the path because it is configured with the PG installation prefix (via its "Binary path" setting in Preferences > Paths, or auto-detected from the installation).

The AppRun Python environment has its own `PATH` that does not include the PostgreSQL binary directory. This is why `shutil.which` and glob searches in standard Debian locations returned nothing.

### Why the in-memory approach does not apply

The `memfd_create` + `ctypes.CDLL` technique used for tree-sitter's shared library works because `dlopen()` loads a `.so` into an existing process. `pg_dump` is a standalone ELF executable, not a shared library — it requires `execve()` to run as a new process. AppArmor restricts which binaries can be exec'd, and `memfd_create` does not bypass that restriction for executables (only for `dlopen()` of shared objects).

## Strategy comparison

| Factor | Strategy A: `pg_dump` subprocess | Strategy B: pure-Python `pg8000` |
| ------ | ------------------------------- | -------------------------------- |
| Fidelity | Complete (triggers, rules, GRANTs, custom types, extensions, tablespace settings) | Partial (tables, columns, constraints, indexes, sequences). Missing: triggers, rules, custom types, GRANTs. |
| Output format | Standard SQL dump, restorable by `psql` or `pg_restore` on any system | Custom SQL output, restorable by `psql` for the covered object types |
| Maintenance | Zero dump-engine code to maintain | Custom DDL/data extraction code requires ongoing maintenance |
| Performance | Native C binary, optimized | ~26 MB/s via COPY protocol (sufficient for 36 MB) |
| Dependency | Requires locating `pg_dump` binary and confirming it is executable from AppRun | Already validated, no additional dependencies |
| Risk | May be blocked by AppArmor even if found | No execution restrictions (pure Python over TCP) |

### For ChoreBoy's databases

The 286 tables across 9 databases are mostly simple CRUD schemas (accounting, scheduling, fertilizer management). They are unlikely to use triggers, rules, custom types, or extensions. This means Strategy B's coverage gap is likely minimal in practice.

## Recommended approach

### Immediate next step: Probe 7

Before committing to a strategy, run `probe7_pgdump_hunt.py` to definitively locate `pg_dump` and test whether it is executable from the AppRun context. The probe will:

1. Search `/proc/*/exe` for the running `postgres` process to derive the `bin/` directory
2. Parse pgAdmin3 config files for stored binary paths
3. Broad filesystem search of `/usr/`, `/opt/`, `/home/` for any file named `pg_dump`
4. Test execution with `pg_dump --version` if found
5. Attempt a real single-table backup if execution succeeds

### Decision tree after probe 7

```
pg_dump found?
  ├── No → Use Strategy B (pure-Python pg8000 backup)
  └── Yes → Executable from AppRun?
        ├── Yes → Use Strategy A (subprocess pg_dump)
        └── No (PermissionError) → Try bridge script
              └── Bridge fails → Fall back to Strategy B
```

**Strategy A** is preferred if `pg_dump` is reachable because it produces complete, standard dumps with zero custom code. **Strategy B** is the validated fallback — already proven to work with good performance.

## Open questions

1. **Where is `pg_dump` installed?** Probe 7 will answer this by searching `/proc` and the filesystem.
2. **Does AppArmor allow AppRun to exec `pg_dump`?** Probe 7 will test this directly.
3. **Does pgAdmin3 store its binary path in a parseable config file?** Probe 7 will check `~/.pgadmin3` and related locations.
4. **For Strategy B, is the DDL coverage sufficient?** The databases appear to be simple CRUD schemas, but a full audit of object types (triggers, rules, custom types) per database would confirm this.
