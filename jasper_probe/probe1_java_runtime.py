#!/usr/bin/env python
"""
Probe 1: Java Runtime Detection
Tests whether a Java runtime is available on this system via subprocess.
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


def run_cmd(cmd, timeout=10):
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError:
        return -1, "", "command not found"
    except subprocess.TimeoutExpired:
        return -2, "", "timeout"
    except Exception as e:
        return -3, "", str(e)


print("=== Probe 1: Java Runtime Detection ===\n")

results.append("[Runtime]")
results.append(f"  Python: {sys.version}")
results.append(f"  Executable: {sys.executable}")
results.append(f"  Probe root: {probe_root}")

discovered = {}

section("Java binary search")

JAVA_SEARCH_PATHS = [
    "java",
    "/usr/bin/java",
    "/usr/lib/jvm/default-java/bin/java",
    "/usr/lib/jvm/java-17-openjdk-amd64/bin/java",
    "/usr/lib/jvm/java-11-openjdk-amd64/bin/java",
    "/usr/lib/jvm/java-8-openjdk-amd64/bin/java",
    "/usr/lib/jvm/jdk1.8.0_202/bin/java",
    "/opt/java/bin/java",
]

java_path = None

code, out, err = run_cmd(["which", "java"])
if code == 0 and out:
    results.append(f"  which java: {out}")
    java_path = out
else:
    results.append(f"  which java: not found")

if not java_path:
    for candidate in JAVA_SEARCH_PATHS:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            java_path = candidate
            results.append(f"  found at: {candidate}")
            break

if not java_path:
    results.append("  RESULT: No Java binary found on this system")
    results.append("")
    results.append("  Java is required for JasperReports.")
    results.append("  If Java is installed in a non-standard location,")
    results.append("  edit JAVA_SEARCH_PATHS in this probe and re-run.")
    output = "\n".join(results)
    print(output)
    results_path = os.path.join(results_dir, "probe1_results.txt")
    with open(results_path, "w") as f:
        f.write(output)
    print(f"\nResults written to {results_path}")
    print("\n=== END Probe 1 (FAIL -- no java found) ===")
    raise SystemExit(1)

discovered["java_path"] = java_path
ok("java binary", java_path)

section("Java version")
code, out, err = run_cmd([java_path, "-version"])
version_output = err if err else out
for line in version_output.splitlines():
    results.append(f"  {line}")
discovered["java_version_output"] = version_output

section("javac (optional)")
javac_path = None
java_dir = os.path.dirname(java_path)
javac_candidate = os.path.join(java_dir, "javac")
if os.path.isfile(javac_candidate) and os.access(javac_candidate, os.X_OK):
    javac_path = javac_candidate

if not javac_path:
    code, out, err = run_cmd(["which", "javac"])
    if code == 0 and out:
        javac_path = out

if javac_path:
    ok("javac", javac_path)
    discovered["javac_path"] = javac_path
else:
    results.append("  javac: not found (ok -- we ship pre-compiled classes)")

section("subprocess execution test")
code, out, err = run_cmd([java_path, "-version"])
if code == 0:
    ok("subprocess.run(java)", "Java executable via subprocess")
else:
    results.append(f"  subprocess.run(java): FAILED (code={code})")
    results.append(f"  stdout: {out}")
    results.append(f"  stderr: {err}")

with open(DISCOVERED_PATH, "w") as f:
    json.dump(discovered, f, indent=2)
results.append(f"\n[Discovery file written]")
results.append(f"  {DISCOVERED_PATH}")

output = "\n".join(results)
print(output)

results_path = os.path.join(results_dir, "probe1_results.txt")
with open(results_path, "w") as f:
    f.write(output)
print(f"\nResults written to {results_path}")
print("\n=== END Probe 1 ===")
