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


def quote_ident(identifier):
    return '"' + identifier.replace('"', '""') + '"'


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


for vendor_path in discover_vendor_paths():
    if vendor_path not in sys.path and os.path.isdir(vendor_path):
        sys.path.insert(0, vendor_path)

print("=== Probe 3: DDL Extraction ===")

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
    path = write_text_file("probe3_results.txt", output)
    print("")
    print(f"Results written to {path}")
    print("=== END Probe 3 (early exit) ===")
    raise SystemExit(1)

section("pg8000 import")
ok("pg8000", getattr(pg8000, "__version__", "imported"))

schema_name, table_name = parse_table_ref(PG_SAMPLE_TABLE)
requested_schema_name = schema_name
requested_table_name = table_name

metadata = {
    "connection": {
        "host": PG_HOST,
        "port": PG_PORT,
        "database": PG_TARGET_DATABASE,
        "user": PG_USER,
    },
    "table": {
        "schema": schema_name,
        "name": table_name,
        "qualified_name": f"{schema_name}.{table_name}",
    },
    "columns": [],
    "constraints": {"primary_or_unique": [], "foreign_keys": []},
    "indexes": [],
    "sequences": [],
    "sequence_defaults": [],
    "views_sample": [],
    "functions_sample": [],
}

conn = None
generated_sql_parts = []
probe_success = True
try:
    conn = pg8000.connect(
        user=PG_USER,
        host=PG_HOST,
        database=PG_TARGET_DATABASE,
        port=PG_PORT,
        password=PG_PASSWORD,
        timeout=10,
        application_name="pg_backup_probe_3",
    )
    section("Connection")
    ok("connect", f"{PG_USER}@{PG_HOST}:{PG_PORT}/{PG_TARGET_DATABASE}")
    cursor = conn.cursor()

    section("Table existence")
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
            metadata["table"] = {
                "schema": schema_name,
                "name": table_name,
                "qualified_name": f"{schema_name}.{table_name}",
            }
            info(
                "sample table fallback",
                f"requested={requested_schema_name}.{requested_table_name}, using={schema_name}.{table_name}",
            )
        else:
            info("table exists", "NO")
            raise RuntimeError(f"Table {requested_schema_name}.{requested_table_name} does not exist")
    ok("table exists", f"{schema_name}.{table_name}")

    section("Columns")
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
    for row in column_rows:
        col = {
            "name": row[0],
            "type": row[1],
            "not_null": bool(row[2]),
            "default": row[3],
        }
        metadata["columns"].append(col)
        results.append(
            f"  {col['name']}: type={col['type']} not_null={col['not_null']} default={col['default']}"
        )
    ok("column_count", str(len(metadata["columns"])))

    section("Primary key and unique constraints")
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
    constraint_rows = cursor.fetchall()
    for row in constraint_rows:
        constraint = {
            "constraint_name": row[0],
            "constraint_type": row[1],
            "column_list": row[2] or "",
        }
        metadata["constraints"]["primary_or_unique"].append(constraint)
        results.append(
            f"  {constraint['constraint_name']}: type={constraint['constraint_type']} columns={constraint['column_list']}"
        )
    info("primary_or_unique_count", str(len(constraint_rows)))

    section("Foreign keys")
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
    foreign_rows = cursor.fetchall()
    for row in foreign_rows:
        fk = {
            "constraint_name": row[0],
            "local_columns": row[1] or "",
            "foreign_table_schema": row[2],
            "foreign_table_name": row[3],
            "foreign_columns": row[4] or "",
            "update_rule": row[5],
            "delete_rule": row[6],
        }
        metadata["constraints"]["foreign_keys"].append(fk)
        results.append(
            "  "
            + f"{fk['constraint_name']}: ({fk['local_columns']}) -> "
            + f"{fk['foreign_table_schema']}.{fk['foreign_table_name']} ({fk['foreign_columns']}) "
            + f"update={fk['update_rule']} delete={fk['delete_rule']}"
        )
    info("foreign_key_count", str(len(foreign_rows)))

    section("Indexes")
    cursor.execute(
        """
        SELECT
            indexname,
            indexdef
        FROM pg_indexes
        WHERE schemaname = %s
          AND tablename = %s
        ORDER BY indexname
        """,
        (schema_name, table_name),
    )
    index_rows = cursor.fetchall()
    for row in index_rows:
        index_info = {"name": row[0], "definition": row[1]}
        metadata["indexes"].append(index_info)
        results.append(f"  {index_info['name']}: {index_info['definition']}")
    info("index_count", str(len(index_rows)))

    section("Sequences")
    cursor.execute(
        """
        SELECT
            sequence_schema,
            sequence_name
        FROM information_schema.sequences
        WHERE sequence_schema = %s
        ORDER BY sequence_name
        """,
        (schema_name,),
    )
    sequence_rows = cursor.fetchall()
    for row in sequence_rows:
        seq = {"schema": row[0], "name": row[1]}
        metadata["sequences"].append(seq)
    info("sequence_count_in_schema", str(len(sequence_rows)))

    cursor.execute(
        """
        SELECT
            column_name,
            column_default
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
          AND column_default LIKE 'nextval(%'
        ORDER BY ordinal_position
        """,
        (schema_name, table_name),
    )
    sequence_default_rows = cursor.fetchall()
    for row in sequence_default_rows:
        seq_default = {"column_name": row[0], "column_default": row[1]}
        metadata["sequence_defaults"].append(seq_default)
        results.append(f"  {seq_default['column_name']}: {seq_default['column_default']}")
    info("sequence_defaults_on_table", str(len(sequence_default_rows)))

    section("Views sample")
    try:
        cursor.execute(
            """
            SELECT
                schemaname,
                viewname,
                definition
            FROM pg_views
            WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
            ORDER BY schemaname, viewname
            LIMIT 10
            """
        )
        view_rows = cursor.fetchall()
        for row in view_rows:
            view_data = {"schema": row[0], "name": row[1], "definition": row[2]}
            metadata["views_sample"].append(view_data)
            results.append(f"  {view_data['schema']}.{view_data['name']}")
        info("views_sample_count", str(len(view_rows)))
    except Exception as exc:
        info("views sample", f"failed: {exc}")

    section("Functions sample")
    try:
        cursor.execute(
            """
            SELECT
                n.nspname,
                p.proname,
                pg_get_functiondef(p.oid)
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
            ORDER BY n.nspname, p.proname
            LIMIT 10
            """
        )
        function_rows = cursor.fetchall()
        for row in function_rows:
            fn_data = {"schema": row[0], "name": row[1], "definition": row[2]}
            metadata["functions_sample"].append(fn_data)
            results.append(f"  {fn_data['schema']}.{fn_data['name']}")
        info("functions_sample_count", str(len(function_rows)))
    except Exception as exc:
        info("functions sample", f"failed: {exc}")

    cursor.close()
except Exception:
    fail("ddl extraction")
    probe_success = False
finally:
    if conn is not None:
        try:
            conn.close()
            section("Connection close")
            ok("close connection")
        except Exception:
            fail("close connection")

ddl_path = ""
metadata_path = os.path.join(results_dir, "probe3_metadata.json")
section("Generated SQL")
if probe_success and metadata["columns"]:
    qualified_table = f"{quote_ident(schema_name)}.{quote_ident(table_name)}"
    column_sql_lines = []
    for column in metadata["columns"]:
        col_line = f"{quote_ident(column['name'])} {column['type']}"
        if column["default"] is not None:
            col_line += f" DEFAULT {column['default']}"
        if column["not_null"]:
            col_line += " NOT NULL"
        column_sql_lines.append(col_line)

    generated_sql_parts.append(f"CREATE TABLE {qualified_table} (\n    " + ",\n    ".join(column_sql_lines) + "\n);")

    for constraint in metadata["constraints"]["primary_or_unique"]:
        generated_sql_parts.append(
            "ALTER TABLE "
            + f"{qualified_table} "
            + "ADD CONSTRAINT "
            + f"{quote_ident(constraint['constraint_name'])} "
            + f"{constraint['constraint_type']} ({constraint['column_list']});"
        )

    for fk in metadata["constraints"]["foreign_keys"]:
        generated_sql_parts.append(
            "ALTER TABLE "
            + f"{qualified_table} "
            + "ADD CONSTRAINT "
            + f"{quote_ident(fk['constraint_name'])} "
            + f"FOREIGN KEY ({fk['local_columns']}) "
            + "REFERENCES "
            + f"{quote_ident(fk['foreign_table_schema'])}.{quote_ident(fk['foreign_table_name'])} "
            + f"({fk['foreign_columns']}) "
            + f"ON UPDATE {fk['update_rule']} "
            + f"ON DELETE {fk['delete_rule']};"
        )

    for index_info in metadata["indexes"]:
        if index_info["definition"]:
            generated_sql_parts.append(index_info["definition"] + ";")

    generated_sql = "\n\n".join(generated_sql_parts) + "\n"
    results.append(f"  generated_statement_count={len(generated_sql_parts)}")
    ddl_path = write_text_file("probe3_extracted_ddl.sql", generated_sql)
else:
    results.append("  generated_statement_count=0")
    info("generated sql", "skipped due prior failure")

with open(metadata_path, "w", encoding="utf-8") as handle:
    json.dump(metadata, handle, indent=2, sort_keys=True)

results.append("")
results.append("[Generated files]")
if ddl_path:
    results.append(f"  {ddl_path}")
results.append(f"  {metadata_path}")

output = "\n".join(results)
print(output)
results_path = write_text_file("probe3_results.txt", output)
print("")
print(f"Results written to {results_path}")
print("=== END Probe 3 ===")
if not probe_success:
    raise SystemExit(1)
