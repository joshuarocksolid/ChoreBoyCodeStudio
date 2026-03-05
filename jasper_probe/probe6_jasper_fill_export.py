#!/usr/bin/env python
"""
Probe 6: JasperReports Fill and Export
Tests filling a compiled report and exporting to PDF and PNG.
First tests with a static report (no DB), then optionally with a DB query.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback

try:
    probe_root = os.path.dirname(os.path.abspath(__file__))
except NameError:
    probe_root = "/home/default/jasper_probe"

results_dir = os.path.join(probe_root, "results")
os.makedirs(results_dir, exist_ok=True)

DISCOVERED_PATH = os.path.join(probe_root, "_discovered.json")

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


def fail(label):
    results.append(f"  {label}: FAILED\n{traceback.format_exc()}")


def bail(msg):
    output = "\n".join(results)
    print(output)
    results_path = os.path.join(results_dir, "probe6_results.txt")
    with open(results_path, "w") as f:
        f.write(output)
    print(f"\nResults written to {results_path}")
    print(f"\n=== END Probe 6 ({msg}) ===")
    raise SystemExit(1)


def run_fill_export(java_path, classpath, jrxml, output_dir, mode, jdbc_url=None, jdbc_user=None, jdbc_pass=None):
    cmd = [java_path, "-cp", classpath, "JasperFillExport", jrxml, output_dir, mode]
    if jdbc_url:
        cmd.extend([jdbc_url, jdbc_user or "", jdbc_pass or ""])

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)

    for line in r.stdout.strip().splitlines():
        parts = line.split("|", 1)
        tag = parts[0] if parts else ""
        detail = parts[1] if len(parts) > 1 else ""

        if tag.endswith("_OK"):
            ok(tag, detail)
        elif tag.endswith("_FAIL"):
            results.append(f"  {tag}: {detail}")
        else:
            results.append(f"  {line}")

    if r.stderr.strip():
        results.append("  stderr (first 10 lines):")
        for line in r.stderr.strip().splitlines()[:10]:
            results.append(f"    {line}")

    return r.returncode


print("=== Probe 6: JasperReports Fill and Export ===\n")

results.append("[Runtime]")
results.append(f"  Probe root: {probe_root}")

if not os.path.exists(DISCOVERED_PATH):
    results.append("\n  ERROR: _discovered.json not found. Run probes 1-2 first.")
    bail("no discovery file")

with open(DISCOVERED_PATH) as f:
    discovered = json.load(f)

java_path = discovered.get("java_path")
classpath = discovered.get("classpath")

if not java_path or not classpath:
    results.append("\n  ERROR: Missing java_path or classpath. Run probes 1-2 first.")
    bail("incomplete discovery")

section("Static report (hello_static.jrxml) -- no database")
static_jrxml = os.path.join(probe_root, "test_reports", "hello_static.jrxml")
if not os.path.exists(static_jrxml):
    results.append(f"  ERROR: {static_jrxml} not found")
    bail("jrxml missing")

try:
    code = run_fill_export(java_path, classpath, static_jrxml, results_dir, "empty")

    if code == 0:
        pdf_path = os.path.join(results_dir, "hello_static.pdf")
        png_path = os.path.join(results_dir, "hello_static_page_1.png")
        if os.path.exists(pdf_path):
            ok("PDF file", f"{os.path.getsize(pdf_path)} bytes")
        if os.path.exists(png_path):
            ok("PNG file", f"{os.path.getsize(png_path)} bytes")
    else:
        results.append("  Static report fill/export FAILED")
except subprocess.TimeoutExpired:
    results.append("  RESULT: Fill/export timed out (90s)")
except Exception:
    fail("static fill/export")

section("Database report (simple_query.jrxml) -- JDBC")
db_jrxml = os.path.join(probe_root, "test_reports", "simple_query.jrxml")
if not os.path.exists(db_jrxml):
    results.append(f"  WARNING: {db_jrxml} not found, skipping DB test")
else:
    jdbc_url = f"jdbc:postgresql://{PG_HOST}:{PG_PORT}/{PG_DATABASE}"
    results.append(f"  JDBC URL: {jdbc_url}")

    try:
        code = run_fill_export(
            java_path, classpath, db_jrxml, results_dir, "jdbc",
            jdbc_url, PG_USER, PG_PASSWORD
        )

        if code == 0:
            pdf_path = os.path.join(results_dir, "simple_query.pdf")
            png_path = os.path.join(results_dir, "simple_query_page_1.png")
            if os.path.exists(pdf_path):
                ok("DB PDF file", f"{os.path.getsize(pdf_path)} bytes")
            if os.path.exists(png_path):
                ok("DB PNG file", f"{os.path.getsize(png_path)} bytes")
        else:
            results.append("  DB report fill/export FAILED (this is expected if DB is not available)")
    except subprocess.TimeoutExpired:
        results.append("  DB fill/export timed out (90s)")
    except Exception:
        fail("db fill/export")
        results.append("  (DB test failure is non-fatal -- static test is the primary gate)")

section("Generated files")
for name in sorted(os.listdir(results_dir)):
    if name.endswith((".pdf", ".png", ".jasper")):
        fpath = os.path.join(results_dir, name)
        results.append(f"  {name}: {os.path.getsize(fpath)} bytes")

output = "\n".join(results)
print(output)

results_path = os.path.join(results_dir, "probe6_results.txt")
with open(results_path, "w") as f:
    f.write(output)
print(f"\nResults written to {results_path}")
print("\n=== END Probe 6 ===")
