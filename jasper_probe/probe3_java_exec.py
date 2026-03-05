#!/usr/bin/env python
"""
Probe 3: Java Subprocess Execution
Confirms that Java can actually execute a class file via subprocess.
Uses the pre-compiled HelloJava.class.
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
    results_path = os.path.join(results_dir, "probe3_results.txt")
    with open(results_path, "w") as f:
        f.write(output)
    print(f"\nResults written to {results_path}")
    print(f"\n=== END Probe 3 ({msg}) ===")
    raise SystemExit(1)


print("=== Probe 3: Java Subprocess Execution ===\n")

results.append("[Runtime]")
results.append(f"  Probe root: {probe_root}")

if not os.path.exists(DISCOVERED_PATH):
    results.append("\n  ERROR: _discovered.json not found. Run probe1 first.")
    bail("no discovery file")

with open(DISCOVERED_PATH) as f:
    discovered = json.load(f)

java_path = discovered.get("java_path")
if not java_path:
    results.append("\n  ERROR: No java_path in _discovered.json. Probe 1 may have failed.")
    bail("no java_path")

section("HelloJava execution")
tools_dir = os.path.join(probe_root, "tools")
class_file = os.path.join(tools_dir, "HelloJava.class")

if not os.path.exists(class_file):
    results.append(f"  HelloJava.class not found at {class_file}")
    bail("class file missing")

try:
    r = subprocess.run(
        [java_path, "-cp", tools_dir, "HelloJava"],
        capture_output=True, text=True, timeout=15
    )
    results.append(f"  Exit code: {r.returncode}")
    results.append(f"  stdout: {r.stdout.strip()}")
    if r.stderr.strip():
        results.append(f"  stderr: {r.stderr.strip()[:500]}")

    if r.returncode == 0 and "HELLO_JAVA_OK" in r.stdout:
        parts = r.stdout.strip().split("|")
        ok("Java class execution", f"version={parts[1] if len(parts) > 1 else '?'}")
    else:
        results.append("  RESULT: Java class execution FAILED")
        results.append("  Java binary exists but cannot execute .class files.")
        results.append("  This likely means Java execution is blocked by ChoreBoy security.")
        bail("exec failed")
except subprocess.TimeoutExpired:
    results.append("  RESULT: Java execution timed out (15s)")
    bail("timeout")
except Exception:
    fail("subprocess.run")
    bail("exception")

section("Classpath execution test")
classpath = discovered.get("classpath", tools_dir)

try:
    r = subprocess.run(
        [java_path, "-cp", classpath, "HelloJava"],
        capture_output=True, text=True, timeout=15
    )
    if r.returncode == 0 and "HELLO_JAVA_OK" in r.stdout:
        ok("Full classpath execution", "Java runs with full JasperReports classpath")
    else:
        results.append(f"  Full classpath execution: FAILED (code={r.returncode})")
        if r.stderr.strip():
            results.append(f"  stderr: {r.stderr.strip()[:500]}")
except Exception:
    fail("classpath test")

output = "\n".join(results)
print(output)

results_path = os.path.join(results_dir, "probe3_results.txt")
with open(results_path, "w") as f:
    f.write(output)
print(f"\nResults written to {results_path}")
print("\n=== END Probe 3 ===")
