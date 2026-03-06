from __future__ import annotations

import json
import os
import sys
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
PG_DATABASE = os.environ.get("PG_DATABASE", "postgres")

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


def write_results_file(filename, content):
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


for vendor_path in discover_vendor_paths():
    if vendor_path not in sys.path and os.path.isdir(vendor_path):
        sys.path.insert(0, vendor_path)

print("=== Probe 2: Database Inventory and Sizing ===")

results.append("[Runtime]")
results.append(f"  Python: {sys.version}")
results.append(f"  Probe root: {probe_root}")
results.append(f"  Results dir: {results_dir}")

try:
    import pg8000
except Exception:
    fail("pg8000 import")
    output = "\n".join(results)
    print(output)
    path = write_results_file("probe2_results.txt", output)
    print("")
    print(f"Results written to {path}")
    print("=== END Probe 2 (early exit) ===")
    raise SystemExit(1)

section("pg8000 import")
ok("pg8000", getattr(pg8000, "__version__", "imported"))


def connect_to(database_name):
    return pg8000.connect(
        user=PG_USER,
        host=PG_HOST,
        database=database_name,
        port=PG_PORT,
        password=PG_PASSWORD,
        timeout=10,
        application_name="pg_backup_probe_2",
    )


inventory = {
    "connection": {
        "host": PG_HOST,
        "port": PG_PORT,
        "user": PG_USER,
        "admin_database": PG_DATABASE,
    },
    "databases": [],
    "summary": {},
}

section("Database list")
admin_conn = None
database_rows = []
try:
    admin_conn = connect_to(PG_DATABASE)
    ok("connect admin", f"{PG_USER}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}")
    cursor = admin_conn.cursor()
    cursor.execute(
        """
        SELECT
            d.datname,
            pg_get_userbyid(d.datdba) AS owner,
            pg_encoding_to_char(d.encoding) AS encoding,
            d.datcollate,
            d.datctype,
            d.datistemplate,
            d.datallowconn,
            pg_database_size(d.datname) AS size_bytes
        FROM pg_database d
        ORDER BY d.datname
        """
    )
    database_rows = cursor.fetchall()
    cursor.close()
    ok("pg_database query", f"{len(database_rows)} database(s)")
except Exception:
    fail("database listing")
    if admin_conn is not None:
        try:
            admin_conn.close()
        except Exception:
            pass
    output = "\n".join(results)
    print(output)
    path = write_results_file("probe2_results.txt", output)
    print("")
    print(f"Results written to {path}")
    print("=== END Probe 2 (early exit) ===")
    raise SystemExit(1)

total_database_bytes = 0
total_non_system_tables = 0
total_non_system_table_bytes = 0
connectable_database_count = 0
largest_table = None

for row in database_rows:
    db_name = row[0]
    owner = row[1]
    encoding = row[2]
    collate = row[3]
    ctype = row[4]
    is_template = bool(row[5])
    allow_conn = bool(row[6])
    size_bytes = int(row[7]) if row[7] is not None else 0
    total_database_bytes += size_bytes

    db_info = {
        "name": db_name,
        "owner": owner,
        "encoding": encoding,
        "collate": collate,
        "ctype": ctype,
        "is_template": is_template,
        "allow_connection": allow_conn,
        "size_bytes": size_bytes,
        "connection_ok": False,
        "error": "",
        "table_count": 0,
        "table_total_bytes": 0,
        "schema_table_counts": [],
        "tables_by_size": [],
    }
    inventory["databases"].append(db_info)
    results.append(
        f"  {db_name}: owner={owner}, template={is_template}, allow_conn={allow_conn}, size_bytes={size_bytes}"
    )

    if is_template or not allow_conn:
        continue

    conn = None
    try:
        conn = connect_to(db_name)
        db_info["connection_ok"] = True
        connectable_database_count += 1
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                table_schema,
                COUNT(*) AS table_count
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
              AND table_schema NOT IN ('pg_catalog', 'information_schema')
            GROUP BY table_schema
            ORDER BY table_count DESC, table_schema
            """
        )
        schema_rows = cursor.fetchall()
        schema_counts = []
        schema_total = 0
        for schema_row in schema_rows:
            schema_name = schema_row[0]
            schema_count = int(schema_row[1])
            schema_total += schema_count
            schema_counts.append({"schema": schema_name, "table_count": schema_count})
        db_info["schema_table_counts"] = schema_counts
        db_info["table_count"] = schema_total
        total_non_system_tables += schema_total

        cursor.execute(
            """
            SELECT
                n.nspname AS table_schema,
                c.relname AS table_name,
                c.reltuples::bigint AS est_rows,
                pg_relation_size(c.oid) AS heap_bytes,
                pg_total_relation_size(c.oid) AS total_bytes
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'r'
              AND n.nspname NOT IN ('pg_catalog', 'information_schema')
            ORDER BY total_bytes DESC, table_schema, table_name
            """
        )
        table_rows = cursor.fetchall()
        table_infos = []
        table_bytes = 0
        for table_row in table_rows:
            table_schema = table_row[0]
            table_name = table_row[1]
            est_rows = int(table_row[2]) if table_row[2] is not None else 0
            heap_bytes = int(table_row[3]) if table_row[3] is not None else 0
            total_bytes = int(table_row[4]) if table_row[4] is not None else 0
            table_bytes += total_bytes
            table_info = {
                "schema": table_schema,
                "name": table_name,
                "qualified_name": f"{table_schema}.{table_name}",
                "estimated_rows": est_rows,
                "heap_bytes": heap_bytes,
                "total_bytes": total_bytes,
            }
            table_infos.append(table_info)
            if largest_table is None or total_bytes > largest_table["total_bytes"]:
                largest_table = {
                    "database": db_name,
                    "schema": table_schema,
                    "name": table_name,
                    "qualified_name": f"{table_schema}.{table_name}",
                    "total_bytes": total_bytes,
                }
        db_info["tables_by_size"] = table_infos
        db_info["table_total_bytes"] = table_bytes
        total_non_system_table_bytes += table_bytes
        top_tables = table_infos[:5]
        if top_tables:
            details = ", ".join(
                [f"{table['qualified_name']}={table['total_bytes']}" for table in top_tables]
            )
            info(f"{db_name} top tables", details)
        else:
            info(f"{db_name} top tables", "none")
        cursor.close()
    except Exception as exc:
        db_info["error"] = str(exc)
        info(f"{db_name} connect", f"failed: {exc}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

if admin_conn is not None:
    try:
        admin_conn.close()
        ok("close admin connection")
    except Exception:
        fail("close admin connection")

inventory["summary"] = {
    "database_count": len(database_rows),
    "connectable_database_count": connectable_database_count,
    "total_database_bytes": total_database_bytes,
    "total_non_system_tables": total_non_system_tables,
    "total_non_system_table_bytes": total_non_system_table_bytes,
    "largest_table": largest_table,
}

section("Summary")
results.append(f"  database_count={len(database_rows)}")
results.append(f"  connectable_database_count={connectable_database_count}")
results.append(f"  total_database_bytes={total_database_bytes}")
results.append(f"  total_non_system_tables={total_non_system_tables}")
results.append(f"  total_non_system_table_bytes={total_non_system_table_bytes}")
if largest_table is not None:
    results.append(
        "  largest_table="
        f"{largest_table['database']}:{largest_table['qualified_name']}:{largest_table['total_bytes']}"
    )
else:
    results.append("  largest_table=none")

inventory_path = os.path.join(results_dir, "probe2_inventory.json")
with open(inventory_path, "w", encoding="utf-8") as handle:
    json.dump(inventory, handle, indent=2, sort_keys=True)

results.append("")
results.append("[Inventory JSON written]")
results.append(f"  {inventory_path}")

output = "\n".join(results)
print(output)
results_path = write_results_file("probe2_results.txt", output)
print("")
print(f"Results written to {results_path}")
print("=== END Probe 2 ===")
