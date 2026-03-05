#!/usr/bin/env python
"""
Probe 6 (JNI): JasperReports Fill and Export

Fills a compiled JasperReport and exports it to PDF and PNG page images.
Tests both the "empty datasource" (static) mode and optionally the
JDBC mode if probe 4 confirmed database connectivity.

Replaces the original probe6_jasper_fill_export.py which used subprocess
(blocked on ChoreBoy by mandatory access control).
"""
from __future__ import annotations

import os
import sys
import traceback

try:
    probe_root = os.path.dirname(os.path.abspath(__file__))
except NameError:
    probe_root = "/home/default/jasper_probe"

sys.path.insert(0, probe_root)

results_dir = os.path.join(probe_root, "results")
os.makedirs(results_dir, exist_ok=True)

PG_HOST = "localhost"
PG_PORT = "5432"
PG_USER = "postgres"
PG_PASSWORD = "true"
PG_DATABASE = "classicaccounting"

results = []


def section(title):
    results.append(f"\n[{title}]")


def ok(label, detail=""):
    suffix = f" ({detail})" if detail else ""
    results.append(f"  {label}: YES{suffix}")


def info(label, detail=""):
    suffix = f" ({detail})" if detail else ""
    results.append(f"  {label}{suffix}")


def write_results():
    output = "\n".join(results)
    print(output)
    results_path = os.path.join(results_dir, "probe6_results.txt")
    with open(results_path, "w") as f:
        f.write(output)
    print(f"\nResults written to {results_path}")


print("=== Probe 6 (JNI): JasperReports Fill and Export ===\n")

results.append("[Runtime]")
results.append(f"  Probe root: {probe_root}")

static_jrxml = os.path.join(probe_root, "test_reports", "hello_static.jrxml")
if not os.path.exists(static_jrxml):
    results.append(f"\n  ERROR: Test JRXML not found: {static_jrxml}")
    write_results()
    print("\n=== END Probe 6 (jrxml missing) ===")
    raise SystemExit(1)

section("1. Boot JVM via jni_helper")
try:
    import jni_helper
    jvm_ptr, env_ptr = jni_helper.ensure_jvm(probe_root)
    ok("JVM ready")
except Exception as e:
    info(f"JVM boot failed: {e}")
    info(traceback.format_exc())
    write_results()
    print("\n=== END Probe 6 (JVM boot failed) ===")
    raise SystemExit(1)

section("2. Static fill and export (empty datasource)")
static_output_dir = os.path.join(results_dir, "static_export")
os.makedirs(static_output_dir, exist_ok=True)

static_passed = False
try:
    output = jni_helper.call_java_main(
        env_ptr, "JasperFillExport",
        [static_jrxml, static_output_dir, "empty"]
    )

    for line in output.splitlines():
        parts = line.split("|", 1)
        tag = parts[0] if parts else ""
        detail = parts[1] if len(parts) > 1 else ""

        if tag.endswith("_OK"):
            ok(tag, detail)
        elif tag.endswith("_FAIL"):
            results.append(f"  {tag}: {detail}")
        else:
            results.append(f"  {line}")

    pdf_files = [f for f in os.listdir(static_output_dir) if f.endswith(".pdf")]
    png_files = [f for f in os.listdir(static_output_dir) if f.endswith(".png")]
    results.append(f"  Files in output: {len(pdf_files)} PDF, {len(png_files)} PNG")

    if pdf_files:
        for pdf in pdf_files:
            path = os.path.join(static_output_dir, pdf)
            results.append(f"    {pdf} ({os.path.getsize(path)} bytes)")
        static_passed = True

    if png_files:
        for png in png_files:
            path = os.path.join(static_output_dir, png)
            results.append(f"    {png} ({os.path.getsize(path)} bytes)")

except Exception as e:
    info(f"JasperFillExport (static) failed: {e}")
    info(traceback.format_exc())

section("3. JDBC fill and export (database)")
jdbc_url = f"jdbc:postgresql://{PG_HOST}:{PG_PORT}/{PG_DATABASE}"
db_jrxml = static_jrxml
db_output_dir = os.path.join(results_dir, "db_export")
os.makedirs(db_output_dir, exist_ok=True)

db_passed = False
try:
    output = jni_helper.call_java_main(
        env_ptr, "JasperFillExport",
        [db_jrxml, db_output_dir, "jdbc", jdbc_url, PG_USER, PG_PASSWORD]
    )

    for line in output.splitlines():
        parts = line.split("|", 1)
        tag = parts[0] if parts else ""
        detail = parts[1] if len(parts) > 1 else ""

        if tag.endswith("_OK"):
            ok(tag, detail)
        elif tag.endswith("_FAIL"):
            results.append(f"  {tag}: {detail}")
        else:
            results.append(f"  {line}")

    pdf_files = [f for f in os.listdir(db_output_dir) if f.endswith(".pdf")]
    png_files = [f for f in os.listdir(db_output_dir) if f.endswith(".png")]
    results.append(f"  Files in output: {len(pdf_files)} PDF, {len(png_files)} PNG")

    if pdf_files:
        for pdf in pdf_files:
            path = os.path.join(db_output_dir, pdf)
            results.append(f"    {pdf} ({os.path.getsize(path)} bytes)")
        db_passed = True

    if png_files:
        for png in png_files:
            path = os.path.join(db_output_dir, png)
            results.append(f"    {png} ({os.path.getsize(path)} bytes)")

except Exception as e:
    info(f"JasperFillExport (jdbc) failed: {e}")
    info(traceback.format_exc())
    results.append("  This failure is expected if PostgreSQL is not running or")
    results.append(f"  database '{PG_DATABASE}' does not exist.")
    results.append("  Static export above is the more important test.")

section("SUMMARY")
if static_passed:
    results.append("  Static fill+export: PASSED (PDF generated)")
else:
    results.append("  Static fill+export: FAILED")

if db_passed:
    results.append("  JDBC fill+export: PASSED (PDF generated)")
else:
    results.append("  JDBC fill+export: FAILED (may be expected)")

if static_passed:
    results.append("  JasperReports pipeline is functional via JNI.")
    results.append("  Ready for probe 7 (Qt print preview).")

write_results()
print("\n=== END Probe 6 ===")
