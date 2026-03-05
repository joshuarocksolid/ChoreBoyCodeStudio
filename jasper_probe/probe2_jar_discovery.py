#!/usr/bin/env python
"""
Probe 2: JasperReports JAR Discovery
Searches for JasperReports JARs on the system and in the shipped lib/ folder.
Builds a classpath and writes it to _discovered.json for subsequent probes.
"""
from __future__ import annotations

import glob
import json
import os
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


print("=== Probe 2: JasperReports JAR Discovery ===\n")

results.append("[Runtime]")
results.append(f"  Python: {sys.version}")
results.append(f"  Probe root: {probe_root}")

discovered = {}
if os.path.exists(DISCOVERED_PATH):
    with open(DISCOVERED_PATH) as f:
        discovered = json.load(f)

REQUIRED_JARS = [
    "jasperreports",
    "ecj",
    "groovy",
    "commons-beanutils",
    "commons-collections",
    "commons-digester",
    "commons-logging",
    "itext",
    "postgresql",
]

OPTIONAL_JARS = [
    "castor-core",
    "castor-xml",
    "jackson-core",
    "jackson-databind",
    "jackson-annotations",
]

section("Shipped lib/ folder")
lib_dir = os.path.join(probe_root, "lib")
shipped_jars = []
if os.path.isdir(lib_dir):
    shipped_jars = sorted(glob.glob(os.path.join(lib_dir, "*.jar")))
    results.append(f"  Found {len(shipped_jars)} JARs in lib/")
    for jar in shipped_jars:
        results.append(f"    {os.path.basename(jar)}")
else:
    results.append("  lib/ directory not found")

section("System JAR search")

SYSTEM_SEARCH_PATTERNS = [
    "/home/*/Documents/JobManager/.jobmanager_user/user/uno_packages/cache/uno_packages/*/JasperReportManager*/lib/JasperReports-6.6.0/6.7.0/*.jar",
    "/home/*/Documents/JobManager/.jobmanager_user/user/uno_packages/cache/uno_packages/*/JasperReportManager*/lib/JasperReports-6.6.0/*.jar",
    "/home/*/.jobmanager_user/user/uno_packages/cache/uno_packages/*/JasperReportManager*/lib/JasperReports-6.6.0/6.7.0/*.jar",
    "/home/*/.jobmanager_user/user/uno_packages/cache/uno_packages/*/JasperReportManager*/lib/JasperReports-6.6.0/*.jar",
    "/home/*/Documents/JobManager/.jobmanager_user/user/uno_packages/cache/uno_packages/*/JasperReportManager*/lib/*.jar",
    "/opt/jaspersoft-studio/configuration/org.eclipse.osgi/*/0/.cp/lib/*.jar",
]

system_jars = []
for pattern in SYSTEM_SEARCH_PATTERNS:
    found = sorted(glob.glob(pattern))
    if found:
        results.append(f"  Pattern: {pattern}")
        results.append(f"    Found {len(found)} JARs")
        system_jars.extend(found)

if system_jars:
    unique_dirs = sorted(set(os.path.dirname(j) for j in system_jars))
    results.append(f"  Total system JARs found: {len(system_jars)} in {len(unique_dirs)} locations")
    for d in unique_dirs:
        results.append(f"    {d}")
else:
    results.append("  No system JARs found (will use shipped lib/ only)")

section("Classpath assembly")

def find_jar(name, jar_list):
    for jar in jar_list:
        basename = os.path.basename(jar).lower()
        if basename.startswith(name.lower()):
            return jar
    return None

classpath_jars = []
all_available = shipped_jars + system_jars

missing = []
for req in REQUIRED_JARS:
    jar = find_jar(req, shipped_jars)
    if not jar:
        jar = find_jar(req, system_jars)
    if jar:
        classpath_jars.append(jar)
        ok(req, os.path.basename(jar))
    else:
        missing.append(req)
        results.append(f"  {req}: MISSING")

for opt in OPTIONAL_JARS:
    jar = find_jar(opt, shipped_jars)
    if not jar:
        jar = find_jar(opt, system_jars)
    if jar:
        classpath_jars.append(jar)

tools_dir = os.path.join(probe_root, "tools")
classpath_jars.append(tools_dir)

classpath = os.pathsep.join(classpath_jars)
discovered["classpath"] = classpath
discovered["classpath_jars"] = classpath_jars
discovered["missing_jars"] = missing

section("Summary")
results.append(f"  Required JARs found: {len(REQUIRED_JARS) - len(missing)}/{len(REQUIRED_JARS)}")
if missing:
    results.append(f"  MISSING: {', '.join(missing)}")
    results.append("  Some probes may fail without these JARs.")
else:
    results.append("  All required JARs found.")

results.append(f"  Total classpath entries: {len(classpath_jars)}")

with open(DISCOVERED_PATH, "w") as f:
    json.dump(discovered, f, indent=2)
results.append(f"\n[Discovery file updated]")
results.append(f"  {DISCOVERED_PATH}")

output = "\n".join(results)
print(output)

results_path = os.path.join(results_dir, "probe2_results.txt")
with open(results_path, "w") as f:
    f.write(output)
print(f"\nResults written to {results_path}")
print("\n=== END Probe 2 ===")
