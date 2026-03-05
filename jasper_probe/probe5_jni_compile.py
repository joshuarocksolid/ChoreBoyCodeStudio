#!/usr/bin/env python
"""
Probe 5 (JNI): JasperReports JRXML Compile

Tests whether JasperReports can compile a JRXML file into a .jasper
binary, running JasperCompileProbe.class inside the in-process JVM
via JNI.

Replaces the original probe5_jasper_compile.py which used subprocess
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
    results_path = os.path.join(results_dir, "probe5_results.txt")
    with open(results_path, "w") as f:
        f.write(output)
    print(f"\nResults written to {results_path}")


print("=== Probe 5 (JNI): JasperReports JRXML Compile ===\n")

results.append("[Runtime]")
results.append(f"  Probe root: {probe_root}")

jrxml_path = os.path.join(probe_root, "test_reports", "hello_static.jrxml")
jasper_path = os.path.join(results_dir, "hello_static.jasper")

if not os.path.exists(jrxml_path):
    results.append(f"\n  ERROR: Test JRXML not found: {jrxml_path}")
    write_results()
    print("\n=== END Probe 5 (jrxml missing) ===")
    raise SystemExit(1)

results.append(f"  Input: {jrxml_path}")
results.append(f"  Output: {jasper_path}")

section("1. Boot JVM via jni_helper")
try:
    import jni_helper
    jvm_ptr, env_ptr = jni_helper.ensure_jvm(probe_root)
    ok("JVM ready")
except Exception as e:
    info(f"JVM boot failed: {e}")
    info(traceback.format_exc())
    write_results()
    print("\n=== END Probe 5 (JVM boot failed) ===")
    raise SystemExit(1)

section("2. Compile hello_static.jrxml")
try:
    output = jni_helper.call_java_main(
        env_ptr, "JasperCompileProbe",
        [jrxml_path, jasper_path]
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

    if os.path.exists(jasper_path):
        size = os.path.getsize(jasper_path)
        ok("Output file", f"{jasper_path} ({size} bytes)")
    else:
        info("Output .jasper file was not created")

except Exception as e:
    info(f"JasperCompileProbe.main() failed: {e}")
    info(traceback.format_exc())

    section("Troubleshooting")
    results.append("  - Check error output above for missing class/JAR errors")
    results.append("  - Ensure all required JARs are in lib/")

section("SUMMARY")
if os.path.exists(jasper_path):
    results.append(f"  JRXML compilation succeeded.")
    results.append(f"  Output: {jasper_path} ({os.path.getsize(jasper_path)} bytes)")
    results.append("  Ready for probe 6 (fill and export).")
else:
    results.append("  JRXML compilation did not produce output.")

write_results()
print("\n=== END Probe 5 ===")
