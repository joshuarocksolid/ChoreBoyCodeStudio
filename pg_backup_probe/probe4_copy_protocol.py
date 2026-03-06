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
PG_TARGET_DATABASE = os.environ.get("PG_TARGET_DATABASE", os.environ.get("PG_DATABASE", "postgres"))
PG_SAMPLE_TABLE = os.environ.get("PG_SAMPLE_TABLE", "public.acct_trans")

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


def parse_table_ref(table_ref):
    cleaned = table_ref.strip()
    if "." in cleaned:
        schema_name, table_name = cleaned.split(".", 1)
    else:
        schema_name, table_name = "public", cleaned
    schema_name = schema_name.strip().strip('"')
    table_name = table_name.strip().strip('"')
    if not schema_name or not table_name:
        raise ValueError("Invalid table reference")
    return schema_name, table_name


def quote_ident(identifier):
    return '"' + identifier.replace('"', '""') + '"'


for vendor_path in discover_vendor_paths():
    if vendor_path not in sys.path and os.path.isdir(vendor_path):
        sys.path.insert(0, vendor_path)

print("=== Probe 4: COPY Protocol and Throughput ===")

results.append("[Runtime]")
results.append(f"  Python: {sys.version}")
results.append(f"  Probe root: {probe_root}")
results.append(f"  Target database: {PG_TARGET_DATABASE}")
results.append(f"  Sample table: {PG_SAMPLE_TABLE}")

try:
    import pg8000
except Exception:
    fail("pg8000 import")
    output = "\n".join(results)
    print(output)
    path = write_text_file("probe4_results.txt", output)
    print("")
    print(f"Results written to {path}")
    print("=== END Probe 4 (early exit) ===")
    raise SystemExit(1)

section("pg8000 import")
ok("pg8000", getattr(pg8000, "__version__", "imported"))

schema_name, table_name = parse_table_ref(PG_SAMPLE_TABLE)
requested_schema_name = schema_name
requested_table_name = table_name
qualified_table = f"{quote_ident(schema_name)}.{quote_ident(table_name)}"

metrics = {
    "connection": {
        "host": PG_HOST,
        "port": PG_PORT,
        "user": PG_USER,
        "database": PG_TARGET_DATABASE,
    },
    "sample_table": f"{schema_name}.{table_name}",
    "copy_protocol": {"supported": False, "error": ""},
    "temp_table_copy": {},
    "sample_table_copy": {},
    "fallback_select_scan": {},
}

conn = None
probe_success = True
try:
    conn = pg8000.connect(
        user=PG_USER,
        host=PG_HOST,
        database=PG_TARGET_DATABASE,
        port=PG_PORT,
        password=PG_PASSWORD,
        timeout=10,
        application_name="pg_backup_probe_4",
    )
    section("Connection")
    ok("connect", f"{PG_USER}@{PG_HOST}:{PG_PORT}/{PG_TARGET_DATABASE}")
    cursor = conn.cursor()

    section("COPY smoke test with temp table")
    temp_csv = ""
    try:
        cursor.execute(
            """
            CREATE TEMP TABLE pg_backup_probe_copy_types (
                id INTEGER,
                txt TEXT,
                amount NUMERIC(10,2),
                created_at TIMESTAMP,
                is_active BOOLEAN
            )
            """
        )
        cursor.execute(
            """
            INSERT INTO pg_backup_probe_copy_types (id, txt, amount, created_at, is_active)
            VALUES
                (1, 'plain text', 10.25, '2026-03-01 10:11:12', TRUE),
                (2, E'line1\nline2', NULL, '2026-03-01 10:11:13', FALSE),
                (3, 'comma,quote "value"', 99.99, NULL, NULL)
            """
        )
        stream = io.StringIO()
        start = time.time()
        cursor.execute(
            "COPY pg_backup_probe_copy_types TO STDOUT WITH CSV HEADER",
            stream=stream,
        )
        elapsed = max(time.time() - start, 1e-9)
        temp_csv = stream.getvalue()
        temp_bytes = len(temp_csv.encode("utf-8"))
        temp_lines = temp_csv.splitlines()
        metrics["copy_protocol"]["supported"] = True
        metrics["temp_table_copy"] = {
            "elapsed_seconds": elapsed,
            "bytes": temp_bytes,
            "line_count": len(temp_lines),
            "preview": temp_lines[:6],
        }
        ok("copy temp table", f"bytes={temp_bytes}, elapsed={elapsed:.6f}s")
        temp_csv_path = write_text_file("probe4_temp_table_copy.csv", temp_csv)
        info("temp copy file", temp_csv_path)
    except Exception as exc:
        metrics["copy_protocol"]["supported"] = False
        metrics["copy_protocol"]["error"] = str(exc)
        info("copy temp table", f"failed: {exc}")

    section("Sample table row count")
    row_count = 0
    table_exists = False
    cursor.execute(
        """
        SELECT EXISTS(
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_name = %s
              AND table_type = 'BASE TABLE'
        )
        """,
        (schema_name, table_name),
    )
    exists_row = cursor.fetchone()
    table_exists = bool(exists_row[0]) if exists_row else False
    if not table_exists:
        cursor.execute(
            """
            SELECT n.nspname, c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'r'
              AND n.nspname NOT IN ('pg_catalog', 'information_schema')
            ORDER BY pg_total_relation_size(c.oid) DESC, n.nspname, c.relname
            LIMIT 1
            """
        )
        fallback_row = cursor.fetchone()
        if fallback_row:
            schema_name = fallback_row[0]
            table_name = fallback_row[1]
            qualified_table = f"{quote_ident(schema_name)}.{quote_ident(table_name)}"
            metrics["sample_table"] = f"{schema_name}.{table_name}"
            table_exists = True
            info(
                "sample table fallback",
                f"requested={requested_schema_name}.{requested_table_name}, using={schema_name}.{table_name}",
            )
    if table_exists:
        ok("sample table exists", f"{schema_name}.{table_name}")
        cursor.execute(f"SELECT COUNT(*) FROM {qualified_table}")
        count_row = cursor.fetchone()
        row_count = int(count_row[0]) if count_row else 0
        info("sample table row_count", str(row_count))
    else:
        info("sample table exists", "NO")

    copy_success = False
    if table_exists and metrics["copy_protocol"]["supported"]:
        section("Sample table COPY throughput")
        try:
            stream = io.StringIO()
            start = time.time()
            cursor.execute(f"COPY {qualified_table} TO STDOUT WITH CSV", stream=stream)
            elapsed = max(time.time() - start, 1e-9)
            payload = stream.getvalue()
            byte_count = len(payload.encode("utf-8"))
            rows_per_sec = float(row_count) / elapsed if row_count > 0 else 0.0
            bytes_per_sec = float(byte_count) / elapsed
            copy_success = True
            metrics["sample_table_copy"] = {
                "method": "COPY TO STDOUT WITH CSV",
                "elapsed_seconds": elapsed,
                "row_count": row_count,
                "bytes": byte_count,
                "rows_per_second": rows_per_sec,
                "bytes_per_second": bytes_per_sec,
            }
            ok(
                "sample table copy",
                f"rows={row_count}, bytes={byte_count}, rows_per_sec={rows_per_sec:.2f}, bytes_per_sec={bytes_per_sec:.2f}",
            )
            preview = "\n".join(payload.splitlines()[:50])
            preview_path = write_text_file("probe4_sample_copy_preview.csv", preview)
            info("sample copy preview file", preview_path)
        except Exception as exc:
            info("sample table copy", f"failed: {exc}")

    if table_exists and not copy_success:
        section("Fallback batched SELECT scan")
        try:
            start = time.time()
            cursor.execute(f"SELECT * FROM {qualified_table}")
            batch_size = 2000
            scanned_rows = 0
            estimated_bytes = 0
            while True:
                batch = cursor.fetchmany(batch_size)
                if not batch:
                    break
                scanned_rows += len(batch)
                for row in batch:
                    estimated_bytes += len(str(row).encode("utf-8"))
            elapsed = max(time.time() - start, 1e-9)
            rows_per_sec = float(scanned_rows) / elapsed if scanned_rows > 0 else 0.0
            bytes_per_sec = float(estimated_bytes) / elapsed if estimated_bytes > 0 else 0.0
            metrics["fallback_select_scan"] = {
                "method": "SELECT * + fetchmany",
                "elapsed_seconds": elapsed,
                "row_count": scanned_rows,
                "estimated_bytes": estimated_bytes,
                "rows_per_second": rows_per_sec,
                "bytes_per_second": bytes_per_sec,
            }
            ok(
                "fallback scan",
                f"rows={scanned_rows}, est_bytes={estimated_bytes}, rows_per_sec={rows_per_sec:.2f}, bytes_per_sec={bytes_per_sec:.2f}",
            )
        except Exception:
            fail("fallback scan")

    cursor.close()
except Exception:
    fail("probe execution")
    probe_success = False
finally:
    if conn is not None:
        try:
            conn.close()
            section("Connection close")
            ok("close connection")
        except Exception:
            fail("close connection")

metrics_path = os.path.join(results_dir, "probe4_metrics.json")
with open(metrics_path, "w", encoding="utf-8") as handle:
    json.dump(metrics, handle, indent=2, sort_keys=True)

results.append("")
results.append("[Metrics file written]")
results.append(f"  {metrics_path}")

output = "\n".join(results)
print(output)
results_path = write_text_file("probe4_results.txt", output)
print("")
print(f"Results written to {results_path}")
print("=== END Probe 4 ===")
if not probe_success:
    raise SystemExit(1)
