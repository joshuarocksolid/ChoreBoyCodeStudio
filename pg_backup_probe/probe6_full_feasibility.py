from __future__ import annotations

import io
import json
import os
import sys
import time
import traceback

try:
    probe_root = os.path.dirname(os.path.abspath(__file__))
except NameError:
    probe_root = "/home/default/pg_backup_probe"

results_dir = os.path.join(probe_root, "results")
os.makedirs(results_dir, exist_ok=True)

PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = int(os.environ.get("PG_PORT", "5432"))
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "true")
PG_ADMIN_DATABASE = os.environ.get("PG_DATABASE", "postgres")
PROBE_TABLE_SAMPLE_COUNT = int(os.environ.get("PG_PROBE6_TABLE_SAMPLE_COUNT", "8"))

results = []


def section(title):
    results.append("")
    results.append(f"[{title}]")


def ok(label, detail=""):
    suffix = f" ({detail})" if detail else ""
    results.append(f"  {label}: YES{suffix}")


def info(label, detail=""):
    suffix = f" ({detail})" if detail else ""
    results.append(f"  {label}{suffix}")


def fail(label):
    results.append(f"  {label}: FAILED")
    results.append(traceback.format_exc().rstrip())


def write_text_file(filename, content):
    path = os.path.join(results_dir, filename)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


def discover_vendor_paths():
    parent = os.path.dirname(probe_root)
    return [
        os.path.join(parent, "ca_invoice_printer", "vendor"),
        "/home/default/ca_invoice_printer/vendor",
        "/home/default/django_probe/vendor",
    ]


def quote_ident(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def connect_to(pg8000_module, database_name):
    return pg8000_module.connect(
        user=PG_USER,
        host=PG_HOST,
        database=database_name,
        port=PG_PORT,
        password=PG_PASSWORD,
        timeout=10,
        application_name="pg_backup_probe_6",
    )


def format_seconds(seconds):
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = seconds / 60.0
    if minutes < 60:
        return f"{minutes:.1f}m"
    hours = minutes / 60.0
    return f"{hours:.2f}h"


def load_inventory_file():
    inventory_path = os.path.join(results_dir, "probe2_inventory.json")
    if not os.path.exists(inventory_path):
        return None
    try:
        with open(inventory_path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def build_live_inventory(pg8000_module):
    inventory = {"databases": [], "summary": {}}
    conn = connect_to(pg8000_module, PG_ADMIN_DATABASE)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            d.datname,
            d.datistemplate,
            d.datallowconn,
            pg_database_size(d.datname) AS size_bytes
        FROM pg_database d
        ORDER BY d.datname
        """
    )
    db_rows = cursor.fetchall()
    cursor.close()
    conn.close()

    total_non_system_table_bytes = 0
    total_non_system_tables = 0

    for db_row in db_rows:
        db_name = db_row[0]
        is_template = bool(db_row[1])
        allow_conn = bool(db_row[2])
        size_bytes = int(db_row[3]) if db_row[3] is not None else 0
        db_info = {
            "name": db_name,
            "is_template": is_template,
            "allow_connection": allow_conn,
            "size_bytes": size_bytes,
            "connection_ok": False,
            "table_count": 0,
            "table_total_bytes": 0,
            "tables_by_size": [],
            "error": "",
        }
        inventory["databases"].append(db_info)
        if is_template or not allow_conn:
            continue
        conn = None
        try:
            conn = connect_to(pg8000_module, db_name)
            db_info["connection_ok"] = True
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    n.nspname AS table_schema,
                    c.relname AS table_name,
                    pg_total_relation_size(c.oid) AS total_bytes
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relkind = 'r'
                  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
                ORDER BY total_bytes DESC, table_schema, table_name
                """
            )
            rows = cursor.fetchall()
            table_infos = []
            table_total = 0
            for row in rows:
                schema_name = row[0]
                table_name = row[1]
                total_bytes = int(row[2]) if row[2] is not None else 0
                table_total += total_bytes
                table_infos.append(
                    {
                        "schema": schema_name,
                        "name": table_name,
                        "qualified_name": f"{schema_name}.{table_name}",
                        "total_bytes": total_bytes,
                    }
                )
            db_info["tables_by_size"] = table_infos
            db_info["table_count"] = len(table_infos)
            db_info["table_total_bytes"] = table_total
            total_non_system_table_bytes += table_total
            total_non_system_tables += len(table_infos)
            cursor.close()
        except Exception as exc:
            db_info["error"] = str(exc)
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    inventory["summary"] = {
        "database_count": len(inventory["databases"]),
        "total_non_system_tables": total_non_system_tables,
        "total_non_system_table_bytes": total_non_system_table_bytes,
    }
    return inventory


for vendor_path in discover_vendor_paths():
    if vendor_path not in sys.path and os.path.isdir(vendor_path):
        sys.path.insert(0, vendor_path)

print("=== Probe 6: Full Backup Feasibility ===")

results.append("[Runtime]")
results.append(f"  Python: {sys.version}")
results.append(f"  Probe root: {probe_root}")
results.append(f"  Table sample count: {PROBE_TABLE_SAMPLE_COUNT}")

try:
    import pg8000
except Exception:
    fail("pg8000 import")
    output = "\n".join(results)
    print(output)
    path = write_text_file("probe6_results.txt", output)
    print("")
    print(f"Results written to {path}")
    print("=== END Probe 6 (early exit) ===")
    raise SystemExit(1)

section("pg8000 import")
ok("pg8000", getattr(pg8000, "__version__", "imported"))

inventory = load_inventory_file()
inventory_source = "probe2_inventory.json" if inventory is not None else "live build"
if inventory is None:
    section("Inventory source")
    info("inventory", "probe2_inventory.json not found or unreadable, building live inventory")
    try:
        inventory = build_live_inventory(pg8000)
        ok("live inventory build")
    except Exception:
        fail("live inventory build")
        output = "\n".join(results)
        print(output)
        path = write_text_file("probe6_results.txt", output)
        print("")
        print(f"Results written to {path}")
        print("=== END Probe 6 (early exit) ===")
        raise SystemExit(1)
else:
    section("Inventory source")
    ok("inventory", "loaded from probe2_inventory.json")

all_tables = []
for db_info in inventory.get("databases", []):
    if not db_info.get("connection_ok"):
        continue
    db_name = db_info.get("name")
    for table in db_info.get("tables_by_size", []):
        all_tables.append(
            {
                "database": db_name,
                "schema": table.get("schema"),
                "name": table.get("name"),
                "qualified_name": table.get("qualified_name", ""),
                "total_bytes": int(table.get("total_bytes", 0) or 0),
            }
        )

all_tables.sort(key=lambda item: item["total_bytes"], reverse=True)
table_sample = all_tables[: max(1, PROBE_TABLE_SAMPLE_COUNT)]

section("Representative table sample")
if not table_sample:
    info("sample", "no connectable non-system tables found")
else:
    for item in table_sample:
        results.append(
            f"  {item['database']}:{item['qualified_name']} size_bytes={item['total_bytes']}"
        )

timings = []
conn_cache = {}


def get_conn_for_db(database_name):
    if database_name in conn_cache:
        return conn_cache[database_name]
    conn = connect_to(pg8000, database_name)
    conn_cache[database_name] = conn
    return conn


if table_sample:
    section("Timed export sample")
    for item in table_sample:
        db_name = item["database"]
        schema_name = item["schema"]
        table_name = item["name"]
        qualified = f"{quote_ident(schema_name)}.{quote_ident(table_name)}"
        timing = {
            "database": db_name,
            "schema": schema_name,
            "table": table_name,
            "qualified_name": f"{schema_name}.{table_name}",
            "table_size_bytes": item["total_bytes"],
            "row_count": 0,
            "method": "",
            "elapsed_seconds": 0.0,
            "bytes_exported": 0,
            "bytes_per_second": 0.0,
            "rows_per_second": 0.0,
            "error": "",
        }
        try:
            conn = get_conn_for_db(db_name)
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {qualified}")
            row_count_row = cursor.fetchone()
            row_count = int(row_count_row[0]) if row_count_row else 0
            timing["row_count"] = row_count
            copy_stream = io.StringIO()
            start = time.time()
            cursor.execute(f"COPY {qualified} TO STDOUT WITH CSV", stream=copy_stream)
            elapsed = max(time.time() - start, 1e-9)
            payload = copy_stream.getvalue()
            byte_count = len(payload.encode("utf-8"))
            timing["method"] = "COPY TO STDOUT WITH CSV"
            timing["elapsed_seconds"] = elapsed
            timing["bytes_exported"] = byte_count
            timing["bytes_per_second"] = float(byte_count) / elapsed if byte_count > 0 else 0.0
            timing["rows_per_second"] = float(row_count) / elapsed if row_count > 0 else 0.0
            timings.append(timing)
            ok(
                timing["qualified_name"],
                f"db={db_name}, rows={row_count}, bytes={byte_count}, bytes_per_sec={timing['bytes_per_second']:.2f}",
            )
            cursor.close()
        except Exception as exc:
            timing["error"] = str(exc)
            timing["method"] = "FAILED"
            timings.append(timing)
            info(
                timing["qualified_name"],
                f"db={db_name}, export failed: {exc}",
            )

for conn in conn_cache.values():
    try:
        conn.close()
    except Exception:
        pass

successful_timings = [item for item in timings if item["bytes_per_second"] > 0]
aggregate_bytes_per_second = 0.0
aggregate_rows_per_second = 0.0
if successful_timings:
    aggregate_bytes = sum(item["bytes_exported"] for item in successful_timings)
    aggregate_elapsed = sum(item["elapsed_seconds"] for item in successful_timings)
    aggregate_rows = sum(item["row_count"] for item in successful_timings)
    if aggregate_elapsed > 0:
        aggregate_bytes_per_second = float(aggregate_bytes) / float(aggregate_elapsed)
        aggregate_rows_per_second = float(aggregate_rows) / float(aggregate_elapsed)

total_non_system_table_bytes = int(inventory.get("summary", {}).get("total_non_system_table_bytes", 0) or 0)
estimated_total_seconds = 0.0
if aggregate_bytes_per_second > 0:
    estimated_total_seconds = float(total_non_system_table_bytes) / aggregate_bytes_per_second

db_estimates = []
for db_info in inventory.get("databases", []):
    if not db_info.get("connection_ok"):
        continue
    db_table_bytes = int(db_info.get("table_total_bytes", 0) or 0)
    db_seconds = 0.0
    if aggregate_bytes_per_second > 0:
        db_seconds = float(db_table_bytes) / aggregate_bytes_per_second
    db_estimates.append(
        {
            "database": db_info.get("name"),
            "table_total_bytes": db_table_bytes,
            "estimated_backup_seconds": db_seconds,
        }
    )
db_estimates.sort(key=lambda item: item["estimated_backup_seconds"], reverse=True)

strategy = ""
if aggregate_bytes_per_second <= 0:
    strategy = "Insufficient timed export data. Run probe4/probe6 again after ensuring table accessibility."
elif estimated_total_seconds <= 120:
    strategy = "Full all-database backup in one run is feasible as a manual user action."
elif estimated_total_seconds <= 900:
    strategy = "Full backup is feasible but slower; prefer per-database backups in UI with an optional full-backup action."
else:
    strategy = "Prefer per-database backups by default; full backup should be optional and clearly time-estimated."

section("Feasibility summary")
results.append(f"  inventory_source={inventory_source}")
results.append(f"  total_non_system_table_bytes={total_non_system_table_bytes}")
results.append(f"  sampled_tables={len(table_sample)}")
results.append(f"  successful_samples={len(successful_timings)}")
results.append(f"  aggregate_bytes_per_second={aggregate_bytes_per_second:.2f}")
results.append(f"  aggregate_rows_per_second={aggregate_rows_per_second:.2f}")
results.append(f"  estimated_total_backup_seconds={estimated_total_seconds:.2f}")
results.append(f"  estimated_total_backup_human={format_seconds(estimated_total_seconds) if estimated_total_seconds else 'n/a'}")
results.append(f"  recommendation={strategy}")

if db_estimates:
    section("Per-database estimated durations")
    for estimate in db_estimates:
        results.append(
            f"  {estimate['database']}: bytes={estimate['table_total_bytes']}, "
            + f"estimated={format_seconds(estimate['estimated_backup_seconds'])}"
        )

feasibility = {
    "inventory_source": inventory_source,
    "connection": {
        "host": PG_HOST,
        "port": PG_PORT,
        "user": PG_USER,
        "admin_database": PG_ADMIN_DATABASE,
    },
    "sample_table_count": len(table_sample),
    "timed_samples": timings,
    "aggregate_bytes_per_second": aggregate_bytes_per_second,
    "aggregate_rows_per_second": aggregate_rows_per_second,
    "total_non_system_table_bytes": total_non_system_table_bytes,
    "estimated_total_backup_seconds": estimated_total_seconds,
    "database_estimates": db_estimates,
    "recommendation": strategy,
}

feasibility_path = os.path.join(results_dir, "probe6_feasibility.json")
with open(feasibility_path, "w", encoding="utf-8") as handle:
    json.dump(feasibility, handle, indent=2, sort_keys=True)

results.append("")
results.append("[Feasibility JSON written]")
results.append(f"  {feasibility_path}")

output = "\n".join(results)
print(output)
results_path = write_text_file("probe6_results.txt", output)
print("")
print(f"Results written to {results_path}")
print("=== END Probe 6 ===")
