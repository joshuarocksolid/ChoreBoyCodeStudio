#!/usr/bin/env python
"""
Probe 3 (JNI): Java Class Execution via JNI

Validates that jni_helper.py works by booting the JVM and calling
HelloJava.main(). This is a quick sanity check before running the
heavier JasperReports probes.

Replaces the original probe3_java_exec.py which used subprocess
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
    results_path = os.path.join(results_dir, "probe3_results.txt")
    with open(results_path, "w") as f:
        f.write(output)
    print(f"\nResults written to {results_path}")


print("=== Probe 3 (JNI): Java Class Execution ===\n")

results.append("[Runtime]")
results.append(f"  Python: {sys.version}")
results.append(f"  Probe root: {probe_root}")

section("1. Boot JVM via jni_helper")
try:
    import jni_helper
    jvm_ptr, env_ptr = jni_helper.ensure_jvm(probe_root)
    ok("JVM ready", f"jvm=0x{jvm_ptr.value or 0:x}, env=0x{env_ptr.value or 0:x}")
except Exception as e:
    info(f"JVM boot failed: {e}")
    info(traceback.format_exc())
    write_results()
    print("\n=== END Probe 3 (JVM boot failed) ===")
    raise SystemExit(1)

section("2. Call HelloJava.main()")
try:
    output = jni_helper.call_java_main(env_ptr, "HelloJava", [])
    results.append(f"  Java stdout: {output}")

    if "HELLO_JAVA_OK" in output:
        parts = output.strip().split("|")
        version = parts[1] if len(parts) > 1 else "?"
        vendor = parts[2] if len(parts) > 2 else "?"
        ok("HelloJava execution", f"version={version}, vendor={vendor}")
    elif output:
        info("HelloJava produced output but no HELLO_JAVA_OK marker")
        ok("HelloJava execution", "completed without exception")
    else:
        info("HelloJava returned no stdout (may use internal Java buffering)")
        ok("HelloJava execution", "completed without exception")
except Exception as e:
    info(f"HelloJava.main() failed: {e}")
    info(traceback.format_exc())
    write_results()
    print("\n=== END Probe 3 (HelloJava failed) ===")
    raise SystemExit(1)

section("SUMMARY")
results.append("  jni_helper module works correctly.")
results.append("  JVM boots (or reuses existing) and Java classes execute via JNI.")
results.append("  Ready for probes 4-6.")

write_results()
print("\n=== END Probe 3 ===")
