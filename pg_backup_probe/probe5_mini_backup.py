from __future__ import annotations

import datetime
import json
import math
import os
import sys
import time
import traceback
from decimal import Decimal

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
PG_BACKUP_ROW_LIMIT_RAW = os.environ.get("PG_BACKUP_ROW_LIMIT", "").strip()
PG_BACKUP_ROW_LIMIT = int(PG_BACKUP_ROW_LIMIT_RAW) if PG_BACKUP_ROW_LIMIT_RAW else None

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


def sql_literal(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "'NaN'::double precision"
        if math.isinf(value):
            return "'Infinity'::double precision" if value > 0 else "'-Infinity'::double precision"
        return repr(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime.datetime):
        return "'" + value.isoformat(sep=" ") .replace("'", "''") + "'"
    if isinstance(value, datetime.date):
        return "'" + value.isoformat().replace("'", "''") + "'"
    if isinstance(value, datetime.time):
        return "'" + value.isoformat().replace("'", "''") + "'"
    if isinstance(value, bytes):
        return "'\\x" + value.hex() + "'::bytea"
    return "'" + str(value).replace("'", "''") + "'"


for vendor_path in discover_vendor_paths():
    if vendor_path not in sys.path and os.path.isdir(vendor_path):
        sys.path.insert(0, vendor_path)

print("=== Probe 5: End-to-End Mini Backup ===")

results.append("[Runtime]")
results.append(f"  Python: {sys.version}")
results.append(f"  Probe root: {probe_root}")
results.append(f"  Target database: {PG_TARGET_DATABASE}")
results.append(f"  Sample table: {PG_SAMPLE_TABLE}")
if PG_BACKUP_ROW_LIMIT is not None:
    results.append(f"  Row limit override: {PG_BACKUP_ROW_LIMIT}")

try:
    import pg8000
except Exception:
    fail("pg8000 import")
    output = "\n".join(results)
    print(output)
    path = write_text_file("probe5_results.txt", output)
    print("")
    print(f"Results written to {path}")
    print("=== END Probe 5 (early exit) ===")
    raise SystemExit(1)

section("pg8000 import")
ok("pg8000", getattr(pg8000, "__version__", "imported"))

schema_name, table_name = parse_table_ref(PG_SAMPLE_TABLE)
requested_schema_name = schema_name
requested_table_name = table_name
qualified_table = f"{quote_ident(schema_name)}.{quote_ident(table_name)}"

summary = {
    "connection": {
        "host": PG_HOST,
        "port": PG_PORT,
        "user": PG_USER,
        "database": PG_TARGET_DATABASE,
    },
    "table": f"{schema_name}.{table_name}",
    "row_limit": PG_BACKUP_ROW_LIMIT,
    "row_count": 0,
    "insert_statement_count": 0,
    "file_size_bytes": 0,
    "elapsed_seconds": 0.0,
    "syntax_check": {"performed": False, "rows_checked": 0, "ok": False, "error": ""},
}

conn = None
backup_path = ""
probe_success = True
try:
    conn = pg8000.connect(
        user=PG_USER,
        host=PG_HOST,
        database=PG_TARGET_DATABASE,
        port=PG_PORT,
        password=PG_PASSWORD,
        timeout=10,
        application_name="pg_backup_probe_5",
    )
    section("Connection")
    ok("connect", f"{PG_USER}@{PG_HOST}:{PG_PORT}/{PG_TARGET_DATABASE}")
    cursor = conn.cursor()

    section("Metadata extraction")
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
    exists = bool(exists_row[0]) if exists_row else False
    if not exists:
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
            summary["table"] = f"{schema_name}.{table_name}"
            info(
                "sample table fallback",
                f"requested={requested_schema_name}.{requested_table_name}, using={schema_name}.{table_name}",
            )
        else:
            raise RuntimeError(f"Table {requested_schema_name}.{requested_table_name} does not exist")
    ok("table exists", f"{schema_name}.{table_name}")

    cursor.execute(
        """
        SELECT
            a.attname AS column_name,
            pg_catalog.format_type(a.atttypid, a.atttypmod) AS formatted_type,
            a.attnotnull AS not_null,
            pg_catalog.pg_get_expr(ad.adbin, ad.adrelid) AS default_expr
        FROM pg_catalog.pg_attribute a
        JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_catalog.pg_attrdef ad ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum
        WHERE n.nspname = %s
          AND c.relname = %s
          AND a.attnum > 0
          AND NOT a.attisdropped
        ORDER BY a.attnum
        """,
        (schema_name, table_name),
    )
    column_rows = cursor.fetchall()
    if not column_rows:
        raise RuntimeError(f"Table {schema_name}.{table_name} has no columns")
    columns = []
    for row in column_rows:
        columns.append(
            {
                "name": row[0],
                "type": row[1],
                "not_null": bool(row[2]),
                "default": row[3],
            }
        )
    ok("column_count", str(len(columns)))

    cursor.execute(
        """
        SELECT
            tc.constraint_name,
            tc.constraint_type,
            string_agg(quote_ident(kcu.column_name), ', ' ORDER BY kcu.ordinal_position) AS column_list
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_schema = kcu.constraint_schema
         AND tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
         AND tc.table_name = kcu.table_name
        WHERE tc.table_schema = %s
          AND tc.table_name = %s
          AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
        GROUP BY tc.constraint_name, tc.constraint_type
        ORDER BY tc.constraint_name
        """,
        (schema_name, table_name),
    )
    primary_unique_constraints = cursor.fetchall()
    info("primary_or_unique_count", str(len(primary_unique_constraints)))

    cursor.execute(
        """
        SELECT
            tc.constraint_name,
            string_agg(quote_ident(kcu.column_name), ', ' ORDER BY kcu.ordinal_position) AS local_columns,
            ccu.table_schema AS foreign_table_schema,
            ccu.table_name AS foreign_table_name,
            string_agg(quote_ident(ccu.column_name), ', ' ORDER BY kcu.ordinal_position) AS foreign_columns,
            rc.update_rule,
            rc.delete_rule
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_schema = kcu.constraint_schema
         AND tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
         AND tc.table_name = kcu.table_name
        JOIN information_schema.referential_constraints rc
          ON tc.constraint_schema = rc.constraint_schema
         AND tc.constraint_name = rc.constraint_name
        JOIN information_schema.constraint_column_usage ccu
          ON rc.unique_constraint_schema = ccu.constraint_schema
         AND rc.unique_constraint_name = ccu.constraint_name
        WHERE tc.table_schema = %s
          AND tc.table_name = %s
          AND tc.constraint_type = 'FOREIGN KEY'
        GROUP BY
            tc.constraint_name,
            ccu.table_schema,
            ccu.table_name,
            rc.update_rule,
            rc.delete_rule
        ORDER BY tc.constraint_name
        """,
        (schema_name, table_name),
    )
    foreign_constraints = cursor.fetchall()
    info("foreign_key_count", str(len(foreign_constraints)))

    cursor.execute(
        """
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = %s
          AND tablename = %s
        ORDER BY indexname
        """,
        (schema_name, table_name),
    )
    indexes = cursor.fetchall()
    info("index_count", str(len(indexes)))

    section("Backup SQL generation")
    safe_table_name = f"{schema_name}_{table_name}".replace(".", "_").replace("/", "_")
    backup_filename = f"probe5_{safe_table_name}_mini_backup.sql"
    backup_path = os.path.join(results_dir, backup_filename)

    create_columns = []
    for column in columns:
        column_line = f"{quote_ident(column['name'])} {column['type']}"
        if column["default"] is not None:
            column_line += f" DEFAULT {column['default']}"
        if column["not_null"]:
            column_line += " NOT NULL"
        create_columns.append(column_line)
    create_table_sql = f"CREATE TABLE {qualified_table} (\n    " + ",\n    ".join(create_columns) + "\n);\n"

    validation_table = "pg_backup_probe5_syntax_test"
    validation_create_sql = (
        f"CREATE TEMP TABLE {quote_ident(validation_table)} (\n    " + ",\n    ".join(create_columns) + "\n)"
    )
    validation_cursor = conn.cursor()
    validation_cursor.execute(validation_create_sql)
    summary["syntax_check"]["performed"] = True
    summary["syntax_check"]["ok"] = True
    syntax_rows_to_check = 5
    syntax_checked = 0

    select_columns_sql = ", ".join([quote_ident(column["name"]) for column in columns])
    select_sql = f"SELECT {select_columns_sql} FROM {qualified_table}"
    if PG_BACKUP_ROW_LIMIT is not None:
        select_sql += f" LIMIT {PG_BACKUP_ROW_LIMIT}"

    start = time.time()
    with open(backup_path, "w", encoding="utf-8") as backup_file:
        backup_file.write("BEGIN;\n\n")
        backup_file.write(f"CREATE SCHEMA IF NOT EXISTS {quote_ident(schema_name)};\n\n")
        backup_file.write(f"DROP TABLE IF EXISTS {qualified_table} CASCADE;\n\n")
        backup_file.write(create_table_sql)
        backup_file.write("\n")

        for row in primary_unique_constraints:
            constraint_name = row[0]
            constraint_type = row[1]
            column_list = row[2] or ""
            line = (
                "ALTER TABLE "
                + f"{qualified_table} "
                + "ADD CONSTRAINT "
                + f"{quote_ident(constraint_name)} "
                + f"{constraint_type} ({column_list});\n"
            )
            backup_file.write(line)

        for row in foreign_constraints:
            constraint_name = row[0]
            local_columns = row[1] or ""
            foreign_schema = row[2]
            foreign_table = row[3]
            foreign_columns = row[4] or ""
            update_rule = row[5]
            delete_rule = row[6]
            line = (
                "ALTER TABLE "
                + f"{qualified_table} "
                + "ADD CONSTRAINT "
                + f"{quote_ident(constraint_name)} "
                + f"FOREIGN KEY ({local_columns}) "
                + "REFERENCES "
                + f"{quote_ident(foreign_schema)}.{quote_ident(foreign_table)} "
                + f"({foreign_columns}) "
                + f"ON UPDATE {update_rule} "
                + f"ON DELETE {delete_rule};\n"
            )
            backup_file.write(line)

        if primary_unique_constraints or foreign_constraints:
            backup_file.write("\n")

        for row in indexes:
            index_def = row[1]
            if index_def:
                backup_file.write(index_def.rstrip(";") + ";\n")

        if indexes:
            backup_file.write("\n")

        cursor.execute(select_sql)
        insert_target = qualified_table
        insert_columns = ", ".join([quote_ident(column["name"]) for column in columns])
        insert_validation_target = quote_ident(validation_table)
        batch_size = 1000
        while True:
            batch = cursor.fetchmany(batch_size)
            if not batch:
                break
            for db_row in batch:
                literal_values = [sql_literal(value) for value in db_row]
                values_sql = ", ".join(literal_values)
                insert_sql = f"INSERT INTO {insert_target} ({insert_columns}) VALUES ({values_sql});\n"
                backup_file.write(insert_sql)
                summary["row_count"] += 1
                summary["insert_statement_count"] += 1

                if syntax_checked < syntax_rows_to_check:
                    validation_insert_sql = (
                        f"INSERT INTO {insert_validation_target} ({insert_columns}) VALUES ({values_sql})"
                    )
                    try:
                        validation_cursor.execute(validation_insert_sql)
                        syntax_checked += 1
                    except Exception as exc:
                        summary["syntax_check"]["ok"] = False
                        summary["syntax_check"]["error"] = str(exc)
                        raise

        backup_file.write("\nCOMMIT;\n")

    summary["syntax_check"]["rows_checked"] = syntax_checked
    summary["elapsed_seconds"] = max(time.time() - start, 0.0)
    summary["file_size_bytes"] = os.path.getsize(backup_path)

    ok(
        "backup generated",
        f"rows={summary['row_count']}, file_size={summary['file_size_bytes']}, elapsed={summary['elapsed_seconds']:.6f}s",
    )
    if summary["syntax_check"]["ok"]:
        ok("syntax check", f"rows_checked={summary['syntax_check']['rows_checked']}")
    else:
        info("syntax check", f"failed: {summary['syntax_check']['error']}")
    info("backup file", backup_path)

    validation_cursor.close()
    cursor.close()
except Exception:
    fail("mini backup probe")
    probe_success = False
finally:
    if conn is not None:
        try:
            conn.close()
            section("Connection close")
            ok("close connection")
        except Exception:
            fail("close connection")

summary_path = os.path.join(results_dir, "probe5_summary.json")
with open(summary_path, "w", encoding="utf-8") as handle:
    json.dump(summary, handle, indent=2, sort_keys=True)

results.append("")
results.append("[Generated files]")
if backup_path:
    results.append(f"  {backup_path}")
results.append(f"  {summary_path}")

output = "\n".join(results)
print(output)
results_path = write_text_file("probe5_results.txt", output)
print("")
print(f"Results written to {results_path}")
print("=== END Probe 5 ===")
if not probe_success:
    raise SystemExit(1)
