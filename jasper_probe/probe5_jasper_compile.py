#!/usr/bin/env python
"""
Probe 5: JasperReports JRXML Compile
Tests whether JasperReports can compile a JRXML file into a .jasper binary.
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
    results_path = os.path.join(results_dir, "probe5_results.txt")
    with open(results_path, "w") as f:
        f.write(output)
    print(f"\nResults written to {results_path}")
    print(f"\n=== END Probe 5 ({msg}) ===")
    raise SystemExit(1)


print("=== Probe 5: JasperReports JRXML Compile ===\n")

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

jrxml_path = os.path.join(probe_root, "test_reports", "hello_static.jrxml")
jasper_path = os.path.join(results_dir, "hello_static.jasper")

if not os.path.exists(jrxml_path):
    results.append(f"\n  ERROR: Test JRXML not found: {jrxml_path}")
    bail("jrxml missing")

section("Compile hello_static.jrxml")
try:
    r = subprocess.run(
        [java_path, "-cp", classpath, "JasperCompileProbe",
         jrxml_path, jasper_path],
        capture_output=True, text=True, timeout=60
    )

    results.append(f"  Exit code: {r.returncode}")

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
        section("stderr (first 20 lines)")
        for line in r.stderr.strip().splitlines()[:20]:
            results.append(f"  {line}")

    if r.returncode == 0 and os.path.exists(jasper_path):
        size = os.path.getsize(jasper_path)
        ok("Output file", f"{jasper_path} ({size} bytes)")
    elif r.returncode != 0:
        results.append("  RESULT: Compilation FAILED")
        section("Troubleshooting")
        results.append("  - Check stderr above for missing class/JAR errors")
        results.append("  - Ensure all required JARs are in lib/ (run probe 2)")

except subprocess.TimeoutExpired:
    results.append("  RESULT: Compilation timed out (60s)")
except Exception:
    fail("subprocess.run")

output = "\n".join(results)
print(output)

results_path = os.path.join(results_dir, "probe5_results.txt")
with open(results_path, "w") as f:
    f.write(output)
print(f"\nResults written to {results_path}")
print("\n=== END Probe 5 ===")
